"""A dependency-free backend that emits a tiny but valid MusicXML 4.0 score.

Its job is to keep the whole pipeline (registry -> interface -> validation ->
join/review) testable on any machine, including ones without homr/oemer/ONNX.
The output is deliberately deterministic so tests can assert on it.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from .base import Capabilities, RecognitionBackend, RecognizeRequest, RecognizeResult
from .registry import register

_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <work>
    <work-title>{title}</work-title>
  </work>
  <part-list>
    <score-part id="P1">
      <part-name>Music</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key>
          <fifths>0</fifths>
        </key>
        <time>
          <beats>4</beats>
          <beat-type>4</beat-type>
        </time>
        <clef>
          <sign>G</sign>
          <line>2</line>
        </clef>
      </attributes>
      <note>
        <pitch>
          <step>C</step>
          <octave>4</octave>
        </pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


@register
class StubBackend(RecognitionBackend):
    capabilities = Capabilities(
        name="stub",
        license="MIT",
        accepts=("pdf", "png", "jpg", "jpeg", "tif", "tiff"),
        multipage=False,
        camera_tolerant=False,
        requires=(),
        notes="Deterministic placeholder output; no real OMR.",
    )

    @classmethod
    def is_available(cls) -> bool:
        return True

    def recognize(self, request: RecognizeRequest) -> RecognizeResult:
        title = escape(request.source.stem or "untitled")
        return RecognizeResult(
            musicxml=_TEMPLATE.format(title=title),
            backend=self.name,
            source=str(request.source),
            warnings=["stub backend: output is a placeholder, not real recognition"],
            meta={"page": request.page, "dpi": request.dpi, "deterministic": True},
        )
