"""Adapter that drives the ``oemer`` CLI as a subprocess.

oemer is MIT-licensed, so its code *could* be vendored -- but we keep the same
subprocess boundary as the other engines so backends stay interchangeable and
one engine crashing never takes the app down with it.

CLI shape (from oemer/ete.py): ``oemer <img> -o <outdir>`` writes
``<stem>.musicxml`` into ``<outdir>``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ._exec import locate_tool, run
from .base import (
    BackendError,
    BackendUnavailable,
    Capabilities,
    RecognitionBackend,
    RecognizeRequest,
    RecognizeResult,
)
from .registry import register


@register
class OemerBackend(RecognitionBackend):
    capabilities = Capabilities(
        name="oemer",
        license="MIT",
        accepts=("png", "jpg", "jpeg"),
        multipage=False,
        camera_tolerant=True,
        requires=("oemer",),
        notes="CNN seg + CV decoding; permissive license; MusicXML out (no MIDI).",
    )

    @classmethod
    def _binary(cls) -> str | None:
        return os.environ.get("OEMER_BIN") or locate_tool("oemer")

    @classmethod
    def is_available(cls) -> bool:
        return cls._binary() is not None

    def recognize(self, request: RecognizeRequest) -> RecognizeResult:
        binary = self._binary()
        if binary is None:
            raise BackendUnavailable("oemer CLI not found; install oemer (MIT) or set OEMER_BIN")
        source = Path(request.source)
        if not source.is_file():
            raise BackendError(f"source not found: {source}")

        warnings: list[str] = []
        with tempfile.TemporaryDirectory(prefix="scorehalo-oemer-") as tmp:
            outdir = Path(tmp)
            work = outdir / source.name
            shutil.copy2(source, work)

            cmd = [binary, str(work), "-o", str(outdir)]
            if request.options.get("save_cache"):
                cmd.append("--save-cache")
            if request.options.get("without_deskew"):
                cmd.append("-d")
            proc = run(cmd, engine=self.name)

            output = outdir / f"{work.stem}.musicxml"
            if proc.returncode != 0 or not output.is_file():
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                raise BackendError(f"oemer failed (rc={proc.returncode}): {tail}")
            if proc.stderr and proc.stderr.strip():
                warnings.append(proc.stderr.strip()[-500:])
            musicxml = output.read_text(encoding="utf-8")

        return RecognizeResult(
            musicxml=musicxml,
            backend=self.name,
            source=str(source),
            warnings=warnings,
            meta={"page": request.page, "dpi": request.dpi},
        )
