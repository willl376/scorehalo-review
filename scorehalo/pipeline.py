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
    meta: dict[int, dict],
    joined: str | None,
    exports: dict[str, str],
) -> dict:
    by_index = {o.index: o for o in outcomes}
    page_entries = []
    for ingested in pages:
        info = meta.get(ingested.index, {})
        outcome = by_index.get(ingested.index)
        skipped = not info.get("keep", True)
        page_entries.append(
            {
                "index": ingested.index,
                "source": ingested.source,
                "source_page": ingested.source_page,
                "image": work.relative(info.get("image") or ingested.image),
                "musicxml_path": work.relative(outcome.musicxml_path) if outcome else None,
                "ok": bool(outcome.ok) if outcome else False,
                "measures": outcome.measures if outcome else 0,
                "notes": outcome.notes if outcome else 0,
                "problems": outcome.problems if outcome else [],
                "error": outcome.error if outcome else None,
                "skipped": skipped,
                "skip_reason": info.get("skip_reason") if skipped else None,
                "triage": info.get("triage"),
                "restore": info.get("restore"),
                "decision": "skipped" if skipped else None,
            }
        )
    return {
        "engine": engine,
        "dpi": dpi,
        "page_count": len(pages),
        "ok_count": sum(1 for o in outcomes if o.ok),
        "failed_count": sum(1 for o in outcomes if o.error),
        "skipped_count": sum(1 for e in page_entries if e["skipped"]),
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
    triage: bool = True,
    skip_text: bool = False,
    mask_graphics: bool = False,
    enhance: bool = False,
    log=print,
) -> RunResult:
    """Run the full pipeline over ``sources`` (PDF/image paths) into ``work_root``.

    ``triage`` gates clearly non-music pages (blank/colour cover) before spending
    CPU; ``skip_text`` additionally drops pages with no staff-like lines.
    ``mask_graphics``/``enhance`` restore each kept page (paint out photos and/or
    raise contrast) before recognition.
    """
    work = WorkDir.create(work_root)
    work.log(f"run: engine={engine} dpi={dpi} sources={sources}")

    # 1. ingest
    log(f"ingesting ({dpi} dpi) ...")
    pages = ingest(sources, work.pages_dir, dpi=dpi, pages=page_numbers)
    log(f"  {len(pages)} page(s) ingested")
    work.log(f"ingested {len(pages)} page(s)")

    # 2. triage + optional restore
    from . import restore as restore_mod
    from . import triage as triage_mod

    options = options or {}
    enhance_kwargs = options.get("enhance") if isinstance(options.get("enhance"), dict) else None

    meta: dict[int, dict] = {}
    recognize_indices: list[int] = []
    recognize_images: list[str] = []
    for page in pages:
        info: dict = {"image": page.image}
        keep = True
        if triage:
            stats = triage_mod.analyze(triage_mod.load_rgb(page.image))
            info["triage"] = stats.to_dict()
            keep, why = triage_mod.should_recognize(stats, skip_text=skip_text)
            info["keep"] = keep
            info["skip_reason"] = None if keep else why
            log(f"  page {page.index:>3}: {stats.label:<6} {'keep' if keep else 'skip'} ({why})")
        if not keep:
            meta[page.index] = info
            continue
        if mask_graphics or enhance:
            restored, report = restore_mod.restore_page(
                triage_mod.load_rgb(page.image),
                mask=mask_graphics,
                enhance_contrast=enhance,
                enhance_kwargs=enhance_kwargs,
            )
            nregions = len(report.get("regions", []))
            if nregions or report.get("enhanced"):
                dest = work.pages_dir / f"page-{page.index:04d}.restored.png"
                from PIL import Image

                Image.fromarray(restored).save(dest)
                info["restore"] = report
                info["image"] = str(dest)
                log(f"  page {page.index:>3}: restored ({nregions} region(s), enhance={report.get('enhanced')})")
        meta[page.index] = info
        recognize_indices.append(page.index)
        recognize_images.append(info["image"])

    # 3. recognize
    backend = get_backend(engine)
    if not backend.is_available():
        raise BackendError(f"backend {engine!r} is not available on this machine")
    if recognize_images:
        log(f"recognizing {len(recognize_images)} page(s) with {engine!r} ...")
        outcomes = recognize_pages(
            backend, recognize_images, str(work.out_dir), dpi=dpi,
            options=options, indices=recognize_indices,
        )
    else:
        outcomes = []
    for outcome in outcomes:
        if outcome.ok:
            detail = f"{outcome.measures} measures, {outcome.notes} notes"
        elif outcome.error:
            detail = outcome.error
        else:
            detail = "; ".join(outcome.problems)
        log(f"  page {outcome.index:>3}: {'ok' if outcome.ok else 'bad':<3} {detail}")
        work.log(f"page {outcome.index}: ok={outcome.ok} {detail}")

    # 4. join
    joined_xml = None
    joined_path = None
    if join:
        candidate = work.score_musicxml
        joined_xml = join_outcomes(outcomes, str(candidate), new_page=True)
        if joined_xml is None:
            log("warning: no valid pages to join")
        else:
            joined_path = str(candidate)

    # 5. exports
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

    # 6. manifest
    manifest = _build_manifest(
        work, engine=engine, dpi=dpi, pages=pages, outcomes=outcomes,
        meta=meta, joined=joined_path, exports=exports,
    )
    manifest_path = work.write_manifest(manifest)
    work.log(
        f"manifest: {len(pages)} pages, {manifest['ok_count']} ok, "
        f"{manifest['skipped_count']} skipped"
    )

    return RunResult(
        work=work,
        page_count=len(pages),
        ok_count=manifest["ok_count"],
        joined=joined_path,
        exports=exports,
        manifest=manifest_path,
    )
