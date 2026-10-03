"""Optional image-space retrieval and rank fusion with text results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import SearchResult

if TYPE_CHECKING:
    from mailarium.platform.settings import Settings

    from .image_embedder import ImageEmbedder


class ImageSearch:
    """Query the image vector collection and rank-fuse it with text results."""

    def __init__(self, image_collection: Any, settings: Settings) -> None:
        """Bind the image collection and image-model settings without loading a model."""
        self._image_collection = image_collection
        self._settings = settings
        self._image_embedder: ImageEmbedder | None = None

    def merge(
        self,
        query: str,
        text_results: list[SearchResult],
        top_k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Rank-fuse text and image spaces without comparing raw distances."""
        image_collection = self._available_image_collection()
        if image_collection is None:
            return text_results[:top_k]
        image_results = self._image_search_results(query, top_k, where, image_collection)
        if image_results is None:
            return text_results[:top_k]
        return rank_fuse_results(text_results, image_results, top_k)

    def release(self) -> list[Any]:
        """Drop the loaded image embedder and return it for closing."""
        image_embedder, self._image_embedder = self._image_embedder, None
        return [image_embedder]

    def _available_image_collection(self) -> Any | None:
        """Return a non-empty configured image collection, when enabled."""
        image_collection = self._image_collection
        if not self._settings.image_search_enabled or image_collection is None:
            return None
        return image_collection if image_collection.count() else None

    def _image_search_results(
        self,
        query: str,
        top_k: int,
        where: dict[str, Any] | None,
        image_collection: Any,
    ) -> list[SearchResult] | None:
        """Encode and query the image space, returning None for an unusable query."""
        if self._image_embedder is None:
            from .image_embedder import ImageEmbedder

            self._image_embedder = ImageEmbedder(
                model_name=self._settings.image_embedding_model,
                model_revision=self._settings.image_embedding_model_revision,
                device=self._settings.device,
                load_mode=self._settings.embedding_load_mode,
            )
        query_vector = self._image_embedder.encode_text(query)
        if not query_vector:
            return None
        payload = image_collection.query(
            query_embeddings=[query_vector],
            n_results=max(top_k, 1),
            include=["documents", "metadatas", "distances"],
            where=where,
        )
        return _image_results_from_payload(payload)


def _image_results_from_payload(payload: dict[str, Any]) -> list[SearchResult]:
    """Hydrate ranked image rows from the collection response shape."""
    ids = (payload.get("ids") or [[]])[0]
    documents = (payload.get("documents") or [[]])[0]
    metadatas = (payload.get("metadatas") or [[]])[0]
    distances = (payload.get("distances") or [[]])[0]
    return [
        _image_result_from_payload_row(chunk_id, index, documents, metadatas, distances) for index, chunk_id in enumerate(ids)
    ]


def _image_result_from_payload_row(
    chunk_id: str,
    index: int,
    documents: list[Any],
    metadatas: list[Any],
    distances: list[Any],
) -> SearchResult:
    """Hydrate one image result while retaining payload-array defaults."""
    document = documents[index] if index < len(documents) else ""
    metadata = metadatas[index] if index < len(metadatas) else {}
    distance = float(distances[index]) if index < len(distances) else 1.0
    return SearchResult(
        chunk_id=chunk_id,
        text=document,
        metadata={**metadata, "retrieval_space": "image"},
        distance=distance,
    )


def rank_fuse_results(
    text_results: list[SearchResult],
    image_results: list[SearchResult],
    top_k: int,
) -> list[SearchResult]:
    """Fuse incompatible vector spaces by reciprocal rank only."""
    scores: dict[str, float] = {}
    rows: dict[str, SearchResult] = {}
    sources: dict[str, set[str]] = {}
    for source, results in (("text", text_results), ("image", image_results)):
        for rank, result in enumerate(results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (60 + rank)
            rows.setdefault(result.chunk_id, result)
            sources.setdefault(result.chunk_id, set()).add(source)
    if not scores:
        return []
    maximum = max(scores.values())
    ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [
        SearchResult(
            chunk_id=rows[chunk_id].chunk_id,
            text=rows[chunk_id].text,
            metadata={
                **rows[chunk_id].metadata,
                "retrieval_spaces": sorted(sources[chunk_id]),
                "score_kind": "rank_fused",
            },
            distance=max(0.0, 1.0 - (scores[chunk_id] / maximum)),
        )
        for chunk_id in ranked_ids[:top_k]
    ]
