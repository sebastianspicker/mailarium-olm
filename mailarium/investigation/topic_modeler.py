"""NMF-based topic modeling for email archives."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _has_prediction_backend(modeler: TopicModeler) -> bool:
    return modeler._is_fitted and modeler._vectorizer is not None and modeler._nmf_model is not None


class TopicModeler:
    """Discover topics in email corpus using TF-IDF + NMF.

    Uses scikit-learn's Non-negative Matrix Factorization (NMF) which is
    well-suited for short documents like emails. scikit-learn is already a
    transitive dependency of sentence-transformers.
    """

    def __init__(
        self,
        n_topics: int = 20,
        max_features: int = 10000,
        ngram_range: tuple[int, int] = (1, 2),
    ):
        """Initialize topic-model parameters and defer fitted estimator construction."""
        self.n_topics = n_topics
        self.max_features = max_features
        self.ngram_range = ngram_range
        self._vectorizer: Any | None = None
        self._nmf_model: Any | None = None
        self._feature_names: Any | None = None
        self._is_fitted = False

    def fit(self, texts: list[str]) -> None:
        """Fit the topic model on a corpus of email texts.

        Args:
            texts: List of email body texts.
        """
        from sklearn.decomposition import NMF
        from sklearn.feature_extraction.text import TfidfVectorizer

        valid_texts = [t for t in texts if t and t.strip()]
        if len(valid_texts) < 2:
            logger.warning("Need at least 2 documents for topic modeling, got %d", len(valid_texts))
            self._is_fitted = False
            return

        # Adjust n_topics if corpus is small
        actual_topics = min(self.n_topics, len(valid_texts) - 1)
        if actual_topics < 2:
            logger.warning("Corpus too small for meaningful topics")
            self._is_fitted = False
            return

        vectorizer = TfidfVectorizer(
            max_features=self.max_features,
            ngram_range=self.ngram_range,
            stop_words="english",
            sublinear_tf=True,
        )

        tfidf_matrix = vectorizer.fit_transform(valid_texts)
        feature_names = vectorizer.get_feature_names_out()

        nmf_model = NMF(
            n_components=actual_topics,
            random_state=42,
            max_iter=300,
            init="nndsvda",
        )
        nmf_model.fit(tfidf_matrix)
        self._vectorizer = vectorizer
        self._feature_names = feature_names
        self._nmf_model = nmf_model
        self._is_fitted = True
        logger.info("Topic model fitted: %d topics from %d documents", actual_topics, len(valid_texts))

    @property
    def is_fitted(self) -> bool:
        """Report whether topic-model training completed and prediction state is available."""
        return self._is_fitted

    def get_topics(self, top_words: int = 10) -> list[dict[str, Any]]:
        """Get all discovered topics with their top words.

        Args:
            top_words: Number of top words per topic.

        Returns:
            List of {id, label, top_words: [str]} dicts.
        """
        if not self._is_fitted or self._nmf_model is None or self._feature_names is None:
            return []

        topics = []
        for topic_idx, topic_vector in enumerate(self._nmf_model.components_):
            top_indices = topic_vector.argsort()[::-1][:top_words]
            words = [self._feature_names[i] for i in top_indices if topic_vector[i] > 0]
            label = " / ".join(words[:3]) if words else f"Topic {topic_idx}"
            topics.append(
                {
                    "id": topic_idx,
                    "label": label,
                    "top_words": words,
                }
            )
        return topics

    def predict(self, text: str) -> list[tuple[int, float]]:
        """Get topic distribution for a single document.

        Args:
            text: Document text.

        Returns:
            List of (topic_id, weight) tuples, sorted by weight descending.
        """
        if not text or not text.strip():
            return []

        if not _has_prediction_backend(self):
            return []

        vectorizer = self._vectorizer
        nmf_model = self._nmf_model
        if vectorizer is None or nmf_model is None:
            return []
        tfidf_vec = vectorizer.transform([text])
        topic_weights = nmf_model.transform(tfidf_vec)[0]

        results = [
            (int(i), round(float(w), 4))
            for i, w in enumerate(topic_weights)
            if w > 0.01  # Filter near-zero weights
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results
