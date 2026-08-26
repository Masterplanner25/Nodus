"""Where a run's state lives, and what the Floor must therefore protect (#585).

A durable run is **one thing split across two directories**: the graph state and
checkpoint in `.nodus/graphs/`, and the run record in
`.nodus/workflow_framework/`. #476 gave those two halves a shared *lifecycle* —
cleanup and the record cap remove them together. Their *location* stayed
asymmetric: `NODUS_WORKFLOW_STORE_ROOT` moved the record half and nothing moved
the graph half, which was a hardcoded module constant. So "give this process its
own store" was not expressible, and every tenant in a process shared one
CWD-relative `.nodus/graphs/`.

`NODUS_RUN_STATE_ROOT` moves both halves together. There is deliberately **no**
per-half variable for graphs: a second knob would re-enable exactly the
half-relocated state this exists to prevent. `NODUS_WORKFLOW_STORE_ROOT` is kept
because it is documented and pinned by a test, but it now reads as the narrower,
legacy gesture that it is.

**Two families live under `.nodus/` and only one of them is here.** These are the
*run-state* paths, resolved against the current working directory. The others —
`cache/`, `modules/`, `deps.json` — are project-scoped, resolved against
`find_project_root()`, and have nothing to do with which run wrote them. Moving
those would change module resolution, so this variable is named for the half it
actually moves rather than for the whole directory.

**The Floor consults these roots.** `DEFAULT_FLOOR` forbids a Nodus program from
writing into the runtime's own state, and it used to answer that question by
looking for a literal `.nodus` path segment. Relocated state has no such segment,
so the supported way to move the store also moved it out of the Floor's reach —
demonstrated, not inferred: with `NODUS_WORKFLOW_STORE_ROOT` set, a guest calling
`fs.write("../relocated/pwned.txt", …)` succeeded, while the identical write to
the default location was denied. `run_state_roots()` is what closes that, and it
is why this module holds no imports beyond `os`: `capability.py` is a low-level
module and must be able to import it.
"""

import os


STATE_DIRNAME = ".nodus"
GRAPHS_DIRNAME = "graphs"
WORKFLOW_DIRNAME = "workflow_framework"
WORKFLOW_SQLITE_FILENAME = "workflow_framework.sqlite3"

RUN_STATE_ROOT_ENV = "NODUS_RUN_STATE_ROOT"
WORKFLOW_STORE_ROOT_ENV = "NODUS_WORKFLOW_STORE_ROOT"


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def run_state_root() -> str:
    """The directory holding both halves of a run's state.

    Read on every call rather than cached, because a host may set it after
    import and the test suite chdirs constantly; a cached value would make the
    answer depend on import order.
    """
    return _env(RUN_STATE_ROOT_ENV) or STATE_DIRNAME


def graph_root() -> str:
    """Graph state and checkpoints. Moves only with `NODUS_RUN_STATE_ROOT`."""
    return os.path.join(run_state_root(), GRAPHS_DIRNAME)


def workflow_store_root() -> str:
    """Run records.

    `NODUS_WORKFLOW_STORE_ROOT` still wins, so anything relying on it keeps
    working — but note that using it *alone* is the half-relocated state #585 is
    about: the records move and the graphs do not.
    """
    return _env(WORKFLOW_STORE_ROOT_ENV) or os.path.join(run_state_root(), WORKFLOW_DIRNAME)


def workflow_sqlite_path() -> str:
    """Default path for the SQLite store — a file beside the local store, not inside it."""
    return os.path.join(run_state_root(), WORKFLOW_SQLITE_FILENAME)


def run_state_roots() -> tuple[str, ...]:
    """Every directory the runtime owns run state in, absolute and de-duplicated.

    The Floor's deny-list. Order is not significant.
    """
    seen: dict[str, None] = {}
    for path in (run_state_root(), graph_root(), workflow_store_root()):
        seen.setdefault(os.path.abspath(path), None)
    return tuple(seen)


def is_inside_run_state(path: str) -> tuple[bool, str | None]:
    """Whether *path* is inside runtime-owned state, and which root caught it.

    Two rules, because neither alone is enough:

    - a literal `.nodus` path segment, which covers the default location and the
      project-scoped `cache/`, `modules/` and `deps.json` this module does not
      otherwise manage;
    - containment in a live run-state root, which covers relocated state that has
      no such segment.

    Segment comparison, not substring: a file named `my.nodus-notes.txt` is not
    caught, and `../.nodus/x` is.
    """
    normalised = os.path.normpath(path).replace("\\", "/")
    if any(segment == STATE_DIRNAME for segment in normalised.split("/")):
        return True, STATE_DIRNAME

    absolute = os.path.abspath(path)
    for root in run_state_roots():
        if absolute == root or absolute.startswith(root + os.sep):
            return True, root
    return False, None
