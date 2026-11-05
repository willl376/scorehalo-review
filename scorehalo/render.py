"""MusicXML -> SVG rendering via Verovio, an optional dependency.

Verovio (LGPL-3.0) is a fast, embeddable engraver.  It is *optional*: the core
ScoreHalo pipeline never needs it, so :func:`available` lets callers degrade
gracefully (e.g. the review UI falls back to raw-XML downloads).

Install it where it is wanted, typically inside the isolated venv::

    ~/scorehalo/.venv/bin/pip install verovio

Kept as an engine-agnostic utility: whatever produced the MusicXML (homr,
Audiveris, oemer, stub) is irrelevant here.
"""

from __future__ import annotations

import importlib

_DEFAULT_OPTIONS = {
    "scale": 40,
    "adjustPageHeight": True,
    "footer": "none",
    "header": "none",
    "pageMarginLeft": 50,
    "pageMarginRight": 50,
    "pageMarginTop": 50,
    "pageMarginBottom": 50,
}


def available() -> bool:
    """True if Verovio can be imported in this interpreter."""
    try:
        importlib.import_module("verovio")
        return True
    except Exception:
        return False


def render_svgs(
    musicxml: str, options: dict | None = None, *, attempts: int = 3
) -> list[str]:
    """Render ``musicxml`` to one SVG string per page.

    Raises ``RuntimeError`` if Verovio is unavailable and ``ValueError`` if the
    document cannot be loaded.  Verovio has a rare one-off font-resource load
    race, so loading is retried a few times with a fresh toolkit before giving up.
    """
    if not available():
        raise RuntimeError(
            "Verovio is not installed in this interpreter; "
            "install it (e.g. pip install verovio) where rendering is wanted"
        )
    import verovio

    merged = dict(_DEFAULT_OPTIONS)
    if options:
        merged.update(options)

    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            toolkit = verovio.toolkit()
            if toolkit.setOptions(merged) is False:
                raise ValueError("Verovio rejected rendering options")
            if toolkit.loadData(musicxml):
                count = toolkit.getPageCount()
                svgs = [toolkit.renderToSVG(page) for page in range(1, count + 1)]
                if not svgs or any(not svg.strip() for svg in svgs):
                    raise ValueError("Verovio returned no usable pages")
                return svgs
            last_error = ValueError("Verovio could not load the MusicXML document")
        except Exception as exc:  # noqa: BLE001 - retry transient toolkit failures
            last_error = exc
    raise last_error or ValueError("Verovio could not load the MusicXML document")
