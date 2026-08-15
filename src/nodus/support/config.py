"""Runtime configuration defaults for service mode."""

import os

MAX_STEPS = 10_000_000
MAX_STDOUT_CHARS = 20_000
MAX_STACK_DEPTH = 10_000
EXECUTION_TIMEOUT_MS = 200
# Resuming is not the same shape of work as running. It reads the graph state and
# checkpoint from disk and rebuilds the graph — recompiling the stored workflow
# source — before any step executes, and all of that is charged to the same
# wall-clock budget. 200ms is not a sensible allowance for it: under load the
# resume died with "Execution timed out" instead of returning, which was one of
# the causes behind #376. Bounded, but proportionate to the work.
RESUME_TIMEOUT_MS = 30_000
SESSION_TIMEOUT_MS = 300_000
MAX_SESSIONS = 100
SNAPSHOT_DIR = os.environ.get("NODUS_SNAPSHOT_DIR", ".nodus/snapshots")
MAX_SNAPSHOTS = 200
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 7331
WORKER_SWEEP_INTERVAL_MS = 500
