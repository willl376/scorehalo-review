"""A tiny, dependency-free review UI for a ScoreHalo ``batch`` output directory.

Serves an HTML page listing every recognized page (with status, measure/note
counts, and an inline-rendered score) plus download links -- so a human can
proofread the MusicXML before importing it into MuseScore.

Rendering is delegated to :mod:`scorehalo.render` (Verovio).  If Verovio is not
installed in the running interpreter the UI still works, showing raw-XML
download links instead of images.

Run it with an interpreter that has Verovio for images::

    ~/scorehalo/.venv/bin/python -m scorehalo serve out/
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
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
.card { background: #fff; border: 1px solid #e2ded8; border-radius: 10px; padding: 0.75rem; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.card img { width: 100%; height: auto; border: 1px solid #eee; border-radius: 6px; background: #fff; }
.meta { font-size: 0.85rem; margin-bottom: 0.5rem; }
.ok { color: #1a7f37; font-weight: 600; }
.bad { color: #c0392b; font-weight: 600; }
.links a { font-size: 0.8rem; margin-right: 0.6rem; }
.note { background: #fff6e5; border: 1px solid #f0d9a8; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0; }
.dl { margin: 1rem 0; }
"""


def safe_path(outdir: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``outdir``; return None on escape/miss."""
    root = Path(outdir).resolve()
    candidate = (root / relative).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def _relative(outdir: Path, path: str | None) -> str | None:
    if not path:
        return None
    try:
        return str(Path(path).resolve().relative_to(Path(outdir).resolve()))
    except ValueError:
        return None


def _raw_link(relative: str) -> str:
    return "/raw?path=" + quote(relative)


def load_manifest(outdir: Path) -> dict:
    return json.loads((Path(outdir) / "manifest.json").read_text(encoding="utf-8"))


def render_index(outdir: Path, score_page_count: int | None = None) -> str:
    """Build the review HTML for a batch output directory."""
    outdir = Path(outdir).resolve()
    manifest = load_manifest(outdir)
    pages = manifest.get("pages", [])
    backend = html.escape(str(manifest.get("backend", "?")))
    ok_count = manifest.get("ok_count", sum(1 for p in pages if p.get("ok")))

    parts: list[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append(f"<title>ScoreHalo review - {backend}</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    parts.append("<h1>ScoreHalo review</h1>")
    parts.append(
        f"<div class='sub'>backend <b>{backend}</b> &middot; "
        f"{ok_count}/{len(pages)} page(s) valid</div>"
    )

    if not render.available():
        parts.append(
            "<div class='note'>Verovio is not installed in this interpreter, so "
            "scores cannot be rendered here. Install it (e.g. "
            "<code>~/scorehalo/.venv/bin/pip install verovio</code>) and run the "
            "server with that interpreter to see engraved pages. Raw MusicXML "
            "downloads still work below.</div>"
        )

    joined = _relative(outdir, manifest.get("joined"))
    manifest_rel = "manifest.json" if (outdir / "manifest.json").is_file() else None

    downloads = []
    if joined:
        downloads.append(f"<a href='{_raw_link(joined)}'>joined score.musicxml</a>")
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
                f"<img src='/svg/score?page={number}' alt='score page {number}'></div>"
            )
        parts.append("</div>")

    parts.append("<h2>Pages</h2><div class='grid'>")
    for page in pages:
        number = page.get("index")
        source = html.escape(Path(str(page.get("source", ""))).name)
        if page.get("ok"):
            status = "<span class='ok'>valid</span>"
        elif page.get("error"):
            status = f"<span class='bad'>error</span> {html.escape(str(page['error']))}"
        else:
            status = "<span class='bad'>invalid</span> " + html.escape(
                "; ".join(page.get("problems") or [])
            )
        detail = ""
        if page.get("ok"):
            detail = (
                f"{page.get('measures', '?')} measures &middot; "
                f"{page.get('notes', '?')} notes"
            )
        rel = _relative(outdir, page.get("musicxml_path"))
        link = f"<a href='{_raw_link(rel)}'>MusicXML</a>" if rel else ""
        parts.append(
            f"<div class='card'><div class='meta'><b>Page {number}</b> &middot; "
            f"{source} &middot; {status}<br>{detail}</div>"
            f"<img src='/svg/page?page={number}' alt='page {number}'>"
            f"<div class='links'>{link}</div></div>"
        )
    parts.append("</div></body></html>")
    return "".join(parts)


class ReviewHandler(BaseHTTPRequestHandler):
    outdir: Path
    server_version = "ScoreHaloReview/0.1"

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
