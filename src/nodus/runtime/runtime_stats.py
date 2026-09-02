"""Runtime stats helpers for scheduler and coroutine introspection."""

from __future__ import annotations

import time

_START = time.monotonic()


def runtime_time_ms() -> float:
    """Milliseconds since **this process started**. For in-process timing only.

    Monotonic, so it cannot go backwards when the system clock is adjusted, which
    is what the scheduler needs. It is meaningless to any other process: see
    `store_time_ms` below, and do not persist a value derived from this one.
    """
    return (time.monotonic() - _START) * 1000.0


#: Below this, a stored timestamp cannot be wall clock and predates #725.
#:
#: 1e12 ms after the epoch is 2001-09-09. Two enormous margins meet here, which is
#: what makes the test unambiguous rather than merely likely: a wall-clock reading
#: has been above this since 2001, and a process would need **31 years of uptime**
#: for `runtime_time_ms()` to reach it.
STORE_TIME_FLOOR_MS = 1_000_000_000_000.0


def store_time_ms() -> float:
    """Wall-clock milliseconds since the epoch, for anything **persisted** (#725).

    Deliberately next to `runtime_time_ms`, because the two are interchangeable at
    a glance and only one is right in any given place. Using the process clock for
    a stored deadline made a wait mean whatever the *sweeping* process's uptime
    made it: a 1 ms deadline set by a two-second-old process was not due to a
    fresh one, and a long deadline set by a fresh process expired instantly under
    an old one.

    Anything written to a store, or compared with something read from one, uses
    this. Both `nodus_lang_workflow` and the task graph's retry deadline do.
    """
    return time.time() * 1000.0


def is_store_time(value: object) -> bool:
    """Was *value* written by `store_time_ms`, rather than a pre-#725 process clock?

    Records written before #725 carry a monotonic-origin number that cannot be
    converted — nothing recorded when the writing process started. They are
    detected and resolved explicitly rather than compared as if comparable.

    **Which way a legacy value resolves depends on what it measures.** For a
    *deadline* (a wait's `registered_at`, a retry's `next_attempt_at`) legacy
    means **not due**: firing early kills work nobody asked to stop. For
    *liveness* (a claim's TTL, a run's idle age) it means **stale**: the process
    that wrote it is gone by definition, so honouring it would strand the run.
    """
    return isinstance(value, (int, float)) and float(value) >= STORE_TIME_FLOOR_MS


def task_snapshot(coroutine) -> dict:
    return {
        "id": float(coroutine.id) if coroutine.id is not None else None,
        "name": coroutine.name,
        "module": coroutine.module,
        "status": coroutine.state,
        "resumes": float(coroutine.resume_count),
        "created_time": float(coroutine.created_time) if coroutine.created_time is not None else None,
        "last_resume": float(coroutine.last_resume) if coroutine.last_resume is not None else None,
        "last_run_time": float(coroutine.last_run_time) if coroutine.last_run_time is not None else None,
    }


def scheduler_stats(scheduler) -> dict:
    return {
        "ready": float(len(scheduler.ready_queue)),
        "sleeping": float(len(scheduler.sleeping_tasks)),
        "completed": float(len(scheduler.completed_tasks)),
        "spawned": float(scheduler.total_tasks_spawned),
        "resumes": float(scheduler.total_resumes),
        "ready_queue": [float(task.id) for task in scheduler.ready_queue if task.id is not None],
        "sleeping_tasks": [float(task_id) for task_id in sorted(scheduler.sleeping_tasks)],
        "completed_tasks": [float(task.id) for task in scheduler.completed_tasks if task.id is not None],
    }
