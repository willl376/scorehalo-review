"""Tests for the work-directory layout and manifest helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scorehalo.workdir import WorkDir, default_root


class WorkDirTests(unittest.TestCase):
    def test_create_makes_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wd = WorkDir.create(tmp)
            self.assertTrue(wd.pages_dir.is_dir())
            self.assertTrue(wd.out_dir.is_dir())
            self.assertTrue(wd.svg_dir.is_dir())

    def test_expected_paths(self) -> None:
        wd = WorkDir(Path("/x/y"))
        self.assertEqual(wd.score_musicxml, Path("/x/y/score.musicxml"))
        self.assertEqual(wd.score_mxl, Path("/x/y/score.mxl"))
        self.assertEqual(wd.manifest_path, Path("/x/y/manifest.json"))
        self.assertEqual(wd.log_path, Path("/x/y/run.log"))

    def test_log_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wd = WorkDir.create(tmp)
            wd.log("alpha")
            wd.log("beta")
            lines = wd.log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("alpha", lines[0])
            self.assertIn("beta", lines[1])

    def test_manifest_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wd = WorkDir.create(tmp)
            path = wd.write_manifest({"engine": "stub", "pages": []})
            self.assertTrue(Path(path).is_file())
            self.assertEqual(wd.read_manifest()["engine"], "stub")

    def test_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wd = WorkDir.create(tmp)
            page = wd.pages_dir / "page-0001.png"
            page.write_text("x", encoding="utf-8")
            self.assertEqual(wd.relative(page), "pages/page-0001.png")
            self.assertIsNone(wd.relative("/etc/passwd"))
            self.assertIsNone(wd.relative(None))

    def test_default_root(self) -> None:
        self.assertEqual(default_root("/a/b/song.pdf").name, "song.work")
        self.assertEqual(default_root("score.pdf", base="/tmp").name, "score.work")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
