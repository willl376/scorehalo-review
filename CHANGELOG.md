# Changelog

All notable changes to ScoreHalo are recorded here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `clefs` module: read-only clef/staff audit. Records every `<clef>`
  declaration, assigns the active clef to each note by musical onset (measure
  inheritance, mid-measure changes, voice/`<backup>` ordering, grace notes,
  `additional`/`print-object="no"` handling, octave changes) and reports
  `clef_unresolved` / `clef_conflict` / `clef_sign_invalid` /
  `clef_staff_invalid` / `clef_line_invalid` instead of guessing.
- `verification` module: `verify_musicxml()` (structural + clef + meter findings)
  and `summary()` for manifests, so per-note detail stays out of
  `manifest.json` and lives in `verification.json`.
- `storage` module: atomic JSON/text writes for manifests, per-page MusicXML and
  the joined score (no half-written files after an interrupted run).
- `join` verifies the clef-declaration inventory across a join and blocks the
  output if a declaration changed.
- `compare` now includes a clef audit per engine and a "Clef audit" section in
  the report; its recognition cache is keyed by the image's SHA-256.
- `validate` checks part-ID consistency (missing / duplicate / part-list
  mismatch) and exposes `validate_clefs()`.
- `run` writes `verification.json`, reports `complete`, `join_error`,
  `export_errors`, `invalid_count`, `source_review: "not_performed"`, and exits
  non-zero when the join or an export failed.
- Review UI: `verification.json` download link, per-page findings list, clef
  declaration/finding counts, and an explicit "Source accuracy: not established"
  line.
- Review UI: **Accept** stores the page MusicXML's SHA-256 and appends to
  `review_history`; an acceptance whose file changed is shown as stale.
- `run` command: the one-command pipeline (`ingest -> recognize -> join ->
  export -> manifest`) for PDFs or images, with `--pages`, `--render`, `--pdf`,
  `--cache` and `--serve`.
- `ingest` module: PDF (pypdfium2) and image (Pillow) inputs -> `page-NNNN.png`.
- `workdir` module: a predictable run directory (`pages/`, `out/`, `svg/`,
  `score.*`, `manifest.json`, `run.log`).
- `export` module: write MusicXML, compressed MusicXML (`.mxl`), SVG pages
  (Verovio) and PDF (cairosvg + pypdf).
- `pipeline` module: orchestrates ingest/recognize/join/export and writes a
  review-UI-compatible `manifest.json` (`joined`, per-page `decision`, ...).
- `serve` review UI upgrade: original-scan + engraved thumbnails, click-to-zoom
  overlay, and per-page **Accept/Reject/Clear** that persists into
  `manifest.json`.
- `doctor` command: reports Python/package paths, optional dependencies
  (music21, verovio, pypdfium2, opencv, numpy) and recognition-engine
  availability in one glance.
- Installed `scorehalo` launcher (`~/.local/bin/scorehalo`) and a consolidated
  `.venv` (homr, verovio, music21, pypdfium2, cairosvg, pypdf).
- `_exec.locate_tool()`: engines installed beside the interpreter (e.g.
  `.venv/bin/homr`) are now found without PATH changes.
- `triage` module: cheap whole-page classification (blank / colour-cover / photo
  / music / mixed / text) from colourfulness, ink ratio and full-width line
  structure; high-confidence non-music pages are skipped before recognition.
- `restore` module: masks large non-music regions (colour blocks / solid photo
  areas) while preserving notation, plus optional CLAHE contrast enhancement.
- `run` flags `--no-triage`, `--skip-text`, `--mask-graphics` and `--enhance`;
  `--enhance-clip` / `--enhance-tile` tune CLAHE.
- Per-page `triage`/`restore`/`skipped`/`skip_reason` are written to
  `manifest.json` and `skipped_count` is reported.
- Review UI shows skipped pages with their reason and no recognized thumbnail.

### Fixed
- `audiveris` backend set `JAVA_TOOL_OPTIONS`, which the Gradle launcher's
  Java-version probe misreads as a version string (`[: Picked: unexpected
  operator`) and aborts; it now uses `JAVA_OPTS`.
- Duplicate `clef_conflict` findings: one was emitted per note after a
  conflicting declaration (19 identical entries on a real homr page). Now one
  finding per (part, staff, measure ordinal, onset).
- Manifest bloat: full per-note clef assignments were embedded per page (~160 kB
  per page). Manifests now carry `verification.summary()`.
- `render` retries a rare Verovio font-resource load race instead of surfacing a
  spurious failure/500.
- `serve` resolves relative manifest paths (the joined-score link was dropped)
  while still blocking traversal.
- `join` inserts `<print new-page="yes"/>` before notes/attributes for correct
  page breaks.

## [0.0.1] - 2026-10-15

### Added
- Pluggable recognition-backend interface (`RecognitionBackend` ABC + registry)
  with subprocess adapters for homr (AGPL), Audiveris (AGPL), oemer (MIT) and a
  dependency-free `stub` backend, so the core stays permissively licensed.
- `recognize` (one page), `batch` (many pages + join + manifest) and `join`
  (per-page MusicXML → one score) commands.
- `compare` command: run several engines over the same pages and report
  structural + pitch-class/agreement metrics (`comparison.md`/`.json`).
- `analysis` module (music21): theory-aware harmonic signatures, agreement and
  MusicXML normalization; exposed via `analyze` and `compare --analysis`.
- `render` module (Verovio) and a local review UI (`serve`).
- `validate` module: stdlib MusicXML 4.0 structural checks.
- Per-engine subprocess timeouts (`SCOREHALO_<ENGINE>_TIMEOUT`, default 1800s).

[Unreleased]: https://example.invalid/scorehalo
