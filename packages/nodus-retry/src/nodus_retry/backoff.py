from __future__ import annotations

import random

from .models import BackoffStrategy


def compute_backoff_delay(
    strategy: BackoffStrategy,
    *,
    attempt_number: int,
    rng: random.Random | None = None,
) -> float:
    base = max(0.0, strategy.base_delay_seconds)
    kind = strategy.kind
    if kind == "fixed":
        delay = base
    elif kind in {"exponential", "bounded_exponential", "jittered_exponential"}:
        delay = base * (2 ** max(0, attempt_number - 1))
    else:
        raise ValueError(f"Unsupported backoff strategy kind: {kind}")

    if strategy.max_delay_seconds is not None:
        delay = min(delay, max(0.0, strategy.max_delay_seconds))

    if kind == "jittered_exponential":
        ratio = max(0.0, strategy.jitter_ratio or 0.0)
        jitter_rng = rng or random
        spread = delay * ratio
        delay = max(0.0, delay + jitter_rng.uniform(-spread, spread))

    return delay
