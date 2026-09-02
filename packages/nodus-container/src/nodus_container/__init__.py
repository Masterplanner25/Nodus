"""Container execution primitives for Nodus runtimes (#85).

An adapter over `std:subprocess`, not a container runtime: it builds an argv,
hands it to an injected runner, and shapes the result into what
`subprocess.run` already returns.

Read `docs/ecosystem/NODUS_CONTAINER.md` before extending it -- particularly the
capability decision, which is the reason this package declares no capability of
its own.
"""

from .models import SUPPORTED_ENGINES, ContainerResult, ContainerSpec, Mount
from .runner import ContainerSpecError, build_argv, run

__all__ = [
    "SUPPORTED_ENGINES",
    "ContainerResult",
    "ContainerSpec",
    "ContainerSpecError",
    "Mount",
    "build_argv",
    "run",
]
