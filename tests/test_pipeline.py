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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
