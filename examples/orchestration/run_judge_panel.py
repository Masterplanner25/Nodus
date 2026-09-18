"""Run judge_panel.nd against stub agents, and show that the fan-out overlaps.

`judge_panel.nd` and `agent_typed.nd` are library modules: they call agents
named "solver", "judge" and "synthesizer", and nothing in `nodus run` registers
those. This is the host half -- three handlers that each sleep DELAY_S to stand
in for a model call, registered on a `NodusRuntime`, which then runs
`judge_panel_demo.nd`.

Run from this directory:

    python run_judge_panel.py

The panel makes 3 + 3x2 + 1 = 10 agent calls. Serially that is 10 x DELAY_S;
the printed wall time is what the fan-out actually took.
"""

import os
import sys
import time

from nodus.runtime.embedding import NodusRuntime

HERE = os.path.dirname(os.path.abspath(__file__))
DELAY_S = 0.2  # each stub "thinks" for this long, like a model round-trip

# A deterministic score per angle, so the winner is stable across runs.
_SCORE = {"throughput": 7, "fairness": 9, "simplicity": 6}


def solver(payload: dict) -> dict:
    time.sleep(DELAY_S)
    bias = payload["bias"]
    return {
        "approach": f"{bias}-first",
        "design": f"a {payload['task']} that optimises for {bias}",
    }


def judge(payload: dict) -> dict:
    time.sleep(DELAY_S)
    angle = payload["candidate"]["angle"]
    return {
        "total": _SCORE[angle],
        "best_idea": f"{payload['judge']} liked the {angle} angle's {payload['candidate']['approach']} approach",
    }


def synthesizer(payload: dict) -> dict:
    time.sleep(DELAY_S)
    grafted = len(payload["graft_ideas"])
    return {"design": f"{payload['winner']['design']}, grafting {grafted} runner-up ideas"}


def main() -> int:
    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    rt.register_agent("solver", solver, description="proposes a design from one angle")
    rt.register_agent("judge", judge, description="scores a candidate")
    rt.register_agent("synthesizer", synthesizer, description="merges the winner with runner-up ideas")

    t0 = time.perf_counter()
    result = rt.run_file(os.path.join(HERE, "judge_panel_demo.nd"))
    elapsed = time.perf_counter() - t0

    sys.stdout.write(result.get("stdout", ""))
    if not result["ok"]:
        print(f"[error] {result['error']}")
        return 1
    print(f"wall time: {elapsed * 1000:.0f} ms  (10 agent calls; serial would be {10 * DELAY_S * 1000:.0f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
