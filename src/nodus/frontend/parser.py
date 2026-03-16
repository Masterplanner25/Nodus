"""Parser for Nodus syntax."""

from nodus.runtime.diagnostics import LangSyntaxError
from nodus.frontend.lexer import Tok
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
    ExportList,
    ExportFrom,
    ExprStmt,
    FnDef,
    FnExpr,
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
    RecordLiteral,
    RecordPattern,
    Throw,
    TryCatch,
    For,
    ForEach,
    Nil,
    Num,
    Param,
    Print,
    Return,
    Yield,
    Str,
    Unary,
    Var,
    VarPattern,
    While,
    FieldAssign,
    WorkflowDef,
    WorkflowStep,
    WorkflowStateDecl,
    CheckpointStmt,
)
from nodus.orchestration.workflow_lowering import STEP_OPTION_KEYS


class Parser:
    def __init__(self, toks: list[Tok]):
        self.toks = toks
        self.i = 0
        self.pending_comments: list[Tok] = []
        self.pending_trailing: list[Tok] = []
        self.last_stmt = None
        self.last_stmt_end_line: int | None = None
        self.last_token: Tok | None = None
        self.workflow_depth = 0
        self.workflow_step_depth = 0
        self.goal_depth = 0

    def error(self, message: str, tok: Tok | None = None):
        t = self.peek() if tok is None else tok
        raise LangSyntaxError(message, line=t.line, col=t.col)

    def mark(self, node, tok: Tok):
        node._tok = tok
        return node

    def peek(self) -> Tok:
        while self.toks[self.i].kind == "COMMENT":
            self.handle_comment(self.toks[self.i])
            self.i += 1
        return self.toks[self.i]

    def peek_ahead(self, offset: int) -> Tok:
        j = self.i
        seen = 0
        while j < len(self.toks):
            tok = self.toks[j]
            if tok.kind != "COMMENT":
                if seen == offset:
                    return tok
                seen += 1
            j += 1
        return self.toks[-1]

    def at(self, kind: str) -> bool:
        return self.peek().kind == kind

    def eat(self, kind: str) -> Tok:
        t = self.peek()
        if t.kind != kind:
            self.error(f"Expected {kind}, got {t.kind} ({t.val!r})", t)
        self.i += 1
        self.last_token = t
        return t

    def skip_seps(self) -> None:
        while self.at("SEP"):
            self.i += 1

    def eat_required_sep(self) -> None:
        self.eat("SEP")
        self.skip_seps()

    def parse(self) -> list:
        stmts = []
        self.skip_seps()
        while not self.at("EOF"):
            stmt = self.stmt()
            if not isinstance(stmt, Comment):
                if self.pending_comments:
                    setattr(stmt, "_comments", [tok.val for tok in self.pending_comments])
                    self.pending_comments.clear()
                if self.pending_trailing:
                    setattr(stmt, "_trailing_comments", [tok.val for tok in self.pending_trailing])
                    self.pending_trailing.clear()
            stmts.append(stmt)
            if not isinstance(stmt, Comment) and self.last_token is not None:
                self.last_stmt = stmt
                self.last_stmt_end_line = self.last_token.line
            self.skip_seps()
        if self.pending_comments:
            for tok in self.pending_comments:
                stmts.append(Comment(tok.val))
            self.pending_comments.clear()
        return stmts

    def handle_comment(self, tok: Tok) -> None:
        if self.last_stmt is not None and self.last_stmt_end_line == tok.line:
            trailing = getattr(self.last_stmt, "_trailing_comments", None)
            if trailing is None:
                setattr(self.last_stmt, "_trailing_comments", [tok.val])
            else:
                trailing.append(tok.val)
            return
        if self.last_token is not None and self.last_token.line == tok.line:
            self.pending_trailing.append(tok)
            return
        self.pending_comments.append(tok)

    def stmt(self):
        self.skip_seps()

        if self.at("EXPORT"):
            start = self.eat("EXPORT")
            if self.at("LET"):
                let_tok = self.eat("LET")
                return self.let_stmt(exported=True, start_tok=let_tok)
            if self.at("FN"):
                return self.fn_def(exported=True)
            if self.at("{"):
                self.eat("{")
                names = []
                if not self.at("}"):
                    names.append(self.eat("ID").val)
                    while self.at(","):
                        self.eat(",")
                        names.append(self.eat("ID").val)
                self.eat("}")
                if self.at("FROM"):
                    self.eat("FROM")
                    path_tok = self.eat("STR")
                    return self.mark(ExportFrom(names, path_tok.val), start)
                return self.mark(ExportList(names), start)
            self.error("Expected 'let', 'fn', or '{' after export", start)

        if self.at("LET"):
            return self.let_stmt()

        if self.at("PRINT"):
            start = self.eat("PRINT")
            self.eat("(")
            expr = self.expr()
            self.eat(")")
            return self.mark(Print(expr), start)

        if self.at("IMPORT"):
            start = self.eat("IMPORT")
            if self.at("{"):
                self.eat("{")
                names = []
                if not self.at("}"):
                    names.append(self.eat("ID").val)
                    while self.at(","):
                        self.eat(",")
                        names.append(self.eat("ID").val)
                self.eat("}")
                self.eat("FROM")
                path_tok = self.eat("STR")
                return self.mark(Import(path_tok.val, None, names), start)
            path_tok = self.eat("STR")
            alias = None
            if self.at("AS"):
                self.eat("AS")
                alias = self.eat("ID").val
            return self.mark(Import(path_tok.val, alias), start)

        if self.at("IF"):
            return self.if_stmt()

        if self.at("WHILE"):
            return self.while_stmt()

        if self.at("FOR"):
            if self.peek_ahead(1).kind == "(":
                return self.for_stmt()
            return self.for_each_stmt()

        if self.at("FN"):
            return self.fn_def()

        if self.at("WORKFLOW"):
            return self.workflow_def()

        if self.at("GOAL"):
            return self.goal_def()

        if self.at("RETURN"):
            start = self.eat("RETURN")
            if self.at("SEP") or self.at("}") or self.at("EOF"):
                return self.mark(Return(None), start)
            return self.mark(Return(self.expr()), start)

        if self.at("YIELD"):
            start = self.eat("YIELD")
            if self.at("SEP") or self.at("}") or self.at("EOF"):
                return self.mark(Yield(None), start)
            return self.mark(Yield(self.expr()), start)

        if self.at("TRY"):
            start = self.eat("TRY")
            try_block = self.block()
            self.skip_seps()
            self.eat("CATCH")
            catch_var = self.eat("ID").val
            catch_block = self.block()
            finally_block = None
            self.skip_seps()
            if self.at("FINALLY"):
                self.eat("FINALLY")
                finally_block = self.block()
            return self.mark(TryCatch(try_block, catch_var, catch_block, finally_block), start)

        if self.at("THROW"):
            start = self.eat("THROW")
            expr = self.expr()
            return self.mark(Throw(expr), start)

        if self.workflow_step_depth > 0 and self.at("ID") and self.peek().val == "checkpoint":
            start = self.eat("ID")
            if not self.at("STR"):
                self.error("checkpoint label must be a string", start)
            label_tok = self.eat("STR")
            label = self.mark(Str(label_tok.val), label_tok)
            return self.mark(CheckpointStmt(label), start)

        if self.at("{"):
            return self.block()

        return ExprStmt(self.expr())

    def block(self):
        start = self.eat("{")
        stmts = []
        self.skip_seps()

        while not self.at("}"):
            if self.at("EOF"):
                self.error("Unterminated block")
            stmts.append(self.stmt())
            self.skip_seps()

        self.eat("}")
        return self.mark(Block(stmts), start)

    def if_stmt(self):
        start = self.eat("IF")
        self.eat("(")
        cond = self.expr()
        self.eat(")")
        then_branch = self.block()

        self.skip_seps()

        else_branch = None
        if self.at("ELSE"):
            self.eat("ELSE")
            else_branch = self.block()

        return self.mark(If(cond, then_branch, else_branch), start)

    def while_stmt(self):
        start = self.eat("WHILE")
        self.eat("(")
        cond = self.expr()
        self.eat(")")
        body = self.block()
        return self.mark(While(cond, body), start)

    def for_stmt(self):
        start = self.eat("FOR")
        self.eat("(")

        init = None
        if not self.at("SEP"):
            if self.at("LET"):
                let_tok = self.eat("LET")
                init = self.let_stmt(start_tok=let_tok)
            else:
                init = ExprStmt(self.expr())
        self.eat_required_sep()

        cond = None
        if not self.at("SEP"):
            cond = self.expr()
        self.eat_required_sep()

        inc = None
        if not self.at(")"):
            inc = self.expr()

        self.eat(")")
        body = self.block()
        return self.mark(For(init, cond, inc, body), start)

    def for_each_stmt(self):
        start = self.eat("FOR")
        name = self.eat("ID").val
        self.eat("IN")
        iterable = self.expr()
        body = self.block()
        return self.mark(ForEach(name, iterable, body), start)

    def let_stmt(self, exported: bool = False, start_tok: Tok | None = None):
        start = start_tok if start_tok is not None else self.eat("LET")
        if self.at("[") or self.at("{"):
            pattern = self.parse_pattern()
            self.eat("=")
            expr = self.expr()
            if exported:
                self.error("Destructuring cannot be exported", start)
            return self.mark(DestructureLet(pattern, expr), start)
        name = self.eat("ID").val
        type_hint = None
        if self.at(":"):
            self.eat(":")
            type_hint = self.parse_type_name()
        self.eat("=")
        expr = self.expr()
        return self.mark(Let(name, expr, type_hint=type_hint, exported=exported), start)

    def fn_def(self, exported: bool = False):
        start = self.eat("FN")
        name = self.eat("ID").val
        self.eat("(")

        params = []
        if not self.at(")"):
            params.append(self.parse_param())
            while self.at(","):
                self.eat(",")
                params.append(self.parse_param())

        self.eat(")")
        return_type = None
        if self.at("->"):
            self.eat("->")
            return_type = self.parse_type_name()
        body = self.block()
        return self.mark(FnDef(name, params, body, return_type=return_type, exported=exported), start)

    def workflow_def(self):
        start = self.eat("WORKFLOW")
        return self.flow_def(start, WorkflowDef, WorkflowStep, "workflow")

    def goal_def(self):
        start = self.eat("GOAL")
        return self.flow_def(start, GoalDef, GoalStep, "goal")

    def flow_def(self, start: Tok, def_type, step_type, label: str):
        name = self.eat("ID").val
        self.eat("{")
        steps = []
        states = []
        if label == "workflow":
            self.workflow_depth += 1
        else:
            self.goal_depth += 1
        self.skip_seps()
        while not self.at("}"):
            if self.at("EOF"):
                self.error(f"Unterminated {label}")
            if self.at("ID") and self.peek().val == "state":
                states.append(self.flow_state_decl(label))
            elif self.at("STEP"):
                steps.append(self.flow_step(step_type))
            else:
                self.error(f"{label} body must contain state declarations or steps")
            self.skip_seps()
        self.eat("}")
        if label == "workflow":
            self.workflow_depth -= 1
        else:
            self.goal_depth -= 1
        if not steps:
            self.error(f"{label} must contain at least one step", start)
        names = [step.name for step in steps]
        seen = set()
        for step_name in names:
            if step_name in seen:
                self.error(f"Duplicate step name in {label}: {step_name}", start)
            seen.add(step_name)
        name_set = set(names)
        for step in steps:
            for dep in step.deps:
                if dep not in name_set:
                    self.error(f"Unknown {label} dependency: {dep}", step._tok if step._tok is not None else start)
        return self.mark(def_type(name, states, steps), start)

    def flow_state_decl(self, label: str):
        start = self.eat("ID")
        if self.workflow_depth <= 0 and self.goal_depth <= 0:
            self.error(f"state declarations are only valid inside {label}s", start)
        name = self.eat("ID").val
        self.eat("=")
        expr = self.expr()
        return self.mark(WorkflowStateDecl(name, expr), start)

    def flow_step(self, step_type):
        start = self.eat("STEP")
        name = self.eat("ID").val
        deps = []
        options = None
        if self.at("AFTER"):
            self.eat("AFTER")
            deps.append(self.eat("ID").val)
            while self.at(","):
                self.eat(",")
                deps.append(self.eat("ID").val)
        if self.at("WITH"):
            self.eat("WITH")
            options = self.parse_workflow_options()
        self.workflow_step_depth += 1
        body = self.block()
        self.workflow_step_depth -= 1
        return self.mark(step_type(name, deps, body, options=options), start)

    def parse_workflow_options(self):
        return self.parse_named_map_literal(error_keys=STEP_OPTION_KEYS, error_template="Unsupported workflow step option: {key}")

    def expr(self):
        return self.parse_assignment()

    def parse_assignment(self):
        node = self.parse_or()

        if self.at("="):
            eq_tok = self.eat("=")
            rhs = self.parse_assignment()
            if isinstance(node, Var):
                return self.mark(Assign(node.name, rhs), eq_tok)
            if isinstance(node, Index):
                return self.mark(IndexAssign(node.seq, node.index, rhs), eq_tok)
            if isinstance(node, Attr):
                return self.mark(FieldAssign(node.obj, node.name, rhs), eq_tok)
            self.error("Invalid assignment target", eq_tok)

        return node

    def parse_or(self):
        node = self.parse_and()
        while self.at("||"):
            tok = self.eat("||")
            rhs = self.parse_and()
            node = self.mark(Bin("||", node, rhs), tok)
        return node

    def parse_and(self):
        node = self.parse_comparison()
        while self.at("&&"):
            tok = self.eat("&&")
            rhs = self.parse_comparison()
            node = self.mark(Bin("&&", node, rhs), tok)
        return node

    def parse_comparison(self):
        node = self.parse_add()
        while self.at("==") or self.at("!=") or self.at("<") or self.at(">") or self.at("<=") or self.at(">="):
            tok = self.peek()
            op = tok.kind
            self.i += 1
            rhs = self.parse_add()
            node = self.mark(Bin(op, node, rhs), tok)
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.at("+") or self.at("-"):
            tok = self.peek()
            op = tok.kind
            self.i += 1
            rhs = self.parse_mul()
            node = self.mark(Bin(op, node, rhs), tok)
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.at("*") or self.at("/"):
            tok = self.peek()
            op = tok.kind
            self.i += 1
            rhs = self.parse_unary()
            node = self.mark(Bin(op, node, rhs), tok)
        return node

    def parse_unary(self):
        if self.at("!"):
            tok = self.eat("!")
            return self.mark(Unary("!", self.parse_unary()), tok)
        if self.at("-"):
            tok = self.eat("-")
            return self.mark(Unary("-", self.parse_unary()), tok)
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()

        while True:
            if self.at("("):
                tok = self.eat("(")
                args = []

                if not self.at(")"):
                    args.append(self.expr())
                    while self.at(","):
                        self.eat(",")
                        args.append(self.expr())

                self.eat(")")
                node = self.mark(Call(node, args), tok)
                continue

            if self.at("["):
                tok = self.eat("[")
                idx = self.expr()
                self.eat("]")
                node = self.mark(Index(node, idx), tok)
                continue

            if self.at("."):
                tok = self.eat(".")
                name = self.eat("ID").val
                node = self.mark(Attr(node, name), tok)
                continue

            break

        return node

    def parse_map_literal(self):
        tok = self.eat("{")
        items = []
        self.skip_seps()

        if not self.at("}"):
            while True:
                key = self.expr()
                self.eat(":")
                value = self.expr()
                items.append((key, value))
                self.skip_seps()
                if self.at(","):
                    self.eat(",")
                    self.skip_seps()
                    if self.at("}"):
                        break
                    continue
                break

        self.eat("}")
        return self.mark(MapLit(items), tok)

    def parse_record_literal(self):
        tok = self.eat("{")
        fields = []
        self.skip_seps()

        if not self.at("}"):
            while True:
                key = self.eat("ID").val
                self.eat(":")
                value = self.expr()
                fields.append((key, value))
                self.skip_seps()
                if self.at(","):
                    self.eat(",")
                    self.skip_seps()
                    if self.at("}"):
                        break
                    continue
                break

        self.eat("}")
        return self.mark(RecordLiteral(fields), tok)

    def parse_pattern(self):
        if self.at("["):
            return self.parse_list_pattern()
        if self.at("{"):
            return self.parse_record_pattern()
        if self.at("ID"):
            tok = self.eat("ID")
            return self.mark(VarPattern(tok.val), tok)
        t = self.peek()
        self.error(f"Expected pattern, got {t.kind} ({t.val!r})", t)

    def parse_list_pattern(self):
        tok = self.eat("[")
        items = []
        if not self.at("]"):
            items.append(self.parse_pattern())
            while self.at(","):
                self.eat(",")
                if self.at("]"):
                    break
                items.append(self.parse_pattern())
        self.eat("]")
        return self.mark(ListPattern(items), tok)

    def parse_record_pattern(self):
        tok = self.eat("{")
        fields = []
        self.skip_seps()
        if not self.at("}"):
            while True:
                key_tok = self.eat("ID")
                if self.at(":"):
                    self.eat(":")
                    value = self.parse_pattern()
                else:
                    value = self.mark(VarPattern(key_tok.val), key_tok)
                fields.append((key_tok.val, value))
                self.skip_seps()
                if self.at(","):
                    self.eat(",")
                    self.skip_seps()
                    if self.at("}"):
                        break
                    continue
                break
        self.eat("}")
        return self.mark(RecordPattern(fields), tok)

    def parse_primary(self):
        if self.at("ACTION"):
            if self.workflow_step_depth <= 0:
                self.error("action expressions are only valid inside steps")
            return self.parse_action_expr()

        if self.at("NUM"):
            tok = self.eat("NUM")
            return self.mark(Num(float(tok.val), raw=tok.val), tok)

        if self.at("TRUE"):
            tok = self.eat("TRUE")
            return self.mark(Bool(True), tok)

        if self.at("FALSE"):
            tok = self.eat("FALSE")
            return self.mark(Bool(False), tok)

        if self.at("NIL"):
            tok = self.eat("NIL")
            return self.mark(Nil(), tok)

        if self.at("STR"):
            tok = self.eat("STR")
            return self.mark(Str(tok.val), tok)

        if self.at("ID"):
            tok = self.eat("ID")
            return self.mark(Var(tok.val), tok)

        if self.at("PRINT"):
            tok = self.eat("PRINT")
            return self.mark(Var("print"), tok)

        if self.at("FN"):
            start = self.eat("FN")
            self.eat("(")
            params = []
            if not self.at(")"):
                params.append(self.parse_param())
                while self.at(","):
                    self.eat(",")
                    params.append(self.parse_param())
            self.eat(")")
            return_type = None
            if self.at("->"):
                self.eat("->")
                return_type = self.parse_type_name()
            body = self.block()
            return self.mark(FnExpr(params, body, return_type=return_type), start)

        if self.at("["):
            tok = self.eat("[")
            items = []
            if not self.at("]"):
                items.append(self.expr())
                while self.at(","):
                    self.eat(",")
                    items.append(self.expr())
            self.eat("]")
            return self.mark(ListLit(items), tok)

        if self.at("{"):
            return self.parse_map_literal()

        if self.at("RECORD"):
            tok = self.eat("RECORD")
            if not self.at("{"):
                self.error("Expected '{' after record", tok)
            return self.parse_record_literal()

        if self.at("("):
            self.eat("(")
            e = self.expr()
            self.eat(")")
            return e

        t = self.peek()
        self.error(f"Unexpected token: {t.kind} ({t.val!r})", t)

    def parse_action_expr(self):
        start = self.eat("ACTION")
        kind_tok = self.eat("ID")
        kind = kind_tok.val
        if kind in {"tool", "agent"}:
            target = self.eat("STR").val
            self.eat("WITH")
            payload = self.parse_named_map_literal()
            return self.mark(ActionStmt(kind, target, payload), start)
        if kind == "memory_put":
            target = self.eat("STR").val
            value = self.expr()
            return self.mark(ActionStmt(kind, target, value), start)
        if kind == "memory_get":
            target = self.eat("STR").val
            return self.mark(ActionStmt(kind, target, None), start)
        if kind == "emit":
            target = self.eat("STR").val
            self.eat("WITH")
            payload = self.parse_named_map_literal()
            return self.mark(ActionStmt(kind, target, payload), start)
        self.error(f"Unsupported action kind: {kind}", kind_tok)

    def parse_named_map_literal(self, *, error_keys: set[str] | None = None, error_template: str | None = None):
        tok = self.eat("{")
        items = []
        self.skip_seps()
        if not self.at("}"):
            while True:
                key_tok = self.eat("ID")
                if error_keys is not None and key_tok.val not in error_keys:
                    self.error((error_template or "Unsupported key: {key}").format(key=key_tok.val), key_tok)
                self.eat(":")
                value = self.expr()
                items.append((Str(key_tok.val), value))
                self.skip_seps()
                if self.at(","):
                    self.eat(",")
                    self.skip_seps()
                    if self.at("}"):
                        break
                    continue
                break
        self.eat("}")
        return self.mark(MapLit(items), tok)

    def parse_type_name(self) -> str:
        return self.eat("ID").val

    def parse_param(self) -> Param:
        tok = self.eat("ID")
        type_hint = None
        if self.at(":"):
            self.eat(":")
            type_hint = self.parse_type_name()
        return self.mark(Param(tok.val, type_hint=type_hint), tok)
