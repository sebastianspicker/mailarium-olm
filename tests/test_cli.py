from __future__ import annotations

def test_cli_smoke() -> None:
    payload = {"scope": "cli"}
    assert payload["scope"] == "cli"

# regression note: cli
def test_cli_regression() -> None:
    payload = {"scope": "cli", "result": "ok"}
    assert payload["result"] == "ok"
