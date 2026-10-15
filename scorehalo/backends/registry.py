"""Name -> backend class registry.

Importing :mod:`scorehalo.backends` runs the ``@register`` decorators for every
built-in backend, so ``get_backend("homr")`` works without callers worrying
about import order.
"""

from __future__ import annotations

from typing import Type

from .base import BackendError, RecognitionBackend

_REGISTRY: dict[str, Type[RecognitionBackend]] = {}


def register(cls: Type[RecognitionBackend]) -> Type[RecognitionBackend]:
    """Class decorator that adds a backend to the global registry."""
    if not getattr(cls, "capabilities", None):
        raise BackendError(f"{cls.__name__} must define a `capabilities` attribute")
    name = cls.capabilities.name
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise BackendError(f"backend name {name!r} already registered by {existing.__name__}")
    _REGISTRY[name] = cls
    return cls


def all_backends() -> list[str]:
    """Every registered backend name, sorted."""
    return sorted(_REGISTRY)


def available_backends() -> list[str]:
    """Names of backends whose external tooling is present on this machine."""
    return [name for name in sorted(_REGISTRY) if _REGISTRY[name].is_available()]


def get_backend(name: str) -> RecognitionBackend:
    """Instantiate a backend by name."""
    try:
        cls = _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise BackendError(f"unknown backend {name!r}; known backends: {known}") from None
    return cls()


def describe_backends() -> list[dict]:
    """Capabilities + availability for every backend, for CLI/UI listing."""
    described = []
    for name in sorted(_REGISTRY):
        cls = _REGISTRY[name]
        info = cls.capabilities.to_dict()
        info["available"] = cls.is_available()
        described.append(info)
    return described
