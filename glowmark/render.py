"""Markdown -> polished HTML rendering engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

EXTENSIONS = [
    "extra",  # tables, fenced code, footnotes, attr_list
    "toc",  # anchor ids + TOC generation
    "sane_lists",
    "smarty",
    "codehilite",
    "admonition",
]

EXTENSION_CONFIGS = {
    "toc": {"permalink": False, "toc_depth": "2-3"},
    "codehilite": {"css_class": "highlight", "guess_lang": False},
}

ADMONITION_RE = re.compile(
    r"^\s*>\s*\[!(?P<kind>NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$",
    re.IGNORECASE,
)
FENCE_RE = re.compile(r"^(?P<fence>```+|~~~+)(?P<lang>\S*)\s*$")

MERMAID_BLOCK_RE = re.compile(
    r"^(?P<fence>```+)mermaid[ \t]*\r?\n(?P<body>.*?)^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

HTML_TAG_RE = re.compile(r"<[^>]+>")
INLINE_MARKUP_RE = re.compile(r"[*_`~\[\]()!#>|\\-]")


@dataclass
class Document:
    body_html: str
    toc_html: str
    title: str
    author: str = ""
    date: str = ""
    description: str = ""
    word_count: int = 0
    reading_minutes: int = 0
    meta: dict = field(default_factory=dict)


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse simple ``key: value`` front matter delimited by ``---`` lines."""
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", text, re.DOTALL)
    if not match:
        return {}, text
    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, text[match.end() :]


def preprocess(text: str) -> str:
    """Convert GitHub-style alerts and mermaid fences for downstream handling."""
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group("fence")
            if not in_fence:
                in_fence = True
                if fence.group("lang").lower() == "mermaid":
                    block: list[str] = []
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith(marker[:3]):
                        block.append(lines[i])
                        i += 1
                    out.append('<div class="mermaid">\n' + "\n".join(block) + "\n</div>")
                    in_fence = False
                else:
                    out.append(line)
                    i += 1
                continue
            in_fence = False
            out.append(line)
            i += 1
            continue
        alert = ADMONITION_RE.match(line) if not in_fence else None
        if alert:
            raw_kind = alert.group("kind").upper()
            out.append(f'!!! {raw_kind.lower()} "{raw_kind.capitalize()}"')
            i += 1
            while i < len(lines):
                body_line = lines[i]
                if body_line.strip() == "":
                    if i + 1 < len(lines) and lines[i + 1].lstrip().startswith(">"):
                        out.append("")
                        i += 1
                        continue
                    break
                stripped = body_line.lstrip()
                if stripped.startswith(">"):
                    content = stripped[1:]
                    out.append("    " + (content[1:] if content.startswith(" ") else content))
                    i += 1
                    continue
                break
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def count_words(text: str) -> int:
    plain = HTML_TAG_RE.sub(" ", text)
    plain = INLINE_MARKUP_RE.sub(" ", plain)
    return len(plain.split())


def render_text(md_text: str, default_title: str = "Untitled") -> Document:
    meta, source = parse_front_matter(md_text)
    word_count = count_words(source)
    body_source = preprocess(source)

    md = markdown.Markdown(extensions=EXTENSIONS, extension_configs=EXTENSION_CONFIGS)
    body_html = md.convert(body_source)
    toc_html = getattr(md, "toc", "")

    title = meta.get("title") or _first_heading(body_html) or default_title
    reading_minutes = max(1, round(word_count / 200))

    return Document(
        body_html=body_html,
        toc_html=toc_html,
        title=title,
        author=meta.get("author", ""),
        date=meta.get("date", ""),
        description=meta.get("description", meta.get("summary", "")),
        word_count=word_count,
        reading_minutes=reading_minutes,
        meta=meta,
    )


def _first_heading(html: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if not match:
        return ""
    return HTML_TAG_RE.sub("", match.group(1)).strip()


def codehilite_css(style_light: str = "default", style_dark: str = "monokai") -> str:
    """Generate Pygments CSS for both themes, scoped so each only applies there."""
    return _codehilite_css_cached(style_light, style_dark)


@lru_cache(maxsize=4)
def _codehilite_css_cached(style_light: str, style_dark: str) -> str:
    light = HtmlFormatter(style=get_style_by_name(style_light)).get_style_defs(
        ".theme-light .highlight"
    )
    dark = HtmlFormatter(style=get_style_by_name(style_dark)).get_style_defs(
        ".theme-dark .highlight"
    )
    return light + "\n" + dark


def render_page(
    doc: Document,
    *,
    css: str,
    js: str,
    code_css: str,
    site_title: str | None = None,
    theme: str = "auto",
    live_reload: bool = False,
) -> str:
    """Assemble the final standalone HTML document."""
    template = (TEMPLATES_DIR / "page.html").read_text(encoding="utf-8")

    head_bits = []
    if doc.author:
        head_bits.append(doc.author)
    if doc.date:
        head_bits.append(doc.date)
    meta_line = " · ".join(head_bits)

    reload_script = (
        "<script>"
        'new EventSource("/events").onmessage=function(e){'
        'if(e.data==="reload")location.reload()};'
        "</script>"
        if live_reload
        else ""
    )

    replacements = {
        "<!--GLOWMARK:TITLE-->": _escape(site_title or doc.title),
        "<!--GLOWMARK:THEME-->": f"theme-{theme}",
        "<!--GLOWMARK:DESCRIPTION-->": _escape(doc.description),
        "<!--GLOWMARK:BODY-->": doc.body_html,
        "<!--GLOWMARK:TOC-->": toc_or_empty(doc.toc_html),
        "<!--GLOWMARK:HEADING-->": _escape(doc.title),
        "<!--GLOWMARK:META_LINE-->": _escape(meta_line),
        "<!--GLOWMARK:META_STYLE-->": "" if meta_line else "hidden",
        "<!--GLOWMARK:READING-->": f"{doc.reading_minutes} min read",
        "<!--GLOWMARK:WORDS-->": f"{doc.word_count:,} words",
        "/*GLOWMARK:STYLE*/": code_css + "\n" + css,
        "//GLOWMARK:JS": js,
        "<!--GLOWMARK:LIVE_RELOAD-->": reload_script,
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def toc_or_empty(toc_html: str) -> str:
    if not toc_html or "<li>" not in toc_html:
        return '<p class="toc-empty">No sections</p>'
    return toc_html


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def load_assets() -> tuple[str, str]:
    css = (TEMPLATES_DIR / "style.css").read_text(encoding="utf-8")
    js = (TEMPLATES_DIR / "app.js").read_text(encoding="utf-8")
    return css, js
