"""Closed-issue test for #488: a goal can be bounded by a host-registered meter.

`budget` accepted exactly two dimensions, both mandatory: `max_iterations` and
`deadline_ms`. So the construct bounded iterations and wall-clock for loops whose
dominant marginal cost is tokens, which it could not express.

The constraint the design turns on, and the issue is right about it: **Nodus
cannot measure spend and should not learn how.** There is no model invocation
anywhere in the core, and that absence is load-bearing — it is what forces every
semantic decision across a typed boundary to a host handler. So `max_cost_usd`
enforced by Nodus counting tokens was never available, and a *named* cost
dimension would bake in a unit Nodus cannot define.

D9 in `docs/design/workflow-dsl/00-cluster-decisions.md`: `limits` is a nested
map of host-registered meters. The host counts; the goal declares a ceiling; the
runtime compares two numbers and never interprets the unit.
"""

import sys

from pathlib import Path

# closes: #488

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402

_FLOW = '''
workflow tune {
    step t {
        checkpoint "pass"
        if (spend()) { checkpoint "good_enough" }
        return 1i
    }
}
'''


def _goal(budget: str) -> str:
    return _FLOW + (
        'goal reach over tune {\n'
        '    until reached("good_enough")\n'
        f'    budget {{ {budget} }}\n'
        '}\n'
    )


class _Host:
    """A host that spends 100 of something per iteration and never succeeds."""

    def __init__(self):
        self.spent = 0

    def spend(self):
        self.spent += 100
        return False


def _runtime(host: _Host, *, meter: bool = True) -> NodusRuntime:
    runtime = NodusRuntime()
    runtime.register_function("spend", host.spend, arity=0)
    if meter:
        runtime.register_meter("tokens", lambda: host.spent)
    return runtime


def _payload(runtime: NodusRuntime, source: str) -> dict:
    """Read the err record back as text.

    `meter` is read through `has_key` rather than directly: the two failure
    payloads are deliberately different shapes. A breach names the one meter that
    breached (`meter`); an unregistered declaration names *all* of them
    (`meters`, a list), because a goal can declare several and a host that
    registered none should be told about all of them at once.
    """
    result = runtime.run_source(
        source + 'fn main() {\n'
        '  let r = run_goal(reach)\n'
        '  let p = r.payload\n'
        '  let m = "nil"\n'
        '  if (has_key(p, "meter")) { m = str(p["meter"]) }\n'
        '  print("\\(r.kind)|\\(r.message)|\\(p["category"])|\\(m)")\n'
        '}\n'
    )
    assert result["ok"], (result.get("error") or {}).get("message")
    kind, message, category, meter = result["stdout"].strip().split("|", 3)
    return {"kind": kind, "message": message, "category": category, "meter": meter}


def test_a_meter_bounds_the_loop():
    host = _Host()
    out = _payload(_runtime(host), _goal("max_iterations: 50, limits: { tokens: 300 }"))
    assert out["kind"] == "goal_error"
    assert out["category"] == "budget_exhausted"
    assert out["meter"] == "tokens"
    assert "meter 'tokens' reached" in out["message"], out["message"]
    assert host.spent == 300, (
        f"the loop must stop at the declared limit, not past it (spent {host.spent})"
    )


def test_the_iteration_cap_did_not_have_to_be_reached():
    """The meter is a real bound, not a tiebreak.

    `max_iterations: 50` would allow 5000 tokens; the meter stops it at 300.
    """
    host = _Host()
    _payload(_runtime(host), _goal("max_iterations: 50, limits: { tokens: 300 }"))
    assert host.spent < 5000


def test_a_declared_meter_with_no_accountant_fails_before_spending():
    """Not silently unbounded — the rule `ask` with no approval channel follows."""
    host = _Host()
    out = _payload(_runtime(host, meter=False), _goal("max_iterations: 50, limits: { tokens: 300 }"))
    assert out["kind"] == "goal_error"
    assert out["category"] == "unregistered_meter"
    assert "no accountant is registered" in out["message"], out["message"]
    assert host.spent == 0, (
        "it must refuse before the first iteration, or the bound it was meant to "
        "cap has already been spent"
    )


def test_limits_alone_is_a_sufficient_bound():
    """A goal bounded by spend should not have to invent an iteration cap."""
    host = _Host()
    out = _payload(_runtime(host), _goal("limits: { tokens: 200 }"))
    assert out["category"] == "budget_exhausted"
    assert host.spent == 200


def test_both_map_and_record_spellings_of_limits_work():
    for spelling in ("limits: { tokens: 200 }", 'limits: { "tokens": 200 }'):
        host = _Host()
        out = _payload(_runtime(host), _goal(spelling))
        assert out["category"] == "budget_exhausted", spelling


def test_the_existing_dimensions_are_unchanged():
    """Nothing regressed for a goal that declares no limits."""
    host = _Host()
    out = _payload(_runtime(host), _goal("max_iterations: 2"))
    assert out["category"] == "budget_exhausted"
    assert out["meter"] == "nil", "no meter was breached; the iteration cap was"
    assert host.spent == 200, "two iterations"


def test_a_broken_accountant_stops_the_loop_rather_than_being_ignored():
    """A host whose meter raises has lost the ability to bound the loop.

    Continuing would be exactly the silently-unbounded run this exists to
    prevent, so a raising reader counts as a breach.
    """
    host = _Host()
    runtime = NodusRuntime()
    runtime.register_function("spend", host.spend, arity=0)

    def broken():
        raise RuntimeError("accountant is down")

    runtime.register_meter("tokens", broken)
    out = _payload(runtime, _goal("max_iterations: 50, limits: { tokens: 300 }"))
    assert out["category"] == "budget_exhausted"
    assert host.spent <= 100, "it must stop on the first check, not run to 50"


def test_register_meter_validates_its_arguments():
    runtime = NodusRuntime()
    for args in (("", lambda: 0), ("tokens", None)):
        try:
            runtime.register_meter(*args)
        except ValueError:
            continue
        raise AssertionError(f"register_meter{args} should have been refused")


def test_a_stuck_meter_cannot_loop_forever():
    """The hole mutation testing found, and the reason for the implicit cap.

    Making both `max_iterations` and `deadline_ms` optional means `limits` can be
    the only declared bound -- and a meter is only a bound while it *moves*. A
    stuck host counter would otherwise loop forever, which is exactly what
    `budget` exists to prevent. Before #488 the mandatory iteration cap made that
    impossible; the implicit cap restores the guarantee.

    Found because removing the meter check hung the falsification run.
    """
    import nodus.vm.vm as vm_module

    original = vm_module.IMPLICIT_GOAL_ITERATION_CAP
    vm_module.IMPLICIT_GOAL_ITERATION_CAP = 25  # the mechanism, not the number
    try:
        host = _Host()
        runtime = NodusRuntime()
        runtime.register_function("spend", host.spend, arity=0)
        runtime.register_meter("tokens", lambda: 0)   # never moves
        out = _payload(runtime, _goal("limits: { tokens: 1000000 }"))
    finally:
        vm_module.IMPLICIT_GOAL_ITERATION_CAP = original

    assert out["category"] == "budget_exhausted"
    assert "implicit cap" in out["message"], out["message"]
    assert "actually moving" in out["message"], (
        "the message must say what to check, or it reads as the author's own bound"
    )
