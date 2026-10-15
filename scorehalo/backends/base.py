"""Core contract for pluggable music-recognition backends.

A *backend* turns one page (PDF/PNG/JPG) into MusicXML.  Keeping this boundary
narrow is deliberate: the strongest OMR engines carry incompatible licenses
(homr and Audiveris are AGPL-3.0; oemer is MIT), so each backend is a thin,
stateless adapter that drives its engine as an external tool -- never importing
or linking its code.  See FIELD_MANUAL.md section 6 (the licensing map).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class Capabilities:
    """Static description of what a backend can do and how it is licensed."""

    name: str
    license: str
    accepts: tuple[str, ...]
    output_formats: tuple[str, ...] = ("musicxml",)
    multipage: bool = False
    camera_tolerant: bool = False
    requires: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "license": self.license,
            "accepts": list(self.accepts),
            "output_formats": list(self.output_formats),
            "multipage": self.multipage,
            "camera_tolerant": self.camera_tolerant,
            "requires": list(self.requires),
            "notes": self.notes,
        }


@dataclass
class RecognizeRequest:
    """A single recognition job: one source page plus options."""

    source: Path
    page: int | None = None
    dpi: int = 300
    options: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = Path(self.source)
        if self.dpi <= 0:
            raise ValueError("dpi must be positive")
        if self.page is not None and self.page < 1:
            raise ValueError("page is 1-based and must be >= 1")


@dataclass
class RecognizeResult:
    """The MusicXML produced by a backend, plus provenance metadata."""

    musicxml: str
    backend: str
    source: str
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.musicxml.strip()


class BackendError(RuntimeError):
    """Base class for backend failures (unknown backend, bad invocation, ...)."""


class BackendUnavailable(BackendError):
    """Raised when a backend's external tool/dependencies are not installed."""


class RecognitionBackend(ABC):
    """Turns one page into a MusicXML string.

    Subclasses must define :attr:`capabilities`, :meth:`is_available` and
    :meth:`recognize`.  Construct them through the registry, which calls the
    class with no arguments.
    """

    capabilities: ClassVar[Capabilities]

    @property
    def name(self) -> str:
        return self.capabilities.name

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True if this backend can actually run here right now."""

    @abstractmethod
    def recognize(self, request: RecognizeRequest) -> RecognizeResult:
        """Recognize a single page and return the result."""

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{type(self).__name__} name={self.name!r} available={self.is_available()}>"
