"""Lexical scope tracking for the Nodus compiler.

The symbol table resolves variable names to one of three scope types:

``global``
    Defined at module top-level.  The VM stores and loads these through
    ``module_globals`` and the LOAD / STORE opcodes.

``local``
    Defined inside a function (any block nested inside ``fn``).  The VM
    stores and loads these through ``frame.locals`` and the STORE_ARG /
    LOAD_LOCAL / STORE opcodes.  The compiler emits the faster LOAD_LOCAL
    opcode (instead of LOAD) when it can confirm a symbol is local-scope and
    the access is inside a function body.

``upvalue``
    A variable defined in an enclosing function that is captured by a nested
    function (closure).  The compiler inserts Cell boxing for the captured
    variable in the enclosing frame and emits LOAD_UPVALUE / STORE_UPVALUE
    with an integer index into the closure's upvalue array.

Two-pass compilation design
----------------------------
Functions are compiled *before* the main module body.  Each function starts
its own Scope (kind="function") pushed with ``enter_scope("function")``.
Upvalue resolution (``resolve_upvalue``) can only proceed once all enclosing
function scopes are in the scope chain, so the two-pass order — inner functions
first, then the outer body — ensures that when the compiler processes a nested
``fn``, all enclosing scopes are already on the stack and ``resolve_upvalue``
can walk up to them.

This is also why ``_current_function_scope`` walks up the scope chain rather
than just looking at the top scope: block scopes (``if``, ``while``, ``for``)
are interleaved between function scopes.
"""

from dataclasses import dataclass


@dataclass
class Symbol:
    name: str
    scope: str  # "global", "local", "upvalue"
    index: int | None = None
    is_function: bool = False


@dataclass
class Upvalue:
    name: str
    is_local: bool
    index: int | None


class Scope:
    def __init__(self, parent=None, kind: str = "module"):
        self.parent = parent
        self.kind = kind
        self.symbols: dict[str, Symbol] = {}
        self.upvalues: list[Upvalue] = []
        self.local_slot_counter: int = 0  # counts local variable slots in this function scope
        self.all_local_slots: dict[str, int] = {}  # name → slot for ALL locals (any depth) in this function

    def define(self, name: str, scope: str, is_function: bool = False) -> Symbol:
        symbol = Symbol(name=name, scope=scope, is_function=is_function)
        self.symbols[name] = symbol
        return symbol


class SymbolTable:
    def __init__(self):
        self.current = Scope(kind="module")
        self.all_symbols: set[str] = set()

    def enter_scope(self, kind: str = "block") -> None:
        self.current = Scope(self.current, kind=kind)

    def exit_scope(self) -> None:
        if self.current.parent is not None:
            self.current = self.current.parent

    def define(self, name: str, is_function: bool = False) -> Symbol:
        scope_kind = "global" if self.current.kind == "module" else "local"
        symbol = self.current.define(name, scope_kind, is_function=is_function)
        self.all_symbols.add(name)
        # Assign a slot index to local variables inside function scopes
        if scope_kind == "local":
            func_scope = self._current_function_scope()
            if func_scope is not None:
                symbol.index = func_scope.local_slot_counter
                func_scope.all_local_slots[name] = symbol.index
                func_scope.local_slot_counter += 1
        return symbol

    def define_function(self, name: str) -> Symbol:
        return self.define(name, is_function=True)

    def is_defined_anywhere(self, name: str) -> bool:
        return name in self.all_symbols

    def is_defined_in_module(self, name: str) -> bool:
        scope = self.current
        while scope.parent is not None:
            scope = scope.parent
        return name in scope.symbols

    def resolve(self, name: str) -> Symbol | None:
        symbol = self.resolve_local(name)
        if symbol is not None:
            return symbol
        return self.resolve_upvalue(name)

    def resolve_local(self, name: str) -> Symbol | None:
        scope = self.current
        while scope:
            if name in scope.symbols:
                return scope.symbols[name]
            if scope.kind in {"function", "module"}:
                break
            scope = scope.parent
        return None

    def resolve_upvalue(self, name: str) -> Symbol | None:
        """Resolve ``name`` as an upvalue from an enclosing function scope.

        Algorithm (implemented by ``_resolve_upvalue_in``):
        1. Find the immediately enclosing function scope (``enclosing``).
        2. Walk scopes between the current function scope and ``enclosing``,
           looking for ``name``.
        3. If ``name`` is found with ``scope == "global"``, return it as-is
           (globals are accessed directly, not via upvalue indirection).
        4. If ``name`` is found in ``enclosing`` as a local variable, add an
           upvalue entry with ``is_local=True``.  The VM will call
           ``capture_local(enclosing_frame, name)`` at closure-creation time
           to box the local into a Cell.
        5. If ``name`` is found in ``enclosing`` as an upvalue itself (i.e.
           it was already captured from a *further* enclosing scope), add an
           upvalue entry with ``is_local=False`` and copy the outer upvalue's
           index.  The VM will re-use the outer Cell.
        6. If not found in ``enclosing``, recurse outward (step 5 of the outer
           recursion handles the chaining).

        Cell boxing and mutability
        --------------------------
        ``is_local=True`` means "the captured variable lives directly in the
        immediately enclosing function's ``frame.locals``."  The VM boxes that
        local into a ``Cell`` the first time a closure captures it
        (``capture_local``), and every closure sharing that capture reads/writes
        the same Cell object, preserving shared-mutable semantics.

        ``is_local=False`` means "the captured variable was already itself an
        upvalue in the enclosing function."  The VM fetches the Cell from the
        enclosing closure's upvalue list by index rather than from ``locals``.

        Returns ``None`` if ``name`` cannot be found in any enclosing scope.
        """
        func_scope = self._current_function_scope()
        if func_scope is None:
            return None
        return self._resolve_upvalue_in(func_scope, name)

    @property
    def frame_size(self) -> int:
        """Number of local variable slots needed for the current function."""
        func_scope = self._current_function_scope()
        if func_scope is None:
            return 0
        return func_scope.local_slot_counter

    def current_function_upvalues(self) -> list[Upvalue]:
        """Return the ordered list of upvalues captured by the current function scope.

        Called by the compiler at the end of compiling a ``fn`` body, after all
        inner function bodies and variable references have been processed.  The
        compiler passes the returned list to ``FunctionInfo`` so that the VM knows
        which variables to capture at the MAKE_CLOSURE opcode.

        Each ``Upvalue`` in the list corresponds to one slot in the closure's
        upvalue array at runtime.  The ``index`` field of a Symbol with
        ``scope="upvalue"`` is its position in this list, and it is the same integer
        passed to LOAD_UPVALUE / STORE_UPVALUE at runtime.

        Returns an empty list for module-level code (where there is no enclosing
        function scope) and for functions that capture no variables.
        """
        func_scope = self._current_function_scope()
        if func_scope is None:
            return []
        return list(func_scope.upvalues)

    def _current_function_scope(self) -> Scope | None:
        scope = self.current
        while scope:
            if scope.kind == "function":
                return scope
            scope = scope.parent
        return None

    def _add_upvalue(self, func_scope: Scope, symbol: Symbol, is_local: bool) -> Symbol:
        if symbol.name in func_scope.symbols and func_scope.symbols[symbol.name].scope == "upvalue":
            return func_scope.symbols[symbol.name]

        source_index = symbol.index  # local slot when is_local=True; outer upvalue idx when is_local=False
        upvalue = Upvalue(name=symbol.name, is_local=is_local, index=source_index)
        func_scope.upvalues.append(upvalue)
        up_index = len(func_scope.upvalues) - 1
        up_symbol = Symbol(name=symbol.name, scope="upvalue", index=up_index)
        func_scope.symbols[symbol.name] = up_symbol
        self.all_symbols.add(symbol.name)
        return up_symbol

    def _resolve_upvalue_in(self, func_scope: Scope, name: str) -> Symbol | None:
        enclosing = self._enclosing_function_scope(func_scope)
        if enclosing is None:
            return None

        scope = func_scope.parent
        while scope:
            if name in scope.symbols:
                symbol = scope.symbols[name]
                if symbol.scope == "global":
                    return symbol
                if scope.kind == "function":
                    if symbol.scope == "upvalue":
                        return self._add_upvalue(func_scope, symbol, is_local=False)
                    return self._add_upvalue(func_scope, symbol, is_local=True)
                return self._add_upvalue(func_scope, symbol, is_local=True)
            if scope == enclosing:
                break
            scope = scope.parent

        outer_symbol = self._resolve_upvalue_in(enclosing, name)
        if outer_symbol is None:
            return None
        if outer_symbol.scope == "global":
            return outer_symbol
        return self._add_upvalue(func_scope, outer_symbol, is_local=False)

    def _enclosing_function_scope(self, func_scope: Scope) -> Scope | None:
        scope = func_scope.parent
        while scope:
            if scope.kind == "function":
                return scope
            scope = scope.parent
        return None
