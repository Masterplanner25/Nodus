"""Embedding API for hosting the Nodus runtime inside Python apps."""

from __future__ import annotations

import inspect
import os
import threading
import warnings
from typing import Any, Callable

from nodus.builtins.nodus_builtins import BUILTIN_CALL_PREFIX, BUILTIN_NAMES, BuiltinInfo
from nodus.result import Result, normalize_filename
from nodus.runtime.errors import coerce_error, legacy_error_dict
from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError, HostFunctionError
from nodus.support.config import MAX_STDOUT_CHARS, MAX_STEPS
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.sandbox import capture_output, configure_vm_limits
from nodus.runtime.capability import ALL_CAPABILITIES, ApprovalChannel, CapabilityPolicy
from nodus.services.memory_runtime import MemoryStore
from nodus.vm.vm import VM
from nodus.vm.types import Record, Closure

_SANDBOX_DEFAULT = object()  # sentinel: allowed_paths not explicitly set by caller


def _path_within_any(path: str, roots: list[str]) -> bool:
    """Is *path* inside any of *roots*? Used to reject an incoherent grant (#467)."""
    try:
        target = os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return False
    for root in roots:
        try:
            normalized_root = os.path.normcase(os.path.realpath(root))
            if os.path.commonpath([target, normalized_root]) == normalized_root:
                return True
        except (OSError, ValueError):
            continue
    return False


def _drain_spawned(vm: "VM | None", join_timeout_s: float = 0.5) -> None:
    """Kill and join any pump threads registered by subprocess_spawn on *vm*.

    Called by NodusRuntime.reset() and NodusRuntime.shutdown() so that spawned
    subprocesses and their stdout/stderr pump threads do not accumulate in
    long-lived embedded servers (EMBED-003/#99).
    """
    if vm is None:
        return
    handles = getattr(vm, "_spawned_handles", [])
    for proc, t_out, t_err in handles:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        t_out.join(timeout=join_timeout_s)
        t_err.join(timeout=join_timeout_s)
    handles.clear()


class ToolRegistry:
    """Python-side view of the Nodus tool registry for a ``NodusRuntime`` instance.

    Provides register/unregister/invoke/lookup/list_tools/has methods that
    mirror the Nodus ``std:tool`` API.  Python-registered tools persist across
    ``run_source()`` calls; Nodus-registered tools are ephemeral (per VM).
    """

    def __init__(self, runtime: "NodusRuntime") -> None:
        self._runtime = runtime
        self._lock = threading.RLock()

    def register(self, metadata: dict[str, Any]) -> None:
        """Register a Python callable as a tool visible to Nodus scripts.

        Parameters
        ----------
        metadata:
            Dict with required keys ``name``, ``handler``, ``description``
            and optional keys ``schema``, ``version``, ``tags``,
            ``deprecated``, ``metadata``.  ``handler`` must be a Python
            callable.

        Raises
        ------
        ValueError:
            If required fields are missing, the name is already registered,
            or the schema is invalid.
        """
        from nodus.builtins.tool_module import _normalize_schema, _validate_tool_name

        name = metadata.get("name", "")
        name_err = _validate_tool_name(name)
        if name_err:
            raise ValueError(f"tool.register: {name_err}")
        handler = metadata.get("handler")
        if handler is None:
            raise ValueError("tool.register: 'handler' is required")
        if not callable(handler):
            raise ValueError("tool.register: 'handler' must be a callable")
        desc = metadata.get("description")
        if not isinstance(desc, str) or not desc:
            raise ValueError("tool.register: 'description' must be a non-empty string")
        schema_raw = metadata.get("schema") or {}
        schema, schema_err = _normalize_schema(schema_raw)
        if schema_err:
            raise ValueError(f"tool.register: invalid schema: {schema_err}")
        tags_raw = metadata.get("tags")
        tags = list(tags_raw) if isinstance(tags_raw, list) else []
        meta_raw = metadata.get("metadata") or {}
        entry = {
            "name": name,
            "handler": handler,
            "description": desc,
            "schema": schema,
            "version": metadata.get("version") or "1.0.0",
            "tags": tags,
            "deprecated": bool(metadata.get("deprecated", False)),
            "metadata": meta_raw,
        }
        with self._lock:
            if name in self._runtime._python_registered_tools:
                raise ValueError(f"Tool '{name}' is already registered")
            self._runtime._python_registered_tools[name] = entry

    def unregister(self, name: str) -> dict:
        """Remove a Python-registered tool and return its metadata.

        Raises
        ------
        KeyError:
            If the tool is not registered.
        """
        with self._lock:
            entry = self._runtime._python_registered_tools.pop(name, None)
        if entry is None:
            raise KeyError(f"Tool '{name}' is not registered")
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def invoke(self, name: str, args: dict | None = None) -> object:
        """Invoke a registered tool and return the result as a Python value.

        Prefers the live VM registry (includes Nodus-ephemeral tools) when
        a VM is active; falls back to Python-registered tools otherwise.

        Parameters
        ----------
        name:
            Tool name to invoke.
        args:
            Python dict of arguments (translated to Nodus values before
            the call; result is translated back).

        Raises
        ------
        KeyError:
            If the tool is not registered.
        RuntimeError:
            If a Nodus-closure handler is requested but no VM is active.
        """
        vm = self._runtime._get_active_vm()
        if vm is not None:
            with vm._tool_registry_lock:
                entry = vm.tool_registry.get(name)
            if entry is None:
                raise KeyError(f"Tool '{name}' is not registered")
            handler = entry["handler"]
            if isinstance(handler, Closure):
                # Convert Python dict → Nodus Record so handler can use dot access
                raw = args or {}
                nodus_args = Record({str(k): self._runtime._to_runtime_value(v) for k, v in raw.items()})
                nodus_result = vm.run_closure(handler, [nodus_args])
                return self._runtime._to_host_value(nodus_result)
            if callable(handler):
                return handler(args or {})
            raise RuntimeError(f"Tool '{name}': handler is not callable")
        # No active VM — use Python-registered tools only
        entry = self._runtime._python_registered_tools.get(name)
        if entry is None:
            raise KeyError(f"Tool '{name}' is not registered")
        handler = entry["handler"]
        if not callable(handler):
            raise RuntimeError(f"Tool '{name}': handler is not callable")
        return handler(args or {})

    def lookup(self, name: str) -> dict | None:
        """Return a tool's metadata dict, or ``None`` if not registered."""
        vm = self._runtime._get_active_vm()
        if vm is not None:
            with vm._tool_registry_lock:
                entry = vm.tool_registry.get(name)
            if entry is not None:
                return {k: v for k, v in entry.items() if not k.startswith("_")}
        entry = self._runtime._python_registered_tools.get(name)
        if entry is None:
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def list_tools(self) -> list:
        """Return a list of all registered tool metadata dicts.

        Merges persistent Python-registered tools with any Nodus-registered
        tools from the most recent VM run.
        """
        result: dict[str, dict] = {}
        for name, entry in self._runtime._python_registered_tools.items():
            result[name] = {k: v for k, v in entry.items() if not k.startswith("_")}
        vm = self._runtime._get_active_vm()
        if vm is not None:
            with vm._tool_registry_lock:
                vm_entries = dict(vm.tool_registry)
            for name, entry in vm_entries.items():
                result[name] = {k: v for k, v in entry.items() if not k.startswith("_")}
        return list(result.values())

    def has(self, name: str) -> bool:
        """Return ``True`` if a tool with this name is registered."""
        if name in self._runtime._python_registered_tools:
            return True
        vm = self._runtime._get_active_vm()
        if vm is not None:
            with vm._tool_registry_lock:
                return name in vm.tool_registry
        return False


class NodusRuntime:
    """Embedded Nodus runtime for hosting inside Python applications.

    ``NodusRuntime`` is the recommended public API for executing Nodus scripts
    from Python.  It manages the full compile-and-run pipeline (lexer -> parser ->
    module loader -> compiler -> optimizer -> VM) and exposes host integration hooks
    (registered functions, sandbox constraints, execution limits).

    Typical usage::

        runtime = NodusRuntime(max_steps=100_000, allowed_paths=["/data"])
        runtime.register_function("log", my_logger)
        result = runtime.run_source('log("hello")')

    A single ``NodusRuntime`` instance can be reused across multiple script
    executions; each call to ``run_source`` / ``run_file`` creates a fresh VM and
    module loader so state does not leak between runs.  ``_last_vm`` is overwritten
    on each call; use ``get_execution_stats()`` for documented post-execution data.
    """

    def __init__(
        self,
        *,
        max_steps: int | None = MAX_STEPS,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = MAX_STDOUT_CHARS,
        project_root: str | None = None,
        allowed_paths: list[str] | None = _SANDBOX_DEFAULT,  # type: ignore[assignment]
        writable_paths: list[str] | None = None,
        allow_input: bool = False,
        allow_subprocess: bool = False,
        allow_network: bool = False,
        allow_env: bool = False,
        agent_timeout_ms: int | float | None = None,
        memory_store: "MemoryStore | None" = None,
        agent_registry: dict | None = None,
        share_process_state: bool = False,
        workflow_runner=None,
        worker_dispatcher=None,
        capability_policy: "CapabilityPolicy | None" = None,
        approval_channel: "ApprovalChannel | None" = None,
        allowed_commands: list[str] | None = None,
        allowed_hosts: list[str] | None = None,
        max_frames: int | None = None,
        on_error: Callable | None = None,
        coroutine_timeout_ms: int | None = None,
        event_sinks: list | None = None,
        persist_workflow_source: bool = True,
    ) -> None:
        """Create a new embedded Nodus runtime.

        Parameters
        ----------
        max_steps:
            Maximum total VM instructions executed per ``run_source`` / ``run_file``
            call.  Raises ``RuntimeLimitExceeded`` when exceeded.  ``None`` means
            unlimited.  Defaults to ``MAX_STEPS`` from ``support/config.py``.
        timeout_ms:
            Wall-clock timeout in milliseconds per execution.  Raises
            ``RuntimeLimitExceeded`` when exceeded.  ``None`` means no timeout.
            Defaults to ``None`` (unlimited), which is correct for long-lived
            sessions — MCP/A2A servers, workflow hosts, event loops.  Pass an
            explicit value (e.g. ``timeout_ms=200``) to guard short sandboxed
            executions the same way ``nodus run`` does.  See EMBED-001 (#97).
        max_stdout_chars:
            Maximum number of stdout characters captured per execution.  Output
            beyond this limit is silently truncated.  ``None`` means unlimited.
            Defaults to ``MAX_STDOUT_CHARS`` from ``support/config.py``.
        project_root:
            Absolute path to the project root directory.  Used by the module loader
            to resolve non-relative imports.  ``None`` disables multi-module imports.
        allowed_paths:
            List of directory paths the script is allowed to access via filesystem
            builtins (``read_file``, ``write_file``, ``append_file``, ``mkdir``,
            ``list_dir``, ``exists``).  Paths outside this list raise a sandbox error.
            Defaults to ``[os.getcwd()]`` (working directory at construction time),
            jailing scripts to the project tree — matching the CLI default.  Pass
            ``allowed_paths=None`` to allow unrestricted filesystem access (explicit
            opt-in).  See BUG-119.
        allow_input:
            If ``False`` (default), the ``input()`` builtin raises a sandbox error.
            Set to ``True`` only when running in interactive/REPL-like contexts where
            stdin is available.
        allow_subprocess:
            If ``False``, all ``subprocess_*`` builtins raise a sandbox error.
            Defaults to ``True`` (subprocess available).  Set to ``False`` to prevent
            scripts from invoking OS processes.
        allow_network:
            If ``False``, all ``http_*`` builtins raise a sandbox error.
            Defaults to ``True`` (HTTP available).  Set to ``False`` to prevent
            scripts from making outbound network requests.
        allowed_commands:
            Allowlist of subprocess binary names (or full paths) the script may
            invoke.  ``None`` (default) means no restriction.  When set, shell
            mode (``subprocess_shell``) is also blocked.  Example:
            ``allowed_commands=["git", "ls"]``.  Basename matching is used, so
            ``"git"`` matches ``/usr/bin/git``.
        allowed_hosts:
            Allowlist of hostnames the script may contact via HTTP builtins.
            ``None`` (default) means no restriction.  Example:
            ``allowed_hosts=["api.example.com"]``.  Port is not considered —
            only the hostname portion of the URL is checked.
        allow_env:
            If ``False``, all ``env_*`` builtins (``env_get``, ``env_set``,
            ``env_unset``, ``env_has``, ``env_list``, ``env_list_keys``) raise
            a sandbox error.  Defaults to ``True`` (env access available).
            Set to ``False`` to prevent scripts from reading or writing process
            environment variables.  Recommended when running untrusted scripts
            that should not have access to credentials in the host environment.
        max_frames:
            Maximum call stack depth.  Raises a sandbox error (``Call stack
            overflow``) on overflow.  ``None`` (the default) means
            ``MAX_STACK_DEPTH`` (10,000), the same cap the CLI applies — pass an
            integer to tighten or loosen it.

            There is no "unlimited" setting: recursion depth is the one limit that
            still bites when ``max_steps`` and ``timeout_ms`` are both ``None``,
            the configuration recommended for long-lived hosts.  A host that truly
            wants an effectively unbounded stack can pass a large integer, but note
            that VM frames are heap-allocated, so nothing else stops the growth —
            Python's own recursion limit is never reached.

            Before #350 the default applied **no cap at all**, contradicting this
            docstring; embedded runs relied on ``max_steps`` to stop runaway
            recursion, and the recommended server configuration had no guard.
        on_error:
            Optional callable invoked when a spawned coroutine dies with an uncaught
            exception.  Signature: ``on_error(coroutine, error) -> bool``.  Return
            ``True`` to stop the scheduler after the error; ``False`` (default) to
            continue running remaining coroutines.

            Without this hook, coroutine errors are printed to stderr and execution
            continues — a completed coroutine and an errored coroutine are
            indistinguishable from the ``run_source()`` return value.  See EMBED-002.

            Per-call overrides are supported via ``run_source(on_error=...)``.
        coroutine_timeout_ms:
            Per-coroutine wall-clock deadline in milliseconds.  When set, every
            coroutine spawned via ``spawn()`` is given this deadline; the scheduler
            kills it if it runs longer than this value without completing.  ``None``
            (default) means no per-coroutine limit.  This is independent of the
            global ``timeout_ms`` (which limits the entire execution).  See #191.
        event_sinks:
            Optional list of event sinks to attach to the VM's event bus before
            each execution.  Each sink may be either a callable (``lambda e: ...``)
            or an object implementing ``emit(event)``.  Convenience sink classes
            ``HumanReadableEventSink`` and ``JsonEventSink`` live in
            ``nodus.runtime.runtime_events``.  Sinks are attached before execution
            begins so they observe all events — unlike ``_last_vm.event_bus`` which
            is too late.  See #190.

            Events only fire for operations that cross subsystem boundaries:
            coroutine lifecycle (spawn/resume/complete), workflow/goal steps,
            subprocess and network capability use, and VM errors.  Simple
            arithmetic and variable assignments emit no events.
        """
        if allowed_paths is _SANDBOX_DEFAULT:
            raw_env = os.environ.get("NODUS_ALLOWED_PATHS")
            if raw_env:
                allowed_paths = [p.strip() for p in raw_env.split(os.pathsep) if p.strip()]
            else:
                allowed_paths = [os.getcwd()]
        self.max_steps = max_steps
        self.timeout_ms = timeout_ms
        self.max_stdout_chars = max_stdout_chars
        self.project_root = project_root
        self.allowed_paths = allowed_paths
        # #467: the subset of `allowed_paths` a guest may write. None means
        # "all of them", which is every release before 5.3.0 -- so this is
        # additive and a runtime that never asks for the split is unchanged.
        #
        # Deliberately NOT read from the environment. `NODUS_ALLOWED_PATHS`
        # exists to widen a default jail when the caller passed nothing;
        # there is nothing here to widen, so an env var could only narrow --
        # and write confinement that changes with ambient state is how you
        # get a program that works locally and is refused in production with
        # no difference in the code.
        self.writable_paths = writable_paths
        if writable_paths is not None and allowed_paths:
            outside = [
                path for path in writable_paths
                if not _path_within_any(path, allowed_paths)
            ]
            if outside:
                raise ValueError(
                    f"writable_paths entries lie outside allowed_paths and would "
                    f"grant nothing: {outside}. A path must be readable to be "
                    f"writable; widen allowed_paths, or drop these."
                )
        self.allow_input = allow_input
        self.allow_subprocess = allow_subprocess
        self.allow_network = allow_network
        self.allow_env = allow_env
        # Default deadline for host agent handlers (#424). None = unbounded,
        # which is the pre-existing behaviour. A step's `timeout_ms` still wins
        # when tighter; this covers agent_call() made outside any step.
        self.agent_timeout_ms = agent_timeout_ms
        # #499: whether a workflow run persists the guest's whole program source
        # into `.nodus/graphs/` (the cross-process rebuild handle, #469). That
        # copy can carry anything the source carries -- tokens in string
        # literals, customer data in fixtures -- so an embedder running code it
        # did not author can turn it off. The cost is stated where it lands: a
        # `run_file` run then resumes from the file *as it is on disk*, and a
        # `run_source` run cannot be resumed in another process at all.
        self.persist_workflow_source = persist_workflow_source
        # Per-runtime memory and agent state (#185).
        #
        # Both used to be process-global, so two runtimes in one process shared
        # them: verified before the fix, runtime B read runtime A's
        # `memory_put("secret", ...)`, and a second runtime could both see *and
        # call* an agent the first had registered. For a multi-tenant host — the
        # nodus-sdk FastAPI bridge, say — that is a cross-tenant leak, not merely
        # surprising state.
        #
        # Isolated by default, matching the call 5.0.0 made for capabilities
        # (#405): the safe reading of an ambiguous default is the one that does not
        # silently cross a tenant boundary. `share_process_state=True` restores the
        # old behaviour in one word for anyone who was relying on it, and passing a
        # store or registry explicitly lets two runtimes share deliberately.
        from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE

        # Stored privately, and deliberately NOT as `self.memory_store` (#185).
        #
        # `memory_store` is already a public name downstream meaning something else:
        # `nodus_sdk.NodusSDKRuntime` subclasses this and defines `memory_store` as
        # a read-only property returning *its* vector store. Assigning the attribute
        # here raised `AttributeError: property 'memory_store' ... has no setter` and
        # broke every construction of that subclass — caught by the v5.0.3 Stage 6
        # sweep, after 5.0.3 had shipped.
        #
        # Two lessons, both cheap to honour: a base class adding a public attribute
        # can break a subclass that made the same name a property, and picking a name
        # already used downstream for a different concept invites exactly that. The
        # VM-side name stays `vm.memory_store`, which is fine — nothing subclasses VM.
        if memory_store is not None:
            self._memory_store = memory_store
        elif share_process_state:
            self._memory_store = GLOBAL_MEMORY_STORE
        else:
            self._memory_store = MemoryStore()

        # Agents are deliberately NOT isolated by default, unlike memory above.
        #
        # #185 treats the two as one defect ("similar process-level scope"). They
        # are not. A guest script can *write* memory — `memory_put` is a builtin —
        # so a shared store is a channel one tenant's script can push data through
        # to another's. A guest cannot register an agent at all: the only agent
        # builtins are `agent_call`, `agent_available` and `agent_describe`, and
        # registration is host-only, from Python.
        #
        # So a shared agent registry holds what the *host* put there, and isolating
        # it by default would break the ordinary `register_agent(...)` then
        # `run_source(...)` flow to prevent a leak guests cannot cause. Hosts that
        # do want per-tenant agent sets pass one explicitly.
        self.agent_registry: dict | None = agent_registry
        # #390: the runner this runtime's workflow runs belong to. None keeps the
        # process-global one, which is the pre-existing behaviour and what a bare
        # embedded runtime wants. A host running several runtimes in one process
        # can give each its own so their stores, graph registries and sweepers do
        # not overlap.
        self.workflow_runner = workflow_runner
        # #492: what honours `step ... with { worker: "name" }`. Only
        # `services/server.py` ever set this, so an embedder could not satisfy a
        # worker declaration at all -- and a declaration nothing can satisfy ran
        # in-process and reported success. Anything with a compatible `.submit`
        # works; `WorkerPool` is the one in the tree.
        self.worker_dispatcher = worker_dispatcher
        self.allowed_commands = allowed_commands
        self.allowed_hosts = allowed_hosts
        self.max_frames = max_frames
        self.on_error = on_error
        self.coroutine_timeout_ms = coroutine_timeout_ms
        self._event_sinks: list = list(event_sinks) if event_sinks else []
        self._host_functions: dict[str, BuiltinInfo] = {}
        self._host_capabilities: dict[str, str | None] = {}
        self.capability_policy: CapabilityPolicy | None = capability_policy
        self.approval_channel: ApprovalChannel | None = approval_channel
        self._python_registered_tools: dict[str, dict] = {}
        self.__last_vm: VM | None = None
        self._tool_registry: ToolRegistry = ToolRegistry(self)
        self._run_lock = threading.Lock()

    def register_function(self, name: str, fn, *, arity: int | tuple[int, ...] | None = None, requires: str | None = None) -> None:
        """Register a Python callable as a host function available to Nodus scripts.

        The function will be available in every subsequent ``run_source`` /
        ``run_file`` call on this runtime instance.

        Parameters
        ----------
        name:
            The name Nodus scripts use to call the function.  Must be a non-empty
            string and must not shadow any built-in Nodus function name.
        fn:
            The Python callable to invoke.  Arguments are automatically converted
            from Nodus runtime values to Python equivalents before the call, and
            the return value is converted back (see ``_to_host_value`` /
            ``_to_runtime_value``).
        arity:
            Number of positional arguments the function accepts.  Can be an ``int``
            for a fixed arity or a ``tuple[int, ...]`` for variadic arities
            (e.g., ``(1, 2)`` means 1 or 2 arguments).  When ``None``, arity is
            inferred from the callable's signature via ``inspect.signature``.
            Functions with ``*args``, ``**kwargs``, keyword-only, or defaulted
            parameters require an explicit ``arity`` value.

        Raises
        ------
        ValueError:
            If ``name`` is empty, shadows a built-in, or ``arity`` is invalid.
        ValueError:
            If ``arity`` is ``None`` and the signature cannot be inspected
            (e.g., the function uses ``*args``).

        Example::

            runtime.register_function("fetch", my_fetch_fn, arity=1)

        requires:
            The capability this function needs, consulted against the runtime's
            ``capability_policy`` before every call (#405). ``None`` — the default
            — means the function declares none and is always permitted, which is
            the pre-existing behaviour. Declaring one makes authority a property
            of the function rather than of the runtime.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("Host function name must be a non-empty string")
        if name in BUILTIN_NAMES:
            raise ValueError(f"Cannot override built-in function: {name}")
        if name.startswith(BUILTIN_CALL_PREFIX):
            # The namespace compiler lowerings use to reach builtins past whatever
            # the program bound to that name (#411). A host is trusted and this is
            # not the threat model, but overwriting one of these aliases would
            # quietly re-open the hole for every annotated function.
            raise ValueError(
                f"Cannot register {name!r}: names beginning with "
                f"{BUILTIN_CALL_PREFIX!r} are reserved for the compiler."
            )
        if requires is not None and requires not in ALL_CAPABILITIES:
            raise ValueError(
                f"unknown capability {requires!r}; known: {sorted(ALL_CAPABILITIES)}"
            )
        resolved_arity = self._resolve_arity(fn, arity)
        self._host_functions[name] = BuiltinInfo(name, resolved_arity, fn)
        self._host_capabilities[name] = requires

    @property
    def tool_registry(self) -> ToolRegistry:
        """The tool registry for this runtime.

        Use this to register Python callables as Nodus-callable tools, invoke
        Nodus-registered tools from Python, or enumerate registered tools.
        Python-registered tools persist across ``run_source()`` calls.
        """
        return self._tool_registry

    def set_effect_store(self, store) -> None:
        """Inject a custom EffectStore for EXACTLY_ONCE idempotency.

        When set, all calls to ``effect_resolve``, ``effect_pending``, and
        ``effect_complete`` from .nd code will use this store instead of the
        default per-VM ``InMemoryEffectStore``.  Must be called before
        ``run_source`` / ``run_file`` to affect that execution.
        """
        self._pending_effect_store = store
        if self.__last_vm is not None:
            self.__last_vm.effect_store = store

    def set_trace_id(self, trace_id: str) -> None:
        """Inject a distributed trace ID into the next (and current) VM execution.

        When set, ``trace_id`` is included in every ``RuntimeEvent`` emitted
        during the execution and is readable from .nd code via
        ``import "std:identity"`` → ``identity.trace_id()``.

        Must be called before ``run_source`` / ``run_file`` to affect that
        execution.  If a VM is already active (``last_vm`` is set), the ID
        is applied to it immediately.
        """
        self._pending_trace_id: str | None = trace_id
        if self.__last_vm is not None:
            self.__last_vm.trace_id = trace_id

    @property
    def _last_vm(self) -> "VM | None":
        warnings.warn(
            "_last_vm is a private implementation detail; use get_execution_stats() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.__last_vm

    def active_vm(self) -> "VM | None":
        """The VM from the most recent run, or ``None`` before the first one.

        Supported, and the way to reach the VM from a host function that needs to
        inspect the live execution — checking the sandbox flags actually in force,
        reading the event bus, or asserting confinement from an embedder's own test
        suite. Before this existed the only route was ``_get_active_vm()``, which
        carried no compatibility promise; embedders were calling it anyway.

        The promise is deliberately narrow: **this accessor** is stable, the ``VM``
        object it hands back is not. `VM` is internal, its attributes move between
        releases, and nothing here commits them. What is safe to rely on is that
        this returns the same object the runtime just executed with, or ``None``.

        Called during a run — from inside a host function — it returns the VM
        executing that call. Called after ``reset()`` or ``shutdown()``, it returns
        ``None``.
        """
        return self.__last_vm

    def _get_active_vm(self) -> "VM | None":
        """Retained alias for :meth:`active_vm`.

        Kept, un-deprecated, because downstream embedders pin it (aindy-runtime
        pins it with a test). Renaming it would break them for no gain; new code
        should call ``active_vm()``.
        """
        return self.__last_vm

    def reset(self) -> None:
        """Clear the reference to the last VM instance.

        ``last_vm`` holds a reference to the VM created by the most recent
        ``run_source`` / ``run_file`` call.  Calling ``reset()`` releases that
        reference, allowing the VM (and its associated bytecode, stack, and globals)
        to be garbage-collected.

        Any subprocesses started by ``subprocess_spawn`` during the last run are
        killed and their pump threads joined before the VM reference is released.
        """
        _drain_spawned(self.__last_vm)
        self.__last_vm = None

    def shutdown(self) -> None:
        """Release all runtime resources held by this instance.

        Kills any subprocesses started by ``subprocess_spawn`` and joins their
        pump threads (EMBED-003/#99).  Clears the last VM reference, registered
        host functions, and registered Python tools.  After calling ``shutdown()``,
        this runtime instance should not be used again.
        """
        _drain_spawned(self.__last_vm)
        self.__last_vm = None
        self._host_functions.clear()
        self._host_capabilities.clear()
        self._python_registered_tools.clear()

    def get_execution_stats(self) -> dict:
        """Return execution statistics from the most recent ``run_source`` / ``run_file`` call.

        Returns a dict with:

        - ``"instructions_executed"`` (int): total VM instructions executed.
        - ``"coroutines_spawned"`` (int): total coroutines passed to ``spawn()``.

        Returns zeroes if no execution has occurred yet.  Stats are reset each time
        a new execution starts (i.e. each ``run_source`` / ``run_file`` call creates
        a fresh VM, so these reflect only the last run).
        """
        vm = self.__last_vm
        if vm is None:
            return {"instructions_executed": 0, "coroutines_spawned": 0}
        return {
            "instructions_executed": vm.instructions_executed,
            "coroutines_spawned": vm.scheduler.total_tasks_spawned,
        }

    @classmethod
    def clear_shared_state(cls) -> None:
        """Reset all process-level shared state left over from prior executions.

        ``NodusRuntime`` instances in the same process share several module-level
        stores: the global memory store (``std:memory``), the agent registry
        (``std:agent``), and the task-graph tables used by workflow primitives.
        These stores are NOT cleared by ``shutdown()`` because clearing them while
        another instance is still running would corrupt that instance's state.

        Call this method only after **all** ``NodusRuntime`` instances in the
        current process have been shut down.  It is safe to call before creating a
        new instance to guarantee a clean slate:

        .. code-block:: python

            rt.shutdown()
            NodusRuntime.clear_shared_state()
            rt2 = NodusRuntime(...)   # starts with no prior state

        This does not fix multi-tenant isolation (concurrent instances still share
        these stores during their lifetimes).  See RUNTIME-001 for the v5 plan.
        """
        import nodus.services.memory_runtime as _mr
        import nodus.services.agent_runtime as _ar
        _mr.GLOBAL_MEMORY_STORE.load_snapshot({})
        _ar.AGENT_REGISTRY.clear()
        try:
            import nodus.orchestration.task_graph as _tg
            _tg._GRAPH_REGISTRY.clear()
            _tg._GRAPH_VMS.clear()
        except Exception:
            pass

    def run_file(
        self,
        path: str,
        *,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = None,
        optimize: bool = True,
        debugger=None,
        max_frames: int | None = None,
        initial_globals: dict | None = None,
        host_globals: dict | None = None,
    ) -> dict:
        """Read a ``.nd`` file from disk and execute it.

        Equivalent to ``run_source(open(path).read(), filename=path, ...)``.

        Parameters
        ----------
        path:
            Absolute or relative path to the ``.nd`` source file.
        max_steps:
            Per-call override for ``self.max_steps``.  ``None`` uses the runtime default.
        timeout_ms:
            Per-call override for ``self.timeout_ms``.  ``None`` uses the runtime default.
        max_stdout_chars:
            Per-call override for ``self.max_stdout_chars``.  ``None`` uses the runtime default.
        optimize:
            Whether to run the bytecode optimizer before execution.  Defaults to ``True``.
        debugger:
            Optional DAP-compatible debugger object attached to the VM for this run.
        max_frames:
            Per-call override for ``self.max_frames``.  ``None`` uses the runtime default.

        Returns
        -------
        dict
            Same shape as ``run_source``.  On success: ``{"ok": True, ...}``.
            On file-not-found or permission error: ``{"ok": False, "stage": "load",
            "error": {"type": "io", "message": ...}, ...}``.
            On parse/runtime failure: ``{"ok": False, "stage": "parse"|"execute", ...}``.

        Unlike earlier versions, ``run_file`` never raises ``OSError`` for missing
        or unreadable files — those produce an ``ok=False`` result dict, consistent
        with ``run_source()`` error behaviour.
        """
        normalized = normalize_filename(path)
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                source = handle.read()
        except OSError as exc:
            return Result.failure(
                stage="load",
                filename=normalized,
                error={"type": "io", "kind": "io", "message": str(exc), "path": path},
            ).to_dict()
        return self.run_source(
            source,
            filename=path,
            max_steps=max_steps,
            timeout_ms=timeout_ms,
            max_stdout_chars=max_stdout_chars,
            optimize=optimize,
            debugger=debugger,
            max_frames=max_frames,
            initial_globals=initial_globals,
            host_globals=host_globals,
        )

    def run_source(
        self,
        source: str,
        *,
        filename: str | None = None,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = None,
        optimize: bool = True,
        import_state: dict | None = None,
        debugger=None,
        max_frames: int | None = None,
        initial_globals: dict | None = None,
        host_globals: dict | None = None,
        on_error: Callable | None = None,
    ) -> dict:
        """Compile and execute a Nodus source string.

        This is the primary entry point for embedded execution.  The method runs
        the complete pipeline: lexer -> parser -> import resolution (ModuleLoader) ->
        bytecode compiler -> optimizer -> VM execution.

        Parameters
        ----------
        source:
            Nodus source code as a string.
        filename:
            Optional label used in error messages and the module loader's import
            resolution.  If ``filename`` names an existing file, relative imports
            in ``source`` resolve against that file's directory rather than the
            process CWD; it does **not** change which program runs.  ``source`` is
            always what executes -- use :meth:`run_file` to run a file's contents.
            Pass ``None`` or ``"<memory>"`` for in-memory snippets.

            Through 5.1.0 an existing path made the loader read the file and
            discard ``source`` entirely, silently and with ``ok=True`` (#521).
        max_steps:
            Per-call override for ``self.max_steps``.
        timeout_ms:
            Per-call override for ``self.timeout_ms``.
        max_stdout_chars:
            Per-call override for ``self.max_stdout_chars``.
        optimize:
            Whether to run the bytecode optimizer.  Defaults to ``True``.
        import_state:
            Pre-populated module loader state dict (used by the REPL and test
            harnesses to share already-loaded modules across calls).  ``None``
            creates a fresh import state.
        debugger:
            Optional DAP-compatible debugger attached to the VM.
        max_frames:
            Per-call override for ``self.max_frames``.

        Returns
        -------
        dict
            Result dict from ``Result.to_dict()``:
            - ``"ok"`` (bool): ``True`` on success.
            - ``"stdout"`` (str): captured standard output.
            - ``"stderr"`` (str): captured standard error.
            - ``"stage"`` (str): always ``"execute"``.
            - ``"filename"`` (str | None): normalized filename.
            On failure the dict also contains ``"error"`` with structured error info.

        Raises
        ------
        LangSyntaxError:
            On parse or compile error (re-raised via ``coerce_error``).
        LangRuntimeError:
            On uncaught runtime error (re-raised via ``coerce_error``).
        """
        with self._run_lock:
            return self._run_source_locked(
                source,
                filename=filename,
                max_steps=max_steps,
                timeout_ms=timeout_ms,
                max_stdout_chars=max_stdout_chars,
                optimize=optimize,
                import_state=import_state,
                debugger=debugger,
                max_frames=max_frames,
                initial_globals=initial_globals,
                host_globals=host_globals,
                on_error=on_error,
            )

    def _run_source_locked(
        self,
        source: str,
        *,
        filename: str | None = None,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = None,
        optimize: bool = True,
        import_state: dict | None = None,
        debugger=None,
        max_frames: int | None = None,
        initial_globals: dict | None = None,
        host_globals: dict | None = None,
        on_error=None,
    ) -> dict:
        normalized = normalize_filename(filename)
        if import_state is None and self.project_root is not None:
            import_state = {
                "loaded": set(),
                "loading": set(),
                "exports": {},
                "modules": {},
                "module_ids": {},
                "project_root": self.project_root,
            }
        elif import_state is not None and self.project_root is not None:
            import_state["project_root"] = self.project_root

        vm = VM(
            [],
            {},
            code_locs=[],
            source_path=filename,
            # #469: the run's rebuild handle. Without this, an embedded run
            # persisted `workflow_source_code: None` and could not be resumed in
            # another process -- `run_source` not at all, `run_file` only by
            # re-reading whatever was on disk at resume time. Passed here rather
            # than assigned afterwards so it stays beside `source_path`.
            source_code=source,
            allowed_paths=self.allowed_paths,
            writable_paths=self.writable_paths,
            allow_subprocess=self.allow_subprocess,
            allow_network=self.allow_network,
            allow_env=self.allow_env,
            allowed_commands=self.allowed_commands,
            allowed_hosts=self.allowed_hosts,
            module_globals=initial_globals,
            host_globals=host_globals,
        )
        # #405: the policy rides on the VM, so the builtin dispatch site can
        # consult it without reaching back into the embedding layer.
        vm.capability_policy = self.capability_policy
        vm.approval_channel = self.approval_channel
        # #424: the default agent deadline rides on the VM for the same reason —
        # `call_agent` is handed the VM and nothing else.
        vm.agent_timeout_ms = self.agent_timeout_ms
        vm.persist_workflow_source = self.persist_workflow_source
        vm.memory_store = self._memory_store
        vm.agent_registry = self.agent_registry
        vm.workflow_runner = self.workflow_runner
        if self.worker_dispatcher is not None:
            vm.worker_dispatcher = self.worker_dispatcher
        if not self.allow_input:
            vm.input_fn = self._blocked_input
        if debugger is not None:
            vm.debugger = debugger
            vm.debug = True
        if self._python_registered_tools:
            vm.tool_registry.update(self._python_registered_tools)
        pending_trace = getattr(self, "_pending_trace_id", None)
        if pending_trace is not None:
            vm.trace_id = pending_trace
        pending_effect_store = getattr(self, "_pending_effect_store", None)
        if pending_effect_store is not None:
            vm.effect_store = pending_effect_store
        resolved_on_error = on_error if on_error is not None else self.on_error
        if resolved_on_error is not None:
            vm.on_error = resolved_on_error
        if self.coroutine_timeout_ms is not None:
            vm.coroutine_timeout_ms = self.coroutine_timeout_ms
        self.__last_vm = vm
        for sink in self._event_sinks:
            vm.event_bus.add_sink(sink)
        host_builtins = {
            name: BuiltinInfo(
                info.name,
                info.arity,
                lambda *args, _fn=info.fn, _vm=vm, _name=name: self._invoke_host_function(_vm, _fn, *args, name=_name),
            )
            for name, info in self._host_functions.items()
        }

        resolved_steps = self.max_steps if max_steps is None else max_steps
        resolved_timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        resolved_stdout = self.max_stdout_chars if max_stdout_chars is None else max_stdout_chars
        configure_vm_limits(vm, max_steps=resolved_steps, timeout_ms=resolved_timeout)
        # #350: configure_vm_limits installs MAX_STACK_DEPTH. Only overwrite it
        # when the caller asked for a different cap — this assignment used to be
        # unconditional, so the default `None` replaced the guard with no guard
        # and embedded runs had no recursion limit at all. Keeping the default in
        # configure_vm_limits keeps CLI and embedded from drifting apart again.
        resolved_frames = self.max_frames if max_frames is None else max_frames
        if resolved_frames is not None:
            vm.max_frames = resolved_frames

        with capture_output(max_stdout_chars=resolved_stdout) as (stdout, stderr):
            try:
                loader = ModuleLoader(
                    project_root=self.project_root,
                    vm=vm,
                    host_builtins=host_builtins,
                    extra_builtins=set(self._host_functions.keys()),
                    debugger=debugger,
                    host_globals=host_globals,
                )
                # `filename` is a label, and `run_source` runs `source`. It used
                # to run the *file* named by the label whenever one existed,
                # discarding the source it was handed and reporting ok (#521) --
                # so the program that ran depended on the process CWD and on what
                # happened to be sitting in it.
                #
                # A real path is still worth honouring for what it legitimately
                # tells us: where relative imports resolve from, and what to call
                # the module. That is all it decides now.
                module_name = filename or "<memory>"
                base_dir = None
                if filename and os.path.isfile(filename):
                    module_name = os.path.abspath(filename)
                    base_dir = os.path.dirname(module_name)
                loader.load_module_from_source(
                    source,
                    module_name=module_name,
                    base_dir=base_dir,
                    auto_run_main=True,
                    initial_globals=initial_globals,
                )
            except HostFunctionError as wrapped:
                stage = "execute"
                structured = coerce_error(wrapped.cause, stage=stage, filename=normalized)
                return Result.failure(
                    stage=stage,
                    filename=normalized,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    errors=[structured.to_dict()],
                    error=legacy_error_dict(wrapped.cause, filename=normalized),
                ).to_dict()
            except Exception as err:
                stage = "parse" if isinstance(err, (LangSyntaxError, SyntaxError)) else "execute"
                structured = coerce_error(err, stage=stage, filename=normalized)
                return Result.failure(
                    stage=stage,
                    filename=normalized,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    errors=[structured.to_dict()],
                    error=legacy_error_dict(err, filename=normalized),
                ).to_dict()

        raw_errors = getattr(vm.scheduler, "_coroutine_errors", [])
        spawned_errors = [coerce_error(e, stage="execute", filename=normalized).to_dict() for e in raw_errors]
        unrun = vm.scheduler._spawned_without_loop
        extra_stderr = stderr.getvalue()
        if unrun > 0:
            noun = "task" if unrun == 1 else "tasks"
            extra_stderr += (
                f"\nWarning: {unrun} spawned {noun} never executed"
                " — call run_loop() after spawn() to run them.\n"
            )
        return Result.success(
            stage="execute",
            filename=normalized,
            stdout=stdout.getvalue(),
            stderr=extra_stderr,
            extras={"spawned_errors": spawned_errors} if spawned_errors else {},
        ).to_dict()

    def _install_host_functions(self, vm: VM) -> None:
        for name, info in self._host_functions.items():
            vm.builtins[name] = BuiltinInfo(
                info.name,
                info.arity,
                lambda *args, _fn=info.fn, _vm=vm, _name=name: self._invoke_host_function(_vm, _fn, *args, name=_name),
            )

    def _resolve_arity(self, fn, arity: int | tuple[int, ...] | None) -> int | tuple[int, ...]:
        if arity is not None:
            if isinstance(arity, int):
                if arity < 0:
                    raise ValueError("Arity must be non-negative")
                return arity
            if isinstance(arity, tuple) and all(isinstance(value, int) and value >= 0 for value in arity):
                return arity
            raise ValueError("Arity must be an int or tuple of ints")

        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        for param in params:
            if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                raise ValueError("Host function uses *args/**kwargs. Provide explicit arity.")
            if param.kind == inspect.Parameter.KEYWORD_ONLY:
                raise ValueError("Host function has keyword-only args. Provide explicit arity.")
            if param.default is not inspect.Parameter.empty:
                raise ValueError("Host function has default args. Provide explicit arity.")
        return len(params)

    def _invoke_host_function(self, vm: VM, fn, *args, name: str | None = None):
        host_args = [self._to_host_value(arg) for arg in args]
        # #405: the other of the two chokepoints a guest cannot route around.
        # A host function declares its capability via `register_function(...,
        # requires=...)`; one that declares none is permitted, which keeps this
        # additive.
        if self.capability_policy is not None:
            vm.check_capability(
                self._host_capabilities.get(name) if name else None,
                name or "<host function>",
                "host_function", host_args,
            )
        try:
            result = fn(*host_args)
        except (LangRuntimeError, LangSyntaxError):
            raise
        except Exception as exc:
            raise HostFunctionError(exc) from exc
        return self._to_runtime_value(result)

    def _blocked_input(self, _prompt: str):
        raise LangRuntimeError("sandbox", "input() is not available in embedded mode")

    def _to_host_value(self, value):
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return [self._to_host_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_host_value(item) for key, item in value.items()}
        if isinstance(value, Record):
            return {str(key): self._to_host_value(item) for key, item in value.fields.items()}
        return value

    def _to_runtime_value(self, value):
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, list):
            return [self._to_runtime_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_runtime_value(item) for key, item in value.items()}
        if isinstance(value, Record):
            return {str(key): self._to_runtime_value(item) for key, item in value.fields.items()}
        return value
