"""Tests for page ingestion (PDF and image -> page PNGs)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scorehalo import ingest as ing


def _png(path: Path, size=(24, 24)) -> None:
    from PIL import Image

    Image.new("RGB", size, "white").save(path)


def _pdf(path: Path, pages: int = 2) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as handle:
        writer.write(handle)


class ErrorTests(unittest.TestCase):
    def test_missing_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ing.IngestError):
                ing.ingest(str(Path(tmp) / "nope.pdf"), Path(tmp) / "out")

    def test_unsupported_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "song.xyz"
            bad.write_text("x", encoding="utf-8")
            with self.assertRaises(ing.IngestError):
                ing.ingest(bad, Path(tmp) / "out")

    def test_bad_dpi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ing.IngestError):
                ing.ingest("x", Path(tmp), dpi=0)


class ImageIngestTests(unittest.TestCase):
    def test_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.png"
            _png(src)
            pages = ing.ingest(src, root / "out", dpi=200)
            self.assertEqual(len(pages), 1)
            self.assertTrue(Path(pages[0].image).is_file())
            self.assertEqual(pages[0].source_page, 1)
            self.assertEqual(pages[0].dpi, 200)

    def test_count_pages_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.png"
            _png(src)
            self.assertEqual(ing.count_pages(src), 1)


class PdfIngestTests(unittest.TestCase):
    def test_count_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "in.pdf"
            _pdf(pdf, pages=3)
            self.assertEqual(ing.count_pages(pdf), 3)
            pages = ing.ingest(pdf, root / "out", dpi=150, pages={1, 3})
            self.assertEqual(len(pages), 2)
            self.assertEqual([p.source_page for p in pages], [1, 3])
            self.assertEqual([p.index for p in pages], [1, 2])

    def test_all_pages_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "in.pdf"
            _pdf(pdf, pages=2)
            pages = ing.ingest(pdf, root / "out", dpi=100)
            self.assertEqual(len(pages), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
