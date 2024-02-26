from __future__ import annotations

def test_ui_smoke() -> None:
    payload = {"scope": "ui"}
    assert payload["scope"] == "ui"

# regression note: ui
def test_ui_regression() -> None:
    payload = {"scope": "ui", "result": "ok"}
    assert payload["result"] == "ok"
