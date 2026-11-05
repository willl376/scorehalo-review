# ScoreHalo

Graphics-tolerant optical music recognition (OMR) with **pluggable recognition
backends**.

This is the backend-interface prototype: a narrow, well-tested boundary so the
heavier OMR engines (homr, oemer, Audiveris, or a future custom model) can be
swapped behind one clean contract without rewriting the application.

## Why a pluggable boundary?

The strongest OMR engines carry incompatible licenses:

| Engine | License | Note |
|---|---|---|
| homr | AGPL-3.0 | also covers its weights; some training data is CC-BY-NC |
| Audiveris | AGPL-3.0 | network use triggers copyleft |
| oemer | MIT | permissive |

So each backend drives its engine **as an external tool (subprocess)** and never
links its code. The application core stays original and permissively licensed.
See `~/music-study/FIELD_MANUAL.md` section 6 for the full licensing map.

## Layout

```
scorehalo/
  backends/
    base.py          # RecognitionBackend ABC + Capabilities/Request/Result
    registry.py      # name -> backend class registry (@register)
    _exec.py         # shared subprocess runner with per-engine timeouts
    stub.py          # dependency-free deterministic backend (tests/pipeline wiring)
    homr_backend.py  # drives the `homr` CLI (AGPL, arm's length)
    audiveris_backend.py  # drives the `Audiveris` CLI (AGPL, arm's length; .mxl)
    oemer_backend.py # drives the `oemer` CLI (MIT, arm's length)
  validate.py        # stdlib MusicXML 4.0 structural checks
  clefs.py           # read-only clef/staff audit (declarations + per-note assignment)
  verification.py    # per-page verification report + compact manifest summary
  storage.py         # atomic file writes (JSON/text) for manifests and scores
  ingest.py          # PDF/image -> page PNGs (pypdfium2 + Pillow)
  workdir.py         # predictable run directory + manifest/log helpers
  triage.py          # fast page classification (blank/cover/photo/music/text)
  restore.py         # graphics masking + contrast enhancement (the differentiator)
  join.py            # partwise page joiner (concat measures, mark page breaks)
  batch.py           # recognize many pages + join into one score + manifest
  pipeline.py        # ingest -> recognize -> join -> export -> manifest (the `run` verb)
  export.py          # write MusicXML / MXL / SVG / PDF (cairosvg + pypdf)
  compare.py         # run several engines on the same pages + agreement report
  analysis.py        # theory-aware normalize/analyze via music21 (optional dependency)
  render.py          # MusicXML -> SVG pages via Verovio (optional dependency)
  serve.py           # local review UI (stdlib HTTP server)
  cli.py             # `python -m scorehalo ...`
tests/               # unittest contract tests
```

## Quick start

One command turns a scanned songbook PDF (or images) into a reviewable score:

```bash
scorehalo run songbook.pdf -b homr --render --pdf --serve
#   -> songbook.work/pages/page-0001.png ...   (rasterized source pages)
#   -> songbook.work/out/pages/page-001.musicxml ...  (per-page recognition)
#   -> songbook.work/score.musicxml / .mxl      (joined score)
#   -> songbook.work/score.pdf, songbook.work/svg/  (rendered preview)
#   -> songbook.work/manifest.json              (per-page status + decisions)
```

`scorehalo doctor` prints the interpreter/package paths, optional dependencies
and which recognition engines are runnable here — the first thing to check on a
new machine.

## Verification: structural, clef and source accuracy

Every run writes **two** levels of report, because they answer different
questions:

- `manifest.json` — the review contract: per-page status, measure/note counts,
  warnings, triage/restore data, the reviewer's `decision`, and a **compact**
  verification summary (`clefs.declarations`, finding list, counts). It stays
  small (a few kB per page) so it can be read by the UI and by scripts.
- `verification.json` — the full evidence: every clef declaration, the active
  clef for each note with its onset and origin, overfull-measure findings, and
  the joined score's report. This is the file to open when a page looks wrong.

What the checks mean, stated plainly:

- **Structural checks passed** means the document is well-formed MusicXML 4.0
  with consistent part ids and non-empty parts. It does **not** mean the notes
  are right.
- **Clef audit** (`clefs.py`) is read-only: it records every `<clef>` the
  encoder wrote, assigns the active clef to each note by musical onset (handling
  inheritance across measures, mid-measure changes, voice/`<backup>` ordering,
  grace notes and `print-object="no"`), and reports what it cannot resolve
  (`clef_unresolved`, `clef_conflict`, `clef_staff_invalid`, ...). It never
  guesses and never edits the score.
- **Source accuracy is not established.** No automated check compares a
  transcription against the scanned page. A clean report means "nothing
  contradicts itself", not "this matches the print". The review UI says so on
  every page.

Because of that, `analyze --fix-clefs` refuses multistaff input: it infers clefs
from encoded pitches, which would hide exactly the error you are looking for.

In the review UI, **Accept** records the SHA-256 of the page's MusicXML. If the
file changes afterwards, the acceptance is shown as stale and the page needs
review again; every decision is appended to `review_history`.

## Graphics tolerance (the differentiator)

Classic OMR (Audiveris) tries to *decompose* a page and breaks down when it meets
a photograph or illustration. ScoreHalo front-loads two cheap, conservative steps
so the engine only ever sees music:

- **Triage** (`triage.py`) classifies each page from whole-page statistics —
  colourfulness (Hasler & Süsstrunk), ink ratio and full-width line structure —
  and skips high-confidence non-music pages (blank, colour cover/photo) before
  spending CPU. `--skip-text` additionally drops pages with no staff-like lines;
  the default never skips a page that has plausible line structure, so sparse
  music is never silently lost.
- **Restore** (`restore.py`) paints out large non-music regions (colour blocks
  and solid photo areas) while leaving the staff notation intact, and can raise
  faint scans with CLAHE (`--enhance`). It is a no-op on an ordinary grayscale
  music page.

Both are reflected in `manifest.json` (per-page `triage`, `restore`, `skipped`,
`skip_reason`) and surfaced in the review UI, where skipped pages are shown with
a reason and no recognized thumbnail. OpenCV is required for restore
(`pip install opencv-python-headless`); triage works from numpy alone.

## Usage

```bash
# what can run here? (paths, optional deps, engines)
python -m scorehalo doctor

# one command: PDF/images -> pages -> recognized -> joined -> exported -> review
python -m scorehalo run songbook.pdf --backend homr -w songbook.work --render --pdf
python -m scorehalo run songbook.pdf --pages 3-10,15        # skip covers/front matter
python -m scorehalo run scan.png --backend stub --serve     # then open the review UI

# graphics-tolerant pass: skip non-music pages and paint out photos/illustrations
python -m scorehalo run songbook.pdf --mask-graphics --enhance
python -m scorehalo run songbook.pdf --skip-text            # also drop lyric/front-matter pages
python -m scorehalo run songbook.pdf --no-triage            # recognize every page

# list backends and whether each can run here
python -m scorehalo backends
python -m scorehalo backends --json

# recognize a single page (stub works everywhere; homr/oemer need their tools installed)
python -m scorehalo recognize page.pdf --backend stub -o out.musicxml
python -m scorehalo recognize page.png --backend homr -o out.musicxml

# recognize a whole multi-page piece and join it into one score
python -m scorehalo batch pages/*.png --backend homr -o out/
#   -> out/pages/page-001.musicxml ...   (per page)
#   -> out/score.musicxml                (joined, page breaks marked)
#   -> out/manifest.json                 (per-page status/notes/measures)

# join existing per-page MusicXML yourself
python -m scorehalo join out/pages/*.musicxml -o score.musicxml

# run two engines over the same pages and measure how much they agree
python -m scorehalo compare pages/*.png --engines homr,audiveris -o compare/
#   -> compare/comparison.md   (per-page structure + agreement, human-readable)
#   -> compare/comparison.json (machine-readable)
#   --cache DIR reuses already-recognized <engine>/<stem>.musicxml results
#   --analysis  adds a theory-aware (music21) harmonic section when music21 is present

# theory-aware analysis / normalization of MusicXML (needs music21 in the interpreter)
python -m scorehalo analyze score.musicxml                     # key, Roman-numeral histogram
python -m scorehalo analyze a.musicxml b.musicxml              # + theory-aware agreement
python -m scorehalo analyze score.musicxml --json -o sig.json  # machine-readable
python -m scorehalo analyze audiveris.musicxml --normalize fixed.musicxml --fix-clefs

# render a MusicXML score to SVG pages (needs Verovio in the interpreter)
python -m scorehalo render score.musicxml -o svg/

# open the local review UI for a batch output directory
python -m scorehalo serve out/            # add --port/--host/--open as needed
```

The review UI (`serve`) lists every recognized page with status, measure/note
counts, and engraved previews, plus download links -- so you can proofread before
importing into MuseScore. Rendering uses **Verovio** (`pip install verovio`);
run the server with an interpreter that has it (`~/scorehalo/.venv/bin/python -m
scorehalo serve ...`). Without Verovio the UI still works, showing raw MusicXML
downloads instead of images. The server binds `127.0.0.1` and blocks path
traversal on its `/raw` endpoint.

The joiner appends each page's measures to the matching part, renumbers them
sequentially, inserts `<print new-page="yes"/>` at each source-page boundary, and
uses the ordered **union** of part ids across pages (so a part that appears only
on later pages is still kept).

The `analyze` verb (and `compare --analysis`) use **music21** (BSD-3, an optional
dependency; `pip install music21`). It reduces a score with `chordify` to one
chord per moment and labels each with a Roman numeral relative to the detected
key -- a *theory-aware* fingerprint that complements the pitch-class metrics.
`analyze --normalize` also round-trips a document through music21 (merging tied
notes, optionally adding best-fit clefs) to produce cleaner MusicXML. This is the
permissive counterpart to the AGPL engines: unlike them, it is safe to import
directly into the core.

Recognizing via the `homr` backend requires the `homr` CLI on `PATH` (or set
`HOMR_BIN`); likewise `oemer` (`OEMER_BIN`) and `audiveris` (`AUDIVERIS_BIN`; the
Audiveris backend also auto-detects the common `~/local/audiveris/app-*/bin` and
`~/src/audiveris/app/build/install/app/bin` install locations). If the tool is
missing the backend reports `--` in the listing and raises a clear error rather
than crashing. All subprocess calls are wrapped with per-engine timeouts
(overridable via ``SCOREHALO_<ENGINE>_TIMEOUT`` seconds; default 1800s) so a slow
or hung engine fails with a clear message instead of blocking forever.

## Tests

```bash
python -m pytest tests            # if pytest is available
python -m unittest discover -s tests   # stdlib only
```

The suite exercises the interface contract with the `stub` backend, so it passes
on machines with none of the heavy engines installed.

## License

MIT for the ScoreHalo core. Engine code (homr/oemer/Audiveris) retains its own
license and is only invoked, never bundled.
