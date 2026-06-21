"""Stage 3 wheel validation for REHYDRATE-001 (#285), v4.0.7.

Deliberately does NOT insert src/ on sys.path, and MUST be run from a directory
outside the nodus-lang repo (the root nodus.py shim force-inserts src/ when the
repo root is importable). Run with the validation venv from a temp dir:

    cp validate_rehydrate_285.py ~/wheel-smoke-285/
    cd ~/wheel-smoke-285
    /path/to/.venv-validation/Scripts/python.exe validate_rehydrate_285.py

Three adversarial programs targeting the patched code path (workflow graph
rebuild / import re-binding) and the adjacent in-process fast path.
"""
import os
import tempfile

import nodus  # noqa: F401  (resolution checked below)
from nodus.cli import cli as nodus_cli
from nodus.orchestration import task_graph
from nodus.tooling.runner import resume_workflow, run_workflow_code
from nodus.vm.vm import VM
from nodus.support.version import __version__

# Fail loudly if we are not running against the installed wheel.
assert "site-packages" in nodus.vm.vm.__file__, (
    f"NOT testing the wheel — nodus resolved to {nodus.vm.vm.__file__}"
)


def _run_to_wait(td, code):
    path = os.path.join(td, "wf.nd")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    with nodus_cli._project_root_context(td):
        result, _vm = run_workflow_code(
            VM([], {}, code_locs=[], source_path=None), code, filename=path, project_root=td
        )
    assert result.get("ok"), f"initial run failed: {result}"
    return result["result"]["graph_id"]


def _resume(td, gid):
    with nodus_cli._project_root_context(td):
        resumed, _vm = resume_workflow(gid)
    return resumed


def program_1_aliased_import_after_rebuild():
    """Aliased stdlib import used in a post-wait step, resumed on a fresh VM."""
    code = """
import "std:json" as json

workflow demo {
    step gate { return workflow_wait("approval.granted", "k1", {kind: "approval"}) }
    step finish after gate { return json.stringify({status: "ok"}) }
}
"""
    with tempfile.TemporaryDirectory() as td:
        gid = _run_to_wait(td, code)
        # evict live graph + VM -> force rebuild (cross-process simulation)
        task_graph._GRAPH_REGISTRY.pop(gid, None)
        task_graph._GRAPH_VMS.pop(gid, None)
        r = _resume(td, gid)["result"]
    assert r["steps"].get("finish") == '{"status": "ok"}', r
    assert r.get("failed", []) == [], r
    return f'finish -> {r["steps"]["finish"]}'


def program_2_inprocess_fast_path():
    """In-process resume (live VM retained) must still work — regression guard."""
    code = """
import "std:json" as json

workflow demo {
    step gate { return workflow_wait("approval.granted", "k2", {kind: "approval"}) }
    step finish after gate { return json.stringify({ok: true}) }
}
"""
    with tempfile.TemporaryDirectory() as td:
        gid = _run_to_wait(td, code)
        # do NOT evict -> reuses the registered VM (fast path)
        r = _resume(td, gid)["result"]
    assert r["steps"].get("finish") == '{"ok": true}', r
    assert r.get("failed", []) == [], r
    return f'finish -> {r["steps"]["finish"]}'


def program_3_different_module_after_rebuild():
    """Not json-specific: a different aliased stdlib module re-binds on rebuild."""
    code = """
import "std:strings" as strings

workflow demo {
    step gate { return workflow_wait("approval.granted", "k3", {kind: "approval"}) }
    step finish after gate { return strings.upper("done") }
}
"""
    with tempfile.TemporaryDirectory() as td:
        gid = _run_to_wait(td, code)
        task_graph._GRAPH_REGISTRY.pop(gid, None)
        task_graph._GRAPH_VMS.pop(gid, None)
        r = _resume(td, gid)["result"]
    assert r["steps"].get("finish") == "DONE", r
    assert r.get("failed", []) == [], r
    return f'finish -> {r["steps"]["finish"]}'


PROGRAMS = [
    program_1_aliased_import_after_rebuild,
    program_2_inprocess_fast_path,
    program_3_different_module_after_rebuild,
]

print(f"REHYDRATE-001 wheel validation (nodus {__version__})")
for fn in PROGRAMS:
    detail = fn()
    print(f"  PASS  {fn.__name__}: {detail}")
print("ALL WHEEL VALIDATION PROGRAMS PASSED")
