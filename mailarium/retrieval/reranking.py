"""Second-stage reranking through a local late-interaction runner or a cross-encoder."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.platform.settings import Settings

    from .late_interaction_backend import LocalLateInteractionBackend
    from .models import SearchResult
    from .reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


class ResultReranker:
    """Own the lazily loaded reranking backends and choose one per request."""

    def __init__(self, settings: Settings) -> None:
        """Record reranker settings without loading either backend."""
        self._settings = settings
        self._cross_encoder: CrossEncoderReranker | None = None
        self._late_interaction_backend: LocalLateInteractionBackend | None = None

    def rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        """Apply a configured local late-interaction runner or cross-encoder."""
        settings = self._settings
        use_late_interaction = bool(
            settings.late_interaction_enabled and settings.late_interaction_runner and settings.late_interaction_model_path
        )
        if use_late_interaction:
            try:
                if self._late_interaction_backend is None:
                    from .late_interaction_backend import LocalLateInteractionBackend

                    self._late_interaction_backend = LocalLateInteractionBackend(
                        runner_path=settings.late_interaction_runner,
                        model_path=settings.late_interaction_model_path,
                        runner_sha256=settings.late_interaction_runner_sha256 or None,
                        allowed_runner_directory=settings.late_interaction_runner_directory or None,
                    )
                return self._late_interaction_backend.rerank(query, results, top_k=top_k)
            except Exception:
                logger.warning("Local late-interaction reranking failed; using cross-encoder", exc_info=True)

        if self._cross_encoder is None:
            from .reranker import CrossEncoderReranker

            self._cross_encoder = CrossEncoderReranker(model_name=settings.rerank_model)
        return self._cross_encoder.rerank(query, results, top_k=top_k)

    def release(self) -> list[Any]:
        """Drop both loaded backends and return them for closing."""
        cross_encoder, self._cross_encoder = self._cross_encoder, None
        late_interaction, self._late_interaction_backend = self._late_interaction_backend, None
        return [cross_encoder, late_interaction]
