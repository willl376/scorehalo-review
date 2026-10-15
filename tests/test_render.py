"""Tests for the MusicXML -> SVG render helper (Verovio is optional)."""

from __future__ import annotations

import unittest

from scorehalo import render

_DOC = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
  </part>
</score-partwise>
"""


class RenderAvailabilityTests(unittest.TestCase):
    def test_available_is_boolean(self) -> None:
        self.assertIsInstance(render.available(), bool)


class RenderSvgTests(unittest.TestCase):
    def test_unavailable_raises_runtime_error(self) -> None:
        if render.available():
            self.skipTest("Verovio is installed here")
        with self.assertRaises(RuntimeError):
            render.render_svgs(_DOC)

    def test_renders_when_available(self) -> None:
        if not render.available():
            self.skipTest("Verovio is not installed")
        svgs = render.render_svgs(_DOC)
        self.assertTrue(svgs)
        self.assertIn("<svg", svgs[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
