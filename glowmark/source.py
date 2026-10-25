"""Read Markdown input as bytes and decode it safely.

The CLI must never let the platform's default text encoding decide how a
Markdown file is interpreted.  Everything is read as bytes, decoded as UTF-8
(with BOM detection and a clear warning when that is not possible), and
newlines are normalised before the renderer sees the text.
"""

from __future__ import annotations

import codecs
import locale
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceText:
    """Decoded Markdown plus any warnings produced while decoding it."""

    text: str
    encoding: str = "utf-8"
    warnings: tuple[str, ...] = ()


def normalize_newlines(text: str) -> str:
    """Normalise CRLF and lone CR to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_bytes(data: bytes) -> SourceText:
    """Decode Markdown bytes as UTF-8, handling BOMs and bad input.

    UTF-8 is always tried first.  If that fails, the platform's preferred
    single-byte encoding (usually Windows-1252 on Windows) is tried as a
    recovery path, and the caller is warned.  If even that fails, invalid
    bytes are replaced and a visible warning is returned.
    """
    warnings: list[str] = []
    encoding = "utf-8"
    replacement_warned = False

    bom_encoding: str | None = None
    if data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE):
        bom_encoding = "utf-32"
    elif data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        bom_encoding = "utf-16"
    elif data.startswith(codecs.BOM_UTF8):
        bom_encoding = "utf-8-sig"

    if bom_encoding is not None:
        encoding = bom_encoding
        try:
            text = data.decode(bom_encoding)
        except UnicodeDecodeError:
            text = data.decode(bom_encoding, errors="replace")
            count = text.count("\ufffd")
            replacement_warned = True
            warnings.append(
                f"Input has a {bom_encoding.upper()} BOM but is not valid "
                f"{bom_encoding.upper()}; "
                f"{count} invalid byte sequence(s) were replaced with U+FFFD. "
                "Re-save the file as UTF-8."
            )
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            text = ""
            candidates: list[str] = []
            preferred = locale.getpreferredencoding(False) or ""
            for candidate in (preferred, "cp1252"):
                key = candidate.lower().replace("-", "").replace("_", "")
                if candidate and key not in {c.lower().replace("-", "").replace("_", "") for c in candidates}:
                    candidates.append(candidate)

            for candidate in candidates:
                try:
                    text = data.decode(candidate)
                except (UnicodeDecodeError, LookupError):
                    continue
                encoding = candidate
                warnings.append(
                    "Input is not valid UTF-8 "
                    f"(byte 0x{data[exc.start]:02x} at offset {exc.start}); "
                    f"decoded as {candidate}. Re-save the file as UTF-8 to avoid mojibake."
                )
                break

            if not text:
                text = data.decode("utf-8", errors="replace")
                encoding = "utf-8 (replaced)"
                count = text.count("\ufffd")
                replacement_warned = True
                warnings.append(
                    "Input is not valid UTF-8; "
                    f"{count} invalid byte sequence(s) were replaced with U+FFFD. "
                    "Re-save the file as UTF-8."
                )

    # A BOM can survive if it was embedded after other whitespace, or if the
    # input was decoded with a single-byte codec.
    if text.startswith("\ufeff"):
        text = text[1:]

    if "\ufffd" in text and not replacement_warned:
        count = text.count("\ufffd")
        warnings.append(
            f"Input contains {count} U+FFFD replacement character(s); "
            "the text may already have been corrupted before glowmark saw it."
        )

    text = normalize_newlines(text)
    return SourceText(text=text, encoding=encoding, warnings=tuple(dict.fromkeys(warnings)))


def read_file(path: str | Path) -> SourceText:
    """Read a Markdown file as bytes and decode it."""
    return decode_bytes(Path(path).read_bytes())


def read_stdin(stream=None) -> SourceText:
    """Read stdin as bytes when possible, falling back to text streams."""
    stream = stream or sys.stdin
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        return decode_bytes(buffer.read())

    text = stream.read()
    warnings: list[str] = []
    if "\ufffd" in text:
        count = text.count("\ufffd")
        warnings.append(
            f"Input contains {count} U+FFFD replacement character(s); "
            "the text may already have been corrupted before glowmark saw it."
        )
    return SourceText(
        text=normalize_newlines(text.lstrip("\ufeff")),
        encoding="text",
        warnings=tuple(warnings),
    )
