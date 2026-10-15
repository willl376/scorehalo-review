"""Adapter that drives the ``homr`` CLI as a subprocess.

homr is AGPL-3.0 (its code *and* its weights), so it is only ever invoked as an
external tool -- never imported or linked.  See FIELD_MANUAL.md section 6.

CLI shape (from homr/homr/main.py): ``homer <image>`` writes ``<stem>.musicxml``
next to the input.  We copy the source into a temp dir so the caller's tree is
never touched.
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
class HomrBackend(RecognitionBackend):
    capabilities = Capabilities(
        name="homr",
        license="AGPL-3.0",
        accepts=("pdf", "png", "jpg", "jpeg"),
        multipage=True,
        camera_tolerant=True,
        requires=("homr",),
        notes="ViT/TrOMR transformer OMR; camera tolerant; MusicXML 4.0 out.",
    )

    @classmethod
    def _binary(cls) -> str | None:
        return os.environ.get("HOMR_BIN") or locate_tool("homr", "homer")

    @classmethod
    def is_available(cls) -> bool:
        return cls._binary() is not None

    def recognize(self, request: RecognizeRequest) -> RecognizeResult:
        binary = self._binary()
        if binary is None:
            raise BackendUnavailable("homr CLI not found; install homr (AGPL) or set HOMR_BIN")
        source = Path(request.source)
        if not source.is_file():
            raise BackendError(f"source not found: {source}")

        warnings: list[str] = []
        with tempfile.TemporaryDirectory(prefix="scorehalo-homr-") as tmp:
            work = Path(tmp) / source.name
            shutil.copy2(source, work)

            cmd = [binary, str(work)]
            if request.options.get("cache"):
                cmd.append("--cache")
            proc = run(cmd, engine=self.name)

            output = work.with_suffix(".musicxml")
            if proc.returncode != 0 or not output.is_file():
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                raise BackendError(f"homr failed (rc={proc.returncode}): {tail}")
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
