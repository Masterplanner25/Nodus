"""Source formatter for Nodus."""

from nodus.frontend.ast.ast_nodes import (
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
    ExportFrom,
    ExportList,
    ExprStmt,
    FieldAssign,
    ExternDecl,
    FnDef,
    FnExpr,
    For,
    ForEach,
    GoalDef,
    GoalPursuit,
    GoalStep,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    ListPattern,
    MapLit,
    Int,
    Nil,
    Num,
    Param,
    Print,
    RecordLiteral,
    RecordPattern,
    InterpolatedString,
    InterpolationPart,
    StringLiteralPart,
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
    Break,
    Continue,
    Match,
    Yield,
)
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser


INDENT = "    "


def format_source(src: str, keep_trailing_comments: bool = False) -> str:
    stmts = Parser(tokenize(src)).parse()
    return format_program(stmts, keep_trailing_comments=keep_trailing_comments)


def _split_demoted_trailing(stmt, produced: list[str]):
    """Separate a statement's own lines from any trailing comments it demoted.

    **Decided by reading the rendered lines, not by the mode**, and that is
    load-bearing. `keep_trailing_comments` looks like it decides this, and does
    not: sixteen branches of `format_stmt` — every block-bodied statement, `fn`
    and `workflow` and `if` among them — call `trailing_lines` directly instead
    of `attach_trailing`, so they demote in *both* modes. Keying off the flag
    left those statements' comments uncarried and the blank line on the wrong
    side of them, which is #739 again in the mode that was supposed to be
    immune.

    Comparing the tail also protects the other direction: a branch that returns
    without emitting the trailing comments at all would otherwise have real code
    chopped off it.
    """
    trailing = getattr(stmt, "_trailing_comments", None)
    if not trailing:
        return produced, []
    demoted = trailing_lines("", trailing)
    if len(produced) < len(demoted) or produced[-len(demoted):] != demoted:
        return produced, []
    return produced[: -len(demoted)], demoted


def _needs_blank_line(prev_import: bool, prev_fn: bool, is_import: bool, is_fn: bool) -> bool:
    """Does a blank line go between the previous top-level statement and this one?

    Named once because it is asked twice: for each statement in the loop, and
    again for trailing comments left over at the end of the file, which re-parse
    as standalone `Comment` statements and must be given the same answer. Written
    out inline the second time, it disagreed — the tail checked only `prev_fn`,
    so a trailing comment on the last `import` got no blank on the first pass and
    one on the second, which is #739 surviving its own fix in a corner.
    """
    if prev_import and not is_import:
        return True
    return prev_fn or is_fn


def format_program(stmts: list, keep_trailing_comments: bool = False) -> str:
    """Render top-level statements, with the blank-line policy between them.

    **A demoted trailing comment is emitted where re-parsing will put it** — as a
    leading comment of the *next* statement, after the blank line — rather than
    directly under the statement it was written on (#739).

    That looks like a cosmetic choice and is not. Moving a comment onto its own
    line destroys the association the source had: read back, `// note` on a line
    of its own belongs to whatever follows it. Printing it above the blank line
    therefore produced a file that parsed as something else, and formatting that
    file gave a third arrangement — so `nodus fmt` wrote files that
    `nodus fmt --check` immediately rejected, with no fixed point to converge on.

    Emitting it where it will be read makes the output a fixed point by
    construction: the second pass formats the same shape the first pass printed.
    The association is still lost, which is what `keep_trailing_comments` is for;
    this only stops the formatter from disagreeing with itself about it.
    """
    lines: list[str] = []
    prev_import = False
    prev_fn = False
    # The previous statement's demoted trailing comments, held back so they land
    # after this statement's blank line instead of before it.
    carried: list[str] = []

    for stmt in stmts:
        is_import = isinstance(stmt, Import)
        is_fn = isinstance(stmt, FnDef)
        produced = format_stmt(
            stmt, indent=0, keep_trailing_comments=keep_trailing_comments
        )
        own, demoted = _split_demoted_trailing(stmt, produced)
        if lines and _needs_blank_line(prev_import, prev_fn, is_import, is_fn):
            lines.append("")
        lines.extend(carried)
        lines.extend(own)
        carried = demoted
        prev_import = is_import
        prev_fn = is_fn

    if carried:
        # Nothing follows, so on re-parse these become standalone `Comment`
        # statements — neither an import nor a function — and they take whatever
        # blank line the rule gives such a statement.
        if lines and _needs_blank_line(prev_import, prev_fn, False, False):
            lines.append("")
        lines.extend(carried)

    return "\n".join(lines).rstrip() + "\n"


def format_named_map(node) -> str:
    """Print a `with { ... }` map with BARE identifier keys.

    These positions — step options, action payloads, goal budgets — are parsed by
    `parse_named_map_literal`, which requires identifier keys and rejects string
    ones. `format_expr` prints a `MapLit` with quoted keys, which is correct for a
    map literal and produces a file that no longer parses here:

        step a with { retries: 2 }   ->   step a with {"retries": 2}
        Syntax error: Expected identifier, got string literal ('retries')

    `nodus fmt` writes in place, so that turned a valid file into a broken one.
    Found by the #427 completeness sweep; no `.nd` file in this repo uses
    `with { }`, which is why the format gate never saw it.
    """
    if not isinstance(node, MapLit):
        return format_expr(node)
    parts = []
    for key, value in node.items:
        name = getattr(key, "v", None)
        if not isinstance(name, str) or not name.isidentifier():
            # Not representable as a bare key — fall back rather than emit
            # something that silently means a different thing.
            return format_expr(node)
        parts.append(f"{name}: {format_expr(value)}")
    return "{ " + ", ".join(parts) + " }" if parts else "{}"


def format_goal_predicate(node, *, parent: str | None = None) -> str:
    """Print a goal `until` predicate.

    Its own printer rather than `format_expr` because the predicate is a
    restricted grammar (`reached("literal")` with `&&`, `||`, `!`), not a general
    expression — the restriction is what makes the compile-time checkpoint check
    exact, so the formatter must not widen it by accident.
    """
    kind = type(node).__name__
    if kind == "Reached":
        return f'reached({format_expr(node.label)})'
    if kind == "PredicateNot":
        return f"!{format_goal_predicate(node.operand, parent='not')}"
    if kind in ("PredicateAnd", "PredicateOr"):
        op = "&&" if kind == "PredicateAnd" else "||"
        text = (
            f"{format_goal_predicate(node.left, parent=kind)} {op} "
            f"{format_goal_predicate(node.right, parent=kind)}"
        )
        # Parenthesise when nesting could change how it reads back.
        if parent is not None and parent != kind:
            return f"({text})"
        return text
    raise TypeError(f"Unknown goal predicate node: {node!r}")


def _body_comment_lines(stmt, prefix: str) -> list[str]:
    """Comments left above a flow body's closing brace (#743).

    A workflow or goal body is a loop over `step` and `state`, both typed
    lists, so a trailing comment cannot simply be appended as a `Comment`
    node the way `block()` does it -- `flow_def` reads `.name` off every
    entry. The parser parks them on the node instead.
    """
    return [
        f"{prefix}{text.rstrip()}"
        for text in (getattr(stmt, "_body_comments", None) or [])
    ]


def _reindent_embedded(lines: list[str], prefix: str) -> list[str]:
    """Split multi-line entries apart and give the continuation lines `prefix`.

    `format_expr` renders a multi-line closure body against column 0, because an
    expression is not told how deep it sits — its signature is
    `format_expr(expr, parent_prec)`, and threading an indent through some fifty
    recursive call sites so that two of them can read it is a poor trade. The
    statement *does* know its depth, so the shift happens once, here, on the way
    out (#742).

    It composes with nesting rather than having to know about it: every
    `format_stmt` fixes up whatever multi-line text it was handed, relative to
    its own indent, so a closure inside a closure inside a function comes out
    right without anyone counting levels.

    **Splitting matters as much as the indent.** A statement whose rendering
    spans lines used to arrive as *one* entry with newlines inside it, so
    anything measuring `len(lines)` — the single-line collapse in the `FnExpr`
    branch above all — read a four-line closure as one line and inlined it.
    """
    out: list[str] = []
    for line in lines:
        if "\n" not in line:
            out.append(line)
            continue
        head, *rest = line.split("\n")
        out.append(head)
        out.extend(prefix + tail if tail else tail for tail in rest)
    return out


def format_stmt(stmt, indent: int, keep_trailing_comments: bool = False) -> list[str]:
    """Render one statement, then answer the two questions every branch shares.

    **A statement's trailing comment is rendered here, once, and nowhere else**
    (#743). `_format_stmt` has thirty-four return points, and each used to decide
    for itself: nineteen called `attach_trailing`, which reads
    `keep_trailing_comments`, and fifteen called `trailing_lines` directly, which
    does not. Those fifteen are every block-bodied statement — `fn`, `workflow`,
    `if`, `while`, `for`, `try`, `goal`, `match` — so `nodus fmt --keep-trailing`,
    documented as *"preserve trailing comments in their original positions"*,
    silently did nothing for any of them. Two more returns rendered no trailing
    comment at all.

    Hoisting it is the fix rather than converting fifteen call sites, because a
    thirty-fifth branch would be written the same way as the fifteen. The
    branches no longer see `trailing` at all.

    Re-indenting first (#742) is deliberate: `attach_trailing` merges onto
    `lines[-1]` in keep mode, so the last entry has to already be a real line
    rather than a multi-line blob.
    """
    prefix = INDENT * indent
    lines = _reindent_embedded(
        _format_stmt(stmt, indent, keep_trailing_comments), prefix
    )
    return attach_trailing(
        lines, prefix, getattr(stmt, "_trailing_comments", None), keep_trailing_comments
    )


def _format_stmt(stmt, indent: int, keep_trailing_comments: bool = False) -> list[str]:
    prefix = INDENT * indent
    lines: list[str] = []

    comments = getattr(stmt, "_comments", None)
    if comments:
        for comment in comments:
            lines.append(f"{prefix}{comment.rstrip()}")

    # No `trailing` binding here on purpose (#743): a branch cannot render a
    # trailing comment if it cannot reach one. `format_stmt` does it once, after
    # this returns.

    # match is an expression, but when it is the whole of a statement we format
    # it multi-line with correct indentation (format_expr has no indent context).
    if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, Match):
        return lines + format_match(stmt.expr, indent)
    if isinstance(stmt, Return) and stmt.expr is not None and isinstance(stmt.expr, Match):
        return lines + format_match(stmt.expr, indent, "return ")
    if isinstance(stmt, Let) and isinstance(stmt.expr, Match):
        name = stmt.name if stmt.type_hint is None else f"{stmt.name}: {stmt.type_hint}"
        lead = f"export let {name} = " if stmt.exported else f"let {name} = "
        return lines + format_match(stmt.expr, indent, lead)

    if isinstance(stmt, Import):
        if stmt.names is not None:
            names = ", ".join(stmt.names)
            lines.append(f"{prefix}import {{ {names} }} from {format_string(stmt.path)}")
            return lines
        if stmt.alias is not None:
            lines.append(f"{prefix}import {format_string(stmt.path)} as {stmt.alias}")
            return lines
        lines.append(f"{prefix}import {format_string(stmt.path)}")
        return lines

    if isinstance(stmt, ExportFrom):
        names = ", ".join(stmt.names)
        lines.append(f"{prefix}export {{ {names} }} from {format_string(stmt.path)}")
        return lines

    if isinstance(stmt, ExportList):
        names = ", ".join(stmt.names)
        lines.append(f"{prefix}export {{ {names} }}")
        return lines

    if isinstance(stmt, Let):
        name = stmt.name if stmt.type_hint is None else f"{stmt.name}: {stmt.type_hint}"
        if stmt.exported:
            lines.append(f"{prefix}export let {name} = {format_expr(stmt.expr)}")
            return lines
        lines.append(f"{prefix}let {name} = {format_expr(stmt.expr)}")
        return lines

    if isinstance(stmt, Print):
        lines.append(f"{prefix}print({format_expr(stmt.expr)})")
        return lines

    if isinstance(stmt, ExprStmt):
        lines.append(f"{prefix}{format_expr(stmt.expr)}")
        return lines

    if isinstance(stmt, Return):
        if stmt.expr is None:
            lines.append(f"{prefix}return")
            return lines
        lines.append(f"{prefix}return {format_expr(stmt.expr)}")
        return lines

    if isinstance(stmt, ExternDecl):
        # #489: a declaration, so it has no body and prints on one line. The
        # parameter and return-type rendering is shared with FnDef below, so the
        # two cannot drift into printing a signature differently.
        param_text = ", ".join(format_param(param) for param in stmt.params)
        return_text = f" -> {stmt.return_type}" if stmt.return_type else ""
        header = f"{prefix}extern {stmt.name}({param_text}){return_text}"
        return lines + [header]

    if isinstance(stmt, FnDef):
        param_text = ", ".join(format_param(param) for param in stmt.params)
        return_text = f" -> {stmt.return_type}" if stmt.return_type else ""
        if stmt.exported:
            header = f"{prefix}export fn {stmt.name}({param_text}){return_text} {{"
        else:
            header = f"{prefix}fn {stmt.name}({param_text}){return_text} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, WorkflowDef):
        header = f"{prefix}workflow {stmt.name} {{"
        body_lines = []
        for state in stmt.states:
            body_lines.extend(format_stmt(state, indent + 1, keep_trailing_comments=keep_trailing_comments))
        for wf_step in stmt.steps:
            body_lines.extend(format_stmt(wf_step, indent + 1, keep_trailing_comments=keep_trailing_comments))
        # #743: a comment above the closing brace, which has no step to
        # attach to. Rendered inside the body, where it was written --
        # unclaimed it escaped the flow entirely on the next parse.
        body_lines.extend(_body_comment_lines(stmt, INDENT * (indent + 1)))
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, GoalDef):
        header = f"{prefix}goal {stmt.name} {{"
        body_lines = []
        for state in stmt.states:
            body_lines.extend(format_stmt(state, indent + 1, keep_trailing_comments=keep_trailing_comments))
        for goal_step in stmt.steps:
            body_lines.extend(format_stmt(goal_step, indent + 1, keep_trailing_comments=keep_trailing_comments))
        # #743: a comment above the closing brace, which has no step to
        # attach to. Rendered inside the body, where it was written --
        # unclaimed it escaped the flow entirely on the next parse.
        body_lines.extend(_body_comment_lines(stmt, INDENT * (indent + 1)))
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, GoalPursuit):
        header = f"{prefix}goal {stmt.name} over {stmt.workflow_name} {{"
        inner = "    " * (indent + 1)
        body_lines = [f"{inner}until {format_goal_predicate(stmt.until)}"]
        body_lines.append(f"{inner}budget {_format_goal_budget(stmt.budget)}")
        if stmt.retry_from is not None:
            body_lines.append(f"{inner}retry from {format_expr(stmt.retry_from)}")
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, WorkflowStateDecl):
        opts = ""
        if getattr(stmt, "options", None) is not None:
            opts = f" with {format_named_map(stmt.options)}"
        lines.append(f"{prefix}state {stmt.name} = {format_expr(stmt.value)}{opts}")
        return lines

    if isinstance(stmt, WorkflowStep):
        clauses, deps = _format_step_map_clause(stmt)
        guard = ""
        when = getattr(stmt, "when", None)
        if when is not None:
            guard = f" when {format_goal_predicate(when)}"
        options = ""
        if stmt.options is not None:
            options = f" with {format_named_map(stmt.options)}"
        header = f"{prefix}step {stmt.name}{clauses}{deps}{guard}{options} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, GoalStep):
        clauses, deps = _format_step_map_clause(stmt)
        guard = ""
        when = getattr(stmt, "when", None)
        if when is not None:
            guard = f" when {format_goal_predicate(when)}"
        options = ""
        if stmt.options is not None:
            options = f" with {format_named_map(stmt.options)}"
        header = f"{prefix}step {stmt.name}{clauses}{deps}{guard}{options} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, If):
        header = f"{prefix}if ({format_expr(stmt.cond)}) {{"
        then_lines = format_block(stmt.then_branch, indent + 1, keep_trailing_comments=keep_trailing_comments)
        out = [header] + then_lines + [f"{prefix}}}"]
        if stmt.else_branch is not None:
            else_lines = format_block(stmt.else_branch, indent + 1, keep_trailing_comments=keep_trailing_comments)
            out[-1] = f"{prefix}}} else {{"
            out += else_lines + [f"{prefix}}}"]
        return lines + out

    if isinstance(stmt, While):
        header = f"{prefix}while ({format_expr(stmt.cond)}) {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, For):
        init = format_for_part(stmt.init)
        cond = format_for_part(stmt.cond)
        inc = format_for_part(stmt.inc)
        header = f"{prefix}for ({init}; {cond}; {inc}) {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"]
    
    if isinstance(stmt, ForEach):
        header = f"{prefix}for {stmt.name} in {format_expr(stmt.iterable)} {{"
        body_lines = format_block(stmt.body, indent + 1, keep_trailing_comments=keep_trailing_comments)
        return lines + [header] + body_lines + [f"{prefix}}}"]

    if isinstance(stmt, Break):
        lines.append(f"{prefix}break")
        return lines

    if isinstance(stmt, Continue):
        lines.append(f"{prefix}continue")
        return lines

    if isinstance(stmt, Block):
        return lines + [f"{prefix}{{"] + format_block(stmt, indent + 1, keep_trailing_comments=keep_trailing_comments) + [f"{prefix}}}"]

    if isinstance(stmt, Comment):
        return lines + [f"{prefix}{stmt.text.rstrip()}"]

    if isinstance(stmt, CheckpointStmt):
        lines.append(f"{prefix}checkpoint {format_expr(stmt.label)}")
        return lines

    if isinstance(stmt, Yield):
        if stmt.expr is None:
            lines.append(f"{prefix}yield")
            return lines
        lines.append(f"{prefix}yield {format_expr(stmt.expr)}")
        return lines

    if isinstance(stmt, Throw):
        lines.append(f"{prefix}throw {format_expr(stmt.expr)}")
        return lines

    if isinstance(stmt, TryCatch):
        try_header = f"{prefix}try {{"
        try_lines = format_block(stmt.try_block, indent + 1, keep_trailing_comments=keep_trailing_comments)
        # #415: a catch-less try/finally renders exactly as written -- the
        # rethrowing catch is a compiler lowering, not source.
        middle: list[str] = []
        if stmt.catch_block is not None:
            middle.append(f"{prefix}}} catch {stmt.catch_var} {{")
            middle.extend(format_block(stmt.catch_block, indent + 1, keep_trailing_comments=keep_trailing_comments))
        if stmt.finally_block is not None:
            middle.append(f"{prefix}}} finally {{")
            middle.extend(format_block(stmt.finally_block, indent + 1, keep_trailing_comments=keep_trailing_comments))
        out = [try_header] + try_lines + middle + [f"{prefix}}}"]
        return lines + out

    if isinstance(stmt, DestructureLet):
        pat = format_pattern(stmt.pattern)
        lines.append(f"{prefix}let {pat} = {format_expr(stmt.expr)}")
        return lines

    raise TypeError(f"Unknown stmt node: {stmt!r}")


def _format_goal_budget(budget) -> str:
    """Render `budget { ... }`, printing only the bounds that are declared (#657).

    `max_iterations` and `deadline_ms` were both mandatory until #488, and this
    printed both unconditionally. Since they became individually optional, a goal
    declaring one of them crashed `fmt` with `Unknown expr node: None`, and
    `limits` — the third bound #488 added — was never rendered at all, so
    formatting silently erased a spend bound.
    """
    parts = []
    if getattr(budget, "max_iterations", None) is not None:
        parts.append(f"max_iterations: {format_expr(budget.max_iterations)}")
    if getattr(budget, "deadline_ms", None) is not None:
        parts.append(f"deadline_ms: {format_expr(budget.deadline_ms)}")
    limits = getattr(budget, "limits", None)
    if limits is not None:
        parts.append(f"limits: {format_named_map(limits)}")
    return "{ " + ", ".join(parts) + " }"


def _format_step_map_clause(stmt) -> tuple[str, str]:
    """Render a step's header clauses and its `after` list (#656, #577).

    Returns `(clauses, deps)`, both already prefixed with a space or empty.

    The parser records some dependencies through a *clause* rather than through
    `after` — `each VAR in SRC` adds `SRC` (#480), and `compensates DEP` adds
    `DEP` (#577) — so that the dependency cannot disagree with the clause. A
    naive render of `deps` therefore printed those as a plain `after` and dropped
    the clause: a file that still parsed and silently did something else, which
    is #656. Each such dependency is removed from the `after` list here, because
    the clause is what expresses it.

    Shared by `WorkflowStep` and `GoalStep`, which had the same omission twice.
    """
    clauses = []
    deps = list(stmt.deps or [])

    compensates = getattr(stmt, "compensates", None)
    if compensates is not None:
        clauses.append(f"compensates {compensates}")
        deps = [dep for dep in deps if dep != compensates]

    each_var = getattr(stmt, "each_var", None)
    each_source = getattr(stmt, "each_source", None)
    if each_var is not None and each_source is not None:
        clauses.append(f"each {each_var} in {each_source}")
        deps = [dep for dep in deps if dep != each_source]

    rendered = (" " + " ".join(clauses)) if clauses else ""
    return rendered, (" after " + ", ".join(deps)) if deps else ""


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
    if isinstance(expr, Int):
        raw = expr.raw if expr.raw is not None else str(expr.v) + "i"
        return raw
    if isinstance(expr, Num):
        return format_number(expr)
    if isinstance(expr, ActionStmt):
        text = f"action {expr.kind}"
        if expr.target is not None:
            text += f" {format_string(expr.target)}"
        if expr.kind in {"tool", "agent", "emit"}:
            text += f" with {format_named_map(expr.payload if expr.payload is not None else MapLit([]))}"
            return text
        if expr.kind == "memory_put":
            text += f" {format_expr(expr.payload)}"
            return text
        return text
    if isinstance(expr, Bool):
        return "true" if expr.v else "false"
    if isinstance(expr, Match):
        # Fallback for match in a nested/inline expression position; statement
        # positions get their indentation from `format_stmt`'s own Match branch.
        #
        # Rendered against column 0 like every other multi-line expression, and
        # shifted to its real depth on the way out of `format_stmt` (#742). This
        # used to note that the closing brace landed at column 0 "same limitation
        # as inline fn expressions" — that limitation is gone for both, and the
        # same one change fixed them, because neither ever needed to know its own
        # depth.
        return "\n".join(format_match(expr, 0))
    if isinstance(expr, Str):
        return format_string(expr.v)
    if isinstance(expr, InterpolatedString):
        parts_str = ""
        for part in expr.parts:
            if isinstance(part, StringLiteralPart):
                # Re-escape the literal text for display (without surrounding quotes)
                parts_str += escape_string_body(part.text)
            elif isinstance(part, InterpolationPart):
                parts_str += f"\\({format_expr(part.expression)})"
        return f'"{parts_str}"'
    if isinstance(expr, Nil):
        return "nil"
    if isinstance(expr, Var):
        return expr.name
    if isinstance(expr, Assign):
        text = f"{expr.name} = {format_expr(expr.expr, 1)}"
        return maybe_paren(text, 1, parent_prec)
    if isinstance(expr, CompoundAssign):
        text = f"{expr.name} {expr.op}= {format_expr(expr.expr, 1)}"
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
        # #737: a body that is *only* a comment must not collapse. `// x` would
        # swallow the closing brace and the file would no longer parse. A
        # statement carrying `_comments` is already safe, because `format_stmt`
        # emits the comment as its own line and the length check below fails.
        if len(expr.body.stmts) == 1 and not isinstance(expr.body.stmts[0], Comment):
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


# Named re-escapes: the inverse of lexer.ESCAPE_MAP for characters that have a
# short escape form. Any other control / non-printable code point falls back to
# \xHH or \uXXXX below so that a formatted file re-parses to the same value.
_STRING_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
    "\0": "\\0",
}


def escape_string_body(value: str) -> str:
    """Re-escape a decoded string value back into Nodus source form.

    Inverse of ``lexer.decode_string_literal``: every character the lexer would
    treat specially (backslash, quote) or that is a non-printable control code
    point is emitted as an escape sequence, so the formatted output round-trips
    to the same runtime string. Named escapes (``\\n \\t \\r \\0 \\\\ \\"``) are
    preferred; any other non-printable char falls back to ``\\xHH`` (<= U+00FF)
    or ``\\uXXXX`` (<= U+FFFF). Printable characters — including non-ASCII — are
    passed through unchanged.
    """
    out = []
    for ch in value:
        named = _STRING_ESCAPES.get(ch)
        if named is not None:
            out.append(named)
            continue
        if ch.isprintable():
            out.append(ch)
            continue
        code = ord(ch)
        if code <= 0xFF:
            out.append(f"\\x{code:02X}")
        elif code <= 0xFFFF:
            out.append(f"\\u{code:04X}")
        else:
            # Astral non-printable (rare): no fixed-width escape form exists in
            # the lexer's grammar (\x is 2 digits, \u is 4). Emit raw.
            out.append(ch)
    return "".join(out)


def format_match(expr, indent: int, lead: str = "") -> list[str]:
    """Format a match expression as indented lines. `lead` is prepended to the
    `match` keyword on the opening line (e.g. "let x = " or "return ")."""
    prefix = INDENT * indent
    arm_prefix = INDENT * (indent + 1)
    out = [f"{prefix}{lead}match {format_expr(expr.scrutinee)} {{"]
    for arm in expr.arms:
        pat = "_" if arm.pattern is None else format_expr(arm.pattern)
        body = arm.body
        if isinstance(body, Block):
            out.append(f"{arm_prefix}{pat} => {{")
            out.extend(format_block(body, indent + 2))
            out.append(f"{arm_prefix}}},")
        elif isinstance(body, Throw):
            out.append(f"{arm_prefix}{pat} => throw {format_expr(body.expr)},")
        elif isinstance(body, Return):
            if body.expr is None:
                out.append(f"{arm_prefix}{pat} => return,")
            else:
                out.append(f"{arm_prefix}{pat} => return {format_expr(body.expr)},")
        else:
            out.append(f"{arm_prefix}{pat} => {format_expr(body)},")
    out.append(f"{prefix}}}")
    return out


def format_string(value: str) -> str:
    return f'"{escape_string_body(value)}"'
