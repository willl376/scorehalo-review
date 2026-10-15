"""Pluggable recognition backends.

Importing this package registers every built-in backend (via the ``@register``
decorator in each module), so callers can immediately use ``get_backend``.
"""

from __future__ import annotations

from .base import (
    BackendError,
    BackendUnavailable,
    Capabilities,
    RecognitionBackend,
    RecognizeRequest,
    RecognizeResult,
)
from .registry import (
    all_backends,
    available_backends,
    describe_backends,
    get_backend,
    register,
)

# Import order matters: these modules run @register at import time.
from . import stub as _stub  # noqa: E402,F401
from . import homr_backend as _homr  # noqa: E402,F401
from . import oemer_backend as _oemer  # noqa: E402,F401
from . import audiveris_backend as _audiveris  # noqa: E402,F401

__all__ = [
    "BackendError",
    "BackendUnavailable",
    "Capabilities",
    "RecognitionBackend",
    "RecognizeRequest",
    "RecognizeResult",
    "all_backends",
    "available_backends",
    "describe_backends",
    "get_backend",
    "register",
]
