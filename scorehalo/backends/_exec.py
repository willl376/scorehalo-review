"""Shared helper for running engine subprocesses with a wall-clock timeout.

Every backend drives its engine as an *external process*.  Without a timeout a
slow or wedged engine (e.g. oemer on a CPU-only box, where a single page can run
far longer than is useful) would block the whole pipeline indefinitely.
:func:`run` enforces a per-engine limit -- overridable via
``SCOREHALO_<ENGINE>_TIMEOUT`` (seconds) -- and turns an overrun into a clean
:class:`~scorehalo.backends.base.BackendError` instead of hanging.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .base import BackendError

DEFAULT_TIMEOUT = 1800.0


def locate_tool(*names: str) -> str | None:
    """Find an executable by trying each ``name`` on PATH, then beside the interpreter.

    The interpreter-adjacent lookup lets a backend find an engine installed in
    the same virtual environment (e.g. ``.venv/bin/homr``) without PATH
    gymnastics.
    """
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        beside = Path(sys.executable).parent / name
        if beside.is_file() and os.access(beside, os.X_OK):
            return str(beside)
    return None


def timeout_for(engine: str, default: float = DEFAULT_TIMEOUT) -> float:
    """Return the timeout (seconds) for ``engine``, honoring the env override."""
    raw = os.environ.get(f"SCOREHALO_{engine.upper()}_TIMEOUT")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def run(cmd, *, engine: str, timeout: float | None = None, cwd=None, env=None):
    """Run ``cmd`` with a timeout, raising ``BackendError`` on overrun."""
    limit = timeout_for(engine) if timeout is None else timeout
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=limit, cwd=cwd, env=env
        )
    except subprocess.TimeoutExpired as exc:
        raise BackendError(
            f"{engine} exceeded its {limit:.0f}s time limit "
            f"(raise SCOREHALO_{engine.upper()}_TIMEOUT to allow longer runs)"
        ) from exc
