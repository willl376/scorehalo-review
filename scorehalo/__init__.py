"""ScoreHalo -- graphics-tolerant OMR with pluggable recognition backends."""

from __future__ import annotations

from . import backends  # noqa: F401  (ensures built-in backends are registered)
from .backends import all_backends, available_backends, get_backend

try:
    from importlib import metadata

    __version__ = metadata.version("scorehalo")
except Exception:
    __version__ = "0.0.1"

__all__ = ["backends", "all_backends", "available_backends", "get_backend", "__version__"]
