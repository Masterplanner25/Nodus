"""AST pretty-printer for Nodus."""

from __future__ import annotations

from dataclasses import is_dataclass

from nodus.frontend.ast.ast_nodes import (
    Assign,
    ActionStmt,
    Attr,
    Bin,
    Block,
    Bool,
    Call,
    Comment,
    ExportFrom,
    ExportList,
    ExprStmt,
    FnDef,
    For,
    GoalDef,
    GoalStep,
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
    Return,
    Str,
    Unary,
    Var,
    WorkflowStateDecl,
    CheckpointStmt,
    WorkflowDef,
    WorkflowStep,
    While,
)


def format_ast(stmts: list, compact: bool = False) -> str:
    printer = AstPrinter(compact=compact)
    printer.emit("Module", 0)
    for stmt in stmts:
        printer.visit(stmt, 1)
    return "\n".join(printer.lines)


class AstPrinter:
    def __init__(self, compact: bool = False):
        self.lines: list[str] = []
        self.compact = compact

    def emit(self, text: str, indent: int):
        self.lines.append(("  " * indent) + text)

    def visit(self, node, indent: int):
        if node is None:
            self.emit("<none>", indent)
            return
        if isinstance(node, list):
            for item in node:
                self.visit(item, indent)
            return
        if isinstance(node, Num):
            self.emit(f"Number {self.format_number(node)}", indent)
            return
        if isinstance(node, Bool):
            self.emit(f"Bool {self.format_bool(node.v)}", indent)
            return
        if isinstance(node, Str):
            self.emit(f"String {self.format_string(node.v)}", indent)
            return
        if isinstance(node, Nil):
            self.emit("Nil", indent)
            return
        if isinstance(node, Var):
            self.emit(f"Identifier {node.name}", indent)
            return
        if isinstance(node, Unary):
            self.emit(f"Unary op={node.op}", indent)
            if self.compact:
                self.visit(node.expr, indent + 1)
            else:
                self.emit("expr:", indent + 1)
                self.visit(node.expr, indent + 2)
            return
        if isinstance(node, Bin):
            self.emit(f"Binary op={node.op}", indent)
            if self.compact:
                self.visit(node.a, indent + 1)
                self.visit(node.b, indent + 1)
            else:
                self.emit("left:", indent + 1)
                self.visit(node.a, indent + 2)
                self.emit("right:", indent + 1)
                self.visit(node.b, indent + 2)
            return
        if isinstance(node, Assign):
            self.emit(f"Assign name={node.name}", indent)
            if self.compact:
                self.visit(node.expr, indent + 1)
            else:
                self.emit("value:", indent + 1)
                self.visit(node.expr, indent + 2)
            return
        if isinstance(node, ListLit):
            self.emit("List", indent)
            if self.compact:
                for item in node.items:
                    self.visit(item, indent + 1)
            else:
                self.emit("items:", indent + 1)
                for item in node.items:
                    self.visit(item, indent + 2)
            return
        if isinstance(node, MapLit):
            self.emit("Map", indent)
            if not node.items:
                return
            if self.compact:
                for key, value in node.items:
                    self.emit("entry:", indent + 1)
                    self.visit(key, indent + 2)
                    self.visit(value, indent + 2)
            else:
                self.emit("entries:", indent + 1)
                for key, value in node.items:
                    self.emit("entry:", indent + 2)
                    self.emit("key:", indent + 3)
                    self.visit(key, indent + 4)
                    self.emit("value:", indent + 3)
                    self.visit(value, indent + 4)
            return
        if isinstance(node, Index):
            self.emit("Index", indent)
            if self.compact:
                self.visit(node.seq, indent + 1)
                self.visit(node.index, indent + 1)
            else:
                self.emit("target:", indent + 1)
                self.visit(node.seq, indent + 2)
                self.emit("index:", indent + 1)
                self.visit(node.index, indent + 2)
            return
        if isinstance(node, IndexAssign):
            self.emit("IndexAssign", indent)
            if self.compact:
                self.visit(node.seq, indent + 1)
                self.visit(node.index, indent + 1)
                self.visit(node.value, indent + 1)
            else:
                self.emit("target:", indent + 1)
                self.visit(node.seq, indent + 2)
                self.emit("index:", indent + 1)
                self.visit(node.index, indent + 2)
                self.emit("value:", indent + 1)
                self.visit(node.value, indent + 2)
            return
        if isinstance(node, Attr):
            self.emit(f"Attr name={node.name}", indent)
            if self.compact:
                self.visit(node.obj, indent + 1)
            else:
                self.emit("object:", indent + 1)
                self.visit(node.obj, indent + 2)
            return
        if isinstance(node, Call):
            self.emit("Call", indent)
            if self.compact:
                self.visit(node.callee, indent + 1)
                for arg in node.args:
                    self.visit(arg, indent + 1)
            else:
                self.emit("callee:", indent + 1)
                self.visit(node.callee, indent + 2)
                self.emit("args:", indent + 1)
                for arg in node.args:
                    self.visit(arg, indent + 2)
            return
        if isinstance(node, Let):
            suffix = " exported" if node.exported else ""
            type_part = f" type={node.type_hint}" if node.type_hint else ""
            self.emit(f"Let name={node.name}{type_part}{suffix}", indent)
            if self.compact:
                self.visit(node.expr, indent + 1)
            else:
                self.emit("value:", indent + 1)
                self.visit(node.expr, indent + 2)
            return
        if isinstance(node, Print):
            self.emit("Print", indent)
            if self.compact:
                self.visit(node.expr, indent + 1)
            else:
                self.emit("value:", indent + 1)
                self.visit(node.expr, indent + 2)
            return
        if isinstance(node, ExprStmt):
            self.emit("ExprStmt", indent)
            self.visit(node.expr, indent + 1)
            return
        if isinstance(node, Block):
            self.emit("Block", indent)
            for stmt in node.stmts:
                self.visit(stmt, indent + 1)
            return
        if isinstance(node, Comment):
            self.emit(f"Comment {self.format_string(node.text.rstrip())}", indent)
            return
        if isinstance(node, If):
            self.emit("If", indent)
            if self.compact:
                self.visit(node.cond, indent + 1)
                self.visit(node.then_branch, indent + 1)
            else:
                self.emit("cond:", indent + 1)
                self.visit(node.cond, indent + 2)
                self.emit("then:", indent + 1)
                self.visit(node.then_branch, indent + 2)
            if node.else_branch is not None:
                if self.compact:
                    self.visit(node.else_branch, indent + 1)
                else:
                    self.emit("else:", indent + 1)
                    self.visit(node.else_branch, indent + 2)
            return
        if isinstance(node, While):
            self.emit("While", indent)
            if self.compact:
                self.visit(node.cond, indent + 1)
                self.visit(node.body, indent + 1)
            else:
                self.emit("cond:", indent + 1)
                self.visit(node.cond, indent + 2)
                self.emit("body:", indent + 1)
                self.visit(node.body, indent + 2)
            return
        if isinstance(node, For):
            self.emit("For", indent)
            if self.compact:
                if node.init is None:
                    self.emit("<none>", indent + 1)
                else:
                    self.visit(node.init, indent + 1)
                if node.cond is None:
                    self.emit("<none>", indent + 1)
                else:
                    self.visit(node.cond, indent + 1)
                if node.inc is None:
                    self.emit("<none>", indent + 1)
                else:
                    self.visit(node.inc, indent + 1)
                self.visit(node.body, indent + 1)
            else:
                self.emit("init:", indent + 1)
                if node.init is None:
                    self.emit("<none>", indent + 2)
                else:
                    self.visit(node.init, indent + 2)
                self.emit("cond:", indent + 1)
                if node.cond is None:
                    self.emit("<none>", indent + 2)
                else:
                    self.visit(node.cond, indent + 2)
                self.emit("inc:", indent + 1)
                if node.inc is None:
                    self.emit("<none>", indent + 2)
                else:
                    self.visit(node.inc, indent + 2)
                self.emit("body:", indent + 1)
                self.visit(node.body, indent + 2)
            return
        if isinstance(node, FnDef):
            suffix = " exported" if node.exported else ""
            params = ", ".join(self.format_param(param) for param in node.params)
            return_part = f" return={node.return_type}" if node.return_type else ""
            self.emit(f"FnDef name={node.name} params=[{params}]{return_part}{suffix}", indent)
            if self.compact:
                self.visit(node.body, indent + 1)
            else:
                self.emit("body:", indent + 1)
                self.visit(node.body, indent + 2)
            return
        if isinstance(node, WorkflowDef):
            self.emit(f"WorkflowDef name={node.name}", indent)
            if node.states:
                self.emit("states:", indent + 1)
                for state in node.states:
                    self.visit(state, indent + 2)
            for step in node.steps:
                self.visit(step, indent + 1)
            return
        if isinstance(node, WorkflowStateDecl):
            self.emit(f"WorkflowStateDecl name={node.name}", indent)
            if self.compact:
                self.visit(node.value, indent + 1)
            else:
                self.emit("value:", indent + 1)
                self.visit(node.value, indent + 2)
            return
        if isinstance(node, WorkflowStep):
            dep_part = f" deps=[{', '.join(node.deps)}]" if node.deps else ""
            self.emit(f"WorkflowStep name={node.name}{dep_part}", indent)
            if node.options is not None:
                self.emit("options:", indent + 1)
                self.visit(node.options, indent + 2)
            self.emit("body:", indent + 1)
            self.visit(node.body, indent + 2)
            return
        if isinstance(node, CheckpointStmt):
            self.emit("CheckpointStmt", indent)
            if self.compact:
                self.visit(node.label, indent + 1)
            else:
                self.emit("label:", indent + 1)
                self.visit(node.label, indent + 2)
            return
        if isinstance(node, GoalDef):
            self.emit(f"GoalDef name={node.name}", indent)
            if node.states:
                self.emit("states:", indent + 1)
                for state in node.states:
                    self.visit(state, indent + 2)
            for step in node.steps:
                self.visit(step, indent + 1)
            return
        if isinstance(node, GoalStep):
            dep_part = f" deps=[{', '.join(node.deps)}]" if node.deps else ""
            self.emit(f"GoalStep name={node.name}{dep_part}", indent)
            if node.options is not None:
                self.emit("options:", indent + 1)
                self.visit(node.options, indent + 2)
            self.emit("body:", indent + 1)
            self.visit(node.body, indent + 2)
            return
        if isinstance(node, ActionStmt):
            target = f" target={self.format_string(node.target)}" if node.target is not None else ""
            self.emit(f"ActionStmt kind={node.kind}{target}", indent)
            if node.payload is not None:
                self.emit("payload:", indent + 1)
                self.visit(node.payload, indent + 2)
            return
        if isinstance(node, Return):
            self.emit("Return", indent)
            if node.expr is not None:
                if self.compact:
                    self.visit(node.expr, indent + 1)
                else:
                    self.emit("value:", indent + 1)
                    self.visit(node.expr, indent + 2)
            return
        if isinstance(node, Import):
            line = f"Import path={self.format_string(node.path)}"
            if node.alias:
                line += f" alias={node.alias}"
            if node.names:
                line += f" names=[{', '.join(node.names)}]"
            self.emit(line, indent)
            return
        if isinstance(node, ExportList):
            self.emit(f"ExportList names=[{', '.join(node.names)}]", indent)
            return
        if isinstance(node, ExportFrom):
            self.emit(f"ExportFrom path={self.format_string(node.path)} names=[{', '.join(node.names)}]", indent)
            return
        if isinstance(node, ModuleAlias):
            exports = ", ".join(sorted(node.exports.keys()))
            self.emit(f"ModuleAlias alias={node.alias} exports=[{exports}]", indent)
            return

        if is_dataclass(node):
            self.emit(type(node).__name__, indent)
            return

        self.emit(f"<unknown {type(node).__name__}>", indent)

    def format_number(self, node: Num) -> str:
        if node.raw is not None:
            return node.raw
        return str(node.v)

    def format_bool(self, value: bool) -> str:
        return "true" if value else "false"

    def format_string(self, value: str) -> str:
        escaped = (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace('"', '\\"')
        )
        return f"\"{escaped}\""

    def format_param(self, param: Param) -> str:
        if param.type_hint is None:
            return param.name
        return f"{param.name}: {param.type_hint}"
