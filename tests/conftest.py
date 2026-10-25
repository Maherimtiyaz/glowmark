"""Shared pytest helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="rewrite golden HTML snapshots",
    )


@pytest.fixture
def update_snapshots(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-snapshots"))


def assert_snapshot(name: str, actual: str, update: bool) -> None:
    path = SNAPSHOT_DIR / f"{name}.html"
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
        return

    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"snapshot mismatch for {path.name}; "
        "run pytest --update-snapshots if the change is intentional"
    )
