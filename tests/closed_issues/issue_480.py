"""Closed-issue test for #480: a step can map over a list.

`step process each item in plan { ... }` runs the body once per item the
producer returned. The declared node is never executed: it becomes the count,
and then the join. Its result is the list of item results, in the producer's
order rather than the order they finished.

Per D5/D6 in `docs/design/workflow-dsl/00-cluster-decisions.md`. The model is
Airflow's `.expand()`: the graph does not grow in the sense that matters, since
the node exists in the source and only its cardinality is discovered at run
time. That is what lets a rebuild reconstruct the run, and it is why this needs
no eighth task status.

Two things D5 anticipated that testing removed rather than implemented, both
recorded here so they are not re-added on the strength of the design doc:

*   **No cardinality-drift refusal.** Drift needs the producer to re-run *and*
    the mapped node to re-expand, and those are mutually exclusive. A completed
    producer is restored, so a re-expansion re-derives the same list (pinned by
    `test_a_run_suspended_mid_fan_out_resumes_to_the_same_instances`); when the
    producer does re-run, the mapped node is restored and never re-expands.
*   **No second copy of the cardinality.** It is already durable, in the
    producer's own restored result.
"""

import sys

from pathlib import Path

# closes: #480
# closes: #468

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.orchestration import task_graph as _task_graph  # noqa: E402

_FLOW = """
workflow w {
    step plan { return ["a", "b", "c"] }
    step process each item in plan { return "did \\(item)" }
    step collect after process { return len(process) }
}
"""


def _run(src: str, *, cwd: str | None = None) -> dict:
    import os

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


def _out(result: dict) -> str:
    return result["stdout"]


def test_the_body_runs_once_per_item():
    result = _run(_FLOW + '\nfn main() { print(run_workflow(w)["steps"]["process"]) }')
    assert result["ok"], _error(result)
    assert '["did a", "did b", "did c"]' in _out(result)


def test_results_are_in_the_producers_order_not_the_finishing_order():
    """Instances run concurrently, so "the order they finished" is not stable.

    The slowest item is first in the producer's list, so a result list built as
    instances completed would put it last.
    """
    src = """
workflow w {
    step plan { return [60i, 10i, 20i] }
    step process each item in plan { sleep(item); return item }
}
fn main() { print(run_workflow(w)["steps"]["process"]) }
"""
    result = _run(src)
    assert result["ok"], _error(result)
    assert "[60, 10, 20]" in _out(result), "index order, not completion order"


def test_a_dependent_receives_the_items_in_the_producers_order_too():
    """`steps` and the join are ordered by different code, so both are pinned.

    What a reader sees in `steps["process"]` is aggregated by index in
    `step_results`; what `collect` is handed is the list the declared node
    settled to. A test of one passes while the other is reversed.
    """
    src = """
workflow w {
    step plan { return [60i, 10i, 20i] }
    step process each item in plan { sleep(item); return item }
    step collect after process { return process }
}
fn main() { print(run_workflow(w)["steps"]["collect"]) }
"""
    result = _run(src)
    assert result["ok"], _error(result)
    assert "[60, 10, 20]" in _out(result), "the join sees the producer's order"


def test_a_dependent_joins_the_declared_node_and_receives_the_list():
    """`collect after process` declares one dependency and takes one argument.

    Rewiring dependents to the N instances handed the body N arguments, and it
    received the last item instead of the list -- `len(process)` returned 11,
    the length of "processed a". The declared node stays the join.
    """
    result = _run(_FLOW + '\nfn main() { print(run_workflow(w)["steps"]["collect"]) }')
    assert result["ok"], _error(result)
    assert _out(result).strip().splitlines()[-1] == "3"


def test_instances_run_concurrently():
    """The reason to write a fan-out at all.

    Four 120ms sleeps: ~480ms in sequence, ~120ms together. The threshold is
    deliberately loose, since this box's timing is unreliable under load -- it
    only has to separate "concurrent" from "serial".
    """
    src = """
workflow w {
    step plan { return [1i, 2i, 3i, 4i] }
    step process each item in plan { sleep(120); return item }
}
fn main() {
    let started = clock()
    let r = run_workflow(w)
    print(clock() - started)
}
"""
    result = _run(src)
    assert result["ok"], _error(result)
    elapsed = float(_out(result).strip().splitlines()[-1])
    assert elapsed < 0.4, f"{elapsed}s suggests the items ran in sequence"


def test_an_empty_producer_skips_the_step_and_reports_an_empty_list():
    """Zero items is a legitimate answer, and not a failure.

    `skipped` rather than `completed`, because "ran nothing, reported success"
    is the wrong default for a declared node with a join behind it -- a join
    has to opt in with `on: [..., "skipped"]` to see it.
    """
    src = """
workflow w {
    step plan { return [] }
    step process each item in plan { return item }
    step collect after process with { on: ["completed", "skipped"] } { return "collected" }
}
fn main() {
    let r = run_workflow(w)
    print(r["statuses"]["process"])
    print(r["steps"]["process"])
    print(r["failed"])
}
"""
    result = _run(src)
    assert result["ok"], _error(result)
    lines = _out(result).strip().splitlines()
    assert lines[-3] == "skipped"
    assert lines[-2] == "[]", "it ran, and the answer was no items"
    assert lines[-1] == "[]", "an empty fan-out is not a failure"


def test_an_unmappable_producer_fails_and_names_the_producer():
    """Not the same as an empty fan-out, and must not report one.

    A producer that returned `nil` did not fan out to zero; the fan-out could
    not be computed at all. So the step fails, and -- unlike the empty case --
    leaves no result behind, exactly as any other failed step does.
    """
    src = """
workflow w {
    step plan { return nil }
    step process each item in plan { return item }
}
fn main() {
    let r = run_workflow(w)
    print(r["statuses"]["process"])
    print(has_key(r["steps"], "process"))
    print(r["error"])
}
"""
    result = _run(src)
    assert result["ok"], _error(result)
    lines = _out(result).strip().splitlines()
    assert lines[-3] == "failed"
    assert lines[-2] == "false", "a failed expansion leaves no result"
    message = lines[-1]
    assert "'plan'" in message, "the producer is where an author can act"
    assert "nil" in message.lower() or "list" in message


def test_a_fan_out_is_bounded_and_the_bound_names_the_producer():
    """Charged to the producer, checked the moment its list arrives."""
    src = """
workflow w {
    step plan { let out = []; let i = 0i
        while (i < 2000i) { out = push(out, i); i = i + 1i }
        return out }
    step process each item in plan { return item }
}
fn main() { print(run_workflow(w)["error"]) }
"""
    result = _run(src)
    assert result["ok"], _error(result)
    message = _out(result).strip().splitlines()[-1]
    assert str(_task_graph.MAX_MAPPED_INSTANCES) in message
    assert "'plan'" in message, "the bound is on what the producer returned"


def test_the_plan_shows_the_declared_node_not_the_instances():
    """`plan_workflow` runs before anything does, so N is not yet knowable.

    This is the claim that the graph does not grow: the node is in the source,
    and only its cardinality is discovered at run time.
    """
    result = _run(_FLOW + "\nfn main() { print(plan_workflow(w)) }")
    assert result["ok"], _error(result)
    assert '[["plan"], ["process"], ["collect"]]' in _out(result)


def test_one_failing_item_names_its_step_once():
    """An instance and its declared node share a step name.

    Listing both named the step twice in `failed` for a single failing item.
    """
    src = """
workflow w {
    step plan { return ["a", "boom", "c"] }
    step process each item in plan {
        if (item == "boom") { return 1i / 0i }
        return "did \\(item)" }
}
fn main() { print(run_workflow(w)["failed"]) }
"""
    result = _run(src)
    assert result["ok"], _error(result)
    assert _out(result).strip().splitlines()[-1] == '["process"]'


def test_a_mapped_steps_status_is_the_steps_not_an_arbitrary_items():
    """Every instance carries the step's name.

    Writing each one into `statuses` let whichever was iterated last stand in
    for the step, reporting `completed` for a step that failed.
    """
    src = """
workflow w {
    step plan { return ["a", "boom", "c"] }
    step process each item in plan {
        if (item == "boom") { return 1i / 0i }
        return "did \\(item)" }
}
fn main() { print(run_workflow(w)["statuses"]["process"]) }
"""
    result = _run(src)
    assert result["ok"], _error(result)
    assert _out(result).strip().splitlines()[-1] == "failed"


def test_every_step_name_aggregation_asks_one_question():
    """A source assertion, because behaviour alone passes on whichever site is
    already right.

    `steps`, `statuses`, `failed` and `tolerated` all key by step name, and each
    learned separately that an instance is not a step -- getting it wrong
    differently each time. `TaskNode.is_mapped_instance` is the one place that
    is asked, so a fifth aggregation cannot quietly answer it again.
    """
    source = Path(_task_graph.__file__).read_text(encoding="utf-8")
    assert "def is_mapped_instance" in source
    body = source.split("def run_task_graph", 1)[1]
    # The raw attribute is how each site spelled the question before it had a
    # name, in whichever polarity suited it -- `is not None` in one place and
    # `is None` in two others. Any read of it inside the runner means somebody
    # asked again, so the only mention allowed is where an instance is built.
    reads = [
        line.strip() for line in body.splitlines()
        if "each_parent" in line and "each_parent=task.task_id" not in line
    ]
    assert reads == [], f"ask TaskNode.is_mapped_instance rather than re-deriving it: {reads}"
    assert body.count("is_mapped_instance") >= 3


def test_a_run_suspended_mid_fan_out_resumes_to_the_same_instances():
    """The durability claim, and why no drift check is needed.

    The run suspends inside one instance. The resumed source returns a *longer*
    list from the producer, which is ignored: `plan` completed, so its result is
    restored and the fan-out re-derives from that. The cardinality is durable
    because the producer's result is, with no second copy of it.
    """
    import tempfile

    waiting = """
workflow w {
    step plan { return ["a", "b"] }
    step process each item in plan {
        if (item == "b") { return workflow_wait("ev.go", "gate", {kind: "g"}) }
        return "did \\(item)" }
}
"""
    drifted = waiting.replace('return ["a", "b"]', 'return ["a", "b", "c"]')
    with tempfile.TemporaryDirectory() as tmp:
        started = _run(waiting + '\nfn main() { print(run_workflow(w)["graph_id"]) }', cwd=tmp)
        assert started["ok"], _error(started)
        graph_id = _out(started).strip().splitlines()[-1]

        resumed = _run(
            drifted + f'\nfn main() {{ print(resume_workflow("{graph_id}", {{ok: true}})["steps"]["plan"]) }}',
            cwd=tmp,
        )
    assert resumed["ok"], _error(resumed)
    assert '["a", "b"]' in _out(resumed), (
        "the producer's restored result decides the fan-out, not the edited source"
    )
