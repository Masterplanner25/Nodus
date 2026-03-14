"""Runtime stats helpers for scheduler and coroutine introspection."""

from __future__ import annotations

import time

_START = time.monotonic()


def runtime_time_ms() -> float:
    return (time.monotonic() - _START) * 1000.0


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
