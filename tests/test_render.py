"""Golden-file tests for the renderer."""

from __future__ import annotations

from pathlib import Path

from conftest import assert_snapshot

from glowmark.render import render_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _snapshot(doc) -> str:
    title = doc.title.replace("--", "- -")
    return (
        f"<!-- title: {title} -->\n"
        f"<!-- words: {doc.word_count} -->\n"
        f"<!-- code_words: {doc.code_word_count} -->\n"
        f"<!-- minutes: {doc.reading_minutes} -->\n"
        f"<!-- warnings: {len(doc.warnings)} -->\n"
        "<!-- toc -->\n"
        f"{doc.toc_html}\n"
        "<!-- body -->\n"
        f"{doc.body_html}\n"
    )


def test_kitchen_sink_snapshot(update_snapshots: bool) -> None:
    source = (FIXTURES / "kitchen-sink.md").read_text(encoding="utf-8")
    doc = render_text(source)
    assert_snapshot("kitchen-sink", _snapshot(doc), update_snapshots)


def test_pandoc_messy_snapshot(update_snapshots: bool) -> None:
    source = (FIXTURES / "pandoc-messy.md").read_text(encoding="utf-8")
    doc = render_text(source)
    assert_snapshot("pandoc-messy", _snapshot(doc), update_snapshots)
