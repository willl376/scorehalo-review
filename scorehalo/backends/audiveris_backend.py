"""Adapter that drives the Audiveris CLI as a subprocess.

Audiveris is a Java (AGPL-3.0) OMR engine with a very different, classic,
step-based pipeline: binarize -> grid (staff lines/barlines) -> headers -> beams
-> heads -> stems -> measures -> chords -> curves -> symbols -> rhythms -> page.
It is strong on clean printed scans and fragile on pages with graphics/photos.

Invoked strictly as an external tool -- we never link or embed its code.

CLI shape: ``Audiveris -batch -export -output <dir> <image-or-pdf>`` writes a
compressed MusicXML ``<stem>.mxl`` (a zip) plus a ``<stem>.omr`` book file into
``<dir>``.  This adapter extracts the MusicXML from the ``.mxl``.
"""

from __future__ import annotations

import glob
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from ._exec import run
from .base import (
    BackendError,
    BackendUnavailable,
    Capabilities,
    RecognitionBackend,
    RecognizeRequest,
    RecognizeResult,
)
from .registry import register


def _read_mxl(path: Path) -> str:
    """Extract the MusicXML document from a compressed MusicXML (``.mxl``) file."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        root_name: str | None = None
        if "META-INF/container.xml" in names:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            for element in container.iter():
                if element.tag.rsplit("}", 1)[-1] == "rootfile" and element.get("full-path"):
                    root_name = element.get("full-path")
                    break
        if root_name is None or root_name not in names:
            candidates = [
                n for n in names if n.endswith(".xml") and not n.startswith("META-INF")
            ]
            if not candidates:
                raise BackendError("no MusicXML document found inside .mxl")
            root_name = candidates[0]
        return archive.read(root_name).decode("utf-8")


@register
class AudiverisBackend(RecognitionBackend):
    capabilities = Capabilities(
        name="audiveris",
        license="AGPL-3.0",
        accepts=("pdf", "png", "jpg", "jpeg", "tif", "tiff"),
        multipage=True,
        camera_tolerant=False,
        requires=("audiveris",),
        notes="Classic Java step pipeline; strong on clean scans, weak on graphics/photos.",
    )

    @classmethod
    def _binary(cls) -> str | None:
        explicit = os.environ.get("AUDIVERIS_BIN")
        if explicit:
            return explicit if Path(explicit).exists() else shutil.which(explicit)
        found = shutil.which("audiveris") or shutil.which("Audiveris")
        if found:
            return found
        patterns = (
            str(Path.home() / "local/audiveris/app-*/bin/Audiveris"),
            str(Path.home() / "src/audiveris/app/build/install/app/bin/Audiveris"),
        )
        for pattern in patterns:
            matches = sorted(glob.glob(pattern))
            if matches:
                return matches[-1]
        return None

    @classmethod
    def is_available(cls) -> bool:
        return cls._binary() is not None

    def recognize(self, request: RecognizeRequest) -> RecognizeResult:
        binary = self._binary()
        if binary is None:
            raise BackendUnavailable(
                "Audiveris launcher not found; install it or set AUDIVERIS_BIN"
            )
        source = Path(request.source)
        if not source.is_file():
            raise BackendError(f"source not found: {source}")

        env = dict(os.environ)
        # NOTE (Big Pickle, 2026-11-03): JAVA_TOOL_OPTIONS makes the Gradle
        # start script's Java-version probe read "Picked up JAVA_TOOL_OPTIONS:"
        # as the version string and abort ("[: Picked: unexpected operator").
        # The launcher documents JAVA_OPTS for extra JVM options, so use that.
        env.setdefault("JAVA_OPTS", "-Djava.awt.headless=true")

        with tempfile.TemporaryDirectory(prefix="scorehalo-audiveris-") as tmp:
            outdir = Path(tmp)
            work = outdir / source.name
            shutil.copy2(source, work)

            cmd = [binary, "-batch", "-export", "-output", str(outdir), str(work)]
            proc = run(cmd, engine=self.name, env=env)

            mxl = outdir / f"{work.stem}.mxl"
            if proc.returncode != 0 or not mxl.is_file():
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                raise BackendError(f"Audiveris failed (rc={proc.returncode}): {tail}")
            musicxml = _read_mxl(mxl)

        return RecognizeResult(
            musicxml=musicxml,
            backend=self.name,
            source=str(source),
            warnings=[],
            meta={"page": request.page, "dpi": request.dpi, "format": "mxl->musicxml"},
        )
