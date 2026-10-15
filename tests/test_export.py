"""Tests for score export (MusicXML, MXL, SVG, PDF)."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from scorehalo import export, render

_DOC = (
    '<?xml version="1.0"?>'
    '<score-partwise version="4.0">'
    "<part-list><score-part id=\"P1\"><part-name>x</part-name></score-part></part-list>"
    '<part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>'
    "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>"
    "</measure></part></score-partwise>"
)


class MusicXmlTests(unittest.TestCase):
    def test_write_musicxml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = export.write_musicxml(_DOC, Path(tmp) / "s.musicxml")
            self.assertEqual(Path(path).read_text(encoding="utf-8"), _DOC)

    def test_write_mxl_container_first_and_stored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = export.write_mxl(_DOC, Path(tmp) / "s.mxl")
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                self.assertEqual(names[0], "META-INF/container.xml")
                self.assertEqual(zf.getinfo(names[0]).compress_type, zipfile.ZIP_STORED)
                self.assertIn("score.xml", names)
                self.assertEqual(zf.read("score.xml").decode("utf-8"), _DOC)

    def test_musicxml_and_mxl_always_available(self) -> None:
        avail = export.available()
        self.assertTrue(avail["musicxml"])
        self.assertTrue(avail["mxl"])
        self.assertEqual(set(avail), {"musicxml", "mxl", "svg", "pdf"})


class RenderTests(unittest.TestCase):
    def test_write_svgs(self) -> None:
        if not render.available():
            self.skipTest("Verovio not installed")
        with tempfile.TemporaryDirectory() as tmp:
            paths = export.write_svgs(_DOC, Path(tmp) / "svg")
            self.assertTrue(paths)
            self.assertTrue(all(Path(p).is_file() for p in paths))

    def test_write_pdf(self) -> None:
        if not export.available()["pdf"]:
            self.skipTest("PDF export stack not installed")
        with tempfile.TemporaryDirectory() as tmp:
            path = export.write_pdf(_DOC, Path(tmp) / "s.pdf")
            self.assertEqual(Path(path).read_bytes()[:5], b"%PDF-")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
