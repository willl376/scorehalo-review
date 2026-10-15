"""Cheap whole-page triage: decide whether a page is worth recognizing as music.

The point of ScoreHalo is to survive songbooks whose pages mix music with covers,
photographs and illustration.  Before spending minutes of CPU on a page, classify
it from fast whole-page statistics:

* ``colorfulness`` -- Hasler & Susstrunk (2003) colourfulness; ~0 for a grayscale
  scan, high for a photo or colour cover.
* ``ink_ratio``    -- fraction of dark pixels; ~0 for a blank page, a few percent
  for music.
* ``line_score``   -- fraction of dark pixels belonging to long horizontal runs;
  staff lines push this high on real music pages.

Only ``numpy`` (plus Pillow to load files) is required.  OpenCV is used for the
morphology when available, with a dependency-free numpy fallback so triage still
works without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# classification labels
BLANK = "blank"
COVER = "cover"
PHOTO = "photo"
MUSIC = "music"
MIXED = "mixed"
TEXT = "text"

# tuning knobs (calibrated on the Carpenters scan; see reports/)
_COLORFUL = 15.0  # colourfulness above this smells like a colour cover/photo
_INK_BLANK = 0.004  # below this, treat as blank
_LINE_MUSIC = 0.10  # full-width-run fraction typical of staff lines
_LINE_MIXED = 0.03  # some full-width line structure, but not a full music page
_LINE_TEXT = 0.008  # opt-in: below this, no staff-like lines at all

_MAX_DIM = 1000  # downscale so analysis is fast and stable


@dataclass
class PageStats:
    """Fast statistics for one page image."""

    width: int
    height: int
    colorfulness: float
    ink_ratio: float
    line_score: float
    label: str = TEXT
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "colorfulness": round(self.colorfulness, 3),
            "ink_ratio": round(self.ink_ratio, 4),
            "line_score": round(self.line_score, 4),
            "label": self.label,
            "reason": self.reason,
        }


def load_rgb(path: str | Path) -> np.ndarray:
    """Load an image as an RGB uint8 array (requires Pillow)."""
    from PIL import Image

    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


def _downscale(rgb: np.ndarray, max_dim: int = _MAX_DIM) -> np.ndarray:
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return rgb
    from PIL import Image

    scale = max_dim / longest
    new = (max(1, int(w * scale)), max(1, int(h * scale)))
    return np.asarray(Image.fromarray(rgb).resize(new, Image.LANCZOS).convert("RGB"))


def colorfulness(rgb: np.ndarray) -> float:
    """Hasler & Susstrunk colourfulness (0 for pure grayscale)."""
    arr = rgb.astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    std = np.sqrt(rg.std() ** 2 + yb.std() ** 2)
    mean = np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    return float(std + 0.3 * mean)


def _gray(rgb: np.ndarray) -> np.ndarray:
    return np.asarray(
        np.dot(rgb[..., :3].astype(np.float32), [0.299, 0.587, 0.114]), dtype=np.float32
    )


def ink_ratio(gray: np.ndarray, threshold: int = 128) -> float:
    """Fraction of pixels darker than ``threshold``."""
    return float((gray < threshold).mean())


def _long_run_fraction_numpy(binary: np.ndarray, min_len: int) -> float:
    """Fraction of foreground pixels that sit in horizontal runs >= ``min_len``."""
    total = int(binary.sum())
    if total == 0:
        return 0.0
    in_runs = 0
    for row in binary:
        idx = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
        starts, ends = idx[0::2], idx[1::2]
        long_pairs = (ends - starts) >= min_len
        in_runs += int((ends[long_pairs] - starts[long_pairs]).sum())
    return in_runs / total


def line_score(gray: np.ndarray, threshold: int = 128) -> float:
    """Fraction of dark pixels that belong to long horizontal runs (staff lines)."""
    binary = gray < threshold
    width = gray.shape[1]
    min_len = max(8, width // 4)
    try:
        import cv2

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1))
        horizontal = cv2.morphologyEx(
            binary.astype(np.uint8), cv2.MORPH_OPEN, kernel, iterations=1
        )
        total = int(binary.sum())
        return float(horizontal.sum() / total) if total else 0.0
    except Exception:  # pragma: no cover - exercised without OpenCV
        return _long_run_fraction_numpy(binary, min_len)


def classify(stats: PageStats) -> PageStats:
    """Assign a label + human-readable reason to ``stats`` (in place, returned)."""
    if stats.ink_ratio < _INK_BLANK:
        stats.label, stats.reason = BLANK, "almost no ink"
    elif stats.colorfulness >= _COLORFUL and stats.line_score < _LINE_MIXED:
        stats.label = COVER
        stats.reason = f"colourful, no staff lines (colorfulness {stats.colorfulness:.0f})"
    elif stats.colorfulness >= _COLORFUL:
        stats.label = MIXED
        stats.reason = f"colourful with line structure (colorfulness {stats.colorfulness:.0f})"
    elif stats.line_score >= _LINE_MUSIC:
        stats.label, stats.reason = MUSIC, f"strong staff lines (line_score {stats.line_score:.2f})"
    elif stats.line_score >= _LINE_MIXED:
        stats.label, stats.reason = MIXED, f"some staff lines (line_score {stats.line_score:.2f})"
    elif stats.line_score >= _LINE_TEXT:
        stats.label, stats.reason = MIXED, f"sparse lines (line_score {stats.line_score:.2f})"
    else:
        stats.label, stats.reason = TEXT, "no staff-like lines"
    return stats


def analyze(image: np.ndarray, *, label: bool = True) -> PageStats:
    """Compute :class:`PageStats` for an RGB image (optionally classified)."""
    rgb = _downscale(image) if max(image.shape[:2]) > _MAX_DIM else image
    gray = _gray(rgb)
    stats = PageStats(
        width=int(image.shape[1]),
        height=int(image.shape[0]),
        colorfulness=colorfulness(rgb),
        ink_ratio=ink_ratio(gray),
        line_score=line_score(gray),
    )
    return classify(stats) if label else stats


def analyze_path(path: str | Path, *, label: bool = True) -> PageStats:
    """Convenience: load ``path`` and :func:`analyze` it."""
    return analyze(load_rgb(path), label=label)


def should_recognize(stats: PageStats, *, skip_text: bool = False) -> tuple[bool, str]:
    """Whether a page is worth sending to an OMR engine, with a reason.

    By default only *high-confidence* non-music pages are skipped (blank and
    colourful cover/photo pages), because skipping a real-but-sparse music page
    is worse than spending CPU on it.  Pass ``skip_text=True`` to additionally
    drop pages with no staff-like lines at all (a heuristic that saves time on
    lyric/front-matter pages).
    """
    if stats.label == BLANK:
        return False, "blank page"
    if stats.label == COVER:
        return False, f"non-music colour page ({stats.reason})"
    if skip_text and stats.label == TEXT:
        return False, f"no staff lines ({stats.reason})"
    return True, stats.reason or stats.label
