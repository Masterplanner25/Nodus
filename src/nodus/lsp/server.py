"""Minimal stdio LSP server for Nodus."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from nodus.frontend.ast.ast_nodes import (
    Assign,
    Attr,
    Bin,
    Block,
    Call,
    ExprStmt,
    FnDef,
    FnExpr,
    For,
    ForEach,
    GoalDef,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    MapLit,
    ModuleAlias,
    Nil,
    Num,
    Param,
    Print,
    RecordLiteral,
    Return,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
    While,
    WorkflowDef,
    WorkflowStateDecl,
    Yield,
)
from nodus.frontend.lexer import KEYWORDS, Tok, tokenize
from nodus.frontend.parser import Parser
from nodus.frontend.type_system import ANY, BOOL, FLOAT, FUNCTION, INT, LIST, NIL, RECORD, STRING, FunctionType, combine_types
from nodus.runtime.dependency_graph import DependencyGraph
from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine
from nodus.tooling.loader import collect_module_info, ensure_project_root, resolve_import_path


COMPLETION_KIND_TEXT = 1
COMPLETION_KIND_FUNCTION = 3
COMPLETION_KIND_VARIABLE = 6
COMPLETION_KIND_MODULE = 9
COMPLETION_KIND_KEYWORD = 14
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class DefinitionRecord:
    name: str
    kind: str
    path: str
    uri: str
    line: int
    col: int
    end_col: int
    detail: str
    type_text: str | None = None
    signature: str | None = None


@dataclass
class ReferenceRecord:
    name: str
    line: int
    col: int
    end_col: int
    target: DefinitionRecord | None = None


@dataclass
class ModuleRecord:
    path: str
    uri: str
    exports: dict[str, DefinitionRecord] = field(default_factory=dict)


@dataclass
class DocumentState:
    uri: str
    path: str
    text: str
    diagnostics: list[dict]
    tokens: list[Tok]
    definitions: list[DefinitionRecord]
    references: list[ReferenceRecord]
    visible_symbols: dict[str, DefinitionRecord]
    module_aliases: dict[str, ModuleRecord]


def _path_to_uri(path: str) -> str:
    return Path(path).resolve().as_uri()


def _uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return os.path.abspath(uri)
    path = unquote(parsed.path)
    if os.name == "nt" and path.startswith("/"):
        path = path[1:]
    return os.path.abspath(path)


def _read_message(stream: BinaryIO) -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("utf-8").strip()
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length_text = headers.get("content-length")
    if not length_text:
        return None
    body = stream.read(int(length_text))
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(stream: BinaryIO, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(body)
    stream.flush()


def _lsp_position(line: int | None, col: int | None) -> dict:
    return {
        "line": max((line or 1) - 1, 0),
        "character": max((col or 1) - 1, 0),
    }


def _range_for(line: int | None, col: int | None, end_col: int | None = None) -> dict:
    start = _lsp_position(line, col)
    end = _lsp_position(line, end_col if end_col is not None else col)
    if end["character"] < start["character"]:
        end["character"] = start["character"]
    return {"start": start, "end": end}


def _type_to_text(type_value) -> str:
    if isinstance(type_value, FunctionType):
        params = ", ".join(_type_to_text(param) for param in type_value.params)
        return f"fn({params}) -> {_type_to_text(type_value.return_type)}"
    return type_value.name


def _name_to_type(name: str | None):
    if name == "int":
        return INT
    if name == "float":
        return FLOAT
    if name == "string":
        return STRING
    if name == "bool":
        return BOOL
    if name == "list":
        return LIST
    if name == "record":
        return RECORD
    if name == "function":
        return FUNCTION
    if name == "nil":
        return NIL
    return ANY


class _TypeEnv:
    def __init__(self) -> None:
        self.scopes: list[dict[str, object]] = [{}]

    def push(self) -> None:
        self.scopes.append({})

    def pop(self) -> None:
        self.scopes.pop()

    def bind(self, name: str, value) -> None:
        self.scopes[-1][name] = value

    def lookup(self, name: str):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name == "clock":
            return FunctionType([], FLOAT)
        if name in {"type", "str", "input"}:
            return FunctionType([ANY], STRING)
        if name == "len":
            return FunctionType([ANY], INT)
        if name == "print":
            return FunctionType([ANY], NIL)
        return ANY


def _identifier_column(lines: list[str], line: int, name: str, start_col: int) -> int:
    if line <= 0 or line > len(lines):
        return max(start_col, 1)
    text = lines[line - 1]
    search_from = max(start_col - 1, 0)
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    match = pattern.search(text, search_from)
    if match is not None:
        return match.start() + 1
    fallback = text.find(name, search_from)
    return fallback + 1 if fallback >= 0 else max(start_col, 1)


def _infer_expr_type(expr, env: _TypeEnv):
    if isinstance(expr, Num):
        if expr.raw is not None and "." not in expr.raw:
            return INT
        return FLOAT
    if isinstance(expr, Str):
        return STRING
    if isinstance(expr, Nil):
        return NIL
    if isinstance(expr, Var):
        return env.lookup(expr.name)
    if isinstance(expr, Unary):
        inner = _infer_expr_type(expr.expr, env)
        if expr.op == "!":
            return BOOL
        if inner in {INT, FLOAT}:
            return inner
        return ANY
    if isinstance(expr, Bin):
        left = _infer_expr_type(expr.a, env)
        right = _infer_expr_type(expr.b, env)
        if expr.op in {"==", "!=", "<", ">", "<=", ">=", "&&", "||"}:
            return BOOL
        if expr.op == "+" and (left == STRING or right == STRING):
            return STRING
        if expr.op in {"+", "-", "*", "/"}:
            return combine_types(left, right)
    if isinstance(expr, ListLit):
        return LIST
    if isinstance(expr, (MapLit, RecordLiteral, WorkflowDef, GoalDef)):
        return RECORD
    if isinstance(expr, (Index, Attr)):
        return ANY
    if isinstance(expr, IndexAssign):
        return _infer_expr_type(expr.value, env)
    if isinstance(expr, Assign):
        return _infer_expr_type(expr.expr, env)
    if isinstance(expr, FnExpr):
        params = [_name_to_type(param.type_hint) for param in expr.params]
        return FunctionType(params, _name_to_type(expr.return_type))
    if isinstance(expr, Call):
        callee = _infer_expr_type(expr.callee, env)
        if isinstance(callee, FunctionType):
            return callee.return_type
    return ANY


class _DocumentIndexer:
    def __init__(self, *, server: "LanguageServer", path: str, uri: str, text: str, tokens: list[Tok], ast: list):
        self.server = server
        self.path = path
        self.uri = uri
        self.text = text
        self.lines = text.splitlines() or [""]
        self.tokens = tokens
        self.ast = ast
        self.definitions: list[DefinitionRecord] = []
        self.references: list[ReferenceRecord] = []
        self.visible_symbols: dict[str, DefinitionRecord] = {}
        self.module_aliases: dict[str, ModuleRecord] = {}
        self.scope_stack: list[dict[str, DefinitionRecord]] = [{}]
        self.type_env = _TypeEnv()
        self.import_state = {"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}}
        ensure_project_root(self.import_state, os.path.dirname(self.path), self.path)

    def build(self) -> DocumentState:
        self._predeclare(self.ast)
        for stmt in self.ast:
            self._walk_stmt(stmt)
        return DocumentState(
            uri=self.uri,
            path=self.path,
            text=self.text,
            diagnostics=[],
            tokens=self.tokens,
            definitions=self.definitions,
            references=self.references,
            visible_symbols=self.visible_symbols,
            module_aliases=self.module_aliases,
        )

    def _current_scope(self) -> dict[str, DefinitionRecord]:
        return self.scope_stack[-1]

    def _push_scope(self) -> None:
        self.scope_stack.append({})
        self.type_env.push()

    def _pop_scope(self) -> None:
        self.scope_stack.pop()
        self.type_env.pop()

    def _bind(self, definition: DefinitionRecord) -> None:
        self._current_scope()[definition.name] = definition
        self.visible_symbols[definition.name] = definition
        if definition.type_text is not None:
            self.type_env.bind(definition.name, _name_to_type(definition.type_text))

    def _lookup(self, name: str) -> DefinitionRecord | None:
        for scope in reversed(self.scope_stack):
            if name in scope:
                return scope[name]
        return None

    def _function_signature(self, stmt: FnDef) -> str:
        params = []
        for param in stmt.params:
            params.append(f"{param.name}: {param.type_hint}" if param.type_hint else param.name)
        suffix = f" -> {stmt.return_type}" if stmt.return_type else ""
        return f"fn {stmt.name}({', '.join(params)}){suffix}"

    def _add_definition(
        self,
        name: str,
        kind: str,
        line: int,
        col: int,
        detail: str,
        *,
        type_text: str | None = None,
        signature: str | None = None,
    ) -> DefinitionRecord:
        definition = DefinitionRecord(
            name=name,
            kind=kind,
            path=self.path,
            uri=self.uri,
            line=line,
            col=col,
            end_col=col + len(name),
            detail=detail,
            type_text=type_text,
            signature=signature,
        )
        self.definitions.append(definition)
        self._bind(definition)
        return definition

    def _add_reference(self, name: str, line: int, col: int, target: DefinitionRecord | None) -> None:
        self.references.append(
            ReferenceRecord(name=name, line=line, col=col, end_col=col + len(name), target=target)
        )

    def _predeclare(self, stmts: list) -> None:
        for stmt in stmts:
            if isinstance(stmt, FnDef):
                tok = getattr(stmt, "_tok", None)
                line = tok.line if tok is not None else 1
                col = _identifier_column(self.lines, line, stmt.name, (tok.col + 2) if tok is not None else 1)
                signature = self._function_signature(stmt)
                self._add_definition(stmt.name, "function", line, col, signature, type_text="function", signature=signature)
                self.type_env.bind(
                    stmt.name,
                    FunctionType([_name_to_type(param.type_hint) for param in stmt.params], _name_to_type(stmt.return_type)),
                )
            elif isinstance(stmt, (WorkflowDef, GoalDef)):
                tok = getattr(stmt, "_tok", None)
                line = tok.line if tok is not None else 1
                col = _identifier_column(self.lines, line, stmt.name, (tok.col + 1) if tok is not None else 1)
                self._add_definition(stmt.name, "variable", line, col, stmt.name, type_text="record")

    def _load_module(self, import_path: str, tok: Tok | None) -> ModuleRecord | None:
        try:
            full_path = resolve_import_path(import_path, os.path.dirname(self.path), self.import_state, tok, self.path)
        except Exception:
            return None
        return self.server.load_module_record(full_path, self.import_state)

    def _walk_stmt(self, stmt) -> None:
        if isinstance(stmt, Import):
            tok = getattr(stmt, "_tok", None)
            module_record = self._load_module(stmt.path, tok)
            if stmt.alias is not None and tok is not None and module_record is not None:
                col = _identifier_column(self.lines, tok.line, stmt.alias, tok.col)
                definition = self._add_definition(
                    stmt.alias,
                    "module",
                    tok.line,
                    col,
                    f"module {Path(module_record.path).stem}",
                )
                self.module_aliases[stmt.alias] = module_record
                self._current_scope()[stmt.alias] = definition
            if module_record is not None:
                names = stmt.names if stmt.names else (None if stmt.alias is not None else list(module_record.exports))
                if names is not None:
                    for name in names:
                        exported = module_record.exports.get(name)
                        if exported is not None:
                            self._current_scope()[name] = exported
                            self.visible_symbols[name] = exported
                            if exported.type_text is not None:
                                self.type_env.bind(name, _name_to_type(exported.type_text))
            return

        if isinstance(stmt, Let):
            self._walk_expr(stmt.expr)
            tok = getattr(stmt, "_tok", None)
            line = tok.line if tok is not None else 1
            col = _identifier_column(self.lines, line, stmt.name, (tok.col + 3) if tok is not None else 1)
            type_text = stmt.type_hint or _type_to_text(_infer_expr_type(stmt.expr, self.type_env))
            self._add_definition(stmt.name, "variable", line, col, f"let {stmt.name}", type_text=type_text)
            return

        if isinstance(stmt, FnDef):
            self._push_scope()
            for param in stmt.params:
                self._bind_param(param, stmt)
            self._walk_stmt(stmt.body)
            self._pop_scope()
            return

        if isinstance(stmt, Block):
            self._push_scope()
            for inner in stmt.stmts:
                self._walk_stmt(inner)
            self._pop_scope()
            return

        if isinstance(stmt, ExprStmt):
            self._walk_expr(stmt.expr)
            return

        if isinstance(stmt, Print):
            self._walk_expr(stmt.expr)
            return

        if isinstance(stmt, If):
            self._walk_expr(stmt.cond)
            self._walk_stmt(stmt.then_branch)
            if stmt.else_branch is not None:
                self._walk_stmt(stmt.else_branch)
            return

        if isinstance(stmt, While):
            self._walk_expr(stmt.cond)
            self._walk_stmt(stmt.body)
            return

        if isinstance(stmt, For):
            self._push_scope()
            if stmt.init is not None:
                self._walk_stmt(stmt.init)
            if stmt.cond is not None:
                self._walk_expr(stmt.cond)
            if stmt.inc is not None:
                self._walk_expr(stmt.inc)
            self._walk_stmt(stmt.body)
            self._pop_scope()
            return

        if isinstance(stmt, ForEach):
            self._walk_expr(stmt.iterable)
            self._push_scope()
            tok = getattr(stmt, "_tok", None)
            line = tok.line if tok is not None else 1
            col = _identifier_column(self.lines, line, stmt.name, (tok.col + 3) if tok is not None else 1)
            self._add_definition(stmt.name, "variable", line, col, f"for {stmt.name}", type_text="any")
            self._walk_stmt(stmt.body)
            self._pop_scope()
            return

        if isinstance(stmt, Return) and stmt.expr is not None:
            self._walk_expr(stmt.expr)
            return

        if isinstance(stmt, Yield) and stmt.expr is not None:
            self._walk_expr(stmt.expr)
            return

        if isinstance(stmt, WorkflowStateDecl):
            self._walk_expr(stmt.value)
            return

        if isinstance(stmt, TryCatch):
            self._walk_stmt(stmt.try_block)
            self._push_scope()
            tok = getattr(stmt, "_tok", None)
            line = tok.line if tok is not None else 1
            col = _identifier_column(self.lines, line, stmt.catch_var, tok.col if tok is not None else 1)
            self._add_definition(stmt.catch_var, "variable", line, col, f"catch {stmt.catch_var}", type_text="string")
            self._walk_stmt(stmt.catch_block)
            self._pop_scope()
            return

        if isinstance(stmt, Throw):
            self._walk_expr(stmt.expr)

    def _bind_param(self, param: Param, fn_stmt: FnDef) -> None:
        tok = getattr(param, "_tok", None)
        line = tok.line if tok is not None else getattr(getattr(fn_stmt, "_tok", None), "line", 1)
        col = tok.col if tok is not None else 1
        self._add_definition(param.name, "variable", line, col, f"param {param.name}", type_text=param.type_hint or "any")

    def _walk_expr(self, expr) -> None:
        if isinstance(expr, Var):
            tok = getattr(expr, "_tok", None)
            if tok is not None:
                self._add_reference(expr.name, tok.line, tok.col, self._lookup(expr.name))
            return

        if isinstance(expr, Assign):
            tok = getattr(expr, "_tok", None)
            if tok is not None:
                col = _identifier_column(self.lines, tok.line, expr.name, 1)
                self._add_reference(expr.name, tok.line, col, self._lookup(expr.name))
            self._walk_expr(expr.expr)
            return

        if isinstance(expr, Unary):
            self._walk_expr(expr.expr)
            return

        if isinstance(expr, Bin):
            self._walk_expr(expr.a)
            self._walk_expr(expr.b)
            return

        if isinstance(expr, ListLit):
            for item in expr.items:
                self._walk_expr(item)
            return

        if isinstance(expr, MapLit):
            for key, value in expr.items:
                self._walk_expr(key)
                self._walk_expr(value)
            return

        if isinstance(expr, RecordLiteral):
            for _key, value in expr.fields:
                self._walk_expr(value)
            return

        if isinstance(expr, Index):
            self._walk_expr(expr.seq)
            self._walk_expr(expr.index)
            return

        if isinstance(expr, IndexAssign):
            self._walk_expr(expr.seq)
            self._walk_expr(expr.index)
            self._walk_expr(expr.value)
            return

        if isinstance(expr, Attr):
            self._walk_expr(expr.obj)
            tok = getattr(expr, "_tok", None)
            if isinstance(expr.obj, Var) and tok is not None:
                module = self.module_aliases.get(expr.obj.name)
                if module is not None:
                    target = module.exports.get(expr.name)
                    col = _identifier_column(self.lines, tok.line, expr.name, tok.col + 1)
                    self._add_reference(expr.name, tok.line, col, target)
            return

        if isinstance(expr, Call):
            self._walk_expr(expr.callee)
            for arg in expr.args:
                self._walk_expr(arg)
            return

        if isinstance(expr, FnExpr):
            self._push_scope()
            for param in expr.params:
                tok = getattr(param, "_tok", None)
                line = tok.line if tok is not None else 1
                col = tok.col if tok is not None else 1
                self._add_definition(param.name, "variable", line, col, f"param {param.name}", type_text=param.type_hint or "any")
            self._walk_stmt(expr.body)
            self._pop_scope()


class LanguageServer:
    def __init__(self, input_stream: BinaryIO | None = None, output_stream: BinaryIO | None = None):
        self.input_stream = input_stream if input_stream is not None else sys.stdin.buffer
        self.output_stream = output_stream if output_stream is not None else sys.stdout.buffer
        self.documents: dict[str, DocumentState] = {}
        self.module_cache: dict[str, ModuleRecord] = {}
        self.current_diagnostics: dict[str, list[dict]] = {}
        self.dependency_graph: DependencyGraph | None = None
        self.diagnostic_engine = WorkspaceDiagnosticEngine()
        self.shutdown_requested = False
        self.exit_code = 0

    def run(self) -> int:
        while True:
            message = _read_message(self.input_stream)
            if message is None:
                break
            if self.handle_message(message):
                break
        return self.exit_code

    def handle_message(self, message: dict) -> bool:
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")
        if method == "exit":
            self.exit_code = 0 if self.shutdown_requested else 1
            return True
        try:
            if method == "initialize":
                self._send_response(msg_id, result=self._handle_initialize())
                return False
            if method == "shutdown":
                self.shutdown_requested = True
                self._send_response(msg_id, result=None)
                return False
            if method == "initialized":
                return False
            if method == "textDocument/didOpen":
                self._handle_did_open(params)
                return False
            if method == "textDocument/didChange":
                self._handle_did_change(params)
                return False
            if method == "textDocument/completion":
                self._send_response(msg_id, result=self._handle_completion(params))
                return False
            if method == "textDocument/hover":
                self._send_response(msg_id, result=self._handle_hover(params))
                return False
            if method == "textDocument/definition":
                self._send_response(msg_id, result=self._handle_definition(params))
                return False
            if msg_id is not None:
                self._send_response(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})
            return False
        except Exception as err:
            if msg_id is not None:
                self._send_response(msg_id, error={"code": -32603, "message": str(err)})
            return False

    def _send(self, payload: dict) -> None:
        _write_message(self.output_stream, payload)

    def _send_response(self, msg_id, *, result=None, error=None) -> None:
        payload = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result
        self._send(payload)

    def _send_notification(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _handle_initialize(self) -> dict:
        return {
            "serverInfo": {"name": "nodus-lsp", "version": "0.7.0"},
            "capabilities": {
                "textDocumentSync": 1,
                "completionProvider": {"triggerCharacters": ["."]},
                "hoverProvider": True,
                "definitionProvider": True,
            },
        }

    def _handle_did_open(self, params: dict) -> None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        text = text_document.get("text", "")
        if not uri:
            return
        self.module_cache.clear()
        state = self._analyze_document(uri, text)
        self.documents[uri] = state
        self._refresh_workspace_diagnostics(state.path, text)

    def _handle_did_change(self, params: dict) -> None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        if not uri:
            return
        changes = params.get("contentChanges", [])
        if not changes:
            return
        self.module_cache.clear()
        state = self._analyze_document(uri, changes[-1].get("text", ""))
        self.documents[uri] = state
        self._refresh_workspace_diagnostics(state.path, state.text)

    def _handle_completion(self, params: dict) -> dict:
        state = self._get_document(params)
        if state is None:
            return {"isIncomplete": False, "items": []}
        position = params.get("position", {})
        line = int(position.get("line", 0))
        character = int(position.get("character", 0))
        lines = state.text.splitlines()
        line_text = lines[line] if line < len(lines) else ""
        before = line_text[:character]
        member_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.$", before)
        if member_match:
            alias = member_match.group(1)
            module = state.module_aliases.get(alias)
            if module is not None:
                items = [self._completion_item(item) for item in sorted(module.exports.values(), key=lambda value: value.name)]
                return {"isIncomplete": False, "items": items}
        prefix_match = IDENTIFIER_RE.search(before)
        prefix = prefix_match.group(0) if prefix_match else ""
        items: list[dict] = []
        seen: set[str] = set()
        for keyword in sorted(KEYWORDS):
            if not prefix or keyword.startswith(prefix):
                items.append({"label": keyword, "kind": COMPLETION_KIND_KEYWORD, "detail": "keyword"})
                seen.add(keyword)
        for definition in sorted(state.visible_symbols.values(), key=lambda item: (item.name, item.line, item.col)):
            if definition.name in seen:
                continue
            if prefix and not definition.name.startswith(prefix):
                continue
            items.append(self._completion_item(definition))
            seen.add(definition.name)
        return {"isIncomplete": False, "items": items}

    def _completion_item(self, definition: DefinitionRecord) -> dict:
        kind = {
            "function": COMPLETION_KIND_FUNCTION,
            "variable": COMPLETION_KIND_VARIABLE,
            "module": COMPLETION_KIND_MODULE,
        }.get(definition.kind, COMPLETION_KIND_TEXT)
        detail = definition.signature or definition.type_text or definition.detail
        return {"label": definition.name, "kind": kind, "detail": detail}

    def _handle_hover(self, params: dict) -> dict | None:
        state = self._get_document(params)
        if state is None:
            return None
        token = self._token_at_position(state, params.get("position", {}))
        if token is None or token.kind != "ID":
            return None
        target = self._resolve_symbol_at(state, token)
        if target is None:
            return None
        if target.kind == "module":
            value = target.detail
        elif target.signature:
            value = target.signature
        elif target.type_text:
            value = f"{target.name}: {target.type_text}"
        else:
            value = target.detail
        return {"contents": {"kind": "plaintext", "value": value}}

    def _handle_definition(self, params: dict):
        state = self._get_document(params)
        if state is None:
            return None
        token = self._token_at_position(state, params.get("position", {}))
        if token is None or token.kind != "ID":
            return None
        target = self._resolve_symbol_at(state, token)
        if target is None:
            return None
        return {"uri": target.uri, "range": _range_for(target.line, target.col, target.end_col)}

    def _resolve_symbol_at(self, state: DocumentState, token: Tok) -> DefinitionRecord | None:
        previous = self._previous_non_comment_token(state.tokens, token)
        if previous is not None and previous.kind == ".":
            alias_token = self._previous_non_comment_token(state.tokens, previous)
            if alias_token is not None and alias_token.kind == "ID":
                module = state.module_aliases.get(alias_token.val)
                if module is not None:
                    return module.exports.get(token.val)
        if token.val in state.module_aliases:
            module = state.module_aliases[token.val]
            return DefinitionRecord(
                name=token.val,
                kind="module",
                path=module.path,
                uri=module.uri,
                line=1,
                col=1,
                end_col=1 + len(token.val),
                detail=f"module {Path(module.path).stem}",
            )
        for reference in reversed(state.references):
            if reference.name == token.val and reference.line == token.line and reference.col == token.col:
                return reference.target
        for definition in state.definitions:
            if definition.name == token.val and definition.line == token.line and definition.col == token.col:
                return definition
        return state.visible_symbols.get(token.val)

    def _publish_diagnostics(self, path: str, diagnostics: list[dict]) -> None:
        self._send_notification("textDocument/publishDiagnostics", {"uri": _path_to_uri(path), "diagnostics": diagnostics})

    def _token_at_position(self, state: DocumentState, position: dict) -> Tok | None:
        line = int(position.get("line", 0)) + 1
        character = int(position.get("character", 0)) + 1
        for token in state.tokens:
            if token.line != line:
                continue
            end_col = token.col + len(token.val)
            if token.col <= character <= end_col:
                return token
        return None

    def _previous_non_comment_token(self, tokens: list[Tok], current: Tok) -> Tok | None:
        previous = None
        for token in tokens:
            if token is current:
                return previous
            if token.kind not in {"COMMENT", "SEP"}:
                previous = token
        return None

    def _get_document(self, params: dict) -> DocumentState | None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        if not uri:
            return None
        return self.documents.get(uri)

    def _analyze_document(self, uri: str, text: str) -> DocumentState:
        path = _uri_to_path(uri)
        tokens: list[Tok] = []
        try:
            tokens = tokenize(text)
            ast = Parser(tokens).parse()
        except Exception as err:
            return DocumentState(uri, path, text, [], tokens, [], [], {}, {})
        document = _DocumentIndexer(server=self, path=path, uri=uri, text=text, tokens=tokens, ast=ast).build()
        return document

    def _refresh_workspace_diagnostics(self, path: str, text: str) -> None:
        overlays = {state.path: state.text for state in self.documents.values()}
        affected = self._collect_affected_paths(path)
        merged: dict[str, list[dict]] = {}
        graph = self.dependency_graph
        updated_paths: set[str] = set()
        for affected_path in sorted(affected):
            result = self.diagnostic_engine.analyze(
                affected_path,
                source=overlays.get(affected_path, text if os.path.abspath(affected_path) == os.path.abspath(path) else None),
                overlays=overlays,
                affected_paths={affected_path},
                dependency_graph=graph,
            )
            graph = result.dependency_graph
            updated_paths.update(result.diagnostics_by_file)
            for file_path, diagnostics in result.diagnostics_by_file.items():
                merged[file_path] = [diagnostic.to_lsp() for diagnostic in diagnostics]
        self.dependency_graph = graph
        stale_paths = {existing for existing in self.current_diagnostics if existing in affected and existing not in updated_paths}
        for stale in sorted(stale_paths):
            self._publish_diagnostics(stale, [])
            self.current_diagnostics.pop(stale, None)
        for file_path, diagnostics in sorted(merged.items()):
            self._publish_diagnostics(file_path, diagnostics)
            self.current_diagnostics[file_path] = diagnostics

    def _collect_affected_paths(self, changed_path: str) -> set[str]:
        normalized = os.path.abspath(changed_path)
        affected = {normalized}
        if self.dependency_graph is None:
            return affected
        reverse: dict[str, set[str]] = {}
        for module_path, node in self.dependency_graph.modules.items():
            for imported in node.imported_modules:
                reverse.setdefault(os.path.abspath(imported), set()).add(os.path.abspath(module_path))
        pending = [normalized]
        while pending:
            current = pending.pop()
            for dependent in reverse.get(current, ()):
                if dependent in affected:
                    continue
                affected.add(dependent)
                pending.append(dependent)
        return affected

    def load_module_record(self, path: str, import_state: dict | None = None) -> ModuleRecord | None:
        resolved = os.path.abspath(path)
        cached = self.module_cache.get(resolved)
        if cached is not None:
            return cached
        try:
            text = self._document_text_for_path(resolved)
            if text is None:
                with open(resolved, "r", encoding="utf-8") as handle:
                    text = handle.read()
            tokens = tokenize(text)
            ast = Parser(tokens).parse()
        except Exception:
            return None
        state = import_state or {"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}}
        state.setdefault("loaded", set())
        state.setdefault("loading", set())
        state.setdefault("exports", {})
        state.setdefault("modules", {})
        state.setdefault("module_ids", {})
        ensure_project_root(state, os.path.dirname(resolved), resolved)
        try:
            info = collect_module_info(ast, resolved, f"__lsp__{len(state['module_ids'])}__")
            exported_names = info.exports
        except Exception:
            exported_names = set()
        top_level: dict[str, object] = {}
        export_from: list[object] = []
        for stmt in ast:
            if isinstance(stmt, (Let, FnDef, WorkflowDef, GoalDef)):
                top_level[stmt.name] = stmt
            elif stmt.__class__.__name__ == "ExportFrom":
                export_from.append(stmt)
        exports: dict[str, DefinitionRecord] = {}
        lines = text.splitlines() or [""]
        for name in exported_names:
            stmt = top_level.get(name)
            if stmt is None:
                continue
            tok = getattr(stmt, "_tok", None)
            line = tok.line if tok is not None else 1
            col = _identifier_column(lines, line, name, tok.col if tok is not None else 1)
            if isinstance(stmt, FnDef):
                signature = _DocumentIndexer(server=self, path=resolved, uri=_path_to_uri(resolved), text=text, tokens=tokens, ast=ast)._function_signature(stmt)
                exports[name] = DefinitionRecord(
                    name=name,
                    kind="function",
                    path=resolved,
                    uri=_path_to_uri(resolved),
                    line=line,
                    col=col,
                    end_col=col + len(name),
                    detail=signature,
                    type_text="function",
                    signature=signature,
                )
            elif isinstance(stmt, Let):
                exports[name] = DefinitionRecord(
                    name=name,
                    kind="variable",
                    path=resolved,
                    uri=_path_to_uri(resolved),
                    line=line,
                    col=col,
                    end_col=col + len(name),
                    detail=f"let {name}",
                    type_text=stmt.type_hint or "any",
                )
            else:
                exports[name] = DefinitionRecord(
                    name=name,
                    kind="variable",
                    path=resolved,
                    uri=_path_to_uri(resolved),
                    line=line,
                    col=col,
                    end_col=col + len(name),
                    detail=name,
                    type_text="record",
                )
        for stmt in export_from:
            tok = getattr(stmt, "_tok", None)
            try:
                module_path = resolve_import_path(stmt.path, os.path.dirname(resolved), state, tok, resolved)
                module = self.load_module_record(module_path, state)
            except Exception:
                module = None
            if module is None:
                continue
            for name in stmt.names:
                if name in module.exports:
                    exports[name] = module.exports[name]
        module_record = ModuleRecord(path=resolved, uri=_path_to_uri(resolved), exports=exports)
        self.module_cache[resolved] = module_record
        return module_record

    def _document_text_for_path(self, path: str) -> str | None:
        normalized = os.path.abspath(path)
        for state in self.documents.values():
            if os.path.abspath(state.path) == normalized:
                return state.text
        return None


def run_stdio_server() -> int:
    return LanguageServer().run()


if __name__ == "__main__":
    raise SystemExit(run_stdio_server())
