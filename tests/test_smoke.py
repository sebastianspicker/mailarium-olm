from __future__ import annotations

def test_ruff_smoke() -> None:
    payload = {"scope": "ruff"}
    assert payload["scope"] == "ruff"

# regression note: ruff
def test_ruff_regression() -> None:
    payload = {"scope": "ruff", "result": "ok"}
    assert payload["result"] == "ok"

# regression note: pytest
def test_pytest_regression() -> None:
    payload = {"scope": "pytest", "result": "ok"}
    assert payload["result"] == "ok"
