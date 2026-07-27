"""Model-revision wiring contracts that do not load model weights."""

from __future__ import annotations

from unittest.mock import MagicMock

from mailarium.config import Settings


class _Collection:
    def attach_database(self, _database) -> None:
        return None

    def count(self) -> int:
        return 0

    def close(self) -> None:
        return None


def _settings(tmp_path) -> Settings:
    return Settings(
        vector_index_path=str(tmp_path / "vector-index"),
        sqlite_path=str(tmp_path / "mail.sqlite"),
        embedding_model="dense/model",
        embedding_model_revision="dense-revision",
        image_embedding_model="image/model",
        image_embedding_model_revision="image-revision",
    )


def test_email_embedder_propagates_dense_and_image_revisions(monkeypatch, tmp_path):
    import mailarium.embedder as embedder_module

    settings = _settings(tmp_path)
    collection_calls: list[dict] = []
    multi_vector = MagicMock()
    monkeypatch.setattr(embedder_module, "resolve_runtime_settings", lambda **_kwargs: settings)
    monkeypatch.setattr(
        embedder_module,
        "get_vector_collection",
        lambda **kwargs: collection_calls.append(kwargs) or _Collection(),
    )
    monkeypatch.setattr(embedder_module, "MultiVectorEmbedder", multi_vector)

    embedder = embedder_module.EmailEmbedder()
    _ = embedder.embedder

    assert [call["model_revision"] for call in collection_calls] == ["dense-revision", "image-revision"]
    assert multi_vector.call_args.kwargs["model_revision"] == "dense-revision"


def test_email_retriever_propagates_dense_and_image_revisions(monkeypatch, tmp_path):
    import mailarium.retriever as retriever_module

    settings = _settings(tmp_path)
    collection_calls: list[dict] = []
    multi_vector = MagicMock()
    monkeypatch.setattr(retriever_module, "resolve_runtime_settings", lambda **_kwargs: settings)
    monkeypatch.setattr(
        retriever_module,
        "get_vector_collection",
        lambda **kwargs: collection_calls.append(kwargs) or _Collection(),
    )
    monkeypatch.setattr(retriever_module, "MultiVectorEmbedder", multi_vector)

    retriever = retriever_module.EmailRetriever()
    _ = retriever.embedder

    assert [call["model_revision"] for call in collection_calls] == ["dense-revision", "image-revision"]
    assert multi_vector.call_args.kwargs["model_revision"] == "dense-revision"


def test_attachment_image_embedder_uses_configured_revision(monkeypatch, tmp_path):
    import mailarium.attachment_extractor as attachment_module
    import mailarium.config as config_module
    import mailarium.image_embedder as image_module

    settings = _settings(tmp_path)
    image_embedder = MagicMock()
    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(image_module, "ImageEmbedder", image_embedder)
    monkeypatch.setattr(attachment_module, "_image_embedder", None)

    attachment_module._get_image_embedder()

    assert image_embedder.call_args.kwargs["model_revision"] == "image-revision"
