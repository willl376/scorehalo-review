"""Cross-engine comparison: run several backends over the same images and report
how far their MusicXML outputs diverge.

Why this exists: different OMR engines (a transformer like homr vs. a classic
step pipeline like Audiveris) can each emit *valid* MusicXML that nonetheless
describes the page differently.  Before trusting any single engine we want a
concrete, engine-agnostic measure of agreement.

Metrics (stdlib only, no ground truth required):

* structural counts -- parts, measures, notes (total and pitched-only)
* **pitch-class cosine** -- similarity of the 12-bin pitch-class histograms
  (captures whether the two engines heard the same harmony)
* **note-signature Jaccard** -- multiset overlap of ``(midi pitch, duration in
  quarter notes)`` pairs (captures note content regardless of part splits)
* measure- and note-count ratios (``min/max``)

None of these is a substitute for a human proofread, but a high pitch-class
cosine + signature Jaccard across engines is a good "both engines agree" signal,
while a low score flags a page that needs eyes.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from .backends import BackendError, RecognizeRequest, get_backend
from .clefs import audit_clefs
from .validate import validate_musicxml

_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name]


def _note_midi(note: ET.Element) -> int | None:
    pitch = _child(note, "pitch")
    if pitch is None:
        return None
    step = _child(pitch, "step")
    octave = _child(pitch, "octave")
    if step is None or octave is None or not (step.text or "").strip():
        return None
    pc = _STEPS.get(step.text.strip().upper())
    if pc is None or not (octave.text or "").strip():
        return None
    alter = _child(pitch, "alter")
    accidental = int(alter.text) if alter is not None and (alter.text or "").strip() else 0
    return 12 * (int(octave.text) + 1) + pc + accidental


def analyze(text: str) -> dict:
    """Return structural + harmonic statistics for one MusicXML document."""
    problems = validate_musicxml(text)
    root = ET.fromstring(text)
    parts = _children(root, "part")

    measures_max = 0
    total_notes = 0
    pitched = 0
    pitch_classes = [0] * 12
    signature: Counter = Counter()

    for part in parts:
        divisions = 1
        measures = _children(part, "measure")
        measures_max = max(measures_max, len(measures))
        for measure in measures:
            attributes = _child(measure, "attributes")
            if attributes is not None:
                div = _child(attributes, "divisions")
                if div is not None and (div.text or "").strip():
                    divisions = int(div.text)
            for note in _children(measure, "note"):
                total_notes += 1
                midi = _note_midi(note)
                if midi is None:
                    continue
                pitched += 1
                pitch_classes[midi % 12] += 1
                dur = _child(note, "duration")
                quarters = (
                    int(dur.text) / divisions
                    if dur is not None and (dur.text or "").strip() and divisions
                    else 0.0
                )
                signature[(midi, round(quarters, 3))] += 1

    return {
        "clefs": audit_clefs(text),
        "valid": not problems,
        "problems": problems,
        "parts": len(parts),
        "measures": measures_max,
        "notes": total_notes,
        "pitched": pitched,
        "pitch_classes": pitch_classes,
        "signature": signature,
    }


def _cosine(a: list[int], b: list[int]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _jaccard(a: Counter, b: Counter) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    intersection = sum(min(a[k], b[k]) for k in keys)
    union = sum(max(a[k], b[k]) for k in keys)
    return intersection / union if union else 0.0


def _ratio(a: int, b: int) -> float:
    high = max(a, b)
    return (min(a, b) / high) if high else 1.0


def compare_images(images, engines, outdir, cache=None, harmonic=False) -> Path:
    """Run ``engines`` on each of ``images`` and write ``comparison.md``.

    ``cache`` (optional) is a directory of already-recognized ``<engine>/<stem>.musicxml``
    files; hits are reused instead of re-running the engine.  ``harmonic`` (optional)
    additionally reduces each engine's output to a theory-aware fingerprint via
    music21 (see :mod:`scorehalo.analysis`) when music21 is available.
    """
    images, engines = list(images), list(engines)
    # NOTE (Big Pickle, 2026-11-03): a single engine is a valid report (per-page
    # structural/agreement metrics for one transcript).  The bundle required two
    # distinct engines; that broke the repo's own single-engine test and a
    # useful workflow, so the requirement is not installed.
    if len(set(engines)) != len(engines):
        raise ValueError("Engine identifiers must be distinct")
    if any(not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name) for name in engines):
        raise ValueError("Invalid engine identifier")
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cache = Path(cache) if cache else None
    if harmonic:
        from . import analysis as analysis_mod

        harmonic = analysis_mod.available()
    else:
        analysis_mod = None

    records: list[dict] = []
    for image in images:
        image = Path(image)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        entry = {"image": str(image), "stem": image.stem, "engines": {}}
        for name in engines:
            cached = cache / name / f"{image.stem}-{digest}.musicxml" if cache else None
            if cached is not None and cached.is_file():
                text = cached.read_text(encoding="utf-8")
                seconds, origin = None, "cached"
            else:
                try:
                    backend = get_backend(name)
                    start = time.time()
                    result = backend.recognize(RecognizeRequest(source=image))
                    seconds, text, origin = time.time() - start, result.musicxml, "ran"
                except Exception as exc:
                    entry["engines"][name] = {"error": str(exc), "valid": False}
                    continue
                if cached is not None:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(text, encoding="utf-8")
            try:
                stats = analyze(text)
            except Exception as exc:
                entry["engines"][name] = {"error": f"Analysis failed: {exc}", "valid": False}
                continue
            stats["seconds"] = seconds
            stats["origin"] = origin
            if harmonic and analysis_mod is not None:
                try:
                    stats["harmonic"] = analysis_mod.harmonic_signature(text)
                except Exception:  # noqa: BLE001 - analysis is best-effort
                    stats["harmonic"] = None
            entry["engines"][name] = stats
        records.append(entry)

    report = render_report(records, list(engines), harmonic=harmonic)
    report_path = outdir / "comparison.md"
    report_path.write_text(report, encoding="utf-8")
    (outdir / "comparison.json").write_text(
        json.dumps(_serializable(records), indent=2), encoding="utf-8"
    )
    return report_path


def _serializable(records: list[dict]) -> list[dict]:
    clean = []
    for entry in records:
        engines = {}
        for name, stats in entry["engines"].items():
            engines[name] = {k: v for k, v in stats.items() if k != "signature"}
        clean.append({"image": entry["image"], "engines": engines})
    return clean


def _agreement(a: dict, b: dict) -> dict:
    return {
        "pitch_class_cosine": round(_cosine(a["pitch_classes"], b["pitch_classes"]), 3),
        "signature_jaccard": round(_jaccard(a["signature"], b["signature"]), 3),
        "measure_ratio": round(_ratio(a["measures"], b["measures"]), 3),
        "note_ratio": round(_ratio(a["pitched"], b["pitched"]), 3),
    }


def render_report(records: list[dict], engines: list[str], harmonic: bool = False) -> str:
    pairs = list(itertools.combinations(engines, 2))
    lines: list[str] = []
    lines.append("# ScoreHalo engine comparison\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Engines: {', '.join(engines)}\n")
    lines.append(f"Pages: {len(records)}\n")

    lines.append("\n## Per-page structure\n")
    header = "| page | engine | ok | parts | measures | notes | pitched | secs |"
    lines.append(header)
    lines.append("|" + "---|" * 8)
    for entry in records:
        for name in engines:
            stats = entry["engines"].get(name, {})
            if "error" in stats:
                lines.append(f"| {entry['stem']} | {name} | ERR | | | | | |")
                continue
            secs = "" if stats["seconds"] is None else f"{stats['seconds']:.1f}"
            lines.append(
                f"| {entry['stem']} | {name} | {'yes' if stats['valid'] else 'no'} "
                f"| {stats['parts']} | {stats['measures']} | {stats['notes']} "
                f"| {stats['pitched']} | {secs} |"
            )

    if pairs:
        lines.append("\n## Cross-engine agreement\n")
        lines.append("_pitch-class cosine_ and _signature Jaccard_ are 0..1 (1 = identical);\n"
                     "_measure/note ratio_ is min/max (1 = same count).\n")
        cols = " | ".join(f"{a} vs {b}" for a, b in pairs)
        lines.append(f"| page | {cols} |")
        lines.append("|" + "---|" * (len(pairs) + 1))
        for entry in records:
            cells = []
            for a, b in pairs:
                sa = entry["engines"].get(a, {})
                sb = entry["engines"].get(b, {})
                if "error" in sa or "error" in sb or "signature" not in sa:
                    cells.append("n/a")
                    continue
                ag = _agreement(sa, sb)
                cells.append(
                    f"pc={ag['pitch_class_cosine']:.2f} sig={ag['signature_jaccard']:.2f} "
                    f"m={ag['measure_ratio']:.2f} n={ag['note_ratio']:.2f}"
                )
            lines.append(f"| {entry['stem']} | " + " | ".join(cells) + " |")

        lines.append("\n## Aggregate\n")
        for a, b in pairs:
            cos, sig, meas, note = [], [], [], []
            for entry in records:
                sa = entry["engines"].get(a, {})
                sb = entry["engines"].get(b, {})
                if "error" in sa or "error" in sb or "signature" not in sa:
                    continue
                ag = _agreement(sa, sb)
                cos.append(ag["pitch_class_cosine"])
                sig.append(ag["signature_jaccard"])
                meas.append(ag["measure_ratio"])
                note.append(ag["note_ratio"])
            if cos:
                mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
                lines.append(
                    f"- **{a} vs {b}**: mean pitch-class cosine "
                    f"`{mean(cos):.3f}`, signature Jaccard `{mean(sig):.3f}`, "
                    f"measure ratio `{mean(meas):.3f}`, note ratio `{mean(note):.3f}` "
                    f"over {len(cos)} page(s)."
                )

    if harmonic:
        from . import analysis as analysis_mod

        _render_harmonic(lines, records, engines, pairs, analysis_mod)

    lines.append("\n## Clef audit (source accuracy not established)\n")
    for entry in records:
        for name, stats in entry["engines"].items():
            audit = stats.get("clefs")
            if audit is not None:
                lines.append(f"- {entry['stem']} / {name}: {len(audit['declarations'])} declarations, {len(audit['findings'])} findings; details in comparison.json")
    lines.append("\n## Reading this report\n")
    lines.append(
        "- Both engines emitting **valid** MusicXML does not mean they agree; the\n"
        "  agreement block is the signal.\n"
        "- High pitch-class cosine + high signature Jaccard indicate similar pitch/duration inventories;\n"
        "  onset, ordering, staff/voice assignments and source accuracy remain unverified.\n"
        "- Low signature Jaccard with high pitch-class cosine => same harmony, but\n"
        "  different note durations/voicing -- proofread before trusting.\n"
    )
    if harmonic:
        lines.append(
            "- _figure cosine_ / _key match_ / _consonance closeness_ are theory-aware\n"
            "  (music21): the same harmony reduced to Roman numerals should look alike\n"
            "  even when the two engines disagree on notation details.\n"
        )
    return "\n".join(lines) + "\n"


def _render_harmonic(lines, records, engines, pairs, analysis_mod) -> None:
    lines.append("\n## Harmonic analysis (music21)\n")
    lines.append(
        "Each engine's output reduced to a key + a Roman-numeral histogram over its\n"
        "chordified vertical sonorities (theory-aware, complements the metrics above).\n"
    )
    lines.append("| page | engine | key | conf | moments | consonance | top figures |")
    lines.append("|" + "---|" * 7)
    for entry in records:
        for name in engines:
            stats = entry["engines"].get(name, {})
            sig = stats.get("harmonic") if isinstance(stats, dict) else None
            if not sig:
                continue
            top = ", ".join(f"{fig}:{n}" for fig, n in list(sig["figures"].items())[:4])
            lines.append(
                f"| {entry['stem']} | {name} | {sig['key']} | {sig['key_confidence']} "
                f"| {sig['moments']} | {sig['consonance_ratio']} | {top} |"
            )

    if pairs:
        lines.append("\n### Theory-aware agreement\n")
        cols = " | ".join(f"{a} vs {b}" for a, b in pairs)
        lines.append(f"| page | {cols} |")
        lines.append("|" + "---|" * (len(pairs) + 1))
        for entry in records:
            cells = []
            for a, b in pairs:
                sa = entry["engines"].get(a, {}).get("harmonic")
                sb = entry["engines"].get(b, {}).get("harmonic")
                if not sa or not sb:
                    cells.append("n/a")
                    continue
                ag = analysis_mod.agreement(sa, sb)
                key = "yes" if ag["key_match"] else "no"
                cells.append(
                    f"fig={ag['figure_cosine']:.2f} key={key} con={ag['consonance_closeness']:.2f} "
                    f"mom={ag['moments_ratio']:.2f}"
                )
            lines.append(f"| {entry['stem']} | " + " | ".join(cells) + " |")
