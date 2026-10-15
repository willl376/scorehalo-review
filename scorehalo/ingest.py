"""Page ingestion: turn any supported input into a list of raster page images.

The recognition engines want *images*, but the common case for scanned songbooks
is a multi-page **PDF**.  So ingestion is the front door of the pipeline: a PDF
(or a plain image) is rasterized into one PNG per page at a chosen DPI, giving
the rest of ScoreHalo a single, uniform page model.

pypdfium2 (Apache/BSD, permissive) does the rasterizing; Pillow normalizes plain
images.  Both are imported lazily so importing this module never requires them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_PDF_SUFFIXES = {".pdf"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}


class IngestError(RuntimeError):
    """Raised when an input cannot be turned into page images."""


@dataclass(frozen=True)
class IngestedPage:
    """One rasterized page on disk, in document order."""

    index: int  # 1-based, across the whole ingestion run
    image: str  # path to the PNG page image
    source: str  # the original document it came from
    source_page: int  # 1-based page number within that document
    dpi: int

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "image": self.image,
            "source": self.source,
            "source_page": self.source_page,
            "dpi": self.dpi,
        }


def _require_pypdfium2():
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover - exercised only without the dep
        raise IngestError(
            "PDF input needs pypdfium2 (pip install pypdfium2)"
        ) from exc
    return pdfium


def _require_pillow():
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        raise IngestError("image input needs Pillow (pip install pillow)") from exc
    return Image


def count_pages(path: str | Path) -> int:
    """Number of pages in a PDF, or 1 for a single image."""
    source = Path(path)
    if not source.is_file():
        raise IngestError(f"input not found: {source}")
    suffix = source.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return 1
    if suffix not in _PDF_SUFFIXES:
        raise IngestError(f"unsupported input type: {source.suffix or '(none)'}")
    pdfium = _require_pypdfium2()
    with pdfium.PdfDocument(str(source)) as pdf:
        return len(pdf)


def _select(page_no: int, pages: set[int] | None) -> bool:
    return pages is None or page_no in pages


def _rasterize_pdf(
    source: Path, outdir: Path, *, dpi: int, pages: set[int] | None, start: int
) -> list[IngestedPage]:
    pdfium = _require_pypdfium2()
    scale = dpi / 72.0
    produced: list[IngestedPage] = []
    with pdfium.PdfDocument(str(source)) as pdf:
        total = len(pdf)
        for page_no in range(1, total + 1):
            if not _select(page_no, pages):
                continue
            bitmap = pdf[page_no - 1].render(scale=scale)
            image = bitmap.to_pil().convert("RGB")
            dest = outdir / f"page-{start + len(produced):04d}.png"
            image.save(dest, format="PNG")
            produced.append(
                IngestedPage(
                    index=start + len(produced),
                    image=str(dest),
                    source=str(source),
                    source_page=page_no,
                    dpi=dpi,
                )
            )
    return produced


def _rasterize_image(
    source: Path, outdir: Path, *, dpi: int, start: int
) -> list[IngestedPage]:
    Image = _require_pillow()
    dest = outdir / f"page-{start:04d}.png"
    with Image.open(source) as img:
        img.convert("RGB").save(dest, format="PNG")
    return [
        IngestedPage(
            index=start,
            image=str(dest),
            source=str(source),
            source_page=1,
            dpi=dpi,
        )
    ]


def ingest(
    sources: str | Path | list[str | Path],
    outdir: str | Path,
    *,
    dpi: int = 300,
    pages: set[int] | None = None,
) -> list[IngestedPage]:
    """Rasterize ``sources`` into ``outdir`` as ``page-NNNN.png`` files.

    ``sources`` may be a single path or a list, mixing PDFs and images.  ``pages``
    optionally restricts which 1-based PDF page numbers are kept (useful to skip
    covers); it does not apply to plain images.
    """
    if dpi <= 0:
        raise IngestError("dpi must be positive")
    if isinstance(sources, (str, Path)):
        sources = [sources]

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    produced: list[IngestedPage] = []
    for item in sources:
        source = Path(item)
        if not source.is_file():
            raise IngestError(f"input not found: {source}")
        suffix = source.suffix.lower()
        start = len(produced) + 1
        if suffix in _PDF_SUFFIXES:
            produced.extend(_rasterize_pdf(source, out, dpi=dpi, pages=pages, start=start))
        elif suffix in _IMAGE_SUFFIXES:
            produced.extend(_rasterize_image(source, out, dpi=dpi, start=start))
        else:
            raise IngestError(f"unsupported input type: {source.suffix or '(none)'}")

    if not produced:
        raise IngestError("no pages were produced (empty selection or empty documents)")
    return produced
