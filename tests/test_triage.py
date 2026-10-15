"""Tests for page triage (synthetic images with known ground truth)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from scorehalo import triage


def _white(h: int = 800, w: int = 600) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _blank() -> np.ndarray:
    return _white()


def _color(h: int = 800, w: int = 600, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)


def _music(h: int = 1400, w: int = 1000) -> np.ndarray:
    """White page with repeating 5-line full-width staves."""
    img = _white(h, w)
    for base in range(120, h - 120, 160):
        for k in range(5):
            y = base + k * 12
            img[y : y + 3, :, :] = 0
    return img


def _text(h: int = 1400, w: int = 1000, seed: int = 1) -> np.ndarray:
    """White page with rows of short dashes (no full-width runs)."""
    img = _white(h, w)
    rng = np.random.default_rng(seed)
    for row in range(60, h - 60, 30):
        x = 40
        while x < w - 60:
            seg = int(rng.integers(10, 40))
            img[row : row + 8, x : x + seg, :] = 0
            x += seg + int(rng.integers(8, 20))
    return img


class ClassificationTests(unittest.TestCase):
    def test_blank(self) -> None:
        stats = triage.analyze(_blank())
        self.assertEqual(stats.label, triage.BLANK)
        self.assertLess(stats.ink_ratio, 0.01)

    def test_color_cover(self) -> None:
        stats = triage.analyze(_color())
        self.assertEqual(stats.label, triage.COVER)
        self.assertGreater(stats.colorfulness, 15)

    def test_music(self) -> None:
        stats = triage.analyze(_music())
        self.assertEqual(stats.label, triage.MUSIC)
        self.assertGreater(stats.line_score, 0.1)

    def test_text_has_no_full_width_lines(self) -> None:
        stats = triage.analyze(_text())
        self.assertEqual(stats.label, triage.TEXT)
        self.assertLess(stats.line_score, 0.01)


class DecisionTests(unittest.TestCase):
    def test_skip_blank_and_cover(self) -> None:
        self.assertFalse(triage.should_recognize(triage.analyze(_blank()))[0])
        self.assertFalse(triage.should_recognize(triage.analyze(_color()))[0])

    def test_keep_music_and_text_by_default(self) -> None:
        self.assertTrue(triage.should_recognize(triage.analyze(_music()))[0])
        self.assertTrue(triage.should_recognize(triage.analyze(_text()))[0])

    def test_skip_text_when_asked(self) -> None:
        keep, _ = triage.should_recognize(triage.analyze(_text()), skip_text=True)
        self.assertFalse(keep)
        keep, _ = triage.should_recognize(triage.analyze(_music()), skip_text=True)
        self.assertTrue(keep)


class HelperTests(unittest.TestCase):
    def test_analyze_path_and_dict(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.png"
            Image.fromarray(_music()).save(path)
            stats = triage.analyze_path(path)
            self.assertEqual(stats.label, triage.MUSIC)
            data = stats.to_dict()
            self.assertEqual(set(data), {"width", "height", "colorfulness", "ink_ratio", "line_score", "label", "reason"})

    def test_numpy_long_run_fallback(self) -> None:
        binary = np.zeros((4, 40), dtype=bool)
        binary[0, :] = True  # full run of 40
        binary[1, 0:5] = True  # short run
        frac = triage._long_run_fraction_numpy(binary, min_len=10)
        self.assertAlmostEqual(frac, 40 / 45, places=3)

    def test_numpy_fallback_empty(self) -> None:
        self.assertEqual(triage._long_run_fraction_numpy(np.zeros((3, 3), bool), 5), 0.0)

    def test_colorfulness_grayscale_is_zero(self) -> None:
        gray = np.full((50, 50, 3), 128, dtype=np.uint8)
        self.assertAlmostEqual(triage.colorfulness(gray), 0.0, places=5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
