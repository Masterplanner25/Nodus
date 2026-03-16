"""Source formatter for Nodus."""

from nodus.frontend.ast.ast_nodes import (
    Assign,
    ActionStmt,
    Attr,
    Bin,
    Block,
    Bool,
    Call,
    Comment,
    DestructureLet,
    ExportFrom,
    ExportList,
    ExprStmt,
    FieldAssign,
    FnDef,
    FnExpr,
    For,
    ForEach,
    GoalDef,
    GoalStep,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    ListPattern,
    MapLit,
    Nil,
    Num,
    Param,
    Print,
    RecordLiteral,
    RecordPattern,
    Return,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
    VarPattern,
    WorkflowDef,
    WorkflowStep,
    WorkflowStateDecl,
    CheckpointStmt,
    While,
    Yield,
)
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser


INDENT = "    "


def format_source(src: str, keep_trailing_comments: bool = False) -> str:
    stmts = Parser(tokenize(src)).parse()
    return format_program(stmts, keep_trailing_comments=keep_trailing_comments)


def format_program(stmts: list, keep_trailing_comments: bool = False) -> str:
    lines: list[str] = []
    prev_import = False
    prev_fn = False

    for stmt in stmts:
        is_import = isinstance(stmt, Import)
        is_fn = isinstance(stmt, FnDef)
        if lines:
            if prev_import and not is_import:
                lines.append("")
            elif prev_fn or is_fn:
                lines.append("")
        lines.extend(format_stmt(stmt, indent=0, keep_trailing_comments=keep_trailing_comments))
        prev_import = is_import
        prev_fn = is_fn

    return "\n".join(lines).rstrip() + "\n"


def format_stmt(stmt, indent: int, keep_trailing_comments: bool = False) -> list[str]:
    prefix = INDENT * indent
    lines: list[str] = []

    comments = getattr(stmt, "_comments", None)
    if comments:
        for comment in comments:
            lines.append(f"{prefix}{comment.rstrip()}")

    trailing = getattr(stmt, "_trailing_comments", None)

    if isinstance(stmt, Import):
        if stmt.names is not None:
            names = ", ".join(stmt.names)
            lines.append(f"{prefix}import {{ {names} }} from {format_string(stmt.path)}")
            return attach_trailing(lines, prefix, trailing, keep_trailing_comments)
        if stmt.alias is not None:
            lines.append(f"{prefix}import {format_string(stmt.path)} as {stmt.alias}")
            return attach_trailing(lines, prefix, trailing, keep_trailing_comments)
        lines.append(f"{prefix}import {format_string(stmt.path)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, ExportFrom):
        names = ", ".join(stmt.names)
        lines.append(f"{prefix}export {{ {names} }} from {format_string(stmt.path)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, ExportList):
        names = ", ".join(stmt.names)
        lines.append(f"{prefix}export {{ {names} }}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, Let):
        name = stmt.name if stmt.type_hint is None else f"{stmt.name}: {stmt.type_hint}"
        if stmt.exported:
            lines.append(f"{prefix}export let {name} = {format_expr(stmt.expr)}")
            return attach_trailing(lines, prefix, trailing, keep_trailing_comments)
        lines.append(f"{prefix}let {name} = {format_expr(stmt.expr)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, Print):
        lines.append(f"{prefix}print({format_expr(stmt.expr)})")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, ExprStmt):
        lines.append(f"{prefix}{format_expr(stmt.expr)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, Return):
        if stmt.expr is None:
            lines.append(f"{prefix}return")
            return attach_trailing(lines, prefix, trailing, keep_trailing_comments)
        lines.append(f"{prefix}return {format_expr(stmt.expr)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, FnDef):
        param_text = ", ".join(format_param(param) for param in stmt.params)
        return_text = f" -> {stmt.return_type}" if stmt.return_type else ""
        if stmt.exported:
            header = f"{prefix}export fn {stmt.name}({param_text}){return_text} {{"
        else:
            header = f"{prefix}fn {stmt.name}({param_text}){return_text} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, WorkflowDef):
        header = f"{prefix}workflow {stmt.name} {{"
        body_lines: list[str] = []
        for state in stmt.states:
            body_lines.extend(format_stmt(state, indent + 1, keep_trailing_comments=keep_trailing_comments))
        for step in stmt.steps:
            body_lines.extend(format_stmt(step, indent + 1, keep_trailing_comments=keep_trailing_comments))
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, GoalDef):
        header = f"{prefix}goal {stmt.name} {{"
        body_lines: list[str] = []
        for state in stmt.states:
            body_lines.extend(format_stmt(state, indent + 1, keep_trailing_comments=keep_trailing_comments))
        for step in stmt.steps:
            body_lines.extend(format_stmt(step, indent + 1, keep_trailing_comments=keep_trailing_comments))
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, WorkflowStateDecl):
        lines.append(f"{prefix}state {stmt.name} = {format_expr(stmt.value)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, WorkflowStep):
        deps = ""
        if stmt.deps:
            deps = " after " + ", ".join(stmt.deps)
        options = ""
        if stmt.options is not None:
            options = f" with {format_expr(stmt.options)}"
        header = f"{prefix}step {stmt.name}{deps}{options} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, GoalStep):
        deps = ""
        if stmt.deps:
            deps = " after " + ", ".join(stmt.deps)
        options = ""
        if stmt.options is not None:
            options = f" with {format_expr(stmt.options)}"
        header = f"{prefix}step {stmt.name}{deps}{options} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, If):
        header = f"{prefix}if ({format_expr(stmt.cond)}) {{"
        then_lines = format_block(stmt.then_branch, indent + 1, keep_trailing_comments=keep_trailing_comments)
        out = [header] + then_lines + [f"{prefix}}}"]
        if stmt.else_branch is not None:
            else_header = f"{prefix}else {{"
            else_lines = format_block(stmt.else_branch, indent + 1, keep_trailing_comments=keep_trailing_comments)
            out[-1] = f"{prefix}}} else {{"
            out += else_lines + [f"{prefix}}}"]
        return lines + out + trailing_lines(prefix, trailing)

    if isinstance(stmt, While):
        header = f"{prefix}while ({format_expr(stmt.cond)}) {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, For):
        init = format_for_part(stmt.init)
        cond = format_for_part(stmt.cond)
        inc = format_for_part(stmt.inc)
        header = f"{prefix}for ({init}; {cond}; {inc}) {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)
    
    if isinstance(stmt, ForEach):
        header = f"{prefix}for {stmt.name} in {format_expr(stmt.iterable)} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"] + trailing_lines(prefix, trailing)

    if isinstance(stmt, Block):
        return lines + [f"{prefix}{{"] + format_block(stmt, indent + 1, keep_trailing_comments=keep_trailing_comments) + [f"{prefix}}}"]

    if isinstance(stmt, Comment):
        return lines + [f"{prefix}{stmt.text.rstrip()}"]

    if isinstance(stmt, CheckpointStmt):
        lines.append(f"{prefix}checkpoint {format_expr(stmt.label)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, Yield):
        if stmt.expr is None:
            lines.append(f"{prefix}yield")
            return attach_trailing(lines, prefix, trailing, keep_trailing_comments)
        lines.append(f"{prefix}yield {format_expr(stmt.expr)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, Throw):
        lines.append(f"{prefix}throw {format_expr(stmt.expr)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    if isinstance(stmt, TryCatch):
        try_header = f"{prefix}try {{"
        try_lines = format_block(stmt.try_block, indent + 1, keep_trailing_comments=keep_trailing_comments)
        catch_header = f"{prefix}}} catch {stmt.catch_var} {{"
        catch_lines = format_block(stmt.catch_block, indent + 1, keep_trailing_comments=keep_trailing_comments)
        if stmt.finally_block is not None:
            finally_header = f"{prefix}}} finally {{"
            finally_lines = format_block(stmt.finally_block, indent + 1, keep_trailing_comments=keep_trailing_comments)
            out = [try_header] + try_lines + [catch_header] + catch_lines + [finally_header] + finally_lines + [f"{prefix}}}"]
        else:
            out = [try_header] + try_lines + [catch_header] + catch_lines + [f"{prefix}}}"]
        return lines + out + trailing_lines(prefix, trailing)

    if isinstance(stmt, DestructureLet):
        pat = format_pattern(stmt.pattern)
        lines.append(f"{prefix}let {pat} = {format_expr(stmt.expr)}")
        return attach_trailing(lines, prefix, trailing, keep_trailing_comments)

    raise TypeError(f"Unknown stmt node: {stmt!r}")


def format_block(block: Block, indent: int, keep_trailing_comments: bool = False) -> list[str]:
    lines: list[str] = []
    for s in block.stmts:
        lines.extend(format_stmt(s, indent=indent, keep_trailing_comments=keep_trailing_comments))
    return lines


def attach_trailing(lines: list[str], prefix: str, trailing, keep_trailing_comments: bool) -> list[str]:
    if not trailing:
        return lines
    if keep_trailing_comments and lines:
        return lines[:-1] + [lines[-1] + " " + " ".join(t.strip() for t in trailing)]
    return lines + trailing_lines(prefix, trailing)


def trailing_lines(prefix: str, trailing) -> list[str]:
    if not trailing:
        return []
    return [f"{prefix}{text.rstrip()}" for text in trailing]


def format_for_part(part) -> str:
    if part is None:
        return ""
    if isinstance(part, Let):
        return f"let {part.name} = {format_expr(part.expr)}"
    if isinstance(part, ExprStmt):
        return format_expr(part.expr)
    return format_expr(part)


def format_pattern(pattern) -> str:
    if isinstance(pattern, VarPattern):
        return pattern.name
    if isinstance(pattern, ListPattern):
        items = ", ".join(format_pattern(e) for e in pattern.elements)
        return f"[{items}]"
    if isinstance(pattern, RecordPattern):
        pairs = ", ".join(f"{k}: {format_pattern(v)}" for k, v in pattern.fields)
        return f"{{{pairs}}}"
    raise TypeError(f"Unknown pattern node: {pattern!r}")


def format_expr(expr, parent_prec: int = 0) -> str:
    if isinstance(expr, Num):
        return format_number(expr)
    if isinstance(expr, ActionStmt):
        text = f"action {expr.kind}"
        if expr.target is not None:
            text += f" {format_string(expr.target)}"
        if expr.kind in {"tool", "agent", "emit"}:
            text += f" with {format_expr(expr.payload if expr.payload is not None else MapLit([]))}"
            return text
        if expr.kind == "memory_put":
            text += f" {format_expr(expr.payload)}"
            return text
        return text
    if isinstance(expr, Bool):
        return "true" if expr.v else "false"
    if isinstance(expr, Str):
        return format_string(expr.v)
    if isinstance(expr, Nil):
        return "nil"
    if isinstance(expr, Var):
        return expr.name
    if isinstance(expr, Assign):
        text = f"{expr.name} = {format_expr(expr.expr, 1)}"
        return maybe_paren(text, 1, parent_prec)
    if isinstance(expr, Unary):
        inner = format_expr(expr.expr, 7)
        if expr.op == "-" and isinstance(expr.expr, Unary) and expr.expr.op == "-":
            inner = f" {inner}"
        text = f"{expr.op}{inner}"
        return maybe_paren(text, 7, parent_prec)
    if isinstance(expr, Bin):
        prec = bin_prec(expr.op)
        left = format_expr(expr.a, prec)
        right = format_expr(expr.b, prec + 1)
        text = f"{left} {expr.op} {right}"
        return maybe_paren(text, prec, parent_prec)
    if isinstance(expr, Call):
        callee = format_expr(expr.callee, 8)
        args = ", ".join(format_expr(arg) for arg in expr.args)
        return f"{callee}({args})"
    if isinstance(expr, Attr):
        obj = format_expr(expr.obj, 8)
        return f"{obj}.{expr.name}"
    if isinstance(expr, Index):
        seq = format_expr(expr.seq, 8)
        return f"{seq}[{format_expr(expr.index)}]"
    if isinstance(expr, IndexAssign):
        seq = format_expr(expr.seq, 8)
        idx = format_expr(expr.index)
        val = format_expr(expr.value, 1)
        text = f"{seq}[{idx}] = {val}"
        return maybe_paren(text, 1, parent_prec)
    if isinstance(expr, ListLit):
        items = ", ".join(format_expr(item) for item in expr.items)
        return f"[{items}]"
    if isinstance(expr, MapLit):
        pairs = ", ".join(f"{format_expr(k)}: {format_expr(v)}" for k, v in expr.items)
        return f"{{{pairs}}}"
    if isinstance(expr, FnExpr):
        param_text = ", ".join(format_param(param) for param in expr.params)
        return_text = f" -> {expr.return_type}" if expr.return_type else ""
        header = f"fn({param_text}){return_text}"
        if not expr.body.stmts:
            return f"{header} {{}}"
        if len(expr.body.stmts) == 1:
            body_lines = format_stmt(expr.body.stmts[0], indent=0)
            if len(body_lines) == 1:
                return f"{header} {{ {body_lines[0].strip()} }}"
        body_lines = format_block(expr.body, indent=1)
        return f"{header} {{\n" + "\n".join(body_lines) + "\n}"
    if isinstance(expr, FieldAssign):
        obj = format_expr(expr.obj, 8)
        val = format_expr(expr.value, 1)
        text = f"{obj}.{expr.name} = {val}"
        return maybe_paren(text, 1, parent_prec)
    if isinstance(expr, RecordLiteral):
        pairs = ", ".join(f"{k}: {format_expr(v)}" for k, v in expr.fields)
        return f"record {{{pairs}}}"
    # Nodes below are statement-level only and are handled by format_stmt(),
    # not format_expr().  They should never appear as sub-expressions.
    raise TypeError(f"Unknown expr node: {expr!r}")


def format_param(param: Param) -> str:
    if param.type_hint is None:
        return param.name
    return f"{param.name}: {param.type_hint}"


def maybe_paren(text: str, prec: int, parent_prec: int) -> str:
    if prec < parent_prec:
        return f"({text})"
    return text


def bin_prec(op: str) -> int:
    if op in {"||"}:
        return 2
    if op in {"&&"}:
        return 3
    if op in {"==", "!=", "<", ">", "<=", ">="}:
        return 4
    if op in {"+", "-"}:
        return 5
    if op in {"*", "/"}:
        return 6
    return 7


def format_number(num: Num) -> str:
    if num.raw is not None:
        return num.raw
    return str(num.v)


def format_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace('"', '\\"')
    )
    return f'"{escaped}"'
