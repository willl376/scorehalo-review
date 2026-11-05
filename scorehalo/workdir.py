"""The conventional ``work/`` layout and manifest helpers for a pipeline run.

Keeping every intermediate artifact in one predictable tree makes runs easy to
inspect, resume and serve.  The layout::

    work/
      pages/                 rasterized page images (from ingest)
      out/pages/             per-page MusicXML (from batch)
      out/manifest.json      batch-level manifest
      score.musicxml         joined score
      score.mxl              compressed MusicXML export
      svg/                   rendered SVG pages
      manifest.json          top-level manifest (serve-compatible)
      run.log                human-readable run log

The top-level ``manifest.json`` is deliberately shaped like the batch manifest
(``pages`` with ``musicxml_path``, plus ``joined``) so the review UI (:mod:`scorehalo.serve`)
can serve the whole ``work/`` directory.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .storage import atomic_json


@dataclass
class WorkDir:
    """A pipeline working directory rooted at :attr:`root`."""

    root: Path

    @classmethod
    def create(cls, root: str | Path) -> "WorkDir":
        wd = cls(Path(root))
        wd.pages_dir.mkdir(parents=True, exist_ok=True)
        wd.out_dir.mkdir(parents=True, exist_ok=True)
        wd.svg_dir.mkdir(parents=True, exist_ok=True)
        return wd

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"

    @property
    def out_dir(self) -> Path:
        return self.root / "out"

    @property
    def svg_dir(self) -> Path:
        return self.root / "svg"

    @property
    def score_musicxml(self) -> Path:
        return self.root / "score.musicxml"

    @property
    def score_mxl(self) -> Path:
        return self.root / "score.mxl"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def log_path(self) -> Path:
        return self.root / "run.log"

    def log(self, message: str) -> None:
        """Append a timestamped line to ``run.log``."""
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")

    def write_manifest(self, data: dict) -> str:
        atomic_json(self.manifest_path, data)
        return str(self.manifest_path)

    def read_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def relative(self, path: str | Path | None) -> str | None:
        """Return ``path`` relative to :attr:`root` (for the manifest/UI)."""
        if not path:
            return None
        try:
            return str(Path(path).resolve().relative_to(self.root.resolve()))
        except ValueError:
            return None


def default_root(source: str | Path, base: str | Path | None = None) -> Path:
    """Derive a work-directory name from an input path (``base/<stem>.work``)."""
    stem = Path(source).stem or "scorehalo"
    base_dir = Path(base) if base else Path.cwd()
    return base_dir / f"{stem}.work"
