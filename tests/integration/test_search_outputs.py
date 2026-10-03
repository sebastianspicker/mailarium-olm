"""Golden search outputs over one synthetic canonical corpus.

The snapshot was recorded from the retrieval implementation before it was
recomposed into collaborators (commit 8c9c054). It pins dense, hybrid,
learned-sparse, metadata-filtered, request-based, thread, sender, folder,
statistics, and serialization outputs, plus search diagnostics, using a
deterministic local encoder instead of downloaded models. Regenerate
deliberately with ``MAILARIUM_UPDATE_SNAPSHOTS=1``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from mailarium.archive import open_archive_database
from mailarium.interfaces.presentation import serialize_results
from mailarium.retrieval.retriever import SearchEngine

SNAPSHOT = Path(__file__).parent / "snapshots" / "search_outputs.json"

_VOCABULARY = ("budget", "launch", "timeline", "berlin", "invoice", "review", "contract", "travel")


class _BagOfWordsEmbedder:
    """Deterministic dense and sparse encoder over a fixed vocabulary."""

    has_sparse = True

    def encode_dense(self, queries: list[str]) -> list[list[float]]:
        return [_vector(query) for query in queries]

    def encode_sparse_query(self, queries: list[str]) -> list[dict[int, float]]:
        return [_sparse(query) for query in queries]


def _vector(text: str) -> list[float]:
    lowered = text.lower()
    counts = [float(lowered.count(word)) + 0.01 * (index + 1) for index, word in enumerate(_VOCABULARY)]
    norm = sum(value * value for value in counts) ** 0.5
    return [value / norm for value in counts]


def _sparse(text: str) -> dict[int, float]:
    lowered = text.lower()
    return {index: float(lowered.count(word)) for index, word in enumerate(_VOCABULARY) if word in lowered}


_CORPUS = [
    (
        "m1__0",
        "Launch timeline: we ship after the Friday review.",
        "m1",
        "alice@example.test",
        "Inbox",
        "2025-03-03",
        "conv-launch",
        True,
        "original",
    ),
    (
        "m1__1",
        "Budget for the launch is 5000 EUR pending review.",
        "m1",
        "alice@example.test",
        "Inbox",
        "2025-03-03",
        "conv-launch",
        True,
        "original",
    ),
    ("m2__0", "I approve the launch budget.", "m2", "bob@example.test", "Inbox", "2025-03-04", "conv-launch", False, "reply"),
    (
        "m3__0",
        "Berlin travel booked for the budget review.",
        "m3",
        "carol@example.test",
        "Projects",
        "2025-03-10",
        "conv-berlin",
        False,
        "original",
    ),
    (
        "m4__0",
        "Invoice attached for the Berlin contract.",
        "m4",
        "dave@example.test",
        "Finance",
        "2025-04-01",
        "conv-invoice",
        True,
        "forward",
    ),
    (
        "m5__0",
        "Contract review meeting moved to Monday.",
        "m5",
        "bob@example.test",
        "Projects",
        "2025-04-02",
        "conv-contract",
        False,
        "reply",
    ),
    (
        "m6__0",
        "Travel invoice reimbursement and timeline.",
        "m6",
        "erin@example.test",
        "Finance",
        "2025-05-15",
        "conv-invoice",
        False,
        "reply",
    ),
]


def _metadata(
    uid: str, sender: str, folder: str, date: str, conversation: str, attachments: bool, email_type: str
) -> dict[str, Any]:
    return {
        "uid": uid,
        "sender_email": sender,
        "sender_name": sender.split("@", 1)[0].title(),
        "folder": folder,
        "date": date,
        "conversation_id": conversation,
        "subject": f"Subject {conversation}",
        "has_attachments": attachments,
        "email_type": email_type,
        "to": "team@example.test",
        "cc": "observer@example.test" if folder == "Projects" else "",
        "chunk_type": "body",
    }


_FILTERED_QUERIES: list[tuple[str, dict[str, Any]]] = [
    ("launch budget", {"top_k": 5}),
    ("launch budget", {"top_k": 2}),
    ("berlin travel", {"top_k": 5}),
    ("invoice", {"top_k": 5, "folder": "finance"}),
    ("review", {"top_k": 5, "sender": "bob"}),
    ("review", {"top_k": 5, "date_from": "2025-03-05", "date_to": "2025-04-30"}),
    ("timeline", {"top_k": 5, "has_attachments": True}),
    ("contract", {"top_k": 5, "email_type": "reply"}),
    ("budget", {"top_k": 5, "min_score": 0.5}),
    ("budget", {"top_k": 5, "cc": "observer"}),
    ("budget", {"top_k": 5, "subject": "berlin"}),
    ("launch budget", {"top_k": 5, "hybrid": True}),
    ("invoice contract", {"top_k": 4, "hybrid": True, "folder": "finance"}),
    ("nothing matches here", {"top_k": 3}),
]


def _result(result: Any) -> dict[str, Any]:
    payload = result.to_dict()
    payload["score"] = None if payload["score"] is None else round(payload["score"], 6)
    payload["distance"] = None if payload["distance"] is None else round(payload["distance"], 6)
    return payload


def _canonical(value: Any, root: Path) -> Any:
    text = json.dumps(value, sort_keys=True, default=str).replace(str(root), "<tmp>")
    text = re.sub(r"(-?\d+\.\d{7,})", lambda match: repr(round(float(match.group(1)), 6)), text)
    text = re.sub(r"\"([a-z_]*(?:_ms|_seconds|elapsed[a-z_]*))\": [0-9.e-]+", r'"\1": "<t>"', text)
    return json.loads(text)


def _set_embedder(engine: SearchEngine, embedder: Any) -> None:
    try:
        engine.embedder = embedder
    except AttributeError:  # recorded against the pre-collaborator engine
        engine._embedder = embedder  # type: ignore[attr-defined]


def test_search_outputs_match_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(root))
    for key in ("MAILARIUM_ALLOWED_RUNTIME_ROOTS", "SQLITE_PATH", "VECTOR_INDEX_PATH", "RAG_SCOPE", "TOP_K"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RERANK_ENABLED", "false")
    monkeypatch.setenv("HYBRID_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_PROFILE", "offline-test")
    monkeypatch.setenv("MCP_MODEL_PROFILE", "balanced")

    sqlite_path = root / "archive.db"
    database = open_archive_database(str(sqlite_path))
    engine = SearchEngine(
        vector_index_path=str(root / "vectors"),
        sqlite_path=str(sqlite_path),
        sparse_enabled=True,
        image_search_enabled=False,
        database=database,
    )
    _set_embedder(engine, _BagOfWordsEmbedder())
    engine.collection.add(
        ids=[row[0] for row in _CORPUS],
        embeddings=[_vector(row[1]) for row in _CORPUS],
        documents=[row[1] for row in _CORPUS],
        metadatas=[_metadata(*row[2:]) for row in _CORPUS],
    )
    database.sparse.insert_sparse_batch(
        [row[0] for row in _CORPUS],
        [_sparse(row[1]) for row in _CORPUS],
        model_id=engine.settings.sparse_model,
        model_revision=engine.settings.sparse_model_revision,
    )

    outputs: dict[str, Any] = {}
    try:
        for index, (query, filters) in enumerate(_FILTERED_QUERIES):
            results = engine.search_filtered(query, **filters)
            outputs[f"{index:02d} search_filtered {query} {json.dumps(filters, sort_keys=True)}"] = {
                "results": [_result(result) for result in results],
                "debug": engine.last_search_debug,
            }
        outputs["search plain"] = [_result(result) for result in engine.search("budget review", top_k=4)]
        outputs["search where"] = [
            _result(result) for result in engine.search("budget review", top_k=4, where={"folder": "Projects"})
        ]
        from mailarium.retrieval import SearchRequest

        response = engine.execute(SearchRequest(query="invoice travel", top_k=3, hybrid=True, folder="Finance"))
        outputs["execute"] = {"results": [_result(result) for result in response.results], "diagnostics": response.diagnostics}
        outputs["thread"] = [_result(result) for result in engine.search_by_thread("conv-launch")]
        outputs["senders"] = engine.list_senders(limit=10)
        outputs["folders"] = engine.list_folders()
        outputs["stats"] = engine.stats()
        serialized_results = engine.search_filtered("launch budget", top_k=3)
        outputs["serialize"] = serialize_results(engine.settings, "launch budget", serialized_results, max_body_chars=20)
    finally:
        engine.close()
        database.close()

    outputs = _canonical(outputs, root)
    if os.environ.get("MAILARIUM_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(outputs, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(outputs) == sorted(expected)
    for key, value in expected.items():
        assert outputs[key] == value, key
