# Changelog

All notable changes to ScoreHalo are recorded here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `doctor` command: reports Python/package paths, optional dependencies
  (music21, verovio, pypdfium2, opencv, numpy) and recognition-engine
  availability in one glance.
- `_exec.locate_tool()`: engines installed beside the interpreter (e.g.
  `.venv/bin/homr`) are now found without PATH changes.

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
