"""A tiny, dependency-free review UI for a ScoreHalo ``work`` directory.

Serves an HTML page listing every recognized page -- the original scan next to
the engraved result, with status, measure/note counts, download links, a
click-to-zoom view and per-page **accept/reject** controls whose decisions are
persisted back into ``manifest.json``.  The point is to proofread the
recognition before importing the MusicXML into MuseScore.

Rendering is delegated to :mod:`scorehalo.render` (Verovio).  If Verovio is not
installed in the running interpreter the UI still works, showing raw-XML download
links instead of images.
"""

from __future__ import annotations

import html
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import render

_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; margin: 0; padding: 1.5rem; background: #faf9f7; color: #1b1b1b; }
h1 { margin-top: 0; }
.sub { color: #666; margin-bottom: 1rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 1rem; }
.card { background: #fff; border: 1px solid #e2ded8; border-radius: 10px; padding: 0.75rem; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.card img { width: 100%; height: auto; border: 1px solid #eee; border-radius: 6px; background: #fff; cursor: zoom-in; }
.meta { font-size: 0.85rem; margin-bottom: 0.5rem; }
.ok { color: #1a7f37; font-weight: 600; }
.bad { color: #c0392b; font-weight: 600; }
.tag { display: inline-block; font-size: 0.75rem; padding: 0.05rem 0.4rem; border-radius: 999px; margin-left: 0.35rem; }
.tag.accept { background: #dafbe1; color: #1a7f37; }
.tag.reject { background: #ffe3e0; color: #c0392b; }
.tag.skip { background: #ececec; color: #666; }
.links a { font-size: 0.8rem; margin-right: 0.6rem; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
.pair figure { margin: 0; }
.pair figcaption { font-size: 0.7rem; color: #888; text-align: center; }
.actions { margin-top: 0.5rem; display: flex; gap: 0.4rem; }
.actions button { font-size: 0.8rem; padding: 0.25rem 0.6rem; border-radius: 6px; border: 1px solid #ccc; background: #f6f6f6; cursor: pointer; }
.actions button.accept:hover { background: #dafbe1; }
.actions button.reject:hover { background: #ffe3e0; }
.note { background: #fff6e5; border: 1px solid #f0d9a8; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0; }
.dl { margin: 1rem 0; }
#overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.85); z-index: 10; align-items: center; justify-content: center; cursor: zoom-out; }
#overlay img { max-width: 96vw; max-height: 96vh; background: #fff; }
"""

_JS = """
function zoom(src) {
  const o = document.getElementById('overlay');
  o.querySelector('img').src = src;
  o.style.display = 'flex';
}
document.addEventListener('click', function (e) {
  const img = e.target.closest('img.zoom');
  if (img) { zoom(img.getAttribute('src')); }
});
document.addEventListener('DOMContentLoaded', function () {
  const o = document.getElementById('overlay');
  if (o) { o.addEventListener('click', function () { o.style.display = 'none'; }); }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { o.style.display = 'none'; } });
});
async function decide(index, value) {
  const r = await fetch('/review?index=' + index + '&value=' + value, { method: 'POST' });
  if (r.ok) { location.reload(); }
}
"""


def safe_path(outdir: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``outdir``; return None on escape/miss."""
    root = Path(outdir).resolve()
    candidate = (root / relative).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def _relative(outdir: Path, path: str | None) -> str | None:
    """Return ``path`` relative to ``outdir`` (accepts absolute or relative input)."""
    if not path:
        return None
    root = Path(outdir).resolve()
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return None


def _raw_link(relative: str) -> str:
    return "/raw?path=" + quote(relative)


def load_manifest(outdir: Path) -> dict:
    return json.loads((Path(outdir) / "manifest.json").read_text(encoding="utf-8"))


def set_decision(outdir: Path, index: int, value: str) -> bool:
    """Persist an accept/reject decision for page ``index`` into the manifest.

    ``value`` is ``"accept"``, ``"reject"`` or ``"clear"``.  Returns False if the
    page index is unknown.
    """
    outdir = Path(outdir)
    manifest = load_manifest(outdir)
    pages = manifest.get("pages", [])
    if not (1 <= index <= len(pages)):
        return False
    pages[index - 1]["decision"] = None if value == "clear" else value
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return True


def _decision_tag(decision: str | None) -> str:
    if decision == "accept":
        return "<span class='tag accept'>accepted</span>"
    if decision == "reject":
        return "<span class='tag reject'>rejected</span>"
    return ""


def render_index(outdir: Path, score_page_count: int | None = None) -> str:
    """Build the review HTML for a ``work`` directory."""
    outdir = Path(outdir).resolve()
    manifest = load_manifest(outdir)
    pages = manifest.get("pages", [])
    engine = html.escape(str(manifest.get("engine") or manifest.get("backend") or "?"))
    ok_count = manifest.get("ok_count", sum(1 for p in pages if p.get("ok")))
    skipped_count = manifest.get("skipped_count", sum(1 for p in pages if p.get("skipped")))

    def raw(rel):
        return f"<a href='{_raw_link(rel)}'>MusicXML</a>" if rel else ""

    parts: list[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append(f"<title>ScoreHalo review - {engine}</title>")
    parts.append(f"<style>{_CSS}</style>")
    parts.append(f"<script>{_JS}</script></head><body>")
    parts.append("<h1>ScoreHalo review</h1>")
    parts.append(
        f"<div class='sub'>engine <b>{engine}</b> &middot; "
        f"{ok_count}/{len(pages)} page(s) valid"
        + (f" &middot; {skipped_count} skipped" if skipped_count else "")
        + "</div>"
    )

    if not render.available():
        parts.append(
            "<div class='note'>Verovio is not installed in this interpreter, so "
            "scores cannot be rendered here. Install it (e.g. "
            "<code>pip install verovio</code>) and run the server with that "
            "interpreter to see engraved pages. Raw MusicXML downloads still work "
            "below.</div>"
        )

    joined = _relative(outdir, manifest.get("joined"))
    manifest_rel = "manifest.json" if (outdir / "manifest.json").is_file() else None
    downloads = []
    if joined:
        downloads.append(f"<a href='{_raw_link(joined)}'>joined score.musicxml</a>")
    for fmt, rel in (manifest.get("exports") or {}).items():
        if rel and rel != joined:
            downloads.append(f"<a href='{_raw_link(rel)}'>{fmt}</a>")
    if manifest_rel:
        downloads.append(f"<a href='{_raw_link(manifest_rel)}'>manifest.json</a>")
    if downloads:
        parts.append("<div class='dl'><b>Download:</b> " + " &middot; ".join(downloads) + "</div>")

    if joined and score_page_count:
        parts.append("<h2>Joined score</h2><div class='grid'>")
        for number in range(1, score_page_count + 1):
            parts.append(
                "<div class='card'><div class='meta'>Score page "
                f"{number}/{score_page_count}</div>"
                f"<img class='zoom' src='/svg/score?page={number}' alt='score page {number}'></div>"
            )
        parts.append("</div>")

    parts.append("<h2>Pages</h2><div class='grid'>")
    for page in pages:
        number = page.get("index")
        source = html.escape(Path(str(page.get("source", ""))).name)
        skipped = bool(page.get("skipped"))
        if skipped:
            reason = html.escape(str(page.get("skip_reason") or "not music"))
            status = f"<span class='tag skip'>skipped</span> {reason}"
        elif page.get("ok"):
            status = "<span class='ok'>valid</span>"
        elif page.get("error"):
            status = f"<span class='bad'>error</span> {html.escape(str(page['error']))}"
        else:
            status = "<span class='bad'>invalid</span> " + html.escape(
                "; ".join(page.get("problems") or [])
            )
        if not skipped:
            status += _decision_tag(page.get("decision"))
        detail = ""
        if page.get("ok"):
            detail = (
                f"{page.get('measures', '?')} measures &middot; "
                f"{page.get('notes', '?')} notes"
            )
        rel = _relative(outdir, page.get("musicxml_path"))
        link = raw(rel)

        # original scan (if ingested) next to the engraved result
        image_rel = page.get("image")
        figures = []
        if image_rel:
            figures.append(
                "<figure><img class='zoom' src='" + _raw_link(image_rel)
                + "' alt='original page " + str(number) + "'>"
                "<figcaption>original</figcaption></figure>"
            )
        if rel:
            figures.append(
                "<figure><img class='zoom' src='/svg/page?page=" + str(number)
                + "' alt='page " + str(number) + "'>"
                "<figcaption>recognized</figcaption></figure>"
            )
        pair = "<div class='pair'>" + "".join(figures) + "</div>" if figures else ""

        actions = ""
        if not skipped:
            actions = (
                "<div class='actions'>"
                f"<button class='accept' onclick=\"decide({number},'accept')\">Accept</button>"
                f"<button class='reject' onclick=\"decide({number},'reject')\">Reject</button>"
                f"<button onclick=\"decide({number},'clear')\">Clear</button>"
                "</div>"
            )

        parts.append(
            f"<div class='card'><div class='meta'><b>Page {number}</b> &middot; "
            f"{source} &middot; {status}<br>{detail}</div>"
            f"{pair}"
            f"<div class='links'>{link}</div>{actions}</div>"
        )
    parts.append("</div>")
    parts.append("<div id='overlay'><img alt='zoom'></div>")
    parts.append("</body></html>")
    return "".join(parts)


class ReviewHandler(BaseHTTPRequestHandler):
    outdir: Path
    server_version = "ScoreHaloReview/0.2"

    def log_message(self, fmt, *args):  # noqa: A003 - silence default logging
        pass

    def _send(self, code: int, body, ctype: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _score_svgs(self) -> list[str]:
        cache = self.server.cache
        if "score" not in cache:
            manifest = load_manifest(self.outdir)
            joined = _relative(self.outdir, manifest.get("joined"))
            if not joined:
                raise FileNotFoundError("no joined score in manifest")
            text = (self.outdir / joined).read_text(encoding="utf-8")
            cache["score"] = render.render_svgs(text)
        return cache["score"]

    def _page_svgs(self, index: int) -> list[str]:
        cache = self.server.cache
        key = ("page", index)
        if key not in cache:
            manifest = load_manifest(self.outdir)
            pages = manifest.get("pages", [])
            if not (1 <= index <= len(pages)):
                raise KeyError(f"no page {index}")
            rel = _relative(self.outdir, pages[index - 1].get("musicxml_path"))
            if not rel:
                raise FileNotFoundError("page has no MusicXML path")
            text = (self.outdir / rel).read_text(encoding="utf-8")
            cache[key] = render.render_svgs(text)
        return cache[key]

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                count = None
                if render.available():
                    try:
                        count = len(self._score_svgs())
                    except Exception:
                        count = None
                return self._send(200, render_index(self.outdir, count))
            if parsed.path == "/svg/page":
                svgs = self._page_svgs(int(query.get("page", ["1"])[0]))
                return self._send(200, svgs[0], "image/svg+xml")
            if parsed.path == "/svg/score":
                svgs = self._score_svgs()
                number = int(query.get("page", ["1"])[0])
                if not (1 <= number <= len(svgs)):
                    return self._send(404, "<h1>404</h1>")
                return self._send(200, svgs[number - 1], "image/svg+xml")
            if parsed.path == "/raw":
                return self._raw(query.get("path", [""])[0])
            return self._send(404, "<h1>404</h1>")
        except KeyError as exc:
            return self._send(404, f"<h1>404</h1><p>{html.escape(str(exc))}</p>")
        except Exception as exc:  # pragma: no cover - defensive
            return self._send(500, f"<h1>500</h1><pre>{html.escape(str(exc))}</pre>")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path != "/review":
            return self._send(404, "<h1>404</h1>")
        try:
            index = int(query.get("index", ["0"])[0])
            value = query.get("value", ["clear"])[0]
        except ValueError:
            return self._send(400, "bad request")
        if value not in {"accept", "reject", "clear"}:
            return self._send(400, "bad value")
        ok = set_decision(self.outdir, index, value)
        return self._send(200 if ok else 404, json.dumps({"ok": ok}))

    def _raw(self, relative: str) -> None:
        target = safe_path(self.outdir, relative)
        if target is None:
            return self._send(404, "<h1>404</h1>")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype)


def make_server(outdir, host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    outdir = Path(outdir).resolve()
    if not (outdir / "manifest.json").is_file():
        raise FileNotFoundError(f"no manifest.json in {outdir}")
    handler = type("_BoundReviewHandler", (ReviewHandler,), {"outdir": outdir})
    httpd = HTTPServer((host, port), handler)
    httpd.outdir = outdir
    httpd.cache = {}
    return httpd


def serve(outdir, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    httpd = make_server(outdir, host, port)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"ScoreHalo review UI at {url} (Ctrl-C to stop)")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
