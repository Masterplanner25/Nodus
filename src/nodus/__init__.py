"""Nodus entrypoint and public API facade."""

# Internal module map (for contributors):
# - frontend/lexer.py: tokenization
# - frontend/ast/ast_nodes.py: AST definitions
# - frontend/parser.py: syntax parsing
# - compiler/compiler.py: bytecode compiler
# - vm/vm.py: stack VM runtime
# - tooling/loader.py: import resolution + module records
# - builtins/nodus_builtins.py: builtin registry/constants
# - runtime/diagnostics.py: error types + formatter
# - tooling/repl.py: REPL loop
# - cli/cli.py: CLI entrypoints

from nodus.support.version import VERSION, __version__
from nodus.compiler.compiler import Compiler, FunctionInfo
from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError, format_error
from nodus.frontend.lexer import Tok, tokenize
from nodus.frontend.parser import Parser
from nodus.result import Result


def compile_source(*args, **kwargs):
    """Compile a Nodus source string to bytecode.

    .. deprecated:: 0.5
        Use ``ModuleLoader(...).load_source(src)`` instead.
        ``compile_source`` emits ``DeprecationWarning`` and is scheduled for
        removal in v1.0.

    Delegates to ``nodus.tooling.loader.compile_source``.
    """
    from nodus.tooling.loader import compile_source as _compile_source

    return _compile_source(*args, **kwargs)


def resolve_imports(*args, **kwargs):
    """Resolve and inline imports for a Nodus source string.

    Delegates to ``nodus.tooling.loader.resolve_imports``.
    Prefer the ``ModuleLoader`` API for new code.
    """
    from nodus.tooling.loader import resolve_imports as _resolve_imports

    return _resolve_imports(*args, **kwargs)


def run_source(*args, **kwargs):
    """Compile and execute a Nodus source string, returning a ``Result`` dict.

    Convenience wrapper around ``nodus.tooling.loader.run_source``.
    For embedding use cases, prefer ``NodusRuntime`` (``nodus.runtime.embedding``)
    which provides sandbox controls, execution limits, and host function registration.
    """
    from nodus.tooling.loader import run_source as _run_source

    return _run_source(*args, **kwargs)


def main(argv=None):
    """CLI entry point — delegates to ``nodus.cli.cli.main``."""
    from nodus.cli.cli import main as _main

    return _main(argv)


def __getattr__(name):
    if name == "VM":
        from nodus.vm.vm import VM as _VM

        return _VM
    raise AttributeError(name)


__all__ = [
    "VERSION",
    "__version__",
    "main",
    "Compiler",
    "FunctionInfo",
    "LangRuntimeError",
    "LangSyntaxError",
    "format_error",
    "Tok",
    "tokenize",
    "compile_source",
    "resolve_imports",
    "run_source",
    "Parser",
    "VM",
    "Result",
]


if __name__ == "__main__":
    raise SystemExit(main())
