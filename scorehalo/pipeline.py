"""End-to-end pipeline: one document in, a recognized reviewable score out.

This is the orchestration layer that ties the pieces together::

    ingest (PDF -> pages) -> recognize (per page) -> join -> export -> manifest

It writes everything into a single predictable :class:`~scorehalo.workdir.WorkDir`
and produces a top-level ``manifest.json`` shaped for the review UI
(:mod:`scorehalo.serve`), so a whole scorebook can be run and proofread with one
command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import export
from .backends import BackendError, get_backend
from .batch import PageOutcome, join_outcomes, recognize_pages
from .ingest import IngestedPage, ingest
from .workdir import WorkDir


@dataclass
class RunResult:
    """Summary of a pipeline run."""

    work: WorkDir
    page_count: int
    ok_count: int
    joined: str | None = None
    exports: dict[str, str] = field(default_factory=dict)
    manifest: str | None = None

    @property
    def root(self) -> Path:
        return self.work.root


def _build_manifest(
    work: WorkDir,
    *,
    engine: str,
    dpi: int,
    pages: list[IngestedPage],
    outcomes: list[PageOutcome],
    joined: str | None,
    exports: dict[str, str],
) -> dict:
    by_index = {p.index: p for p in pages}
    page_entries = []
    for outcome in outcomes:
        ingested = by_index.get(outcome.index)
        page_entries.append(
            {
                "index": outcome.index,
                "source": outcome.source,
                "source_page": ingested.source_page if ingested else None,
                "image": work.relative(ingested.image) if ingested else None,
                "musicxml_path": work.relative(outcome.musicxml_path),
                "ok": outcome.ok,
                "measures": outcome.measures,
                "notes": outcome.notes,
                "problems": outcome.problems,
                "error": outcome.error,
                "decision": None,
            }
        )
    return {
        "engine": engine,
        "dpi": dpi,
        "page_count": len(outcomes),
        "ok_count": sum(1 for o in outcomes if o.ok),
        "failed_count": sum(1 for o in outcomes if o.error),
        "joined": work.relative(joined),
        "exports": {fmt: work.relative(path) for fmt, path in exports.items()},
        "pages": page_entries,
    }


def run_pipeline(
    sources,
    work_root: str | Path,
    *,
    engine: str = "stub",
    dpi: int = 300,
    page_numbers: set[int] | None = None,
    render_svg: bool = False,
    make_pdf: bool = False,
    join: bool = True,
    options: dict | None = None,
    log=print,
) -> RunResult:
    """Run the full pipeline over ``sources`` (PDF/image paths) into ``work_root``."""
    work = WorkDir.create(work_root)
    work.log(f"run: engine={engine} dpi={dpi} sources={sources}")

    # 1. ingest
    log(f"ingesting ({dpi} dpi) ...")
    pages = ingest(sources, work.pages_dir, dpi=dpi, pages=page_numbers)
    log(f"  {len(pages)} page(s) ingested")
    work.log(f"ingested {len(pages)} page(s)")

    # 2. recognize
    backend = get_backend(engine)
    if not backend.is_available():
        raise BackendError(f"backend {engine!r} is not available on this machine")
    log(f"recognizing with {engine!r} ...")
    outcomes = recognize_pages(
        backend, [p.image for p in pages], str(work.out_dir), dpi=dpi, options=options
    )
    for outcome in outcomes:
        if outcome.ok:
            detail = f"{outcome.measures} measures, {outcome.notes} notes"
        elif outcome.error:
            detail = outcome.error
        else:
            detail = "; ".join(outcome.problems)
        log(f"  page {outcome.index:>3}: {'ok' if outcome.ok else 'bad':<3} {detail}")
        work.log(f"page {outcome.index}: ok={outcome.ok} {detail}")

    # 3. join
    joined_xml = None
    joined_path = None
    if join:
        candidate = work.score_musicxml
        joined_xml = join_outcomes(outcomes, str(candidate), new_page=True)
        if joined_xml is None:
            log("warning: no valid pages to join")
        else:
            joined_path = str(candidate)

    # 4. exports
    exports: dict[str, str] = {}
    if joined_path is not None:
        exports["musicxml"] = joined_path
        try:
            exports["mxl"] = export.write_mxl(joined_xml, work.score_mxl)
        except export.ExportError as exc:  # pragma: no cover
            log(f"warning: mxl export skipped: {exc}")
        if render_svg:
            try:
                exports["svg"] = str(work.svg_dir)
                export.write_svgs(joined_xml, work.svg_dir)
                log(f"rendered SVG -> {work.relative(work.svg_dir)}")
            except export.ExportError as exc:
                log(f"warning: SVG render skipped: {exc}")
        if make_pdf:
            try:
                exports["pdf"] = export.write_pdf(joined_xml, work.root / "score.pdf")
                log("wrote PDF score.pdf")
            except export.ExportError as exc:
                log(f"warning: PDF export skipped: {exc}")

    # 5. manifest
    manifest = _build_manifest(
        work, engine=engine, dpi=dpi, pages=pages, outcomes=outcomes,
        joined=joined_path, exports=exports,
    )
    manifest_path = work.write_manifest(manifest)
    work.log(f"manifest: {len(outcomes)} pages, {manifest['ok_count']} ok")

    return RunResult(
        work=work,
        page_count=len(outcomes),
        ok_count=manifest["ok_count"],
        joined=joined_path,
        exports=exports,
        manifest=manifest_path,
    )
