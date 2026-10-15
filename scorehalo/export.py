"""Score export: MusicXML, compressed MusicXML (.mxl), SVG and PDF.

The pipeline's product is a joined MusicXML score; this module turns it into the
forms a user actually wants: a portable ``.musicxml``, a compressed ``.mxl`` for
notation apps, per-page ``.svg`` (Verovio) and a single multi-page ``.pdf``
(Verovio SVG -> cairosvg -> pypdf merge).

Optional tools (verovio/cairosvg/pypdf) are imported lazily and their absence
raises a clear :class:`ExportError` rather than a bare ImportError.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

_CONTAINER_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    "  <rootfiles>\n"
    '    <rootfile full-path="score.xml" '
    'media-type="application/vnd.recordare.musicxml+xml"/>\n'
    "  </rootfiles>\n"
    "</container>\n"
)


class ExportError(RuntimeError):
    """Raised when an export target cannot be produced here."""


def write_musicxml(musicxml: str, path: str | Path) -> str:
    """Write plain MusicXML text; return the path."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(musicxml, encoding="utf-8")
    return str(dest)


def write_mxl(musicxml: str, path: str | Path) -> str:
    """Write a compressed MusicXML (``.mxl``) archive.

    Per the MusicXML spec the ``META-INF/container.xml`` entry comes first and is
    stored uncompressed; the score itself is deflated.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("META-INF/container.xml")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, _CONTAINER_XML)
        zf.writestr("score.xml", musicxml)
    return str(dest)


def write_svgs(musicxml: str, outdir: str | Path, options: dict | None = None) -> list[str]:
    """Render ``musicxml`` to ``outdir/page-NNN.svg``; return the paths."""
    from . import render

    if not render.available():
        raise ExportError("SVG export needs Verovio (pip install verovio)")
    svgs = render.render_svgs(musicxml, options)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for number, svg in enumerate(svgs, 1):
        path = out / f"page-{number:03d}.svg"
        path.write_text(svg, encoding="utf-8")
        paths.append(str(path))
    return paths


def _require_cairosvg():
    try:
        import cairosvg
    except Exception as exc:  # pragma: no cover - exercised only without the dep
        raise ExportError("PDF export needs cairosvg (pip install cairosvg)") from exc
    return cairosvg


def _require_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as exc:  # pragma: no cover
        raise ExportError("PDF export needs pypdf (pip install pypdf)") from exc
    return PdfReader, PdfWriter


def write_pdf(musicxml: str, path: str | Path, options: dict | None = None) -> str:
    """Render ``musicxml`` to a single multi-page PDF; return the path."""
    from . import render

    if not render.available():
        raise ExportError("PDF export needs Verovio (pip install verovio)")
    cairosvg = _require_cairosvg()
    PdfReader, PdfWriter = _require_pypdf()

    svgs = render.render_svgs(musicxml, options)
    writer = PdfWriter()
    for svg in svgs:
        pdf_bytes = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
        writer.add_page(PdfReader(io.BytesIO(pdf_bytes)).pages[0])

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        writer.write(handle)
    return str(dest)


def available() -> dict[str, bool]:
    """Report which export formats can be produced in this interpreter."""
    from . import render

    def can(module: str) -> bool:
        try:
            __import__(module)
            return True
        except Exception:
            return False

    return {
        "musicxml": True,
        "mxl": True,
        "svg": render.available(),
        "pdf": render.available() and can("cairosvg") and can("pypdf"),
    }
