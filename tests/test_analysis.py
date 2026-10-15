"""Tests for the optional music21-backed analysis layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scorehalo import analysis, compare
from scorehalo.validate import validate_musicxml

requires_music21 = unittest.skipUnless(analysis.available(), "music21 not installed")


def _doc(pitches) -> str:
    notes = "".join(
        f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
        f"<duration>1</duration><type>quarter</type></note>"
        for step, octave in pitches
    )
    return (
        '<?xml version="1.0"?>'
        '<score-partwise version="4.0">'
        '<part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1">'
        "<attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
        "<time><beats>4</beats><beat-type>4</beat-type></time></attributes>"
        + notes
        + "</measure></part></score-partwise>"
    )


_CMA = _doc(
    [("C", 4), ("E", 4), ("G", 4), ("C", 5), ("E", 4), ("G", 4), ("C", 5), ("E", 4)]
)


class AvailableTests(unittest.TestCase):
    def test_available_is_bool(self) -> None:
        self.assertIsInstance(analysis.available(), bool)


@requires_music21
class SignatureTests(unittest.TestCase):
    def test_everything_present(self) -> None:
        sig = analysis.harmonic_signature(_CMA)
        self.assertEqual(sig["key"], "C major")
        for key in ("key_confidence", "moments", "consonant", "dissonant",
                    "consonance_ratio", "parts", "measures", "notes"):
            self.assertIn(key, sig)
        self.assertEqual(sig["parts"], 1)
        self.assertEqual(sig["measures"], 1)
        self.assertEqual(sig["notes"], 8)
        self.assertGreaterEqual(sig["moments"], 1)
        self.assertIsInstance(sig["figures"], dict)

    def test_agreement_with_self_is_perfect(self) -> None:
        ag = analysis.agreement(analysis.harmonic_signature(_CMA),
                                analysis.harmonic_signature(_CMA))
        self.assertEqual(ag["figure_cosine"], 1.0)
        self.assertTrue(ag["key_match"])
        self.assertEqual(ag["consonance_closeness"], 1.0)
        self.assertEqual(ag["moments_ratio"], 1.0)

    def test_agreement_metrics_are_bounded(self) -> None:
        ag = analysis.agreement(analysis.harmonic_signature(_CMA),
                                analysis.harmonic_signature(_doc([("A", 3), ("C", 4)])))
        for key in ("figure_cosine", "consonance_closeness", "moments_ratio"):
            self.assertGreaterEqual(ag[key], 0.0)
            self.assertLessEqual(ag[key], 1.0)

    def test_keyless_document_does_not_crash(self) -> None:
        sig = analysis.harmonic_signature("<score-partwise version='4.0'/>")
        self.assertIsNone(sig["key"])
        self.assertEqual(sig["notes"], 0)


@requires_music21
class NormalizeTests(unittest.TestCase):
    def test_output_is_valid_musicxml(self) -> None:
        text = analysis.normalize(_CMA)
        self.assertFalse(validate_musicxml(text))
        # and it round-trips through the analyzer
        self.assertEqual(analysis.harmonic_signature(text)["notes"], 8)

    def test_round_trips_without_loss(self) -> None:
        sig = analysis.harmonic_signature(analysis.normalize(_CMA))
        self.assertEqual(sig["key"], "C major")


class UnavailableTests(unittest.TestCase):
    def test_require_raises_when_missing(self) -> None:
        if analysis.available():
            self.skipTest("music21 is installed; can't exercise the missing path")
        with self.assertRaises(RuntimeError):
            analysis.harmonic_signature(_CMA)


@requires_music21
class CompareHarmonicTests(unittest.TestCase):
    def test_report_includes_harmonic_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.png").write_bytes(b"png")
            (root / "b.png").write_bytes(b"png")
            report = compare.compare_images(
                [root / "a.png", root / "b.png"], ["stub"], root / "out", harmonic=True
            )
            text = report.read_text(encoding="utf-8")
            self.assertIn("Harmonic analysis (music21)", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
