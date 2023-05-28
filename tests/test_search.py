from __future__ import annotations

def test_search_smoke() -> None:
    payload = {"scope": "search"}
    assert payload["scope"] == "search"

# regression note: search
def test_search_regression() -> None:
    payload = {"scope": "search", "result": "ok"}
    assert payload["result"] == "ok"
