"""Batch recognition + page join.

Ties the single-page backend interface to a whole piece: recognize each page in
turn, save the per-page MusicXML, then join them into one score and write a
manifest describing what happened.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .backends.base import RecognitionBackend, RecognizeRequest
from .join import join_musicxml
from .validate import validate_musicxml


def _counts(musicxml: str) -> tuple[int, int]:
    """Return (measures_in_first_part, notes_total)."""
    try:
        root = ET.fromstring(musicxml)
    except ET.ParseError:
        return (0, 0)

    def ln(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    parts = [c for c in root if ln(c.tag) == "part"]
    measures = sum(1 for c in parts[0] if ln(c.tag) == "measure") if parts else 0
    notes = sum(1 for p in parts for m in p for n in m if ln(n.tag) == "note")
    return (measures, notes)


@dataclass
class PageOutcome:
    index: int
    source: str
    musicxml_path: str | None = None
    ok: bool = False
    measures: int = 0
    notes: int = 0
    problems: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "source": self.source,
            "musicxml_path": self.musicxml_path,
            "ok": self.ok,
            "measures": self.measures,
            "notes": self.notes,
            "problems": self.problems,
            "error": self.error,
        }


def recognize_pages(
    backend: RecognitionBackend,
    sources: list[str],
    outdir: str,
    *,
    dpi: int = 300,
    options: dict | None = None,
) -> list[PageOutcome]:
    """Recognize each source page; write per-page MusicXML under ``outdir/pages``."""
    out = Path(outdir)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    outcomes: list[PageOutcome] = []
    for index, source in enumerate(sources, start=1):
        src = Path(source)
        outcome = PageOutcome(index=index, source=str(src))
        try:
            result = backend.recognize(
                RecognizeRequest(source=src, page=index, dpi=dpi, options=options or {})
            )
        except Exception as exc:  # noqa: BLE001 - report, don't abort the batch
            outcome.error = str(exc)
            outcomes.append(outcome)
            continue

        xml_path = pages_dir / f"page-{index:03d}.musicxml"
        xml_path.write_text(result.musicxml, encoding="utf-8")
        outcome.musicxml_path = str(xml_path)
        outcome.problems = validate_musicxml(result.musicxml)
        outcome.ok = not outcome.problems
        outcome.measures, outcome.notes = _counts(result.musicxml)
        outcomes.append(outcome)
    return outcomes


def join_outcomes(
    outcomes: list[PageOutcome], out_path: str, *, new_page: bool = True
) -> str | None:
    """Join the OK pages into one score, write it, and return it (or None)."""
    documents = [
        Path(o.musicxml_path).read_text(encoding="utf-8")
        for o in outcomes
        if o.ok and o.musicxml_path
    ]
    if not documents:
        return None
    joined = join_musicxml(documents, new_page=new_page)
    Path(out_path).write_text(joined, encoding="utf-8")
    return joined


def write_manifest(
    outcomes: list[PageOutcome],
    outdir: str,
    *,
    backend: str,
    joined_path: str | None,
) -> str:
    """Write ``outdir/manifest.json`` summarising the batch; return its path."""
    manifest = {
        "backend": backend,
        "page_count": len(outcomes),
        "ok_count": sum(1 for o in outcomes if o.ok),
        "failed_count": sum(1 for o in outcomes if o.error),
        "joined": joined_path,
        "pages": [o.to_dict() for o in outcomes],
    }
    path = Path(outdir) / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(path)
