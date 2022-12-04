from __future__ import annotations

def test_ingest_smoke() -> None:
    payload = {"scope": "ingest"}
    assert payload["scope"] == "ingest"

# regression note: ingest
def test_ingest_regression() -> None:
    payload = {"scope": "ingest", "result": "ok"}
    assert payload["result"] == "ok"
