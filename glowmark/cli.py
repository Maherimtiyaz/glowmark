"""glowmark command line interface."""

from __future__ import annotations

import argparse
import sys
import tempfile
import webbrowser
from pathlib import Path

from . import __version__
from .render import codehilite_css, load_assets, render_page, render_text
from .source import SourceText, read_file, read_stdin

DEFAULT_PORT = 7654


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glowmark",
        description="Turn Markdown into a beautiful, standalone HTML page.",
        epilog="examples:\n"
        "  glowmark README.md\n"
        "  glowmark --serve docs/guide.md\n"
        "  glowmark --web                 # paste markdown in the browser\n"
        "  glowmark notes.md --out page.html --theme dark\n"
        "  cat ideas.md | glowmark - --out ideas.html",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file", nargs="?", default=None, help="markdown file to render, or '-' for stdin"
    )
    parser.add_argument("-s", "--serve", action="store_true", help="live-reload preview server")
    parser.add_argument(
        "-w",
        "--web",
        action="store_true",
        help="open a paste-in browser editor with live preview",
    )
    parser.add_argument(
        "-o", "--out", metavar="PATH", help="write a standalone HTML file instead of previewing"
    )
    parser.add_argument(
        "-t",
        "--theme",
        choices=["auto", "light", "dark"],
        default="auto",
        help="color theme (default: auto)",
    )
    parser.add_argument("--title", help="override the document title")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"preview port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument("--version", action="version", version=f"glowmark {__version__}")
    return parser


def read_source(file_arg: str) -> tuple[SourceText, str]:
    """Return (decoded source, default title from the filename)."""
    if file_arg == "-":
        return read_stdin(), ""
    path = Path(file_arg)
    if not path.exists():
        sys.exit(f"glowmark: file not found: {file_arg}")
    if path.is_dir():
        sys.exit(f"glowmark: expected a file, got a directory: {file_arg}")
    try:
        return read_file(path), path.stem
    except OSError as exc:
        sys.exit(f"glowmark: could not read {file_arg}: {exc}")


def _warn(warnings: tuple[str, ...] | list[str]) -> None:
    for warning in warnings:
        print(f"glowmark: warning: {warning}", file=sys.stderr)


def _write_utf8(path: Path, text: str) -> int:
    data = text.encode("utf-8")
    path.write_bytes(data)
    return len(data)


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    modes = [bool(args.serve), bool(args.web), bool(args.out)]
    if sum(modes) > 1:
        sys.exit("glowmark: --serve, --web and --out are mutually exclusive")
    if args.file is None and not args.web:
        parser.error("the following arguments are required: file (or use --web)")

    if args.serve:
        return _serve(args)
    if args.web:
        return _web(args)

    source, default_title = read_source(args.file)
    _warn(source.warnings)
    doc = render_text(
        source.text,
        default_title=default_title,
        title_override=args.title,
        input_warnings=source.warnings,
    )
    css, js = load_assets()
    html = render_page(
        doc,
        css=css,
        js=js,
        code_css=codehilite_css(),
        theme=args.theme,
    )

    if args.out:
        out_path = Path(args.out)
        size = _write_utf8(out_path, html)
        print(f"wrote {out_path}  ({size:,} bytes, UTF-8)")
        return

    tmp = Path(tempfile.gettempdir()) / f"glowmark-{_slug(doc.title)}.html"
    size = _write_utf8(tmp, html)
    print(f"preview: {tmp}  ({size:,} bytes, UTF-8)")
    if not args.no_open:
        webbrowser.open(tmp.as_uri())


def _serve(args: argparse.Namespace) -> None:
    if args.file == "-":
        sys.exit("glowmark: --serve needs a real file path (stdin is not watchable)")
    from .server import serve

    source = Path(args.file)
    if not source.exists():
        sys.exit(f"glowmark: file not found: {args.file}")

    httpd = serve(source, port=args.port, theme=args.theme, title=args.title)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"serving {source} at {url}  (edit the file to live-reload, ctrl+c to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        observer = getattr(httpd, "observer", None)
        if observer:
            observer.stop()
        httpd.shutdown()
        httpd.server_close()


def _web(args: argparse.Namespace) -> None:
    from .web import serve_web

    seed = None
    if args.file is not None:
        if args.file == "-":
            seed_source = read_stdin()
        else:
            seed_source, _ = read_source(args.file)
        _warn(seed_source.warnings)
        seed = seed_source.text

    httpd = serve_web(seed=seed, port=args.port, theme=args.theme, title=args.title)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"web editor at {url}  (paste markdown, live preview, ctrl+c to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.shutdown()
        httpd.server_close()


def _configure_stdio() -> None:
    """Avoid UnicodeEncodeError when printing paths on legacy consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _slug(title: str) -> str:
    slug = "".join(c.lower() if c.isascii() and c.isalnum() else "-" for c in title)
    return "-".join(filter(None, slug.split("-")))[:40] or "doc"


if __name__ == "__main__":
    main()
