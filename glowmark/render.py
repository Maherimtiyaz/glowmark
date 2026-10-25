"""Markdown -> polished HTML rendering engine.

The parser is markdown-it-py configured for CommonMark + the GitHub Flavored
Markdown features glowmark advertises.  Keeping the parser GFM-compatible is
important: nested lists, fenced code inside list items, task lists and
backslash escapes should behave the way they do on GitHub.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape as html_escape
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from .source import normalize_newlines

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_ALERT_RE = re.compile(
    r"^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*\n?",
    re.IGNORECASE,
)
_FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
_TABLE_DELIM_RE = re.compile(
    r"^\s*\|?\s*:?-{1,}:?\s*(?:\|\s*:?-{1,}:?\s*)+\|?\s*$"
)
_WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)

_FORMATTER = HtmlFormatter(nowrap=True)


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
    code_word_count: int = 0
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class _Heading:
    level: int
    id: str
    text: str


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse simple ``key: value`` front matter delimited by ``---`` lines."""
    text = normalize_newlines(text)
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?", text, re.DOTALL)
    if not match:
        return {}, text

    block = match.group(1)
    # A document can legitimately start with a horizontal rule.  Only treat
    # the block as front matter when it actually contains key/value pairs.
    if not any(re.match(r"^[A-Za-z0-9_-]+:\s*", line) for line in block.splitlines()):
        return {}, text

    meta: dict = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, text[match.end() :]


def repair_tables(text: str) -> str:
    """Remove blank lines inside GFM tables.

    HTML/Word/Pandoc exports often put a blank line between every table row.
    CommonMark (correctly) ends the table at the first blank line, so this
    pre-pass stitches those rows back together without touching fenced code.
    """
    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        if in_fence:
            out.append(line)
            stripped = line.strip()
            if (
                stripped.startswith(fence_char * fence_len)
                and stripped.strip(fence_char).strip() == ""
            ):
                in_fence = False
            i += 1
            continue

        fence = _FENCE_OPEN_RE.match(line)
        if fence:
            in_fence = True
            fence_char = fence.group(1)[0]
            fence_len = len(fence.group(1))
            out.append(line)
            i += 1
            continue

        if _TABLE_DELIM_RE.match(line):
            previous = len(out) - 1
            while previous >= 0 and not out[previous].strip():
                previous -= 1
            if previous >= 0 and _looks_like_table_row(out[previous]):
                del out[previous + 1 :]
                out.append(line)
                i += 1

                while i < len(lines):
                    if not lines[i].strip():
                        lookahead = i
                        while lookahead < len(lines) and not lines[lookahead].strip():
                            lookahead += 1
                        if lookahead < len(lines) and _looks_like_table_row(lines[lookahead]):
                            i = lookahead
                            continue
                        break
                    if _looks_like_table_row(lines[i]):
                        out.append(lines[i])
                        i += 1
                        continue
                    break
                continue

        out.append(line)
        i += 1

    return "\n".join(out)


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped or "|" not in stripped:
        return False
    if stripped.startswith(("#", ">", "```", "~~~", "- ", "* ", "+ ")):
        return False
    return not _TABLE_DELIM_RE.match(stripped)


def _highlight_code(code: str, lang: str, _attrs: str = "") -> str:
    lexer = None
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripnl=False)
        except ClassNotFound:
            lexer = None
    body = pygments_highlight(code, lexer, _FORMATTER) if lexer else html_escape(code)
    return f'<pre class="highlight"><code>{body}</code></pre>'


def _render_fence(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    info = (token.info or "").strip()
    lang = info.split(maxsplit=1)[0] if info else ""
    if lang.lower() == "mermaid":
        return f'<div class="mermaid">\n{html_escape(token.content)}\n</div>\n'
    return self.fence(tokens, idx, options, env)


def _alerts_plugin(md: MarkdownIt) -> None:
    """Turn GitHub blockquote alerts into admonition cards."""

    def rule(state) -> None:
        tokens = state.tokens
        i = 0
        while i < len(tokens):
            if tokens[i].type != "blockquote_open":
                i += 1
                continue

            depth = 0
            j = i
            while j < len(tokens):
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= len(tokens):
                break

            inline_index = i + 1
            if inline_index < j and tokens[inline_index].type == "paragraph_open":
                inline_index += 1

            kind = ""
            if inline_index < j and tokens[inline_index].type == "inline":
                inline = tokens[inline_index]
                for child in inline.children or []:
                    if child.type == "text":
                        match = _ALERT_RE.match(child.content)
                        if match:
                            kind = match.group(1).lower()
                            child.content = child.content[match.end() :].lstrip(" \t")
                        break

                if kind:
                    inline.children = [
                        child
                        for child in (inline.children or [])
                        if not (child.type == "text" and not child.content)
                    ]
                    while inline.children and inline.children[0].type in (
                        "softbreak",
                        "hardbreak",
                    ):
                        inline.children.pop(0)

                    tokens[i].meta["admonition"] = kind
                    tokens[j].meta["admonition"] = kind

                    # The marker was the only content in the first paragraph.
                    if not inline.children:
                        start = inline_index - 1
                        end = inline_index + 2
                        if (
                            start >= 0
                            and tokens[start].type == "paragraph_open"
                            and end <= len(tokens)
                            and tokens[end - 1].type == "paragraph_close"
                        ):
                            del tokens[start:end]
                            j -= end - start
            i = j + 1

    def open_rule(self, tokens, idx, options, env) -> str:
        kind = tokens[idx].meta.get("admonition")
        if kind:
            return (
                f'<div class="admonition {kind}">\n'
                f'<p class="admonition-title">{kind.title()}</p>\n'
            )
        return self.renderToken(tokens, idx, options, env)

    def close_rule(self, tokens, idx, options, env) -> str:
        if tokens[idx].meta.get("admonition"):
            return "</div>\n"
        return self.renderToken(tokens, idx, options, env)

    md.core.ruler.push("alerts", rule)
    md.add_render_rule("blockquote_open", open_rule)
    md.add_render_rule("blockquote_close", close_rule)


def _build_markdown() -> MarkdownIt:
    md = MarkdownIt(
        "commonmark",
        {
            "html": True,
            "typographer": True,
            "highlight": _highlight_code,
        },
    )
    md.enable(["table", "strikethrough", "replacements", "smartquotes"])
    md.use(anchors_plugin, min_level=1, max_level=6)
    md.use(tasklists_plugin, enabled=True)
    md.use(footnote_plugin)
    md.use(_alerts_plugin)
    md.add_render_rule("fence", _render_fence)
    return md


def _inline_text(token) -> str:
    parts: list[str] = []
    for child in token.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type == "image":
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _collect_headings(tokens) -> list[_Heading]:
    headings: list[_Heading] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        inline = tokens[index + 1] if index + 1 < len(tokens) else None
        text = _inline_text(inline) if inline is not None else ""
        heading_id = token.attrGet("id") or _fallback_slug(text)
        headings.append(_Heading(int(token.tag[1]), heading_id, text))
    return headings


def _fallback_slug(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"\s+", "-", slug) or "section"


def _select_toc_headings(headings: list[_Heading]) -> list[_Heading]:
    preferred = [heading for heading in headings if 2 <= heading.level <= 3]
    if preferred:
        return preferred
    # A document whose sections are all H1 should still get a TOC rather than
    # the old "No sections" placeholder.
    return [heading for heading in headings if heading.text]


def _render_toc(headings: list[_Heading]) -> str:
    if not headings:
        return ""

    root: dict = {"level": 0, "children": []}
    stack = [root]
    for heading in headings:
        while len(stack) > 1 and heading.level <= stack[-1]["level"]:
            stack.pop()
        node = {
            "level": heading.level,
            "id": heading.id,
            "text": heading.text,
            "children": [],
        }
        stack[-1]["children"].append(node)
        stack.append(node)

    def render(nodes: list[dict]) -> str:
        parts = ["<ul>"]
        for node in nodes:
            parts.append(
                f'<li><a href="#{html_escape(node["id"], quote=True)}">'
                f"{html_escape(node['text'])}</a>"
            )
            if node["children"]:
                parts.append(render(node["children"]))
            parts.append("</li>")
        parts.append("</ul>")
        return "".join(parts)

    return render(root["children"])


def _count_words(tokens) -> tuple[int, int]:
    """Return (prose_words, code_words).

    Code is deliberately excluded from the prose count and reading time;
    otherwise a long technical document reports a wildly inflated reading
    time.
    """
    prose = 0
    code = 0
    for token in tokens:
        if token.type == "inline":
            for child in token.children or []:
                if child.type == "text":
                    prose += len(_WORD_RE.findall(child.content))
                elif child.type == "code_inline":
                    code += len(_WORD_RE.findall(child.content))
        elif token.type in ("fence", "code_block"):
            code += len(_WORD_RE.findall(token.content))
    return prose, code


def _first_paragraph(tokens) -> str:
    for index, token in enumerate(tokens):
        if token.type != "paragraph_open" or index + 1 >= len(tokens):
            continue
        text = _inline_text(tokens[index + 1])
        if text:
            return text[:160].rstrip() + ("…" if len(text) > 160 else "")
    return ""


def render_text(
    md_text: str,
    default_title: str = "Untitled",
    *,
    title_override: str | None = None,
    input_warnings: tuple[str, ...] | list[str] = (),
) -> Document:
    """Render Markdown text into a :class:`Document`."""
    text = normalize_newlines(md_text)
    if text.startswith("\ufeff"):
        text = text[1:]

    meta, source = parse_front_matter(text)
    source = repair_tables(source)

    md = _build_markdown()
    env: dict = {}
    tokens = md.parse(source, env)
    body_html = md.renderer.render(tokens, md.options, env)

    headings = _collect_headings(tokens)
    toc_html = _render_toc(_select_toc_headings(headings))
    prose_words, code_words = _count_words(tokens)

    first_h1 = next((heading.text for heading in headings if heading.level == 1 and heading.text), "")
    title = (title_override or meta.get("title") or first_h1 or default_title or "Untitled").strip()

    warnings = list(dict.fromkeys(str(warning) for warning in input_warnings))
    if "\ufffd" in source:
        warnings.append(
            "The input contains U+FFFD replacement characters; "
            "some text may already have been corrupted."
        )
    warnings = list(dict.fromkeys(warnings))

    description = meta.get("description", meta.get("summary", "")) or _first_paragraph(tokens)
    reading_minutes = max(1, math.ceil(prose_words / 200))

    return Document(
        body_html=body_html,
        toc_html=toc_html,
        title=title,
        author=meta.get("author", ""),
        date=meta.get("date", ""),
        description=description,
        word_count=prose_words,
        reading_minutes=reading_minutes,
        code_word_count=code_words,
        warnings=warnings,
        meta=meta,
    )


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
    auto_light = light.replace(".theme-light .highlight", ".theme-auto .highlight")
    auto_dark = dark.replace(".theme-dark .highlight", ".theme-auto .highlight")
    return "\n".join(
        [
            light,
            auto_light,
            dark,
            "@media (prefers-color-scheme: dark) {\n" + auto_dark + "\n}",
        ]
    )


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

    warnings_html = ""
    if doc.warnings:
        items = "".join(f"<li>{_escape(warning)}</li>" for warning in doc.warnings)
        warnings_html = (
            '<div class="input-warning" role="alert">'
            "<strong>Input warning</strong>"
            f"<ul>{items}</ul>"
            "</div>"
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
        "<!--GLOWMARK:WARNINGS-->": warnings_html,
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
    return html_escape(text, quote=True)


def load_assets() -> tuple[str, str]:
    css = (TEMPLATES_DIR / "style.css").read_text(encoding="utf-8")
    js = (TEMPLATES_DIR / "app.js").read_text(encoding="utf-8")
    return css, js
