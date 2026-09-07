"""Copy the examples `nodus test-examples` runs into the package (#605's sibling).

`package-data` paths are relative to the package directory, so files at the repo
root cannot be shipped from there — they have to exist under `src/nodus/`. Same
constraint that put `llms.txt` in two places, and the same answer: the copy is
**generated, not maintained**.

Without it, `nodus test-examples` from an installed wheel looked under
`<venv>/Lib/examples`, found nothing, printed nine "Missing examples" lines and
returned **0**. A command that ships, cannot work, and reports success.

Only the files the command actually runs are copied, plus what they import. The
rest of `examples/` — benchmarks, the orchestration and webhook demos, the
compiler experiment — stays repo-only, because a wheel is not a place to put
material nobody executes from it.

`tests/test_examples_shipped.py` fails if the two copies differ or if the
manifest names a file that does not exist. Editing `src/nodus/examples/` by hand
is the mistake that test exists to catch; the source of truth is `examples/`.

Run after editing any example the command runs:

    python -m tools.sync_examples
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "examples"
SHIPPED = ROOT / "src" / "nodus" / "examples"

#: Everything the packaged copy needs: the files `EXAMPLE_FILES` in
#: `nodus/cli/cli.py` names, plus the modules they import. Kept as an explicit
#: list rather than copying the tree, so adding a 300 KB benchmark to
#: `examples/` cannot silently land in the wheel.
PACKAGED = (
    "hello.nd",
    "features_demo.nd",
    "import_demo.nd",
    "namespace_import_demo.nd",
    "relative_import_demo.nd",
    "stdlib_demo.nd",
    "std_selective_import_demo.nd",
    "modules/greetings.nd",
    "project_layout_demo/main.nd",
    "project_layout_demo/math.nd",
    "project_layout_demo/utils/index.nd",
)


def sync() -> list[str]:
    """Write the packaged copies. Returns the relative paths that changed."""
    changed: list[str] = []
    for name in PACKAGED:
        src = SOURCE / name
        dst = SHIPPED / name
        text = src.read_text(encoding="utf-8")
        if dst.is_file() and dst.read_text(encoding="utf-8") == text:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8", newline="\n")
        changed.append(name)

    # A file dropped from PACKAGED must leave the package too, or the wheel keeps
    # shipping something the repo no longer has -- which is the drift this whole
    # generated-copy arrangement exists to prevent.
    if SHIPPED.is_dir():
        keep = {(SHIPPED / n).resolve() for n in PACKAGED}
        for path in sorted(SHIPPED.rglob("*")):
            if ".nodus" in path.parts:
                # Bytecode cache written by running the examples. Gitignored,
                # and package-data only globs *.nd, so it never ships.
                continue
            if path.is_file() and path.resolve() not in keep:
                path.unlink()
                changed.append(f"removed {path.relative_to(SHIPPED).as_posix()}")
    return changed


def main() -> int:
    missing = [n for n in PACKAGED if not (SOURCE / n).is_file()]
    if missing:
        for name in missing:
            print(f"missing source: examples/{name}", file=sys.stderr)
        return 1
    changed = sync()
    if changed:
        for name in changed:
            print(f"  {name}")
        print(f"{len(changed)} file(s) updated in {SHIPPED.relative_to(ROOT).as_posix()}")
    else:
        print(f"{SHIPPED.relative_to(ROOT).as_posix()}: already in step")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
