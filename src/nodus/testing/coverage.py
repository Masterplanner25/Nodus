"""Coverage collection for the Nodus test runner (Design Doc 08)."""

from __future__ import annotations

import json
import os
import string
import time
from collections import defaultdict


class CoverageCollector:
    """Subscribes to VM line-execution events and aggregates hit counts."""

    def __init__(self) -> None:
        # path -> line_number -> hit_count
        self.hits: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._start_ms = time.monotonic() * 1000

    def emit(self, event) -> None:
        """Called by the RuntimeEventBus for each event."""
        if event.type == "line_executed" and event.data:
            path = event.data.get("path")
            line = event.data.get("line")
            if path and line:
                self.hits[path][line] += 1

    def attach(self, vm) -> None:
        """Subscribe to a VM's event bus."""
        vm.event_bus._sinks.append(self)

    def detach(self, vm) -> None:
        """Unsubscribe from a VM's event bus."""
        try:
            vm.event_bus._sinks.remove(self)
        except ValueError:
            pass

    def build_report(
        self,
        executable_lines: dict[str, list[int]] | None = None,
        exclude_patterns: list[str] | None = None,
        include_patterns: list[str] | None = None,
        test_command: str = "nodus test",
    ) -> dict:
        """Build the coverage data structure from collected hits."""
        import fnmatch

        files: dict[str, dict] = {}
        for path, line_hits in self.hits.items():
            # Apply exclusions
            if exclude_patterns:
                norm = path.replace("\\", "/")
                if any(fnmatch.fnmatch(norm, p) for p in exclude_patterns):
                    continue
            if include_patterns:
                norm = path.replace("\\", "/")
                if not any(fnmatch.fnmatch(norm, p) for p in include_patterns):
                    continue
            # Skip test files
            if path.endswith("_test.nd"):
                continue

            exe = set(executable_lines.get(path, [])) if executable_lines else set(line_hits.keys())
            covered = {k: v for k, v in line_hits.items() if k in exe}
            uncovered = sorted(exe - set(covered.keys()))
            total = len(exe)
            pct = (len(covered) / total * 100) if total else 0.0
            files[path] = {
                "executable_lines": sorted(exe),
                "covered_lines": covered,
                "uncovered_lines": uncovered,
                "coverage_pct": round(pct, 2),
            }

        total_exe = sum(len(f["executable_lines"]) for f in files.values())
        total_cov = sum(len(f["covered_lines"]) for f in files.values())
        overall_pct = (total_cov / total_exe * 100) if total_exe else 0.0

        return {
            "files": files,
            "summary": {
                "total_files": len(files),
                "total_executable_lines": total_exe,
                "total_covered_lines": total_cov,
                "overall_coverage_pct": round(overall_pct, 2),
            },
            "timestamp": _iso_now(),
            "test_command": test_command,
        }

    def write_reports(
        self, data: dict, output_dir: str = "./coverage",
        formats: list[str] | None = None,
    ) -> None:
        """Write coverage.json and coverage.html to output_dir."""
        formats = formats or ["json", "html"]
        os.makedirs(output_dir, exist_ok=True)

        if "json" in formats:
            json_path = os.path.join(output_dir, "coverage.json")
            # Convert int keys to str for JSON
            serializable = _make_serializable(data)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)

        if "html" in formats:
            html_path = os.path.join(output_dir, "coverage.html")
            html = _render_html(data)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

    def format_summary(self, data: dict) -> str:
        """Return a human-readable coverage summary string."""
        lines = ["\nCoverage Summary:"]
        files = data.get("files", {})
        for path, info in sorted(files.items()):
            pct = info["coverage_pct"]
            cov = len(info["covered_lines"])
            exe = len(info["executable_lines"])
            bar = f"{pct:5.1f}% ({cov}/{exe} lines)"
            short = os.path.basename(path)
            lines.append(f"  {short:<40} {bar}")
        s = data.get("summary", {})
        lines.append("  " + "─" * 50)
        lines.append(
            f"  {'Overall':<40} {s.get('overall_coverage_pct', 0):5.1f}%"
            f" ({s.get('total_covered_lines', 0)}/{s.get('total_executable_lines', 0)} lines)"
        )
        # Uncovered lines
        uncovered_files = {p: i for p, i in files.items() if i["uncovered_lines"]}
        if uncovered_files:
            lines.append("\nUncovered lines:")
            for path, info in sorted(uncovered_files.items()):
                short = os.path.basename(path)
                nums = ", ".join(str(n) for n in info["uncovered_lines"][:20])
                if len(info["uncovered_lines"]) > 20:
                    nums += f" ... (+{len(info['uncovered_lines']) - 20} more)"
                lines.append(f"  {short}: {nums}")
        return "\n".join(lines) + "\n"


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_serializable(obj):
    if isinstance(obj, dict):
        return {str(k): _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    return obj


_HTML_TEMPLATE = string.Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Nodus Coverage Report</title>
<style>
body { font-family: monospace; margin: 20px; background: #1e1e1e; color: #d4d4d4; }
h1 { color: #e8e8e8; }
.summary { margin-bottom: 20px; }
.file-section { margin-bottom: 30px; }
.file-name { font-size: 1.1em; font-weight: bold; color: #9cdcfe; margin-bottom: 5px; }
.progress { background: #333; height: 12px; border-radius: 4px; margin-bottom: 8px; }
.progress-bar { background: #4ec94e; height: 12px; border-radius: 4px; }
.source { background: #252526; padding: 10px; border-radius: 4px; }
.line { display: flex; }
.line-num { color: #6a9955; width: 40px; text-align: right; margin-right: 10px; user-select: none; }
.covered { background: #1a3a1a; }
.uncovered { background: #3a1a1a; }
.skipped { }
</style>
</head>
<body>
<h1>Coverage Report</h1>
<p class="summary">Generated: $timestamp | Overall: $overall_pct% ($total_cov/$total_exe lines)</p>
$file_sections
</body>
</html>""")


def _render_html(data: dict) -> str:
    files = data.get("files", {})
    summary = data.get("summary", {})
    file_sections = []
    for path, info in sorted(files.items()):
        pct = info["coverage_pct"]
        covered_set = set(info["covered_lines"].keys())
        uncovered_set = set(info["uncovered_lines"])

        source_lines = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for i, raw_line in enumerate(f, 1):
                    css = ""
                    if i in covered_set:
                        css = "covered"
                    elif i in uncovered_set:
                        css = "uncovered"
                    content = raw_line.rstrip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    source_lines.append(
                        f'<div class="line {css}"><span class="line-num">{i}</span><span>{content}</span></div>'
                    )
        except OSError:
            source_lines = [f"<div>(source not available: {path})</div>"]

        section = (
            f'<div class="file-section">'
            f'<div class="file-name">{path} — {pct:.1f}%</div>'
            f'<div class="progress"><div class="progress-bar" style="width:{pct:.1f}%"></div></div>'
            f'<div class="source">' + "".join(source_lines) + "</div></div>"
        )
        file_sections.append(section)

    return _HTML_TEMPLATE.substitute(
        timestamp=_iso_now(),
        overall_pct=f"{summary.get('overall_coverage_pct', 0):.1f}",
        total_cov=summary.get("total_covered_lines", 0),
        total_exe=summary.get("total_executable_lines", 0),
        file_sections="\n".join(file_sections),
    )
