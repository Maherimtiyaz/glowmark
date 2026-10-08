"""Local preview server with SSE live reload."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .render import (
    codehilite_css,
    load_assets,
    render_page,
    render_text,
)


class ReloadHub:
    """Broadcasts a version bump to every connected SSE client."""

    def __init__(self) -> None:
        self.version = 0
        self.cond = threading.Condition()

    def bump(self) -> None:
        with self.cond:
            self.version += 1
            self.cond.notify_all()

    def wait(self, since: int, timeout: float) -> int:
        with self.cond:
            self.cond.wait_for(lambda: self.version != since, timeout=timeout)
            return self.version


def build_handler(source_path: Path, theme: str, title: str | None, hub: ReloadHub):
    css, js = load_assets()
    code_css = codehilite_css()

    class PreviewHandler(BaseHTTPRequestHandler):
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
                text = source_path.read_text(encoding="utf-8")
                doc = render_text(text, default_title=source_path.stem)
                html = render_page(
                    doc,
                    css=css,
                    js=js,
                    code_css=code_css,
                    site_title=title,
                    theme=theme,
                    live_reload=True,
                )
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/events":
                self._stream_events()
            else:
                self._send(404, b"Not found", "text/plain; charset=utf-8")

        def _stream_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            version = hub.version
            try:
                while True:
                    version = hub.wait(version, timeout=15.0)
                    self.wfile.write(b"data: reload\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    return PreviewHandler


def serve(
    source_path: Path,
    *,
    port: int = 7654,
    theme: str = "auto",
    title: str | None = None,
) -> ThreadingHTTPServer:
    """Start the preview server and watch the source file for changes."""
    hub = ReloadHub()
    handler = build_handler(source_path, theme, title, hub)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True

    observer = _watch(source_path, hub)
    httpd.observer = observer  # type: ignore[attr-defined]
    return httpd


def _watch(source_path: Path, hub: ReloadHub):
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        return None

    resolved = source_path.resolve()
    last_bump = 0.0

    class Handler(FileSystemEventHandler):
        def on_modified(self, event) -> None:
            nonlocal last_bump
            if getattr(event, "is_directory", False):
                return
            if Path(event.src_path).resolve() != resolved:
                return
            now = time.monotonic()
            if now - last_bump < 0.15:  # debounce editor double-writes
                return
            last_bump = now
            hub.bump()

    observer = Observer()
    observer.schedule(Handler(), str(resolved.parent), recursive=False)
    observer.daemon = True
    observer.start()
    return observer
