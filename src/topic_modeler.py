"""NMF-based topic modeling for email archives."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOPIC_MODEL_CACHE_VERSION = 1
_ALLOWED_CACHE_SUFFIXES = frozenset({".pkl", ".pickle"})


def _trusted_model_codec() -> Any:
    """Return joblib for trusted sklearn cache persistence."""
    import joblib

    return joblib


def _topic_distribution(row: Any) -> list[tuple[int, float]]:
    distribution = [(int(i), round(float(w), 4)) for i, w in enumerate(row) if w > 0.01]
    distribution.sort(key=lambda item: item[1], reverse=True)
    return distribution


def _validate_cache_version(data: dict[str, Any]) -> None:
    cached_version = data.get("_topic_model_cache_version", data.get("_pickle_cache_version", 0))
    if cached_version != _TOPIC_MODEL_CACHE_VERSION:
        raise ValueError(
            f"Topic model cache version mismatch: "
            f"expected {_TOPIC_MODEL_CACHE_VERSION}, got {cached_version}. "
            f"Retrain the model with the current code version."
        )


def _validate_sklearn_version(saved_version: str) -> None:
    try:
        import sklearn
    except ImportError:
        logger.warning("scikit-learn not installed — cannot validate model version")
        return

    current_major = sklearn.__version__.split(".", maxsplit=1)[0]
    saved_major = saved_version.split(".", maxsplit=1)[0] if saved_version != "unknown" else None
    if saved_major and current_major != saved_major:
        raise ValueError(
            f"Topic model was saved with scikit-learn {saved_version} "
            f"but current version is {sklearn.__version__}. "
            f"Major version mismatch — please retrain the model."
        )
    if saved_version != "unknown" and saved_version != sklearn.__version__:
        logger.warning(
            "Topic model was saved with scikit-learn %s, current is %s. Minor version differences may cause subtle issues.",
            saved_version,
            sklearn.__version__,
        )


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
        self.n_topics = n_topics
        self.max_features = max_features
        self.ngram_range = ngram_range
        self._vectorizer = None
        self._nmf_model = None
        self._feature_names = None
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

        self._vectorizer = TfidfVectorizer(
            max_features=self.max_features,
            ngram_range=self.ngram_range,
            stop_words="english",
            sublinear_tf=True,
        )

        tfidf_matrix = self._vectorizer.fit_transform(valid_texts)
        self._feature_names = self._vectorizer.get_feature_names_out()

        self._nmf_model = NMF(
            n_components=actual_topics,
            random_state=42,
            max_iter=300,
            init="nndsvda",
        )
        self._nmf_model.fit(tfidf_matrix)
        self._is_fitted = True
        logger.info("Topic model fitted: %d topics from %d documents", actual_topics, len(valid_texts))

    @property
    def is_fitted(self) -> bool:
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

        tfidf_vec = self._vectorizer.transform([text])
        topic_weights = self._nmf_model.transform(tfidf_vec)[0]

        results = [
            (int(i), round(float(w), 4))
            for i, w in enumerate(topic_weights)
            if w > 0.01  # Filter near-zero weights
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def predict_batch(self, texts: list[str]) -> list[list[tuple[int, float]]]:
        """Get topic distributions for multiple documents.

        Args:
            texts: List of document texts.

        Returns:
            List of topic distribution lists, one per document.
        """
        if not texts:
            return []

        if not _has_prediction_backend(self):
            return []

        valid_texts = [t if t and t.strip() else " " for t in texts]
        tfidf_matrix = self._vectorizer.transform(valid_texts)
        topic_matrix = self._nmf_model.transform(tfidf_matrix)

        return [_topic_distribution(row) for row in topic_matrix]

    def save(self, path: str) -> None:
        """Save fitted model to disk.

        Args:
            path: File path to save the model.
        """
        if not self._is_fitted:
            raise ValueError("Model must be fitted before saving")

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        import sklearn

        data = {
            "vectorizer": self._vectorizer,
            "nmf_model": self._nmf_model,
            "feature_names": self._feature_names,
            "n_topics": self.n_topics,
            "max_features": self.max_features,
            "ngram_range": self.ngram_range,
            "sklearn_version": sklearn.__version__,
            "_topic_model_cache_version": _TOPIC_MODEL_CACHE_VERSION,
        }
        _trusted_model_codec().dump(data, path)
        logger.info("Topic model saved to %s", path)

    @classmethod
    def load(cls, path: str) -> TopicModeler:
        """Load a fitted model from disk.

        Args:
            path: File path to load the model from.

        Returns:
            Fitted TopicModeler instance.

        Raises:
            ValueError: If the saved model was built with a different major
                version of scikit-learn (deserialization may produce wrong results).
        """
        p = Path(path)
        if p.suffix not in _ALLOWED_CACHE_SUFFIXES:
            raise ValueError(f"Topic model file must be .pkl or .pickle, got: {p.suffix!r}")
        if not p.is_file():
            raise FileNotFoundError(f"Topic model file not found: {path}")
        logger.warning("Loading topic model from trusted cache %s. Only load controlled runtime cache files.", path)
        data = _trusted_model_codec().load(path)

        _validate_cache_version(data)

        # Validate scikit-learn version compatibility
        _validate_sklearn_version(data.get("sklearn_version", "unknown"))

        instance = cls(
            n_topics=data["n_topics"],
            max_features=data["max_features"],
            ngram_range=data["ngram_range"],
        )
        instance._vectorizer = data["vectorizer"]
        instance._nmf_model = data["nmf_model"]
        instance._feature_names = data["feature_names"]
        instance._is_fitted = True
        return instance
