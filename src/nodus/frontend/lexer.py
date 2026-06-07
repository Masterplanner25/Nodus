"""Tokenization and keyword handling for Nodus."""

import re
from dataclasses import dataclass

from nodus.runtime.diagnostics import LangSyntaxError


@dataclass
class Tok:
    kind: str
    val: str
    line: int
    col: int


TOKEN_RE = re.compile(
    r"""
    (?P<WS>[ \t]+)
  | (?P<COMMENT1>\#.*)
  | (?P<COMMENT2>//.*)
  | (?P<NL>\n+)
  | (?P<NUM_INT_BAD>\d+I)
  | (?P<NUM_INT_DOUBLE>\d+i[A-Za-z_][A-Za-z0-9_]*)
  | (?P<NUM_INT>\d+i)
  | (?P<NUM>\d+(\.\d+)?([eE][+-]?\d+)?)
  | (?P<ID>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<OP>&&|\|\||==|!=|<=|>=|->|[+\-*/=%(){}\[\],;:.<>!@])
    """,
    re.VERBOSE,
)

_MAX_INTERP_DEPTH = 32

KEYWORDS = {
    "let",
    "print",
    "if",
    "else",
    "while",
    "for",
    "true",
    "false",
    "fn",
    "return",
    "nil",
    "import",
    "as",
    "export",
    "from",
    "try",
    "catch",
    "finally",
    "throw",
    "record",
    "in",
    "yield",
    "workflow",
    "goal",
    "step",
    "after",
    "with",
    "action",
}

# Simple single-character escape sequences.
# \x and \u are handled separately in decode_string_literal because they
# consume additional hex-digit characters from the source text.
ESCAPE_MAP = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    '"': '"',
    "\\": "\\",
}


def decode_string_literal(
    token_text: str,
    *,
    line: int | None = None,
    col: int | None = None,
) -> str:
    """Decode a quoted string token into its runtime string value.

    Raises LangSyntaxError (with source location when provided) for any
    malformed escape sequence so that callers do not need a try/except.

    Supported escape sequences:
        \\\\  backslash
        \\"   double quote
        \\n   newline (U+000A)
        \\t   horizontal tab (U+0009)
        \\r   carriage return (U+000D)
        \\0   null byte (U+0000)
        \\xHH two-digit hex byte  (e.g. \\x41 -> 'A')
        \\uXXXX four-digit Unicode code point (e.g. \\u03B1 -> 'α')
    """
    s = token_text[1:-1]
    out = []
    i = 0

    while i < len(s):
        ch = s[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue

        i += 1
        if i >= len(s):
            raise LangSyntaxError(
                "Unterminated escape sequence in string literal",
                line=line,
                col=col,
            )

        esc = s[i]

        # \xHH — two-digit hex byte
        if esc == "x":
            hex_digits = s[i + 1 : i + 3]
            if len(hex_digits) < 2:
                raise LangSyntaxError(
                    r"Incomplete \x escape: expected 2 hex digits",
                    line=line,
                    col=col,
                )
            try:
                out.append(chr(int(hex_digits, 16)))
            except ValueError:
                raise LangSyntaxError(
                    rf"Invalid \x escape: \x{hex_digits}",
                    line=line,
                    col=col,
                )
            i += 3
            continue

        # \uXXXX — four-digit Unicode code point
        if esc == "u":
            hex_digits = s[i + 1 : i + 5]
            if len(hex_digits) < 4:
                raise LangSyntaxError(
                    r"Incomplete \u escape: expected 4 hex digits",
                    line=line,
                    col=col,
                )
            try:
                out.append(chr(int(hex_digits, 16)))
            except ValueError:
                raise LangSyntaxError(
                    rf"Invalid \u escape: \u{hex_digits}",
                    line=line,
                    col=col,
                )
            i += 5
            continue

        if esc not in ESCAPE_MAP:
            raise LangSyntaxError(
                f"Unsupported escape sequence: \\{esc}",
                line=line,
                col=col,
            )

        out.append(ESCAPE_MAP[esc])
        i += 1

    return "".join(out)


def _lex_string(src: str, pos: int, start_line: int, start_col: int, depth: int = 0):
    """Tokenize a string literal starting at src[pos] (which is `"`).

    Returns (tokens, new_pos, new_line, new_col).

    For plain strings (no interpolation): [Tok("STR", decoded_value, ...)].
    For interpolated strings: [STRING_START, STRING_LITERAL*, (INTERP_START expr-tokens INTERP_END)*, STRING_LITERAL?, STRING_END].
    """
    if depth > _MAX_INTERP_DEPTH:
        raise LangSyntaxError(
            f"Nesting depth exceeded ({_MAX_INTERP_DEPTH})",
            line=start_line,
            col=start_col,
        )

    line = start_line
    col = start_col
    pos += 1  # skip opening `"`
    col += 1

    literal_buf: list[str] = []
    local_tokens: list[Tok] = []
    has_interpolation = False

    def _flush_literal(emit_line: int, emit_col: int) -> None:
        if literal_buf:
            local_tokens.append(Tok("STRING_LITERAL", "".join(literal_buf), emit_line, emit_col))
            literal_buf.clear()

    while pos < len(src):
        ch = src[pos]

        if ch == '"':
            pos += 1
            col += 1
            if not has_interpolation:
                val = "".join(literal_buf)
                return [Tok("STR", val, start_line, start_col)], pos, line, col
            _flush_literal(line, col)
            result = (
                [Tok("STRING_START", '"', start_line, start_col)]
                + local_tokens
                + [Tok("STRING_END", '"', line, col)]
            )
            return result, pos, line, col

        if ch == '\\' and pos + 1 < len(src):
            next_ch = src[pos + 1]
            if next_ch == '(':
                # String interpolation: \( triggers expression mode
                interp_line, interp_col = line, col
                if not has_interpolation:
                    has_interpolation = True
                _flush_literal(line, col)
                local_tokens.append(Tok("INTERP_START", r"\(", interp_line, interp_col))
                pos += 2
                col += 2
                pos, line, col, expr_toks = _lex_interp(
                    src, pos, line, col, interp_line, interp_col, depth
                )
                local_tokens.extend(expr_toks)
                continue
            # Standard escape sequences (decoded inline into literal_buf)
            if next_ch == 'n':
                literal_buf.append('\n')
                pos += 2
                col += 2
            elif next_ch == 't':
                literal_buf.append('\t')
                pos += 2
                col += 2
            elif next_ch == 'r':
                literal_buf.append('\r')
                pos += 2
                col += 2
            elif next_ch == '0':
                literal_buf.append('\0')
                pos += 2
                col += 2
            elif next_ch == '"':
                literal_buf.append('"')
                pos += 2
                col += 2
            elif next_ch == '\\':
                literal_buf.append('\\')
                pos += 2
                col += 2
            elif next_ch == 'x':
                hex_digits = src[pos + 2 : pos + 4]
                if len(hex_digits) < 2:
                    raise LangSyntaxError(
                        r"Incomplete \x escape: expected 2 hex digits", line=line, col=col
                    )
                try:
                    literal_buf.append(chr(int(hex_digits, 16)))
                except ValueError:
                    raise LangSyntaxError(
                        rf"Invalid \x escape: \x{hex_digits}", line=line, col=col
                    )
                pos += 4
                col += 4
            elif next_ch == 'u':
                hex_digits = src[pos + 2 : pos + 6]
                if len(hex_digits) < 4:
                    raise LangSyntaxError(
                        r"Incomplete \u escape: expected 4 hex digits", line=line, col=col
                    )
                try:
                    literal_buf.append(chr(int(hex_digits, 16)))
                except ValueError:
                    raise LangSyntaxError(
                        rf"Invalid \u escape: \u{hex_digits}", line=line, col=col
                    )
                pos += 6
                col += 6
            else:
                raise LangSyntaxError(
                    f"Unsupported escape sequence: \\{next_ch}", line=line, col=col
                )
            continue

        if ch == '\n':
            raise LangSyntaxError(
                "Unterminated string literal", line=start_line, col=start_col
            )

        literal_buf.append(ch)
        pos += 1
        col += 1

    raise LangSyntaxError("Unterminated string literal", line=start_line, col=start_col)


def _lex_interp(
    src: str, pos: int, line: int, col: int, interp_line: int, interp_col: int, depth: int
):
    """Tokenize expression tokens inside \\(...) until matching ')' at depth 0.

    Returns (new_pos, new_line, new_col, expr_tokens).
    expr_tokens ends with the INTERP_END token.
    """
    tokens: list[Tok] = []
    paren_depth = 0

    while pos < len(src):
        ch = src[pos]

        if ch == '"':
            nested, pos, line, col = _lex_string(src, pos, line, col, depth + 1)
            tokens.extend(nested)
            continue

        if ch == ')':
            if paren_depth == 0:
                tokens.append(Tok("INTERP_END", ")", line, col))
                pos += 1
                col += 1
                return pos, line, col, tokens
            paren_depth -= 1
            tokens.append(Tok(")", ")", line, col))
            pos += 1
            col += 1
            continue

        if ch == '(':
            paren_depth += 1
            tokens.append(Tok("(", "(", line, col))
            pos += 1
            col += 1
            continue

        if ch == ':' and paren_depth == 0:
            raise LangSyntaxError(
                "Format specifiers are reserved for a future version; "
                "remove ':' from the top-level interpolation expression",
                line=line, col=col,
            )

        if ch in (' ', '\t'):
            pos += 1
            col += 1
            continue

        if ch == '\n':
            tokens.append(Tok("SEP", "\n", line, col))
            line += 1
            col = 1
            pos += 1
            continue

        m = TOKEN_RE.match(src, pos)
        if not m:
            raise LangSyntaxError(
                f"Unexpected character {ch!r} in interpolation", line=line, col=col
            )

        kind = m.lastgroup
        text = m.group(kind or 0)
        tok_line, tok_col = line, col

        if kind == "WS":
            col += len(text)
            pos = m.end()
            continue
        if kind in ("COMMENT1", "COMMENT2"):
            tokens.append(Tok("COMMENT", text, tok_line, tok_col))
            col += len(text)
            pos = m.end()
            continue
        if kind == "NL":
            for _ in text:
                tokens.append(Tok("SEP", "\n", line, col))
                line += 1
                col = 1
            pos = m.end()
            continue
        if kind == "NUM_INT_BAD":
            raise LangSyntaxError(
                f"Integer suffix must be lowercase 'i', not 'I': use {text[:-1]}i instead of {text}",
                line=tok_line, col=tok_col,
            )
        if kind == "NUM_INT_DOUBLE":
            digits = ""
            for ch2 in text:
                if ch2.isdigit():
                    digits += ch2
                else:
                    break
            raise LangSyntaxError(
                f"Invalid integer literal {text!r}: did you mean {digits}i?",
                line=tok_line, col=tok_col,
            )
        if kind == "NUM_INT":
            tokens.append(Tok("NUM_INT", text[:-1], tok_line, tok_col))
            col += len(text)
            pos = m.end()
            continue
        if kind == "NUM":
            tokens.append(Tok("NUM", text, tok_line, tok_col))
            col += len(text)
            pos = m.end()
            continue
        if kind == "ID":
            kw = text.upper() if text in KEYWORDS else None
            tokens.append(Tok(kw or "ID", text, tok_line, tok_col))
            col += len(text)
            pos = m.end()
            continue
        if kind == "OP":
            if text == ";":
                tokens.append(Tok("SEP", text, tok_line, tok_col))
            else:
                tokens.append(Tok(text, text, tok_line, tok_col))
            col += len(text)
            pos = m.end()
            continue

        raise LangSyntaxError(
            f"Unexpected token {text!r} in interpolation", line=tok_line, col=tok_col
        )

    raise LangSyntaxError(
        "Unclosed interpolation expression", line=interp_line, col=interp_col
    )


def tokenize(src: str) -> list[Tok]:
    if src.startswith("\ufeff"):
        src = src[1:]
    src = src.replace("\r\n", "\n").replace("\r", "\n")

    pos = 0
    line = 1
    col = 1
    out: list[Tok] = []
    # When _open_depth > 0 we are inside unclosed (, [ or { \u2014 newlines are
    # whitespace, not statement separators (same rule as Python/JS/Go).
    _open_depth = 0

    while pos < len(src):
        start_line = line
        start_col = col

        # String literals (plain and interpolated) are handled character-by-character.
        if src[pos] == '"':
            new_tokens, pos, line, col = _lex_string(src, pos, start_line, start_col)
            out.extend(new_tokens)
            continue

        m = TOKEN_RE.match(src, pos)
        if not m:
            ch = src[pos]
            if ch.isalpha() and ord(ch) > 127:
                raise LangSyntaxError(
                    f"Identifiers must use ASCII letters only: {ch!r}",
                    line=start_line,
                    col=start_col,
                )
            raise LangSyntaxError(f"Unexpected character {ch!r}", line=start_line, col=start_col)

        kind = m.lastgroup
        text = m.group(kind or 0)
        pos = m.end()

        if kind in {"WS"}:
            col += len(text)
            continue
        if kind in {"COMMENT1", "COMMENT2"}:
            out.append(Tok("COMMENT", text, start_line, start_col))
            col += len(text)
            continue
        if kind == "NL":
            if _open_depth == 0:
                out.append(Tok("SEP", "\n", start_line, start_col))
            line += len(text)
            col = 1
            continue
        if kind == "NUM_INT_BAD":
            raise LangSyntaxError(
                f"Integer suffix must be lowercase 'i', not 'I': use {text[:-1]}i instead of {text}",
                line=start_line,
                col=start_col,
            )
        if kind == "NUM_INT_DOUBLE":
            digits = ""
            for ch2 in text:
                if ch2.isdigit():
                    digits += ch2
                else:
                    break
            raise LangSyntaxError(
                f"Invalid integer literal {text!r}: did you mean {digits}i?",
                line=start_line,
                col=start_col,
            )
        if kind == "NUM_INT":
            # Strip the trailing 'i' suffix; store the digit part only.
            out.append(Tok("NUM_INT", text[:-1], start_line, start_col))
            col += len(text)
            continue
        if kind == "NUM":
            out.append(Tok("NUM", text, start_line, start_col))
            col += len(text)
            continue
        if kind == "ID":
            if text in KEYWORDS:
                out.append(Tok(text.upper(), text, start_line, start_col))
            else:
                out.append(Tok("ID", text, start_line, start_col))
            col += len(text)
            continue
        if kind == "OP":
            if text == ";":
                out.append(Tok("SEP", text, start_line, start_col))
            else:
                out.append(Tok(text, text, start_line, start_col))
                if text in ("(", "[", "{"):
                    _open_depth += 1
                elif text in (")", "]", "}"):
                    _open_depth = max(0, _open_depth - 1)
            col += len(text)

    out.append(Tok("EOF", "", line, col))
    return out
