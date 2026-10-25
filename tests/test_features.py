"""Behavioural tests for the features glowmark advertises."""

from __future__ import annotations

from glowmark.render import (
    codehilite_css,
    load_assets,
    render_page,
    render_text,
)


def test_bom_does_not_hide_the_title() -> None:
    doc = render_text("\ufeff# Voice Agent Platform\n\nBody.\n")
    assert doc.title == "Voice Agent Platform"
    assert "voice-agent-platform" in doc.toc_html


def test_title_fallback_chain() -> None:
    assert render_text("# Heading\n").title == "Heading"
    assert render_text("---\ntitle: Front Matter\n---\n\n# Heading\n").title == "Front Matter"
    assert render_text("# Heading\n", title_override="Override").title == "Override"
    assert render_text("No heading here.\n", default_title="notes").title == "notes"
    assert render_text("No heading here.\n").title == "Untitled"


def test_toc_comes_from_the_heading_tree() -> None:
    doc = render_text("# Title\n\n## One\n\n### Child\n\n## Two\n")
    assert '<a href="#one">One</a>' in doc.toc_html
    assert '<a href="#child">Child</a>' in doc.toc_html
    assert doc.toc_html.index("#one") < doc.toc_html.index("#child") < doc.toc_html.index("#two")
    assert "<ul>" in doc.toc_html


def test_toc_falls_back_to_h1_when_there_are_no_subsections() -> None:
    doc = render_text("# Only Heading\n\nText.\n")
    assert '<a href="#only-heading">Only Heading</a>' in doc.toc_html


def test_nested_fence_in_list_is_real_code() -> None:
    doc = render_text(
        "1. Step\n\n   ```bash\n   echo \"hi\"\n   ```\n\n"
        "2. Nested\n\n   - Child\n\n     ```js\n     console.log(1)\n     ```\n"
    )
    assert '```' not in doc.body_html
    assert doc.body_html.count('<pre class="highlight">') == 2
    assert "<li>" in doc.body_html
    assert "console" in doc.body_html


def test_backslash_escapes_follow_commonmark() -> None:
    doc = render_text(r"Escaped \*literal\*, \_underscore\_ and \& ampersand." + "\n")
    assert "*literal*" in doc.body_html
    assert "_underscore_" in doc.body_html
    assert "&amp; ampersand" in doc.body_html
    assert "\\*" not in doc.body_html


def test_task_lists_are_checkboxes() -> None:
    doc = render_text("- [x] done\n- [ ] todo\n")
    assert 'checked="checked"' in doc.body_html
    assert doc.body_html.count('type="checkbox"') == 2
    assert "[x]" not in doc.body_html
    assert "[ ]" not in doc.body_html


def test_github_alerts_become_admonitions() -> None:
    doc = render_text(
        "> [!NOTE]\n> Note body.\n\n"
        "> [!TIP]\n> Tip body.\n\n"
        "> [!WARNING]\n> Warning body.\n\n"
        "> [!IMPORTANT]\n> Important body.\n\n"
        "> [!CAUTION]\n> Caution body.\n"
    )
    for kind in ("note", "tip", "warning", "important", "caution"):
        assert f'class="admonition {kind}"' in doc.body_html
    assert "[!NOTE]" not in doc.body_html
    assert "Note body." in doc.body_html


def test_blank_lines_between_table_rows_are_repaired() -> None:
    doc = render_text(
        "| A | B |\n| - | - |\n\n| 1 | 2 |\n\n| 3 | 4 |\n"
    )
    assert doc.body_html.count("<table>") == 1
    assert "<td>1</td>" in doc.body_html
    assert "<td>3</td>" in doc.body_html


def test_stats_ignore_code_blocks() -> None:
    prose = " ".join(["word"] * 100)
    code = " ".join(["code"] * 500)
    doc = render_text(f"{prose}\n\n```python\n{code}\n```\n")
    assert doc.word_count == 100
    assert doc.code_word_count == 500
    assert doc.reading_minutes == 1


def test_rendered_page_is_utf8_and_surfaces_warnings() -> None:
    css, js = load_assets()
    doc = render_text("# Title\n", input_warnings=["Input is not valid UTF-8."])
    html = render_page(doc, css=css, js=js, code_css=codehilite_css())
    assert '<meta charset="utf-8">' in html
    assert "Input warning" in html
    assert "Input is not valid UTF-8." in html
    assert "<!--GLOWMARK:" not in html


def test_auto_theme_gets_pygments_colours() -> None:
    css = codehilite_css()
    assert ".theme-auto .highlight" in css
    assert "@media (prefers-color-scheme: dark)" in css
