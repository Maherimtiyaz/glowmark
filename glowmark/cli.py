"""glowmark command line interface."""

from __future__ import annotations

import argparse
import sys
import tempfile
import webbrowser
from pathlib import Path

from . import __version__
from .render import codehilite_css, load_assets, render_page, render_text

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


def read_source(file_arg: str) -> tuple[str, str]:
    """Return (markdown_text, default_title)."""
    if file_arg == "-":
        return sys.stdin.read(), "stdin"
    path = Path(file_arg)
    if not path.exists():
        sys.exit(f"glowmark: file not found: {file_arg}")
    if path.is_dir():
        sys.exit(f"glowmark: expected a file, got a directory: {file_arg}")
    return path.read_text(encoding="utf-8", errors="replace"), path.stem


def main(argv: list[str] | None = None) -> None:
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

    text, default_title = read_source(args.file)
    doc = render_text(text, default_title=default_title)
    css, js = load_assets()
    html = render_page(
        doc,
        css=css,
        js=js,
        code_css=codehilite_css(),
        site_title=args.title,
        theme=args.theme,
    )

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(html, encoding="utf-8")
        print(f"wrote {out_path}  ({len(html):,} bytes)")
        return

    tmp = Path(tempfile.gettempdir()) / f"glowmark-{_slug(doc.title)}.html"
    tmp.write_text(html, encoding="utf-8")
    print(f"preview: {tmp}")
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
            seed = sys.stdin.read()
        else:
            seed, _ = read_source(args.file)

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


def _slug(title: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in title)
    return "-".join(filter(None, slug.split("-")))[:40] or "doc"


if __name__ == "__main__":
    main()
