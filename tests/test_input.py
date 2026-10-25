"""Input decoding and end-to-end CLI tests."""

from __future__ import annotations

import codecs
import os
import subprocess
import sys
from pathlib import Path

from glowmark.source import decode_bytes, read_file

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str], stdin: bytes | None = None, env: dict | None = None):
    return subprocess.run(
        [sys.executable, "-m", "glowmark.cli", *args],
        input=stdin,
        cwd=ROOT,
        capture_output=True,
        env=env,
    )


def test_utf8_bom_is_stripped() -> None:
    source = decode_bytes(b"\xef\xbb\xbf# Caf\xc3\xa9 \xe2\x80\x94 \xce\xbc-law")
    assert source.text == "# Café — μ-law"
    assert source.warnings == ()


def test_utf16_bom_is_detected() -> None:
    data = codecs.BOM_UTF16_LE + "# UTF-16 ✨\n".encode("utf-16-le")
    source = decode_bytes(data)
    assert source.text == "# UTF-16 ✨\n"
    assert source.encoding == "utf-16"


def test_crlf_is_normalised() -> None:
    source = decode_bytes(b"# Title\r\n\r\nBody\r\n")
    assert source.text == "# Title\n\nBody\n"


def test_non_utf8_input_warns_instead_of_silently_replacing() -> None:
    source = decode_bytes(b"# Caf\xe9\n")
    assert "Café" in source.text
    assert any("not valid UTF-8" in warning for warning in source.warnings)


def test_undecodable_bytes_get_a_visible_warning() -> None:
    source = decode_bytes(b"# Bad \x81\n")
    assert "\ufffd" in source.text
    assert any("replaced with U+FFFD" in warning for warning in source.warnings)


def test_malformed_bom_input_warns_instead_of_crashing() -> None:
    cases = [
        b"\xef\xbb\xbf# Bad \x81\n",
        codecs.BOM_UTF16_LE + b"# Bad \x81",
        codecs.BOM_UTF32_LE + b"# Bad",
    ]
    for data in cases:
        source = decode_bytes(data)
        assert "\ufffd" in source.text
        assert any("replaced with U+FFFD" in warning for warning in source.warnings)
        assert not source.text.startswith("\ufeff")


def test_read_file_handles_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.md"
    path.write_bytes(b"\xef\xbb\xbf# File Title\n")
    source = read_file(path)
    assert source.text == "# File Title\n"


def test_cli_stdin_keeps_utf8_bytes_intact(tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = _run(
        ["-", "--out", str(out)],
        "# Café — μ-law → ✨\n\nBody.\n".encode(),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert "Café — μ-law → ✨" in html
    assert "??" not in html


def test_cli_stdin_handles_bom(tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    result = _run(["-", "--out", str(out)], b"\xef\xbb\xbf# BOM Title\n\nBody.\n")
    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert "<title>BOM Title</title>" in html
    assert '<h1>BOM Title</h1>' in html


def test_cli_file_path_handles_bom(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_bytes(b"\xef\xbb\xbf# File Title\n")
    out = tmp_path / "out.html"
    result = _run([str(source), "--out", str(out)])
    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert "<title>File Title</title>" in html


def test_cli_prints_and_embeds_a_warning_for_bad_bytes(tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    result = _run(["-", "--out", str(out)], b"# Bad \x81\n")
    assert result.returncode == 0, result.stderr
    assert b"warning" in result.stderr.lower()
    html = out.read_text(encoding="utf-8")
    assert "Input warning" in html
    assert "\ufffd" in html


def test_cli_handles_malformed_bom_input(tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    result = _run(["-", "--out", str(out)], b"\xef\xbb\xbf# Bad \x81\n")
    assert result.returncode == 0, result.stderr
    assert b"warning" in result.stderr.lower()
    html = out.read_text(encoding="utf-8")
    assert "Input warning" in html


def test_cli_title_override_wins(tmp_path: Path) -> None:
    out = tmp_path / "out.html"
    result = _run(
        ["-", "--title", "Override", "--out", str(out)],
        b"# Original\n",
    )
    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert "<title>Override</title>" in html
    assert "<h1>Override</h1>" in html
