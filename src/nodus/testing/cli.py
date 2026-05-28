"""CLI handler for 'nodus test [path] [flags]'."""

from __future__ import annotations

import os
import sys

from nodus.testing.discovery import discover_test_files, matches_filter
from nodus.testing.runner import TestResult, TestRunner
from nodus.testing.formatter import format_text, format_json, format_junit, _is_tty


def run_test_command(cmd_args: list[str]) -> int:
    """Entry point for 'nodus test [path] [flags]'. Returns exit code."""
    # Parse flags
    flags_with_values = {
        "--filter", "--parallel", "--format", "--seed",
        "--coverage-output", "--coverage-exclude", "--coverage-include",
        "--coverage-min", "--coverage-format",
    }
    flags_no_values = {
        "--watch", "--coverage", "--coverage-per-test",
        "--bail", "--verbose", "--quiet",
    }
    positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)

    test_path = positional[0] if positional else "tests"
    filter_pattern = flags.get("--filter", "")
    output_format = flags.get("--format", "auto")
    bail = "--bail" in flags
    verbose = "--verbose" in flags
    quiet = "--quiet" in flags
    do_coverage = "--coverage" in flags
    coverage_output = flags.get("--coverage-output", "./coverage")
    coverage_min = float(flags.get("--coverage-min", 0))
    coverage_formats_str = flags.get("--coverage-format", "json,html")
    coverage_formats = [f.strip() for f in coverage_formats_str.split(",")]
    coverage_exclude = flags.get("--coverage-exclude", "")
    coverage_include = flags.get("--coverage-include", "")

    # Discover test files
    test_files = discover_test_files(test_path)
    if not test_files:
        print(f"No *_test.nd files found in: {test_path}", file=sys.stderr)
        return 2

    # Determine output format
    if output_format == "auto":
        output_format = "pretty" if _is_tty() else "plain"
    use_color = output_format == "pretty"

    all_results: list[TestResult] = []
    failed_early = False

    # Set up coverage collector
    coverage_collector = None
    if do_coverage:
        from nodus.testing.coverage import CoverageCollector
        coverage_collector = CoverageCollector()

    for test_file in test_files:
        if failed_early:
            break
        file_results = _run_one_file(
            test_file,
            filter_pattern=filter_pattern,
            coverage_collector=coverage_collector,
        )
        all_results.extend(file_results)
        if bail and any(r.status in ("fail", "error") for r in file_results):
            failed_early = True

    # Output results
    if output_format in ("pretty", "plain"):
        output = format_text(all_results, use_color=use_color, verbose=verbose, quiet=quiet)
        sys.stdout.write(output)
    elif output_format == "json":
        sys.stdout.write(format_json(all_results))
    elif output_format == "junit":
        sys.stdout.write(format_junit(all_results))
    else:
        output = format_text(all_results, use_color=False, verbose=verbose, quiet=quiet)
        sys.stdout.write(output)

    # Coverage reporting
    if do_coverage and coverage_collector is not None:
        exclude_pats = [coverage_exclude] if coverage_exclude else []
        include_pats = [coverage_include] if coverage_include else []
        cov_data = coverage_collector.build_report(
            exclude_patterns=exclude_pats or None,
            include_patterns=include_pats or None,
            test_command=f"nodus test {' '.join(cmd_args)}",
        )
        summary_text = coverage_collector.format_summary(cov_data)
        sys.stdout.write(summary_text)
        coverage_collector.write_reports(cov_data, output_dir=coverage_output,
                                         formats=coverage_formats)
        print(f"\nCoverage reports written to: {coverage_output}", file=sys.stderr)

        if coverage_min > 0:
            overall = cov_data["summary"]["overall_coverage_pct"]
            if overall < coverage_min:
                print(
                    f"Coverage {overall:.1f}% below minimum {coverage_min:.1f}%",
                    file=sys.stderr,
                )
                return 1

    # Determine exit code
    n_failed = sum(1 for r in all_results if r.status in ("fail", "error"))
    if n_failed > 0:
        return 1
    if not all_results:
        return 2
    return 0


def _run_one_file(
    path: str,
    *,
    filter_pattern: str = "",
    coverage_collector=None,
) -> list[TestResult]:
    """Load one test file, run its tests, return results."""
    import nodus
    from nodus.runtime.module_loader import ModuleLoader

    vm = nodus.VM([], {}, code_locs=[], source_path=path)

    # Attach coverage collector if active
    if coverage_collector is not None:
        coverage_collector.attach(vm)

    try:
        loader = ModuleLoader(project_root=os.path.dirname(os.path.abspath(path)), vm=vm)
        try:
            loader.load_module_from_path(path)
        except Exception as exc:
            from nodus.runtime.diagnostics import LangSyntaxError
            if isinstance(exc, (LangSyntaxError, SyntaxError)):
                err_msg = str(exc)
            else:
                err_msg = str(exc)
            return [TestResult(
                suite_path=["(file load error)"],
                case_name=os.path.basename(path),
                status="error",
                failure_message=err_msg,
                failure_kind="discovery_error",
                source_path=path,
            )]

        runner = TestRunner(vm, source_path=path)
        results = runner.run_all()

        # Apply filter
        if filter_pattern:
            results = [
                r for r in results
                if matches_filter(
                    " > ".join(r.suite_path + [r.case_name]),
                    filter_pattern,
                )
            ]

        return results
    finally:
        if coverage_collector is not None:
            coverage_collector.detach(vm)


def _parse_flags(
    args: list[str],
    flags_with_values: set[str],
    flags_no_values: set[str],
) -> tuple[list[str], dict[str, str | bool]]:
    """Simple flag parser (no argparse dependency)."""
    positional: list[str] = []
    flags: dict[str, str | bool] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in flags_no_values:
            flags[arg] = True
        elif arg in flags_with_values:
            if i + 1 < len(args):
                flags[arg] = args[i + 1]
                i += 1
        elif arg.startswith("--"):
            # Unknown flag with possible = syntax
            if "=" in arg:
                k, v = arg.split("=", 1)
                flags[k] = v
            else:
                flags[arg] = True
        else:
            positional.append(arg)
        i += 1
    return positional, flags
