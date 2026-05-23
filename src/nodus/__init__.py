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
# NodusRuntime is the primary public embedding API.
# Added to __all__ in v1.0 for discoverability.
from nodus.runtime.embedding import NodusRuntime


def __getattr__(name):
    # Heavy modules are loaded lazily to avoid circular imports and keep
    # startup time low for callers that only use lightweight nodus APIs.
    if name in ("resolve_imports", "run_source"):
        from nodus.tooling.loader import (  # noqa: F401
            resolve_imports as _resolve_imports,
            run_source as _run_source,
        )
        globals()["resolve_imports"] = _resolve_imports
        globals()["run_source"] = _run_source
        return globals()[name]
    if name == "main":
        from nodus.cli.cli import main as _main  # noqa: F401
        globals()["main"] = _main
        return _main
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
    "resolve_imports",
    "run_source",
    "Parser",
    "VM",
    "Result",
    "NodusRuntime",
]


if __name__ == "__main__":
    raise SystemExit(__getattr__("main")())
