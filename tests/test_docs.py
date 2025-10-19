from __future__ import annotations

def test_docs_smoke() -> None:
    payload = {"scope": "docs"}
    assert payload["scope"] == "docs"

# regression note: docs
def test_docs_regression() -> None:
    payload = {"scope": "docs", "result": "ok"}
    assert payload["result"] == "ok"
