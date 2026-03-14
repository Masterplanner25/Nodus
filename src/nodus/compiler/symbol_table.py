"""Lexical scope tracking for the compiler."""

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
        func_scope = self._current_function_scope()
        if func_scope is None:
            return None
        return self._resolve_upvalue_in(func_scope, name)

    def current_function_upvalues(self) -> list[Upvalue]:
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

        source_index = None if is_local else symbol.index
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
