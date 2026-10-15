"""Tests for the local review UI (stdlib HTTP server + index HTML)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scorehalo import render, serve

_DOC = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
    </measure>
  </part>
</score-partwise>
"""


def _make_outdir(root: Path) -> Path:
    (root / "pages").mkdir(parents=True)
    (root / "pages" / "page-001.musicxml").write_text(_DOC, encoding="utf-8")
    (root / "score.musicxml").write_text(_DOC, encoding="utf-8")
    manifest = {
        "backend": "stub",
        "page_count": 1,
        "ok_count": 1,
        "failed_count": 0,
        "joined": str(root / "score.musicxml"),
        "pages": [
            {
                "index": 1,
                "source": "/somewhere/page-030.png",
                "musicxml_path": str(root / "pages" / "page-001.musicxml"),
                "ok": True,
                "measures": 1,
                "notes": 1,
                "problems": [],
                "error": None,
            }
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


class SafePathTests(unittest.TestCase):
    def test_allows_file_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.xml").write_text("x", encoding="utf-8")
            self.assertEqual(serve.safe_path(root, "a.xml"), (root / "a.xml").resolve())

    def test_blocks_traversal_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(serve.safe_path(root, "../etc/passwd"))
            self.assertIsNone(serve.safe_path(root, "nope.xml"))


class IndexTests(unittest.TestCase):
    def test_load_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_outdir(Path(tmp))
            self.assertEqual(serve.load_manifest(root)["backend"], "stub")

    def test_index_lists_pages_and_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_outdir(Path(tmp))
            page = serve.render_index(root)
            self.assertIn("Page 1", page)
            self.assertIn("valid", page)
            self.assertIn("/raw?path=pages/page-001.musicxml", page)
            self.assertIn("/raw?path=score.musicxml", page)
            self.assertIn("/svg/page?page=1", page)

    def test_index_notes_missing_verovio(self) -> None:
        if render.available():
            self.skipTest("Verovio is installed here")
        with tempfile.TemporaryDirectory() as tmp:
            page = serve.render_index(_make_outdir(Path(tmp)))
            self.assertIn("Verovio is not installed", page)

    def test_index_shows_skipped_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_outdir(Path(tmp))
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["pages"].append(
                {
                    "index": 2,
                    "source": "/somewhere/cover.png",
                    "image": "pages/page-0002.png",
                    "musicxml_path": None,
                    "ok": False,
                    "measures": 0,
                    "notes": 0,
                    "problems": [],
                    "error": None,
                    "skipped": True,
                    "skip_reason": "non-music colour page",
                    "decision": "skipped",
                }
            )
            manifest["skipped_count"] = 1
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            page = serve.render_index(root)
            self.assertIn("skipped", page)
            self.assertIn("non-music colour page", page)
            self.assertIn("1 skipped", page)
            # a skipped page has no recognized thumbnail
            self.assertNotIn("/svg/page?page=2", page)


class ServerTests(unittest.TestCase):
    def test_make_server_requires_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                serve.make_server(Path(tmp))

    def test_make_server_binds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_outdir(Path(tmp))
            httpd = serve.make_server(root, "127.0.0.1", 0)
            try:
                self.assertGreater(httpd.server_port, 0)
            finally:
                httpd.server_close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
