"""Page restoration: mask out photos/graphics so the music survives.

This is the differentiator.  Classic OMR (Audiveris) tries to *decompose* a page
and gives up when it meets a photograph or illustration.  ScoreHalo instead
*restores* the page first: detect large non-music regions (colour blocks, solid
photographs) and paint them out, leaving the staff notation untouched, so the
recognition engine only ever sees music.

The detector is deliberately conservative so it is a no-op on an ordinary
grayscale music scan:

* **colour** pixels (high HSV saturation) are graphic/photo material;
* **solid ink blobs** survive a heavy morphological opening -- thin music strokes
  (staff lines, stems, noteheads) do not.

Regions below ``min_area_frac`` of the page are ignored.  OpenCV is required and
imported lazily (it is an optional dependency).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class RestoreError(RuntimeError):
    """Raised when a page cannot be restored (e.g. OpenCV missing)."""


@dataclass
class GraphicRegion:
    """A detected non-music region (bounding box, in output-page pixels)."""

    x: int
    y: int
    width: int
    height: int
    area: int
    kind: str  # "color" or "solid"

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "area": self.area,
            "kind": self.kind,
        }


def available() -> bool:
    """Whether the restoration stack (OpenCV) is importable."""
    try:
        import cv2  # noqa: F401

        return True
    except Exception:  # pragma: no cover - depends on the environment
        return False


def _require_cv2():
    try:
        import cv2

        return cv2
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise RestoreError(
            "page restoration needs OpenCV (pip install opencv-python-headless)"
        ) from exc


def detect_graphics(
    image: np.ndarray,
    *,
    max_dim: int = 1500,
    solid_frac: float = 0.02,
    sat_thresh: int = 60,
    min_area_frac: float = 0.02,
) -> tuple[np.ndarray, list[GraphicRegion]]:
    """Return a boolean mask (full image size) of non-music pixels + regions.

    ``solid_frac`` sets the opening kernel as a fraction of the (downscaled)
    page height: ink that survives it is a solid block, not a thin stroke.
    ``min_area_frac`` drops small specks.
    """
    cv2 = _require_cv2()
    h, w = image.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale < 1.0:
        small = cv2.resize(
            image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
        )
    else:
        small = image
    sh, sw = small.shape[:2]

    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    sat_mask = hsv[..., 1] > sat_thresh

    dark = (gray < 128).astype(np.uint8)
    k = max(3, int(round(sh * solid_frac)))
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    solid = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
    solid = cv2.dilate(solid, kernel, iterations=1)

    raw = (sat_mask | (solid > 0)).astype(np.uint8)
    raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(raw, connectivity=8)
    min_area = max(1, int(min_area_frac * sh * sw))
    keep = np.zeros_like(raw)
    regions: list[GraphicRegion] = []
    for i in range(1, count):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        rw = int(stats[i, cv2.CC_STAT_WIDTH])
        rh = int(stats[i, cv2.CC_STAT_HEIGHT])
        component = labels == i
        kind = "color" if sat_mask[component].mean() > 0.5 else "solid"
        keep[component] = 1
        regions.append(GraphicRegion(x, y, rw, rh, area, kind))

    if scale < 1.0:
        full = cv2.resize(keep, (w, h), interpolation=cv2.INTER_NEAREST)
        # scale region boxes back to full resolution
        inv = 1.0 / scale
        regions = [
            GraphicRegion(
                int(r.x * inv), int(r.y * inv), int(r.width * inv), int(r.height * inv), r.area, r.kind
            )
            for r in regions
        ]
    else:
        full = keep
    return full.astype(bool), regions


def mask_graphics(image: np.ndarray, **kwargs) -> tuple[np.ndarray, list[GraphicRegion]]:
    """Return a copy of ``image`` with detected graphic regions painted white."""
    mask, regions = detect_graphics(image, **kwargs)
    if not mask.any():
        return image.copy(), regions
    out = image.copy()
    out[mask] = 255
    return out, regions


def enhance(image: np.ndarray, *, clip_limit: float = 2.0, tile: int = 8) -> np.ndarray:
    """Contrast-limit adaptive histogram equalization (CLAHE) for faint scans."""
    cv2 = _require_cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    return cv2.cvtColor(clahe.apply(gray), cv2.COLOR_GRAY2RGB)


def restore_page(
    image: np.ndarray,
    *,
    mask: bool = True,
    enhance_contrast: bool = False,
    **kwargs,
) -> tuple[np.ndarray, dict]:
    """Mask graphics (colour-aware) and/or enhance an RGB page.

    Masking runs first so the colour-based detector still sees the original
    colour; enhancement then works on the cleaned page.  Returns the restored
    image and a small report dict for the manifest.
    """
    report: dict = {"regions": [], "enhanced": False}
    out = image
    if mask:
        out, regions = mask_graphics(out, **kwargs)
        report["regions"] = [r.to_dict() for r in regions]
    if enhance_contrast:
        out = enhance(out)
        report["enhanced"] = True
    return out, report
