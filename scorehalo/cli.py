"""Command line entry point: ``python -m scorehalo ...``."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import sys
from pathlib import Path

import scorehalo
from scorehalo import backends
from scorehalo.backends import BackendError, RecognizeRequest, get_backend
from scorehalo.batch import join_outcomes, recognize_pages, write_manifest
from scorehalo.compare import compare_images
from scorehalo.join import join_files
from scorehalo.validate import validate_musicxml


_OPTIONAL_DEPS = (
    ("music21", ("music21",), "theory-aware analysis (analyze, compare --analysis)"),
    ("verovio", ("verovio",), "SVG/PDF rendering (render, serve, run --render)"),
    ("pypdfium2", ("pypdfium2",), "PDF -> page raster (ingest, run)"),
    ("cv2", ("opencv-python-headless", "opencv-python"), "page triage / graphics masking"),
    ("numpy", ("numpy",), "numeric arrays"),
)


def _dep_status(module: str, dists: tuple[str, ...]) -> str | None:
    """Return the installed version of ``module`` or None if it cannot import."""
    try:
        importlib.import_module(module)
    except Exception:
        return None
    for dist in dists:
        try:
            return importlib.metadata.version(dist)
        except Exception:
            continue
    return "installed"


def _cmd_doctor(args: argparse.Namespace) -> int:
    import platform

    lines = ["ScoreHalo doctor", ""]
    lines.append(f"  version     {scorehalo.__version__}")
    lines.append(f"  python      {platform.python_version()}  ({sys.executable})")
    lines.append(f"  package     {Path(scorehalo.__file__).parent}")
    lines.append(f"  platform    {platform.system()} {platform.release()}")

    lines.append("")
    lines.append("optional dependencies")
    all_deps = True
    for module, dists, purpose in _OPTIONAL_DEPS:
        version = _dep_status(module, dists)
        all_deps = all_deps and version is not None
        mark = "OK" if version else "--"
        shown = version or f"missing (pip install {dists[0]})"
        lines.append(f"  [{mark}] {module:<10} {shown:<22} {purpose}")

    lines.append("")
    lines.append("recognition engines")
    for info in backends.describe_backends():
        mark = "OK" if info["available"] else "--"
        lines.append(f"  [{mark}] {info['name']:<10} {info['license']:<10} {info['notes']}")

    lines.append("")
    if all_deps:
        lines.append("summary: core + all optional features available")
    else:
        lines.append("summary: core runs; some optional features are unavailable")
    print("\n".join(lines))
    return 0


def _parse_pages(spec: str | None) -> set[int] | None:
    """Parse a page selection like ``"3-10,15"`` into a set of 1-based numbers."""
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty page selection component")
        bounds = part.split("-")
        if len(bounds) > 2:
            raise ValueError("invalid page range")
        low = int(bounds[0])
        high = int(bounds[-1])
        if low < 1 or high < low:
            raise ValueError("page numbers must be positive and ranges ascending")
        pages.update(range(low, high + 1))
    return pages


def _cmd_run(args: argparse.Namespace) -> int:
    from scorehalo.ingest import IngestError
    from scorehalo.pipeline import run_pipeline
    from scorehalo.workdir import default_root

    sources: list[Path] = []
    for item in args.sources:
        path = Path(item)
        if path.is_dir():
            sources.extend(sorted(p for p in path.iterdir() if p.is_file()))
        else:
            sources.append(path)
    if not sources:
        print("error: no input files", file=sys.stderr)
        return 2

    root = Path(args.work) if args.work else default_root(sources[0])
    options = {"cache": True} if args.cache else {}
    if args.enhance_clip is not None or args.enhance_tile is not None:
        options["enhance"] = {}
        if args.enhance_clip is not None:
            options["enhance"]["clip_limit"] = args.enhance_clip
        if args.enhance_tile is not None:
            options["enhance"]["tile"] = args.enhance_tile
    try:
        result = run_pipeline(
            [str(s) for s in sources],
            root,
            engine=args.backend,
            dpi=args.dpi,
            page_numbers=_parse_pages(args.pages),
            render_svg=args.render,
            make_pdf=args.pdf,
            options=options or None,
            triage=not args.no_triage,
            skip_text=args.skip_text,
            mask_graphics=args.mask_graphics,
            enhance=args.enhance,
        )
    except (IngestError, BackendError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"work dir: {result.root}")
    print(f"pages ok: {result.ok_count}/{result.page_count}")
    if result.joined:
        print(f"score:    {result.joined}")
    for fmt, path in result.exports.items():
        print(f"{fmt:<9}: {path}")
    print(f"manifest: {result.manifest}")

    if args.serve:
        from scorehalo.serve import serve as serve_review

        serve_review(str(result.root), port=args.port, open_browser=args.open)

    manifest = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
    return 0 if result.ok_count == result.page_count and not manifest.get("join_error") and not manifest.get("export_errors") else 1


def _cmd_backends(args: argparse.Namespace) -> int:
    described = backends.describe_backends()
    if args.json:
        print(json.dumps(described, indent=2))
        return 0
    for info in described:
        mark = "OK" if info["available"] else "--"
        print(f"[{mark}] {info['name']:<8} {info['license']:<10} {info['notes']}")
        requires = ",".join(info["requires"]) or "none"
        accepts = ",".join(info["accepts"])
        print(f"         accepts={accepts}  requires={requires}")
    return 0


def _cmd_recognize(args: argparse.Namespace) -> int:
    try:
        backend = get_backend(args.backend)
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not backend.is_available():
        print(f"error: backend {args.backend!r} is not available on this machine", file=sys.stderr)
        return 2

    request = RecognizeRequest(source=Path(args.source), page=args.page, dpi=args.dpi)
    try:
        result = backend.recognize(request)
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    problems = validate_musicxml(result.musicxml)
    for problem in problems:
        print(f"invalid: {problem}", file=sys.stderr)

    if args.output:
        Path(args.output).write_text(result.musicxml, encoding="utf-8")
        print(f"wrote {args.output} ({len(result.musicxml)} bytes, backend={result.backend})")
    else:
        sys.stdout.write(result.musicxml)

    return 1 if problems else 0


def _cmd_batch(args: argparse.Namespace) -> int:
    try:
        backend = get_backend(args.backend)
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not backend.is_available():
        print(f"error: backend {args.backend!r} is not available on this machine", file=sys.stderr)
        return 2

    sources = list(args.sources)
    print(f"recognizing {len(sources)} page(s) with backend {args.backend!r} ...", file=sys.stderr)
    outcomes = recognize_pages(backend, sources, args.output, dpi=args.dpi)
    for outcome in outcomes:
        if outcome.ok:
            status, detail = "ok", f"{outcome.measures} measures, {outcome.notes} notes"
        elif outcome.error:
            status, detail = "error", outcome.error
        else:
            status, detail = "invalid", "; ".join(outcome.problems)
        print(f"  page {outcome.index:>3}: {status:<7} {Path(outcome.source).name}  {detail}", file=sys.stderr)

    joined_path = None
    if not args.no_join:
        candidate = str(Path(args.output) / "score.musicxml")
        try:
            if join_outcomes(outcomes, candidate, new_page=not args.no_new_page) is not None:
                joined_path = candidate
            else:
                print("warning: no valid pages to join", file=sys.stderr)
        except ValueError as exc:
            print(f"warning: join blocked: {exc}", file=sys.stderr)

    manifest = write_manifest(outcomes, args.output, backend=args.backend, joined_path=joined_path)
    ok = sum(1 for outcome in outcomes if outcome.ok)
    print(f"done: {ok}/{len(outcomes)} pages ok; manifest={manifest}")
    if joined_path:
        print(f"joined score: {joined_path}")
    return 0 if ok == len(outcomes) and (args.no_join or joined_path) else 1


def _cmd_compare(args: argparse.Namespace) -> int:
    engines = [name.strip() for name in args.engines.split(",") if name.strip()]
    try:
        report = compare_images(
            args.sources, engines, args.output, cache=args.cache, harmonic=args.analysis
        )
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {report}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from scorehalo import analysis as analysis_mod

    if not analysis_mod.available():
        print("error: music21 is not installed in this interpreter", file=sys.stderr)
        return 2

    paths = [Path(p) for p in args.inputs]
    sigs: dict[str, dict] = {}
    for path in paths:
        try:
            sigs[str(path)] = analysis_mod.harmonic_signature(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report and stop
            print(f"error: {path}: {exc}", file=sys.stderr)
            return 1

    if args.normalize:
        try:
            Path(args.normalize).write_text(
                analysis_mod.normalize(
                    paths[0].read_text(encoding="utf-8"),
                    strip_ties=not args.keep_ties,
                    fix_clefs=args.fix_clefs,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"error: normalize: {exc}", file=sys.stderr)
            return 1
        print(f"wrote normalized {args.normalize}")

    if args.json:
        print(json.dumps(sigs, indent=2))
        return 0

    lines = ["# ScoreHalo harmonic analysis (music21)", ""]
    for name, sig in sigs.items():
        lines.append(f"## {name}")
        lines.append(f"- key: {sig['key']} (key correlation {sig['key_confidence']})")
        lines.append(
            f"- moments: {sig['moments']} | consonant {sig['consonant']} / "
            f"dissonant {sig['dissonant']} (ratio {sig['consonance_ratio']})"
        )
        lines.append(
            f"- parts/measures/notes: {sig['parts']}/{sig['measures']}/{sig['notes']}"
        )
        top = ", ".join(f"{f}:{n}" for f, n in list(sig["figures"].items())[:8])
        lines.append(f"- figures: {top}")
        lines.append("")
    if len(sigs) > 1:
        lines.append("## Theory-aware agreement")
        names = list(sigs)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                ag = analysis_mod.agreement(sigs[names[i]], sigs[names[j]])
                key = "yes" if ag["key_match"] else "no"
                lines.append(
                    f"- **{Path(names[i]).name} vs {Path(names[j]).name}**: "
                    f"figure cosine `{ag['figure_cosine']}` key match `{key}` "
                    f"consonance closeness `{ag['consonance_closeness']}` "
                    f"moments ratio `{ag['moments_ratio']}`"
                )
    report = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(report)
    return 0


def _cmd_join(args: argparse.Namespace) -> int:
    try:
        joined = join_files(list(args.inputs), args.output, new_page=not args.no_new_page)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    problems = validate_musicxml(joined)
    for problem in problems:
        print(f"invalid: {problem}", file=sys.stderr)
    print(f"wrote {args.output} ({len(joined)} bytes from {len(args.inputs)} document(s))")
    return 1 if problems else 0


def _cmd_render(args: argparse.Namespace) -> int:
    from scorehalo import render as render_mod

    if not render_mod.available():
        print("error: Verovio is not installed in this interpreter", file=sys.stderr)
        return 2
    text = Path(args.input).read_text(encoding="utf-8")
    try:
        svgs = render_mod.render_svgs(text, {"scale": args.scale})
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    for number, svg in enumerate(svgs, 1):
        (outdir / f"page-{number:03d}.svg").write_text(svg, encoding="utf-8")
    print(f"wrote {len(svgs)} SVG page(s) to {outdir}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from scorehalo.serve import serve as serve_review

    try:
        serve_review(args.outdir, host=args.host, port=args.port, open_browser=args.open)
    except (FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scorehalo",
        description="ScoreHalo -- pluggable optical music recognition.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check the environment: deps, engines, render")
    doctor.set_defaults(func=_cmd_doctor)

    run = sub.add_parser(
        "run", help="full pipeline: document -> recognized, joined, reviewable score"
    )
    run.add_argument("sources", nargs="+", help="PDF/image files, or a directory")
    run.add_argument("-b", "--backend", default="homr", help="engine (default: homr)")
    run.add_argument("-w", "--work", default=None, help="work dir (default: <stem>.work)")
    run.add_argument("--dpi", type=int, default=300, help="render DPI for PDFs")
    run.add_argument("--pages", default=None, help="PDF page selection, e.g. 3-10,15")
    run.add_argument("--render", action="store_true", help="also render SVG pages")
    run.add_argument("--pdf", action="store_true", help="also produce a PDF score")
    run.add_argument("--cache", action="store_true", help="pass --cache to the engine")
    run.add_argument(
        "--no-triage", action="store_true", help="disable page triage (recognize every page)"
    )
    run.add_argument(
        "--skip-text", action="store_true", help="also skip pages with no staff-like lines"
    )
    run.add_argument(
        "--mask-graphics", action="store_true", help="paint out photos/graphics before recognition"
    )
    run.add_argument("--enhance", action="store_true", help="CLAHE contrast enhancement before recognition")
    run.add_argument("--enhance-clip", type=float, help="CLAHE clip limit (default 2.0)")
    run.add_argument("--enhance-tile", type=int, help="CLAHE tile grid size (default 8)")
    run.add_argument("--serve", action="store_true", help="start review UI when done")
    run.add_argument("--port", type=int, default=8765, help="review UI port")
    run.add_argument("--open", action="store_true", help="open review UI in a browser")
    run.set_defaults(func=_cmd_run)

    listing = sub.add_parser("backends", help="list available recognition backends")
    listing.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    listing.set_defaults(func=_cmd_backends)

    recognize = sub.add_parser("recognize", help="recognize one page into MusicXML")
    recognize.add_argument("source", help="path to a PDF/PNG/JPG page")
    recognize.add_argument("-b", "--backend", default="stub", help="backend name (default: stub)")
    recognize.add_argument("-o", "--output", help="write MusicXML here (default: stdout)")
    recognize.add_argument("--page", type=int, default=None, help="1-based page number")
    recognize.add_argument("--dpi", type=int, default=300, help="render DPI for PDFs")
    recognize.set_defaults(func=_cmd_recognize)

    batch = sub.add_parser("batch", help="recognize several pages and join them into one score")
    batch.add_argument("sources", nargs="+", help="page images (PDF/PNG/JPG), in order")
    batch.add_argument("-b", "--backend", default="stub", help="backend name (default: stub)")
    batch.add_argument("-o", "--output", default="out", help="output directory (default: out)")
    batch.add_argument("--dpi", type=int, default=300, help="render DPI (passed to the backend)")
    batch.add_argument("--no-join", action="store_true", help="skip joining into score.musicxml")
    batch.add_argument(
        "--no-new-page",
        action="store_true",
        help="don't mark source-page breaks with <print new-page>",
    )
    batch.set_defaults(func=_cmd_batch)

    compare = sub.add_parser(
        "compare", help="run several backends on the same pages and report agreement"
    )
    compare.add_argument("sources", nargs="+", help="page images, in order")
    compare.add_argument(
        "-e", "--engines", default="homr,audiveris", help="comma-separated backend names"
    )
    compare.add_argument("-o", "--output", default="compare", help="output directory")
    compare.add_argument(
        "--cache",
        default=None,
        help="directory of cached <engine>/<stem>.musicxml results to reuse",
    )
    compare.add_argument(
        "--analysis",
        action="store_true",
        help="add a theory-aware (music21) harmonic section when music21 is available",
    )
    compare.set_defaults(func=_cmd_compare)

    analyze = sub.add_parser(
        "analyze", help="theory-aware analysis of MusicXML via music21 (optional dependency)"
    )
    analyze.add_argument("inputs", nargs="+", help="MusicXML files to analyze")
    analyze.add_argument("-o", "--output", help="write the report here (default: stdout)")
    analyze.add_argument("--json", action="store_true", help="emit signatures as JSON")
    analyze.add_argument(
        "--normalize", default=None, help="normalize the first input and write it here"
    )
    analyze.add_argument("--keep-ties", action="store_true", help="don't merge tied notes")
    analyze.add_argument("--fix-clefs", action="store_true", help="insert best-fit clefs")
    analyze.set_defaults(func=_cmd_analyze)

    join = sub.add_parser("join", help="join existing per-page MusicXML files into one score")
    join.add_argument("inputs", nargs="+", help="MusicXML files, in order")
    join.add_argument("-o", "--output", required=True, help="output MusicXML path")
    join.add_argument(
        "--no-new-page",
        action="store_true",
        help="don't mark source-page breaks with <print new-page>",
    )
    join.set_defaults(func=_cmd_join)

    render = sub.add_parser(
        "render", help="render a MusicXML file to SVG pages (requires Verovio)"
    )
    render.add_argument("input", help="MusicXML file to render")
    render.add_argument("-o", "--output", default="render", help="output directory")
    render.add_argument("--scale", type=int, default=40, help="Verovio scale (default 40)")
    render.set_defaults(func=_cmd_render)

    serve = sub.add_parser(
        "serve", help="run the local review UI for a batch output directory"
    )
    serve.add_argument("outdir", help="batch output directory (contains manifest.json)")
    serve.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8765, help="bind port (default 8765)")
    serve.add_argument("--open", action="store_true", help="open the UI in a browser")
    serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
