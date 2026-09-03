"""Parser for Nodus syntax."""

from dataclasses import dataclass
from typing import NoReturn

from nodus.runtime.diagnostics import LangSyntaxError
from nodus.frontend.lexer import COMPENSATION_KEYWORDS, EXPRESSION_KEYWORDS, EXTERN_KEYWORDS, LOOP_CONTROL_KEYWORDS, STEP_MAP_KEYWORDS, Tok
from nodus.frontend.type_system import TYPE_NAMES, is_known_type_name, suggest_type_name
from nodus.frontend.ast.ast_nodes import (
    Annotation,
    Assign,
    CompoundAssign,
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
    ExternDecl,
    FnDef,
    FnExpr,
    GoalBudget,
    GoalDef,
    GoalPursuit,
    GoalStep,
    If,
    PredicateAnd,
    PredicateNot,
    PredicateOr,
    Reached,
    Import,
    Index,
    IndexAssign,
    InterpolatedString,
    InterpolationPart,
    StringLiteralPart,
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
    Int,
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
    Break,
    Continue,
    Match,
    MatchArm,
    FieldAssign,
    WorkflowDef,
    WorkflowStep,
    WorkflowStateDecl,
    CheckpointStmt,
)
from nodus.frontend.goal_validation import validate_goal_pursuits, validate_step_guards
from nodus.orchestration.workflow_lowering import STATE_OPTION_KEYS, STEP_OPTION_KEYS

# Human-readable display names for token kinds used in error messages.
_TOKEN_DISPLAY: dict[str, str] = {
    "ID": "identifier",
    "STR": "string literal",
    "STRING_START": "interpolated string",
    "NUM": "number",
    "NUM_INT": "integer literal",
    "SEP": "end of statement",
    "EOF": "end of file",
    "LET": "'let'",
    "FN": "'fn'",
    "RETURN": "'return'",
    "YIELD": "'yield'",
    "IF": "'if'",
    "ELSE": "'else'",
    "WHILE": "'while'",
    "FOR": "'for'",
    "IN": "'in'",
    "AS": "'as'",
    "FROM": "'from'",
    "IMPORT": "'import'",
    "EXPORT": "'export'",
    "PRINT": "'print'",
    "TRY": "'try'",
    "CATCH": "'catch'",
    "FINALLY": "'finally'",
    "THROW": "'throw'",
    "RECORD": "'record'",
    "WITH": "'with'",
    "ACTION": "'action'",
    "TRUE": "'true'",
    "FALSE": "'false'",
    "NIL": "'nil'",
}


def _tok_name(kind: str) -> str:
    if kind in _TOKEN_DISPLAY:
        return _TOKEN_DISPLAY[kind]
    return f"'{kind}'"


def _tok_desc(kind: str, val: str) -> str:
    name = _tok_name(kind)
    if kind in ("ID", "STR", "NUM", "NUM_INT"):
        return f"{name} ({val!r})"
    return name


_MAX_PARSE_DEPTH = 50

# Token kinds that can only *follow* a completed value, never begin one (#717).
#
# `match` is a contextual keyword, which is supposed to mean it stays usable as
# an identifier -- and it was the one word of fourteen that was not. The
# expression-atom dispatch fired on the name alone, so `let match = 7i` bound
# fine and every read (`print(match)`, `match + 1i`, `"\(match)"`) was a syntax
# error. One token of lookahead separates the two: a match expression is
# `match <scrutinee> { arm, ... }`, so the word is always followed by the start
# of an expression, while an identifier read is followed by one of these.
#
# **This is a deny-list rather than an allow-list on purpose, and the direction
# is what makes the change safe.** Before it, an `ID` named `match` in
# expression position *always* took `parse_match`, so every program diverted
# here is one that raises today -- `parse_match` calls `self.expr()` and it has
# nothing to parse. Turning those into a `Var` read can only convert an error
# into a working program; it cannot change the meaning of any match expression
# that parses now. An allow-list ("kinds that may start a scrutinee") would have
# the opposite failure mode: one omission silently breaks a shipped, Mostly
# Stable construct.
#
# Residual ambiguity, stated rather than papered over: `match - 1i`,
# `match(f)`, `match[0]` and `match ! x` still parse as match expressions,
# because each token can also begin a scrutinee (unary minus, a parenthesised
# or list scrutinee, unary not). A soft keyword cannot resolve those without
# unbounded lookahead, and reserving the word would break the contract this
# fixes. `let m = match; ... m - 1i` is the workaround, and the tests pin the
# boundary so it does not drift silently.
_VALUE_FOLLOWERS = frozenset({
    ")", "]", "}", ",", ";", ":", "SEP", "EOF", "INTERP_END",
    ".", "=", "=>", "->",
    "+", "*", "/", "%",
    "==", "!=", "<", ">", "<=", ">=", "&&", "||",
    "+=", "-=", "*=", "/=",
})

# The two clauses that take a predicate. They share a grammar and a parser, so
# the error naming the grammar has to be told which one the author wrote --
# `step … when (x < 5)` used to be refused with a sentence about goal `until`,
# a clause that appears nowhere in the program being compiled (#471).
GOAL_UNTIL_CLAUSE = "goal `until`"
STEP_WHEN_CLAUSE = "step guard `when`"

_PREDICATE_GRAMMAR = 'reached("label"), &&, ||, ! and parentheses'

#: Where to go when someone reaches for a value here. The restriction is
#: deliberate: `reached()` takes a string literal so the complete set of
#: checkpoints is known at parse time and can be checked against the flow, which
#: is what turns a typo'd label into a compile error rather than a step that
#: silently never runs. Branching on data is done by recording the checkpoint
#: conditionally -- so the hint has to say that, or the refusal reads as a gap.
_PREDICATE_HINT = (
    "To branch on a value, record a checkpoint conditionally in the upstream "
    'step and guard on it: `if (score < 80i) { checkpoint "needs_review" }`, '
    'then `when reached("needs_review")`.'
)


def _predicate_help(clause: str) -> str:
    message = f"{clause} supports {_PREDICATE_GRAMMAR}"
    if clause == STEP_WHEN_CLAUSE:
        return f"{message}. {_PREDICATE_HINT}"
    return message


@dataclass(frozen=True)
class UnknownTypeName:
    """An annotation naming a type the checker has never heard of (#609).

    Carries the token position, because the AST keeps only the string: a
    consumer reporting from the node alone could say *which function* but not
    *which annotation*.
    """

    name: str
    suggestion: str | None
    line: int
    col: int

    def message(self) -> str:
        hint = f" — did you mean '{self.suggestion}'?" if self.suggestion else "."
        return (
            f"Unknown type name '{self.name}'{hint} It is currently ignored, so "
            f"nothing on this annotation is checked; in 6.0.0 it becomes an "
            f"error. Known types: {', '.join(sorted(TYPE_NAMES))}."
        )


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
        self._block_depth = 0
        self.goal_depth = 0
        self._parse_depth = 0
        # #609. Every consumer builds its own Parser (`check_source`, the
        # diagnostics walker, the LSP), so collecting here is what makes them
        # agree without each re-deriving the answer.
        self.unknown_type_names: list[UnknownTypeName] = []

    def error(self, message: str, tok: Tok | None = None) -> NoReturn:
        # Annotated NoReturn so type checking understands that every `self.error()`
        # call ends the path — without it mypy treats values guarded by an error
        # branch as still possibly-None at the next use.
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
            self.error(f"Expected {_tok_name(kind)}, got {_tok_desc(t.kind, t.val)}", t)
        self.i += 1
        self.last_token = t
        return t

    def skip_seps(self) -> None:
        while self.at("SEP"):
            self.i += 1

    def eat_required_sep(self) -> None:
        self.eat("SEP")
        self.skip_seps()

    def take_pending_comments(self) -> list[str]:
        """Claim the comments queued so far, before parsing the next statement.

        **Taken before, not bound after** — and that ordering is the whole fix
        (#737). By the time a body is entered, the comment written above the
        function and the comment written above the body's first statement are
        both sitting on one queue, indistinguishable. Whichever loop drains first
        claims both: draining only in `parse()` pulled the inner comment out to
        the header, and draining only in `block()` pushed the outer comment down
        into the body. Claiming at the point the statement *starts* is what
        separates them, because that is the moment only one of them exists.

        Safe to hand back a plain list: `stmt()` never returns a `Comment` — the
        only construction site is `flush_trailing_comments` — so nothing claimed
        here can be discarded by the caller.
        """
        taken = [tok.val for tok in self.pending_comments]
        self.pending_comments.clear()
        return taken

    def bind_comments(self, stmt, leading: list[str]):
        """Attach `leading` to `stmt`, plus whatever trailed it while parsing.

        The two run in opposite directions and that is not a mistake: a leading
        comment is queued *before* its statement, a trailing one *during* it.
        """
        if leading:
            setattr(stmt, "_comments", leading)
        if self.pending_trailing:
            setattr(stmt, "_trailing_comments", [tok.val for tok in self.pending_trailing])
            self.pending_trailing.clear()
        if self.last_token is not None:
            self.last_stmt = stmt
            self.last_stmt_end_line = self.last_token.line
        return stmt

    def flush_trailing_comments(self, stmts: list) -> None:
        """A comment with no statement after it becomes a node of its own.

        At the end of a block as well as the end of a file: without this the
        comment above a closing brace would stay queued and re-attach itself to
        whatever statement came next, outside the block.
        """
        for tok in self.pending_comments:
            stmts.append(Comment(tok.val))
        self.pending_comments.clear()

    def parse(self) -> list:
        stmts = []
        self.skip_seps()
        while not self.at("EOF"):
            leading = self.take_pending_comments()
            stmt = self.stmt()
            self.bind_comments(stmt, leading)
            stmts.append(stmt)
            self.skip_seps()
        self.flush_trailing_comments(stmts)
        # #409: a goal's checkpoints are checked against the workflow it pursues.
        # Module-level rather than inside `goal_pursuit`, because the workflow may
        # be declared after the goal that pursues it.
        validate_goal_pursuits(stmts)
        # #471: a step guard's checkpoints are checked against its own flow.
        validate_step_guards(stmts)
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

        # #489: contextual, and matched from the lexer's set rather than a bare
        # literal -- a word the parser recognises but `lexer.ALL_KEYWORDS` does
        # not name ships unhighlighted, which is how `each` shipped (#480).
        if self.at("ID") and self.peek().val in EXTERN_KEYWORDS and self.peek_ahead(1).kind == "ID":
            return self.extern_decl()

        if self.at("EXPORT"):
            start = self.eat("EXPORT")
            if self.at("LET"):
                let_tok = self.eat("LET")
                return self.let_stmt(exported=True, start_tok=let_tok)
            if self.at("@"):
                return self.annotated_fn_def(exported=True)
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

        if self.at("@"):
            return self.annotated_fn_def()

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
            # #415: `catch` is optional when `finally` is present. The
            # cleanup-without-handling form used to demand `catch e { throw e }`
            # as boilerplate -- forcing every cleanup site onto the
            # catch-re-throws path.
            catch_var = None
            catch_block = None
            if self.at("CATCH"):
                self.eat("CATCH")
                if self.at("("):
                    self.eat("(")
                    catch_var = self.eat("ID").val
                    self.eat(")")
                else:
                    catch_var = self.eat("ID").val
                catch_block = self.block()
                self.skip_seps()
            finally_block = None
            if self.at("FINALLY"):
                self.eat("FINALLY")
                finally_block = self.block()
            if catch_block is None and finally_block is None:
                self.error("try needs a 'catch', a 'finally', or both", start)
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

        # Contextual keywords: read from CONTEXTUAL_KEYWORDS so tooling that
        # needs the keyword list (the editor grammar) cannot fall behind the
        # parser without a test noticing (#357).
        if self.at("ID") and self.peek().val in LOOP_CONTROL_KEYWORDS:
            tok = self.eat("ID")
            node = Break() if tok.val == "break" else Continue()
            return self.mark(node, tok)

        return ExprStmt(self.expr())

    def block(self):
        start = self.eat("{")
        stmts = []
        self.skip_seps()

        # #489: `extern` is a module-scope declaration, so the parser needs to
        # know it is inside something. Counted rather than inferred from the
        # statement list afterwards, so the error can name the right token.
        self._block_depth += 1
        try:
            while not self.at("}"):
                if self.at("EOF"):
                    self.error("Unterminated block")
                # #737: claimed here, exactly as the top-level loop claims its
                # own. Without this the queue drains upward and every comment in
                # the body lands on the enclosing function.
                leading = self.take_pending_comments()
                inner = self.stmt()
                self.bind_comments(inner, leading)
                stmts.append(inner)
                self.skip_seps()
            self.flush_trailing_comments(stmts)
        finally:
            self._block_depth -= 1

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
            self.skip_seps()
            if self.at("IF"):
                else_branch = self.if_stmt()
            else:
                else_branch = self.block()

        return self.mark(If(cond, then_branch, else_branch), start)

    def while_stmt(self):
        start = self.eat("WHILE")
        if not self.at("("):
            self.error("while condition must be in parentheses: while (condition) { ... }", start)
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

    def annotated_fn_def(self, exported: bool = False):
        annotations = []
        while self.at("@"):
            at_tok = self.eat("@")
            name = self.eat("ID").val
            args = None
            if self.at("("):
                self.eat("(")
                args = []
                if not self.at(")"):
                    while True:
                        key = self.eat("ID").val
                        self.eat(":")
                        val = self.expr()
                        args.append((key, val))
                        if not self.at(","):
                            break
                        self.eat(",")
                self.eat(")")
            annotations.append(self.mark(Annotation(name, args), at_tok))
            self.skip_seps()
        fn = self.fn_def(exported=exported)
        fn.annotations = annotations
        return fn

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
        # `goal NAME over WORKFLOW { ... }` is the stopping-condition form (#409).
        # `goal NAME { step ... }` is the original and is unchanged — it is Mostly
        # Stable, graduated v4.0.5, so this is additive rather than a replacement.
        if self.at("ID") and self.peek_ahead(1).kind == "ID" and self.peek_ahead(1).val == "over":
            return self.goal_pursuit(start)
        return self.flow_def(start, GoalDef, GoalStep, "goal")

    def goal_pursuit(self, start: Tok):
        name = self.eat("ID").val
        self.eat("ID")  # `over` — checked by the caller
        workflow_tok = self.eat("ID")
        workflow_name = workflow_tok.val
        self.eat("{")
        self.skip_seps()

        until = None
        budget = None
        retry_from = None
        while not self.at("}"):
            if self.at("EOF"):
                self.error("Unterminated goal", start)
            if not self.at("ID"):
                self.error(
                    "goal body must contain `until`, `budget` or `retry from`",
                    self.peek(),
                )
            clause_tok = self.peek()
            clause = clause_tok.val
            if clause == "until":
                if until is not None:
                    self.error("Duplicate `until` in goal", clause_tok)
                self.eat("ID")
                until = self.goal_predicate()
            elif clause == "budget":
                if budget is not None:
                    self.error("Duplicate `budget` in goal", clause_tok)
                self.eat("ID")
                budget = self.goal_budget(clause_tok)
            elif clause == "retry":
                if retry_from is not None:
                    self.error("Duplicate `retry from` in goal", clause_tok)
                self.eat("ID")
                if not self.at("FROM"):
                    self.error("Expected `from` after `retry`", self.peek())
                self.eat("FROM")
                if not self.at("STR"):
                    self.error("retry from label must be a string", self.peek())
                label_tok = self.eat("STR")
                retry_from = self.mark(Str(label_tok.val), label_tok)
            else:
                self.error(f"Unsupported goal clause: {clause}", clause_tok)
            self.skip_seps()
        self.eat("}")

        if until is None:
            self.error(
                f"goal '{name}' has no `until` - a goal without a stopping "
                f"condition is a workflow, so write it as one",
                start,
            )
        if budget is None:
            # Deliberately not defaulted. An unbounded pursuit is a hang, and
            # bounded execution is the runtime's whole proposition, so the bound
            # is declared or the program is rejected.
            self.error(
                f"goal '{name}' has no `budget` - declare "
                f"`budget {{ max_iterations: N, deadline_ms: M }}`",
                start,
            )
        return self.mark(
            GoalPursuit(name, workflow_name, until, budget, retry_from=retry_from),
            start,
        )

    def goal_budget(self, start: Tok):
        # #488: the outer vocabulary stays **closed and parse-checkable**, which
        # is the property this surface already had and is worth keeping — an
        # unknown key is refused here with an accurate message rather than
        # silently ignored. `limits` is the single key whose *contents* are open,
        # and they are resolved against the host at run time because only the
        # host knows what it is counting. A flat open vocabulary would have had
        # to move the unknown-key check to run time to know that.
        options = self.parse_named_map_literal(
            error_keys={"max_iterations", "deadline_ms", "limits"},
            error_template=(
                "Unsupported budget option: {key}. `budget` takes "
                "max_iterations, deadline_ms and limits (a map of "
                "host-registered meters)."
            ),
        )
        found: dict[str, object] = {}
        for key_node, value_node in options.items:
            key = getattr(key_node, "v", None)
            if isinstance(key, str):
                found[key] = value_node
        limits = found.get("limits")
        if limits is not None:
            # `{ tokens: 100000 }` parses as a *record* literal (unquoted keys)
            # and `{ "tokens": 100000 }` as a map. Both read naturally here, and
            # the rest of the budget is already unquoted, so accept either and
            # normalise to a map — the lowering emits data, and a Record is not
            # JSON serializable.
            if isinstance(limits, RecordLiteral):
                limits = self.mark(
                    MapLit([(Str(key), value) for key, value in limits.fields]),
                    start,
                )
            if not isinstance(limits, MapLit):
                self.error(
                    "goal budget `limits` must be a map of meter names to "
                    "numbers, e.g. `limits: { tokens: 100000 }`",
                    start,
                )
            if not limits.items:
                self.error(
                    "goal budget `limits` is empty. Name at least one meter, or "
                    "omit the key.",
                    start,
                )
        if not any(k in found for k in ("max_iterations", "deadline_ms", "limits")):
            self.error(
                "goal budget must set at least one of `max_iterations`, "
                "`deadline_ms` or `limits`. An unbounded goal is a hang.",
                start,
            )
        return self.mark(
            GoalBudget(
                found.get("max_iterations"),
                found.get("deadline_ms"),
                limits,
            ),
            start,
        )

    # --- the `until` / `when` predicate ------------------------------------
    # A restricted grammar rather than a general expression. `reached("L")` takes
    # a string literal only, so the complete set of checkpoints a goal depends on
    # is known at parse time and can be checked against the workflow it pursues
    # (#409). A general expression would make that check best-effort.

    def goal_predicate(self, clause: str = GOAL_UNTIL_CLAUSE):
        node = self.goal_predicate_and(clause)
        while self.at("||"):
            tok = self.eat("||")
            node = self.mark(PredicateOr(node, self.goal_predicate_and(clause)), tok)
        return node

    def goal_predicate_and(self, clause: str):
        node = self.goal_predicate_unary(clause)
        while self.at("&&"):
            tok = self.eat("&&")
            node = self.mark(PredicateAnd(node, self.goal_predicate_unary(clause)), tok)
        return node

    def goal_predicate_unary(self, clause: str):
        if self.at("!"):
            tok = self.eat("!")
            return self.mark(PredicateNot(self.goal_predicate_unary(clause)), tok)
        return self.goal_predicate_primary(clause)

    def goal_predicate_primary(self, clause: str):
        if self.at("("):
            self.eat("(")
            node = self.goal_predicate(clause)
            self.eat(")")
            return node
        tok = self.peek()
        if self.at("ID") and tok.val == "reached":
            self.eat("ID")
            self.eat("(")
            if not self.at("STR"):
                self.error("reached() takes a string literal checkpoint label", self.peek())
            label_tok = self.eat("STR")
            self.eat(")")
            return self.mark(Reached(self.mark(Str(label_tok.val), label_tok)), tok)
        self.error(_predicate_help(clause), tok)

    def flow_def(self, start: Tok, def_type, step_type, label: str):
        name = self.eat("ID").val
        # `workflow build(mode) { ... }` (#481). Optional, so every existing flow
        # parses unchanged. Empty parentheses are refused rather than silently
        # accepted as "no parameters" — writing them says a list was intended.
        params: list[Param] = []
        if self.at("("):
            paren = self.eat("(")
            if self.at(")"):
                self.error(
                    f"{label} '{name}' declares an empty parameter list. Omit the "
                    f"parentheses if it takes no parameters.",
                    paren,
                )
            while True:
                params.append(self.parse_param())
                if self.at(","):
                    self.eat(",")
                    continue
                break
            self.eat(")")
            seen_params: set[str] = set()
            for param in params:
                if param.name in seen_params:
                    self.error(
                        f"Duplicate parameter '{param.name}' in {label} '{name}'",
                        start,
                    )
                seen_params.add(param.name)
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
            # #737: a workflow body is its own statement loop, not a `block()`,
            # so it needs its own claim. Without one, the comment above a `step`
            # stayed queued while the step's body was parsed and was taken by the
            # *step body's* first statement — the same defect one level in, and
            # the reason a workflow is worth testing separately from a function.
            leading = self.take_pending_comments()
            if self.at("ID") and self.peek().val == "state":
                states.append(self.bind_comments(self.flow_state_decl(label), leading))
            elif self.at("STEP"):
                steps.append(self.bind_comments(self.flow_step(step_type), leading))
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
        # #481: a parameter and a step sharing a name would make `mode` mean one
        # thing at the top of a step body and another after `after mode`. Refuse
        # rather than pick.
        for param in params:
            if param.name in name_set:
                self.error(
                    f"{label} '{name}' has a parameter and a step both named "
                    f"'{param.name}'",
                    start,
                )
            if any(state.name == param.name for state in states):
                self.error(
                    f"{label} '{name}' has a parameter and a state cell both "
                    f"named '{param.name}'",
                    start,
                )
        return self.mark(def_type(name, states, steps, params=params), start)

    def flow_state_decl(self, label: str):
        start = self.eat("ID")
        if self.workflow_depth <= 0 and self.goal_depth <= 0:
            self.error(f"state declarations are only valid inside {label}s", start)
        name = self.eat("ID").val
        self.eat("=")
        expr = self.expr()
        # After the initializer, so the cell reads as "this is the value, and this
        # is how it behaves" -- and so the `: type` slot stays free for typing
        # state later, which is a separate question (#479 is about step outputs).
        options = None
        if self.at("WITH"):
            self.eat("WITH")
            options = self.parse_state_options()
        return self.mark(WorkflowStateDecl(name, expr, options=options), start)

    def parse_state_options(self):
        return self.parse_named_map_literal(
            error_keys=STATE_OPTION_KEYS,
            error_template="Unsupported workflow state option: {key}",
        )

    def flow_step(self, step_type):
        start = self.eat("STEP")
        name = self.eat("ID").val
        deps = []
        options = None
        # `compensates DEP` (#577), first in the header: it says what this step
        # *is* before what it depends on. A step carrying it is a compensation
        # handler and is excluded from the forward graph.
        compensates = None
        if self.at("ID") and self.peek().val in COMPENSATION_KEYWORDS:
            comp_tok = self.peek()
            self.eat("ID")
            compensates = self.eat("ID").val
            if compensates == name:
                self.error(
                    f"step '{name}' compensates itself; a handler undoes another "
                    f"step's work",
                    comp_tok,
                )
        # `each VAR in DEP` -- a mapped node (#480). Written before `after`,
        # because `in DEP` *is* a dependency: the step cannot be expanded until
        # the producer has run, and requiring the author to also write
        # `after DEP` would let the two disagree.
        each_var = None
        each_source = None
        if self.at("ID") and self.peek().val in STEP_MAP_KEYWORDS:
            each_tok = self.peek()
            self.eat("ID")
            each_var = self.eat("ID").val
            if not (self.at("IN")):
                self.error(
                    "step `each` needs a source: `each item in producer { ... }`",
                    each_tok,
                )
            self.eat("IN")
            each_source = self.eat("ID").val
            deps.append(each_source)
            if each_var == each_source:
                self.error(
                    f"step '{name}' binds `each {each_var} in {each_source}` -- the "
                    f"item and the producer cannot share a name, or the body "
                    f"cannot say which it means",
                    each_tok,
                )
        if self.at("AFTER"):
            self.eat("AFTER")
            deps.append(self.eat("ID").val)
            while self.at(","):
                self.eat(",")
                deps.append(self.eat("ID").val)
        # `when <predicate>` sits between `after` and `with`, which is how it
        # reads: what this step depends on, whether it should run at all, then how
        # it should be run. Contextual, so `when` stays usable as an identifier.
        when = None
        if self.at("ID") and self.peek().val == "when":
            self.eat("ID")
            when = self.goal_predicate(STEP_WHEN_CLAUSE)
        if self.at("WITH"):
            self.eat("WITH")
            options = self.parse_workflow_options()
        self.workflow_step_depth += 1
        body = self.block()
        self.workflow_step_depth -= 1
        if compensates is not None:
            # Refused here rather than left inert. Each of these could only ever
            # be a no-op or an ambiguity, which is the shape this cluster has
            # been removing -- see the table in
            # docs/design/workflow-dsl/01-compensation.md.
            # `each` is checked first: `each x in src` adds `src` to `deps`, so
            # testing `deps` before it would refuse an `each` handler with the
            # `after` message and send the author looking for a clause they did
            # not write.
            if each_var is not None:
                self.error(
                    f"compensation handler '{name}' cannot declare `each` — it "
                    f"inherits the fan-out of the step it compensates, one "
                    f"instance at a time",
                    start,
                )
            if deps:
                self.error(
                    f"compensation handler '{name}' cannot declare `after` — it "
                    f"is not part of the forward graph, so there is nothing "
                    f"there for it to wait on",
                    start,
                )
            if when is not None:
                self.error(
                    f"compensation handler '{name}' cannot declare `when` — its "
                    f"trigger is the run ending failed, and a guard could only "
                    f"suppress it silently",
                    start,
                )
            # The compensated step's value binds by the rule `after` already
            # uses, so the handler's body reads it by name.
            deps = [compensates]
        return self.mark(
            step_type(name, deps, body, options=options, when=when,
                      each_var=each_var, each_source=each_source,
                      compensates=compensates),
            start,
        )

    def extern_decl(self):
        """`extern NAME(param: type, ...) -> type` -- a host function this program needs (#489).

        Types are optional per parameter and reuse `parse_type_name`, so the
        vocabulary is the one #609 made sound rather than a second list. There is
        no body: an extern is a *declaration*, and the host supplies the value.
        """
        start = self.eat("ID")  # `extern`
        if self._block_depth > 0:
            self.error(
                "`extern` declares a host function this program requires, so it "
                "belongs at the top of the file rather than inside a block",
                start,
            )
        name = self.eat("ID").val
        self.eat("(")
        params = []
        seen: set[str] = set()
        if not self.at(")"):
            while True:
                param_tok = self.peek()
                param_name = self.eat("ID").val
                if param_name in seen:
                    self.error(
                        f"extern '{name}' declares parameter '{param_name}' twice",
                        param_tok,
                    )
                seen.add(param_name)
                type_hint = None
                if self.at(":"):
                    self.eat(":")
                    type_hint = self._extern_type_name(name, param_name)
                params.append(Param(param_name, type_hint))
                if not self.at(","):
                    break
                self.eat(",")
        self.eat(")")
        return_type = None
        if self.at("->"):
            self.eat("->")
            return_type = self._extern_type_name(name, "return")
        return self.mark(ExternDecl(name, params, return_type), start)

    def _extern_type_name(self, extern_name: str, slot: str) -> str:
        """A type in an `extern`, checked as an **error** rather than a warning.

        #609 stages an unrecognised annotation as a warning until 6.0.0, because
        code already exists that a sudden error would break. `extern` is new, so
        nothing can be relying on a misspelling being ignored -- the same reason
        #479 made `returns:` an error on arrival. A type that silently meant
        "any" would make the declaration inert, which is the shape this whole
        cluster has been removing.
        """
        tok = self.peek()
        declared = self.parse_type_name()
        if not is_known_type_name(declared):
            hint = suggest_type_name(declared)
            suffix = f" -- did you mean '{hint}'?" if hint else "."
            self.error(
                f"extern '{extern_name}' names unknown type '{declared}' for "
                f"{slot}{suffix} Known types: {', '.join(sorted(TYPE_NAMES))}.",
                tok,
            )
        return declared

    def parse_workflow_options(self):
        options = self.parse_named_map_literal(
            error_keys=STEP_OPTION_KEYS,
            error_template="Unsupported workflow step option: {key}",
        )
        # #479: `returns:` names a type, so it is checked here against the one
        # vocabulary (#609). Unlike an annotation on a function, this is **an
        # error rather than a warning**: the option is new, so nothing can
        # already be relying on a misspelling being ignored, and a `returns:`
        # that silently means "any type at all" would be a declared-but-inert
        # field -- the exact shape this cluster has been removing.
        for key_node, value_node in options.items:
            if getattr(key_node, "v", None) != "returns":
                continue
            declared = getattr(value_node, "v", None)
            if not isinstance(declared, str):
                self.error(
                    "step `returns:` must be a type name in quotes, "
                    'e.g. `with { returns: "int" }`',
                    getattr(value_node, "_tok", None) or self.peek(),
                )
            if not is_known_type_name(declared):
                hint = suggest_type_name(declared)
                suffix = f" -- did you mean '{hint}'?" if hint else "."
                self.error(
                    f"step `returns:` names unknown type '{declared}'{suffix} "
                    f"Known types: {', '.join(sorted(TYPE_NAMES))}.",
                    getattr(value_node, "_tok", None) or self.peek(),
                )
        return options

    def expr(self):
        self._parse_depth += 1
        if self._parse_depth > _MAX_PARSE_DEPTH:
            t = self.peek()
            self._parse_depth -= 1
            raise LangSyntaxError(
                f"Expression too deeply nested (max depth: {_MAX_PARSE_DEPTH})",
                line=t.line,
                col=t.col,
            )
        try:
            return self.parse_assignment()
        except RecursionError:
            t = self.peek()
            raise LangSyntaxError(
                f"Expression too deeply nested (max depth: {_MAX_PARSE_DEPTH})",
                line=t.line,
                col=t.col,
            ) from None
        finally:
            self._parse_depth -= 1

    _COMPOUND_OPS = {"+=": "+", "-=": "-", "*=": "*", "/=": "/"}

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

        for tok_text, bin_op in self._COMPOUND_OPS.items():
            if self.at(tok_text):
                op_tok = self.eat(tok_text)
                rhs = self.parse_assignment()
                if isinstance(node, Var):
                    return self.mark(CompoundAssign(node.name, bin_op, rhs), op_tok)
                if isinstance(node, Index):
                    new_val = self.mark(Bin(bin_op, node, rhs), op_tok)
                    return self.mark(IndexAssign(node.seq, node.index, new_val), op_tok)
                if isinstance(node, Attr):
                    new_val = self.mark(Bin(bin_op, node, rhs), op_tok)
                    return self.mark(FieldAssign(node.obj, node.name, new_val), op_tok)
                self.error(f"Invalid left-hand side for '{tok_text}'", op_tok)

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
        while self.at("*") or self.at("/") or self.at("%"):
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
                        self.skip_seps()
                        if self.at(")"):
                            break
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
                key_start = self.peek()
                key = self.expr()
                # Bare single identifier in map key position is a parse error.
                if isinstance(key, Var) and key_start.kind == "ID":
                    self.error(
                        f'bare identifier "{key.name}" cannot be a map key.\n'
                        f'  - to use the variable\'s value as the key, write: {{({key.name}): ...}}\n'
                        f'  - to use the literal string "{key.name}" as the key, write: {{"{key.name}": ...}}',
                        key_start,
                    )
                self.eat(":")
                self.skip_seps()
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
                if self.at("STR"):
                    self.error(
                        'cannot mix quoted and bare-identifier keys in the same literal.\n'
                        '  - to use a map literal with string keys, quote all keys: {"key": value, ...}\n'
                        '  - to use a record literal with field names, use bare identifiers: {field: value, ...}',
                    )
                key = self.eat("ID").val
                self.eat(":")
                self.skip_seps()
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
        self.error(f"Expected a destructuring pattern ('[', '{{', or identifier), got {_tok_desc(t.kind, t.val)}", t)

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

        if self.at("NUM_INT"):
            tok = self.eat("NUM_INT")
            return self.mark(Int(int(tok.val), raw=tok.val + "i"), tok)

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

        if self.at("STRING_START"):
            return self.parse_interpolated_string()

        if (
            self.at("ID")
            and self.peek().val in EXPRESSION_KEYWORDS
            and self.peek_ahead(1).kind not in _VALUE_FOLLOWERS
        ):
            return self.parse_match()

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
                    self.skip_seps()
                    if self.at("]"):
                        break
                    items.append(self.expr())
            self.eat("]")
            return self.mark(ListLit(items), tok)

        if self.at("{"):
            # Lookahead: if first key is exactly "ID :" → record literal context.
            # Anything else (quoted key, paren, complex expression) → map literal.
            look = self.i + 1
            while look < len(self.toks) and self.toks[look].kind == "SEP":
                look += 1
            first_tok = self.toks[look] if look < len(self.toks) else None
            look2 = look + 1
            while look2 < len(self.toks) and self.toks[look2].kind == "SEP":
                look2 += 1
            second_tok = self.toks[look2] if look2 < len(self.toks) else None
            if (first_tok and first_tok.kind == "ID"
                    and second_tok and second_tok.kind == ":"):
                return self.parse_record_literal()
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
        kind = t.kind
        if kind == "}":
            self.error("Unexpected '}' - check for a missing expression or extra closing brace", t)
        elif kind in ("EOF", "SEP"):
            self.error(f"Unexpected {_tok_name(kind)} - expression is incomplete", t)
        elif (kind == "=" and self.last_token is not None
              and self.last_token.kind in ("+", "-", "*", "/")):
            op = self.last_token.kind
            self.error(
                f"Nodus has no '{op}=' operator; use the full form: x = x {op} value",
                t,
            )
        else:
            self.error(f"Unexpected {_tok_desc(kind, t.val)} in expression", t)

    def parse_match(self):
        start = self.eat("ID")  # 'match'
        scrutinee = self.expr()
        if not self.at("{"):
            self.error(
                "match requires arms in braces: match <expr> { pattern => body, ... }",
                start,
            )
        self.eat("{")
        self.skip_seps()
        arms = []
        seen_wildcard = False
        while not self.at("}"):
            if self.at("EOF"):
                self.error("Unterminated match expression: expected '}'")
            if seen_wildcard:
                self.error(
                    "the wildcard arm '_' must be the last arm in a match",
                    self.peek(),
                )
            if self.at("ID") and self.peek().val == "_":
                self.eat("ID")
                pattern = None
                seen_wildcard = True
            else:
                pattern = self.expr()
            if not self.at("=>"):
                self.error("match arm requires '=>' between pattern and body", self.peek())
            self.eat("=>")
            # An arm body is a block, a bare diverging statement (throw/return),
            # or an expression whose value becomes the arm's result.
            if self.at("{"):
                body = self.block()
            elif self.at("THROW"):
                throw_tok = self.eat("THROW")
                body = self.mark(Throw(self.expr()), throw_tok)
            elif self.at("RETURN"):
                ret_tok = self.eat("RETURN")
                if self.at("SEP") or self.at("}") or self.at(",") or self.at("EOF"):
                    body = self.mark(Return(None), ret_tok)
                else:
                    body = self.mark(Return(self.expr()), ret_tok)
            else:
                body = self.expr()
            arms.append(MatchArm(pattern, body))
            self.skip_seps()
            if self.at(","):
                self.eat(",")
                self.skip_seps()
        self.eat("}")
        if not arms:
            self.error("match must have at least one arm", start)
        return self.mark(Match(scrutinee, arms), start)

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

    def parse_interpolated_string(self):
        start = self.eat("STRING_START")
        parts = []
        while not self.at("STRING_END"):
            if self.at("STRING_LITERAL"):
                tok = self.eat("STRING_LITERAL")
                parts.append(StringLiteralPart(tok.val))
            elif self.at("INTERP_START"):
                interp_tok = self.eat("INTERP_START")
                if self.at("INTERP_END"):
                    self.error(
                        f"Empty interpolation expression at line {interp_tok.line} column {interp_tok.col}",
                        interp_tok,
                    )
                self.skip_seps()
                expr = self.expr()
                self.skip_seps()
                self.eat("INTERP_END")
                parts.append(InterpolationPart(expr))
            elif self.at("EOF"):
                self.error("Unclosed interpolated string", start)
            else:
                self.error(
                    f"Unexpected token {self.peek().kind!r} inside interpolated string"
                )
        self.eat("STRING_END")
        return self.mark(InterpolatedString(parts), start)

    def parse_named_map_literal(self, *, error_keys: set[str] | None = None, error_template: str | None = None):
        tok = self.eat("{")
        items: list[tuple[object, object]] = []
        self.skip_seps()
        if not self.at("}"):
            while True:
                key_tok = self.eat("ID")
                if error_keys is not None and key_tok.val not in error_keys:
                    self.error((error_template or "Unsupported key: {key}").format(key=key_tok.val), key_tok)
                self.eat(":")
                self.skip_seps()
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

    # Type names that are also keywords, so they never arrive as an `ID`. Both
    # name real Nodus types; without this, `-> record` was a syntax error and
    # `record` sat in `TYPE_NAMES` as a dead entry nobody could reach (#609).
    _KEYWORD_TYPE_NAMES = ("RECORD", "NIL")

    def parse_type_name(self) -> str:
        tok = self.peek()
        if tok.kind in self._KEYWORD_TYPE_NAMES:
            self.i += 1
            self.last_token = tok
        else:
            tok = self.eat("ID")
        name = tok.val
        if not is_known_type_name(name):
            # #609: an unrecognised name used to become `any` in silence, so one
            # transposed letter disabled checking on that parameter forever. It
            # is recorded here — the only place that sees both the name and the
            # token — and reported by whoever asks. Warning in 5.x, error at
            # 6.0.0 alongside #545/#547.
            self.unknown_type_names.append(UnknownTypeName(
                name=name,
                suggestion=suggest_type_name(name),
                line=tok.line,
                col=tok.col,
            ))
        return name

    def parse_param(self) -> Param:
        tok = self.eat("ID")
        type_hint = None
        if self.at(":"):
            self.eat(":")
            type_hint = self.parse_type_name()
        return self.mark(Param(tok.val, type_hint=type_hint), tok)
