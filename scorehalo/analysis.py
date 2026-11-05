"""Theory-aware analysis and normalization, via music21 (BSD-3) -- optional.

Unlike the OMR engines (homr/Audiveris/oemer), music21 is a permissive library,
so it is safe to import directly into the ScoreHalo core.  It is still *optional*:
:func:`available` lets callers degrade gracefully when music21 is absent.

It provides three things the engine-agnostic :mod:`scorehalo.compare` cannot:

* **normalization** -- round-trip a document through music21, merging tied notes
  (``stripTies``) and optionally inferring missing clefs, producing cleaner
  MusicXML for downstream tools (e.g. Verovio).
* **harmonic reduction** -- ``chordify`` the whole score into one chord per
  moment, then label each chord with a Roman numeral relative to the detected
  key.  This is a *theory-aware fingerprint* of a page.
* **agreement** -- compare two such fingerprints (Roman-numeral distribution,
  key, consonance ratio) as a complement to the pitch-class metrics.

Install where wanted, typically in the isolated venv::

    ~/scorehalo/.venv/bin/pip install music21
"""

from __future__ import annotations

import importlib
import math
import warnings
import tempfile
from collections import Counter
from pathlib import Path


def available() -> bool:
    """True if music21 can be imported in this interpreter."""
    try:
        importlib.import_module("music21")
        return True
    except Exception:
        return False


def _require():
    if not available():
        raise RuntimeError(
            "music21 is not installed in this interpreter; "
            "install it (e.g. pip install music21) where analysis is wanted"
        )
    from music21 import converter

    return converter


def _parse(musicxml: str):
    converter = _require()
    return converter.parseData(musicxml, format="musicxml")


def _to_musicxml(score) -> str:
    """Serialize a music21 stream back to uncompressed MusicXML text."""
    with tempfile.TemporaryDirectory(prefix="scorehalo-m21-") as tmp:
        path = Path(tmp) / "out.musicxml"
        score.write("musicxml", fp=str(path))
        return path.read_text(encoding="utf-8")


def normalize(musicxml: str, *, strip_ties: bool = True, fix_clefs: bool = False) -> str:
    """Return a music21-normalized copy of ``musicxml``.

    ``strip_ties`` merges notes tied across barlines into single notes (so note
    counts and durations are not double-counted).  ``fix_clefs`` inserts a
    best-fit clef into any part that lacks one.
    """
    from music21 import clef, stream

    score = _parse(musicxml)
    if strip_ties:
        try:
            score = score.stripTies()
        except Exception:  # noqa: BLE001 - never fail normalization on a quirk
            pass
    if fix_clefs:
        warnings.warn("fix_clefs infers from encoded pitches, not source images; use only on a derivative", RuntimeWarning, stacklevel=2)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(musicxml)
        def local(tag): return tag.rsplit("}", 1)[-1]
        if any((local(e.tag) == "staves" and (e.text or "").strip() != "1") or
               (local(e.tag) == "staff" and (e.text or "").strip() != "1") for e in root.iter()):
            raise ValueError("Automatic clef inference is disabled for multistaff input; review the source")
        parts = score.parts if isinstance(score, stream.Score) else [score]
        for part in parts:
            if not part.recurse().getElementsByClass(clef.Clef):
                part.insert(0, clef.bestClef(part, recurse=True))
    return _to_musicxml(score)


def _roman_figures(score) -> Counter:
    """Roman-numeral histogram of the chordified score (relative to its key)."""
    from music21 import chord, roman

    try:
        key = score.analyze("key")
    except Exception:  # noqa: BLE001
        key = None

    figures: Counter = Counter()
    for this_chord in score.chordify().recurse().getElementsByClass(chord.Chord):
        if key is None:
            figures["?"] += 1
            continue
        try:
            figures[roman.romanNumeralFromChord(this_chord, key).figure] += 1
        except Exception:  # noqa: BLE001 - odd OMR chords have no figure
            figures["?"] += 1
    return figures


def harmonic_signature(musicxml: str) -> dict:
    """Reduce ``musicxml`` to a serializable theory-aware fingerprint."""
    from music21 import note, stream

    score = _parse(musicxml)

    key_name, key_confidence = None, None
    try:
        key = score.analyze("key")
        key_name = key.name
        key_confidence = round(float(key.correlationCoefficient), 3)
    except Exception:  # noqa: BLE001 - too few notes to detect a key
        key = None

    figures = _roman_figures(score)

    tree = score.asTimespans(flatten=True, classList=(note.GeneralNote,))
    consonant = dissonant = 0
    for verticality in tree.iterateVerticalities():
        try:
            if verticality.toChord().isConsonant():
                consonant += 1
            else:
                dissonant += 1
        except Exception:  # noqa: BLE001
            dissonant += 1
    total_verticalities = consonant + dissonant

    parts = score.parts if isinstance(score, stream.Score) else [score]
    measures = max((len(p.getElementsByClass(stream.Measure)) for p in parts), default=0)
    notes = sum(1 for _ in score.recurse().notes)

    return {
        "key": key_name,
        "key_confidence": key_confidence,
        "figures": dict(figures.most_common()),
        "moments": sum(figures.values()),
        "consonant": consonant,
        "dissonant": dissonant,
        "consonance_ratio": round(consonant / total_verticalities, 3) if total_verticalities else 0.0,
        "parts": len(parts),
        "measures": measures,
        "notes": notes,
    }


def _cosine(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    na = math.sqrt(sum(a.get(k, 0) ** 2 for k in keys))
    nb = math.sqrt(sum(b.get(k, 0) ** 2 for k in keys))
    if na == 0 or nb == 0:
        return 0.0
    return sum(a.get(k, 0) * b.get(k, 0) for k in keys) / (na * nb)


def _ratio(a: int, b: int) -> float:
    high = max(a, b)
    return (min(a, b) / high) if high else 1.0


def agreement(a: dict, b: dict) -> dict:
    """Compare two :func:`harmonic_signature` results (0..1, 1 = identical)."""
    return {
        "figure_cosine": round(_cosine(a.get("figures", {}), b.get("figures", {})), 3),
        "key_match": a.get("key") == b.get("key") and a.get("key") is not None,
        "consonance_closeness": round(
            1.0 - abs(a.get("consonance_ratio", 0.0) - b.get("consonance_ratio", 0.0)), 3
        ),
        "moments_ratio": round(_ratio(a.get("moments", 0), b.get("moments", 0)), 3),
    }
