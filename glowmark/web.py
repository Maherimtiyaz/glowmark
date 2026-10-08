"""Web editor mode: paste markdown in the browser, see the live glowmark preview."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .render import (
    codehilite_css,
    load_assets,
    render_page,
    render_text,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
MAX_BODY = 4_000_000  # 4 MB of markdown is plenty


def build_page(theme: str, title: str | None, seed: str | None) -> str:
    template = (TEMPLATES_DIR / "web.html").read_text(encoding="utf-8")
    css, _ = load_assets()
    web_js = (TEMPLATES_DIR / "web.js").read_text(encoding="utf-8")
    seed_json = json.dumps(seed) if seed is not None else "null"
    seed_json = seed_json.replace("</", "<\\/")  # keep </script> inert
    web_js = web_js.replace("<!--GLOWMARK:SEED-->", seed_json)

    replacements = {
        "<!--GLOWMARK:THEME-->": f"theme-{theme}",
        "<!--GLOWMARK:SEED-->": seed_json,
        "/*GLOWMARK:STYLE*/": codehilite_css() + "\n" + css,
        "//GLOWMARK:JS": web_js,
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def build_handler(theme: str, title: str | None, seed: str | None):
    page = build_page(theme, title, seed)
    css, js = load_assets()
    code_css = codehilite_css()

    class WebHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(404, b"Not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path != "/render":
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY:
                    raise ValueError("bad length")
                data = json.loads(self.rfile.read(length))
                markdown_text = data.get("md", "")
                full = bool(data.get("full"))
                doc = render_text(markdown_text, default_title="Untitled")
                if full:
                    payload = {
                        "html": render_page(
                            doc,
                            css=css,
                            js=js,
                            code_css=code_css,
                            site_title=title,
                            theme=theme,
                        )
                    }
                else:
                    payload = {
                        "body": doc.body_html,
                        "title": doc.title,
                        "words": doc.word_count,
                        "minutes": doc.reading_minutes,
                    }
                body = json.dumps(payload).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:  # noqa: BLE001
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send(400, body, "application/json; charset=utf-8")

    return WebHandler


def serve_web(
    *,
    seed: str | None = None,
    port: int = 7654,
    theme: str = "auto",
    title: str | None = None,
) -> ThreadingHTTPServer:
    handler = build_handler(theme, title, seed)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    return httpd
