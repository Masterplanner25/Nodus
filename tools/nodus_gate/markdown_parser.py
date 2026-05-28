"""Markdown code-block extractor for nodus_gate.

Extracts fenced code blocks with their type annotation and source location.
Supports four fence types:
  - ``nodus``                — run, verify no error
  - ``nodus-no-run``         — static symbol extraction only, no execution
  - ``nodus-expect=output``  — run, verify output against next plain block
  - ``nodus-skip``           — ignored by all phases
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_FENCE_OPEN = re.compile(r"^```(\S*)(?:\s+(.*))?$")
_FENCE_CLOSE = re.compile(r"^```\s*$")


@dataclass
class CodeBlock:
    fence_type: str          # e.g. "nodus", "nodus-no-run", "nodus-expect=output"
    source: str              # the code content (no surrounding ```)
    file_path: str           # absolute path to the source markdown file
    start_line: int          # 1-based line number of the opening fence
    options: str             # anything after the fence type on the opening line
    # For nodus-expect=output: the expected output block (set during extraction)
    expected_output: str | None = None

    @property
    def should_run(self) -> bool:
        return self.fence_type in ("nodus", "nodus-expect=output")

    @property
    def expect_output(self) -> bool:
        return self.fence_type == "nodus-expect=output"

    @property
    def is_static_only(self) -> bool:
        """True for nodus-no-run: static symbol extraction applies but no run."""
        return self.fence_type == "nodus-no-run"

    @property
    def is_skip(self) -> bool:
        return self.fence_type == "nodus-skip"

    @property
    def timeout_ms(self) -> int:
        """Return per-block timeout in ms, or default 10000."""
        opts = self.options or ""
        m = re.search(r"timeout=(\d+)(s|ms)?", opts)
        if not m:
            return 10_000
        value = int(m.group(1))
        unit = m.group(2) or "ms"
        return value * 1000 if unit == "s" else value


def extract_blocks(path: str | Path) -> list[CodeBlock]:
    """Extract all Nodus code blocks from a markdown file."""
    path = str(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []

    blocks: list[CodeBlock] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        m = _FENCE_OPEN.match(line)
        if m:
            fence_type = m.group(1)
            options = (m.group(2) or "").strip()
            start = i + 1  # 1-based
            body_lines: list[str] = []
            i += 1
            while i < len(lines):
                inner = lines[i].rstrip("\n")
                if _FENCE_CLOSE.match(inner):
                    break
                body_lines.append(lines[i])
                i += 1
            block = CodeBlock(
                fence_type=fence_type,
                source="".join(body_lines),
                file_path=path,
                start_line=start,
                options=options,
            )
            blocks.append(block)
        i += 1

    # Second pass: pair nodus-expect=output blocks with their expected output
    for idx, block in enumerate(blocks):
        if not block.expect_output:
            continue
        # Look for the next plain (no nodus* type) code block as the output companion
        for j in range(idx + 1, len(blocks)):
            nxt = blocks[j]
            if nxt.fence_type.startswith("nodus"):
                break  # another nodus block before an output block
            # Plain block (fence_type doesn't start with "nodus")
            block.expected_output = nxt.source
            break

    # Remove non-nodus blocks (plain output companions etc.) from the returned list
    return [b for b in blocks if b.fence_type.startswith("nodus")]


def collect_doc_files(
    root: str | Path,
    *,
    include_design: bool = False,
) -> list[str]:
    """Return sorted list of markdown files to scan."""
    root = Path(root)
    patterns = [
        "docs/language/*.md",
        "docs/guide/*.md",
        "docs/policy/*.md",
        "docs/runtime/*.md",
        "llms.txt",
        "README.md",
    ]
    if include_design:
        patterns.append("docs/design/**/*.md")

    files: set[str] = set()
    for pattern in patterns:
        for p in root.glob(pattern):
            if p.is_file():
                files.add(str(p))

    # Also try docs/language/ top-level files directly
    lang = root / "docs" / "language"
    if lang.is_dir():
        for p in lang.glob("*.md"):
            files.add(str(p))

    return sorted(files)
