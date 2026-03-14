"""Backward-compat shim. Use `nodus.py` as the canonical runtime entrypoint."""

from nodus import *  # noqa: F401,F403


if __name__ == "__main__":
    from nodus import main

    raise SystemExit(main())
