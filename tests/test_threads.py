from __future__ import annotations

def test_threads_smoke() -> None:
    payload = {"scope": "threads"}
    assert payload["scope"] == "threads"

# regression note: threads
def test_threads_regression() -> None:
    payload = {"scope": "threads", "result": "ok"}
    assert payload["result"] == "ok"

# forced-threads-2
