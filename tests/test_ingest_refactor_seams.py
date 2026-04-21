"""Structural tests for ingest pipeline extraction."""

from __future__ import annotations

from unittest.mock import patch

import src.ingest as ingest_mod


def test_ingest_wrapper_delegates_to_pipeline_module() -> None:
    with patch("src.ingest_pipeline.ingest_impl", return_value={"emails_parsed": 3}) as mock_impl:
        result = ingest_mod.ingest("mock.olm", dry_run=True, batch_size=7)
    assert result == {"emails_parsed": 3}
    mock_impl.assert_called_once()


def test_reingest_bodies_wrapper_delegates_to_reingest_module() -> None:
    with patch("src.ingest_reingest.reingest_bodies_impl", return_value={"message": "ok"}) as mock_impl:
        result = ingest_mod.reingest_bodies("mock.olm", sqlite_path="db.sqlite", force=True)
    assert result["message"] == "ok"
    mock_impl.assert_called_once()
    call = mock_impl.call_args
    assert call.args == ("mock.olm",)
    assert call.kwargs["sqlite_path"] == "db.sqlite"
    assert call.kwargs["force"] is True
    assert call.kwargs["parse_olm_fn"] is ingest_mod.parse_olm


def test_reembed_wrapper_delegates_to_reingest_module() -> None:
    with patch("src.ingest_reingest.reembed_impl", return_value={"message": "done"}) as mock_impl:
        result = ingest_mod.reembed(chromadb_path="chroma", sqlite_path="db.sqlite", batch_size=12)
    assert result["message"] == "done"
    mock_impl.assert_called_once_with(chromadb_path="chroma", sqlite_path="db.sqlite", batch_size=12)


def test_reset_index_wrapper_delegates_to_reingest_module() -> None:
    args = object()
    with patch("src.ingest_reingest.reset_index_impl") as mock_impl:
        ingest_mod._reset_index(args)
    mock_impl.assert_called_once_with(args)


def test_embed_pipeline_is_reexported_from_extracted_module() -> None:
    from src.ingest_embed_pipeline import _EmbedPipeline as extracted_pipeline

    assert ingest_mod._EmbedPipeline is extracted_pipeline


def test_embed_pipeline_sentinel_is_reexported_from_extracted_module() -> None:
    from src.ingest_embed_pipeline import _SENTINEL as extracted_sentinel

    assert ingest_mod._SENTINEL is extracted_sentinel
