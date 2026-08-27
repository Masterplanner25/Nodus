"""Closed-issue test for #481: workflows take parameters.

`workflow build(mode) { ... }` was a syntax error, so a family of related
pipelines had to be N separate workflows or read a module-level `let`.

The module-global workaround worked, and its worst property is why this exists:
`state chosen = mode` was captured into the run and restored, while a bare
`mode` read inside a step was re-derived when the module was rebuilt — and
nothing in the language marked which was which. The *spelling* silently decided
whether the value survived a resume. A declared parameter is durable by
construction, which removes the choice rather than documenting it.

Bound at `run_workflow(flow, args)`, per D4 in
`docs/design/workflow-dsl/00-cluster-decisions.md` — deliberately not
`run_workflow(build("lite"))`, which the issue sketches. The flow value is an
ordinary map, and #394 has just finished pinning its shape.
"""

import os
import sys
import tempfile

from pathlib import Path

# closes: #481

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402

_FLOW = """
workflow build(mode) {
    state seen = ""
    step plan {
        checkpoint "planned"
        seen = mode
        return mode
    }
    step apply after plan { return "applied \\(mode)" }
}
"""


def _run(src: str, *, cwd: str | None = None) -> dict:
    runtime = NodusRuntime()
    if cwd is None:
        return runtime.run_source(src)
    previous = os.getcwd()
    os.chdir(cwd)
    try:
        return runtime.run_source(src)
    finally:
        os.chdir(previous)


def _error(result: dict) -> str:
    return ((result.get("error") or {}).get("message") or result.get("stderr") or "").strip()


def test_a_workflow_takes_parameters():
    result = _run(_FLOW + '\nfn main() { print(run_workflow(build, {mode: "lite"})["steps"]["apply"]) }')
    assert result["ok"], _error(result)
    assert "applied lite" in result["stdout"]


def test_two_runs_can_differ_and_that_is_the_point():
    """The workaround's first failure: one value per module, per process."""
    result = _run(
        _FLOW
        + '\nfn main() {\n'
        '  print(run_workflow(build, {mode: "lite"})["steps"]["apply"])\n'
        '  print(run_workflow(build, {mode: "full"})["steps"]["apply"])\n}'
    )
    assert result["ok"], _error(result)
    assert "applied lite" in result["stdout"]
    assert "applied full" in result["stdout"]


def test_the_argument_survives_a_resume():
    """The claim the whole feature rests on.

    A resume rebuilds the graph by re-executing source. The argument is read
    back from the run record rather than re-bound, so nothing the second
    execution does can change it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        started = _run(
            _FLOW + '\nfn main() { print(run_workflow(build, {mode: "lite"})["graph_id"]) }',
            cwd=tmp,
        )
        assert started["ok"], _error(started)
        graph_id = started["stdout"].strip().splitlines()[-1]

        resumed = _run(
            _FLOW + f'\nfn main() {{ print(resume_workflow("{graph_id}", "planned")["steps"]["apply"]) }}',
            cwd=tmp,
        )
    assert resumed["ok"], _error(resumed)
    assert "applied lite" in resumed["stdout"], (
        "the parameter must come from the run record on a resume"
    )


def test_both_map_and_record_spellings_bind():
    """`{mode: "x"}` is a record and `{"mode": "x"}` is a map.

    Named arguments read naturally as the first, and `with { ... }` on a step
    already uses that spelling. A record is normalised to a map before it
    reaches run metadata, because a Record is not JSON serializable — the same
    persist-time failure that makes a `state` cell reject one.
    """
    for spelling in ('{mode: "x"}', '{"mode": "x"}'):
        result = _run(_FLOW + f'\nfn main() {{ print(run_workflow(build, {spelling})["steps"]["apply"]) }}')
        assert result["ok"], f"{spelling}: {_error(result)}"
        assert "applied x" in result["stdout"], spelling


def test_a_wrong_argument_is_refused_where_it_is_written():
    """Not left to a step reading `nil` — that is what declaring them buys."""
    cases = [
        ("run_workflow(build)", "but none were given"),
        ('run_workflow(build, {node: "x"})', "has no parameter"),
        ('run_workflow(build, "lite")', "expects args as a map or record"),
    ]
    for call, expected in cases:
        result = _run(_FLOW + f"\nfn main() {{ {call} }}")
        assert not result["ok"], f"{call} should be refused"
        assert expected in _error(result), f"{call}: {_error(result)}"


def test_a_flow_without_parameters_refuses_arguments():
    result = _run(
        "workflow plain { step a { return 1i } }\n"
        'fn main() { run_workflow(plain, {mode: "x"}) }'
    )
    assert not result["ok"]
    assert "declares no parameters" in _error(result)


def test_planning_does_not_require_arguments():
    """`plan_workflow` asks about shape, not values."""
    result = _run(_FLOW + '\nfn main() { print(plan_workflow(build)["levels"]) }')
    assert result["ok"], _error(result)
    assert "plan" in result["stdout"]


def test_a_goal_pursuing_a_parameterised_workflow_is_refused_accurately():
    """`goal … over …` has no slot to bind arguments.

    Refused at the pursuit rather than in the binder — left to the binder it
    reported "pass them to run_workflow(tune, {…})", naming a call the author
    did not write and could not reach from there.
    """
    result = _run(
        "workflow tune(target) { step t { checkpoint \"good\"\n return target } }\n"
        'goal reach over tune { until reached("good")\n'
        "  budget { max_iterations: 2, deadline_ms: 5000 } }\n"
        "fn main() { run_goal(reach) }"
    )
    assert not result["ok"]
    message = _error(result)
    assert "pursues workflow 'tune'" in message, message
    assert "no way to bind them" in message, message


def test_a_parameter_may_not_collide_with_a_step_or_a_state_cell():
    for src, expected in [
        ("workflow w(a) { step a { return 1i } }", "parameter and a step both named"),
        ("workflow w(s) { state s = 1i\n step a { return 1i } }", "parameter and a state cell both named"),
        ("workflow w(m, m) { step a { return 1i } }", "Duplicate parameter"),
        ("workflow w() { step a { return 1i } }", "empty parameter list"),
    ]:
        result = _run(src + "\nfn main() { }")
        assert not result["ok"], src
        assert expected in _error(result), f"{src}: {_error(result)}"
