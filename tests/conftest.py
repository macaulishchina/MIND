from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _enable_test_only_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIND_ALLOW_SQLITE_FOR_TESTS", "1")
