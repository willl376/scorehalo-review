"""Tests for the end-to-end pipeline (uses the dependency-free stub engine)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scorehalo.backends import BackendError
from scorehalo.pipeline import run_pipeline


def _png(path: Path, size=(40, 40)) -> None:
    from PIL import Image

    Image.new("RGB", size, "white").save(path)


def _silent(*_args, **_kwargs) -> None:
    return None


class PipelineLayoutTests(unittest.TestCase):
    def test_stub_run_writes_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "a.png")
            _png(root / "b.png")
            result = run_pipeline(
                [str(root / "a.png"), str(root / "b.png")],
                root / "work",
                engine="stub",
                triage=False,
                log=_silent,
            )
            work = root / "work"
            self.assertEqual(result.page_count, 2)
            self.assertEqual(result.ok_count, 2)
            self.assertTrue((work / "score.musicxml").is_file())
            self.assertTrue((work / "score.mxl").is_file())
            self.assertTrue((work / "manifest.json").is_file())
            self.assertTrue((work / "run.log").is_file())

            manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["engine"], "stub")
            self.assertEqual(manifest["joined"], "score.musicxml")
            self.assertEqual(manifest["ok_count"], 2)
            self.assertEqual(manifest["pages"][0]["musicxml_path"], "out/pages/page-001.musicxml")
            self.assertTrue(manifest["pages"][0]["image"].startswith("pages/"))
            self.assertIsNone(manifest["pages"][0]["decision"])

    def test_render_and_pdf_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "a.png")
            result = run_pipeline(
                [str(root / "a.png")],
                root / "w",
                engine="stub",
                triage=False,
                render_svg=True,
                make_pdf=True,
                log=_silent,
            )
            self.assertIn("svg", result.exports)
            self.assertIn("pdf", result.exports)
            self.assertTrue((root / "w" / "score.pdf").is_file())

    def test_unknown_backend_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "a.png")
            with self.assertRaises(BackendError):
                run_pipeline([str(root / "a.png")], root / "w", engine="no-such-engine", log=_silent)

    def test_page_selection(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "song.pdf"
            writer = PdfWriter()
            for _ in range(3):
                writer.add_blank_page(width=200, height=200)
            with open(pdf, "wb") as handle:
                writer.write(handle)
            result = run_pipeline(
                [str(pdf)],
                root / "w",
                engine="stub",
                dpi=100,
                page_numbers={1, 3},
                log=_silent,
            )
            self.assertEqual(result.page_count, 2)
            manifest = json.loads((root / "w" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([p["source_page"] for p in manifest["pages"]], [1, 3])


def _staff_png(path: Path, h: int = 400, w: int = 400, block: bool = False) -> None:
    import numpy as np
    from PIL import Image

    img = np.full((h, w, 3), 255, dtype=np.uint8)
    for base in range(60, h - 60, 80):
        for k in range(5):
            y = base + k * 10
            img[y : y + 2, :, :] = 0
    if block:
        img[200:260, 200:260, :] = 0
    Image.fromarray(img).save(path)


class PipelineTriageTests(unittest.TestCase):
    def test_triage_skips_blank_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "blank.png")  # pure white -> blank
            result = run_pipeline([str(root / "blank.png")], root / "w", engine="stub", log=_silent)
            manifest = json.loads((root / "w" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result.ok_count, 0)
            self.assertEqual(manifest["skipped_count"], 1)
            self.assertTrue(manifest["pages"][0]["skipped"])
            self.assertEqual(manifest["pages"][0]["decision"], "skipped")
            self.assertIsNone(manifest["pages"][0]["musicxml_path"])

    def test_triage_keeps_music_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _staff_png(root / "music.png")
            result = run_pipeline([str(root / "music.png")], root / "w", engine="stub", log=_silent)
            manifest = json.loads((root / "w" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result.ok_count, 1)
            self.assertFalse(manifest["pages"][0]["skipped"])
            self.assertEqual(manifest["pages"][0]["triage"]["label"], "music")

    def test_mask_graphics_restores_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _staff_png(root / "music.png", block=True)
            run_pipeline(
                [str(root / "music.png")], root / "w", engine="stub",
                mask_graphics=True, log=_silent,
            )
            manifest = json.loads((root / "w" / "manifest.json").read_text(encoding="utf-8"))
            page = manifest["pages"][0]
            self.assertIsNotNone(page["restore"])
            self.assertGreaterEqual(len(page["restore"]["regions"]), 1)
            self.assertIn("restored", page["image"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
