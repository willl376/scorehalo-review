"""Tests for the cross-engine comparison metrics and report."""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scorehalo import compare

_DOC = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>2</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration><type>quarter</type></note>
      <note><rest/><duration>2</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


class AnalyzeTests(unittest.TestCase):
    def test_counts_and_pitch(self) -> None:
        stats = compare.analyze(_DOC)
        self.assertTrue(stats["valid"], stats["problems"])
        self.assertEqual(stats["parts"], 1)
        self.assertEqual(stats["measures"], 1)
        self.assertEqual(stats["notes"], 2)
        self.assertEqual(stats["pitched"], 1)
        self.assertEqual(stats["pitch_classes"][0], 1)  # C
        self.assertEqual(stats["signature"][(60, 1.0)], 1)  # C4, one quarter

    def test_invalid_document_flagged(self) -> None:
        stats = compare.analyze("<score-timewise/>")
        self.assertFalse(stats["valid"])
        self.assertTrue(stats["problems"])


class MetricTests(unittest.TestCase):
    def test_cosine_identical(self) -> None:
        self.assertAlmostEqual(compare._cosine([1, 2, 3], [1, 2, 3]), 1.0)

    def test_cosine_orthogonal(self) -> None:
        self.assertEqual(compare._cosine([1, 0], [0, 1]), 0.0)

    def test_jaccard_identical(self) -> None:
        c = Counter({(1, 2.0): 3})
        self.assertAlmostEqual(compare._jaccard(c, Counter(c)), 1.0)

    def test_jaccard_partial(self) -> None:
        a = Counter({(1, 2.0): 1})
        b = Counter({(1, 2.0): 1, (3, 4.0): 1})
        self.assertAlmostEqual(compare._jaccard(a, b), 0.5)

    def test_ratio(self) -> None:
        self.assertEqual(compare._ratio(4, 4), 1.0)
        self.assertAlmostEqual(compare._ratio(3, 4), 0.75)
        self.assertEqual(compare._ratio(0, 0), 1.0)


class AgreementTests(unittest.TestCase):
    def test_identical_documents_agree_fully(self) -> None:
        agreement = compare._agreement(compare.analyze(_DOC), compare.analyze(_DOC))
        self.assertEqual(agreement["pitch_class_cosine"], 1.0)
        self.assertEqual(agreement["signature_jaccard"], 1.0)
        self.assertEqual(agreement["measure_ratio"], 1.0)
        self.assertEqual(agreement["note_ratio"], 1.0)


class CompareImagesTests(unittest.TestCase):
    def test_single_engine_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.png").write_bytes(b"png")
            (root / "b.png").write_bytes(b"png")
            report = compare.compare_images(
                [root / "a.png", root / "b.png"], ["stub"], root / "out"
            )
            self.assertTrue(report.is_file())
            text = report.read_text(encoding="utf-8")
            self.assertIn("Per-page structure", text)
            self.assertIn("a", text)
            self.assertIn("b", text)
            self.assertTrue((root / "out" / "comparison.json").is_file())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
