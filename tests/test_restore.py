"""Tests for page restoration (graphics masking + enhancement)."""

from __future__ import annotations

import unittest

import numpy as np

from scorehalo import restore

H, W = 1400, 1000


def _music_page(block: str = "none", seed: int = 0) -> np.ndarray:
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    for base in range(120, H - 120, 160):
        for k in range(5):
            y = base + k * 12
            img[y : y + 3, :, :] = 0
    if block == "solid":
        img[300:700, 200:800, :] = 0
    elif block == "color":
        rng = np.random.default_rng(seed)
        img[300:700, 200:800, :] = rng.integers(0, 256, (400, 600, 3), dtype=np.uint8)
    elif block == "speck":
        img[300:320, 200:220, :] = 0
    return img


class AvailabilityTests(unittest.TestCase):
    def test_available(self) -> None:
        self.assertTrue(restore.available())


class DetectTests(unittest.TestCase):
    def test_pure_music_untouched(self) -> None:
        img = _music_page("none")
        out, regions = restore.mask_graphics(img)
        self.assertEqual(regions, [])
        self.assertTrue(np.array_equal(out, img))

    def test_solid_block_masked_music_kept(self) -> None:
        img = _music_page("solid")
        out, regions = restore.mask_graphics(img)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].kind, "solid")
        block = out[300:700, 200:800, :] == 255
        self.assertTrue(block.all())
        # staff line at y=120..122 survives outside the block (x < 200)
        self.assertTrue((out[120:123, :200, :] == 0).all())

    def test_color_block_masked(self) -> None:
        img = _music_page("color")
        out, regions = restore.mask_graphics(img)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].kind, "color")
        # essentially the whole block is painted out
        frac_white = float((out[300:700, 200:800, :] == 255).all(axis=2).mean())
        self.assertGreater(frac_white, 0.99)
        self.assertTrue((out[120:123, :200, :] == 0).all())

    def test_small_speck_ignored(self) -> None:
        img = _music_page("speck")
        _, regions = restore.detect_graphics(img)
        self.assertEqual(regions, [])


class RestorePageTests(unittest.TestCase):
    def test_report_shape(self) -> None:
        img = _music_page("solid")
        out, report = restore.restore_page(img, mask=True)
        self.assertIn("regions", report)
        self.assertFalse(report["enhanced"])
        self.assertEqual(len(report["regions"]), 1)
        self.assertNotEqual(out[500, 500].tolist(), [0, 0, 0])

    def test_enhance_only(self) -> None:
        img = _music_page("none")
        out, report = restore.restore_page(img, mask=False, enhance_contrast=True)
        self.assertTrue(report["enhanced"])
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, np.uint8)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
