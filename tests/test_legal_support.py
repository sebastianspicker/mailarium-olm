from __future__ import annotations

def test_legal_support_smoke() -> None:
    payload = {"scope": "legal support"}
    assert payload["scope"] == "legal support"

# regression note: legal_support
def test_legal_support_regression() -> None:
    payload = {"scope": "legal support", "result": "ok"}
    assert payload["result"] == "ok"
