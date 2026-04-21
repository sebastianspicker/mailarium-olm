"""KMeans clustering for email archives using pre-computed embeddings."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmailClusterer:
    """Cluster emails by embedding similarity using KMeans.

    Uses embeddings already stored in ChromaDB. scikit-learn is a
    transitive dependency of sentence-transformers.
    """

    def __init__(self, n_clusters: int | None = None):
        """Initialize the clusterer.

        Args:
            n_clusters: Fixed number of clusters. If None, auto-detect
                using silhouette score (range 5-30).
        """
        self.n_clusters = n_clusters
        self._labels = None
        self._centroids = None
        self._embeddings = None
        self._uids = None
        self._is_fitted = False

    def fit(
        self,
        embeddings: np.ndarray,
        uids: list[str],
        n_clusters: int | None = None,
    ) -> None:
        """Fit KMeans on pre-computed embeddings.

        Args:
            embeddings: 2D array of shape (n_samples, n_features).
            uids: List of email UIDs corresponding to rows.
            n_clusters: Override number of clusters.
        """
        if len(embeddings) < 3:
            logger.warning("Need at least 3 embeddings for clustering, got %d", len(embeddings))
            self._is_fitted = False
            return

        k = n_clusters or self.n_clusters
        if k is None:
            k = self._auto_detect_k(embeddings)

        # Ensure k <= n_samples
        k = min(k, len(embeddings))
        if k < 2:
            k = 2

        self._labels, self._centroids = self._fit_kmeans(embeddings, k, n_init=3)
        self._embeddings = embeddings
        self._uids = uids
        self._is_fitted = True
        logger.info("Clustered %d emails into %d clusters", len(uids), k)

    def _auto_detect_k(self, embeddings: np.ndarray) -> int:
        """Auto-detect optimal k using silhouette score sampling."""
        from sklearn.metrics import silhouette_score

        n = len(embeddings)
        if n < 10:
            return min(3, n - 1)

        # Sample for speed
        sample_size = min(2000, n)
        if sample_size < n:
            rng = np.random.RandomState(42)
            indices = rng.choice(n, sample_size, replace=False)
            sample = embeddings[indices]
        else:
            sample = embeddings

        best_k = min(5, sample_size - 1)
        best_score = -1
        max_k = min(31, sample_size - 1)
        k_range = range(5, max_k, 5) if max_k > 5 else range(2, max_k + 1)

        for k in k_range:
            labels, _ = self._fit_kmeans(sample, k, n_init=2)
            try:
                score = silhouette_score(sample, labels, sample_size=min(500, sample_size))
                if score > best_score:
                    best_score = score
                    best_k = k
            except ValueError:
                continue

        logger.info("Auto-detected k=%d (silhouette=%.3f)", best_k, best_score)
        return best_k

    @staticmethod
    def _fit_kmeans(
        embeddings: np.ndarray,
        n_clusters: int,
        n_init: int = 3,
        max_iter: int = 100,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Deterministic NumPy k-means fallback for local clustering."""
        data = np.asarray(embeddings, dtype=np.float64)
        best_labels: np.ndarray | None = None
        best_centroids: np.ndarray | None = None
        best_inertia = float("inf")

        for init_idx in range(max(1, n_init)):
            seed = 42 + init_idx
            labels, centroids, inertia = EmailClusterer._fit_kmeans_once(
                data,
                n_clusters,
                np.random.RandomState(seed),
                max_iter=max_iter,
            )
            if inertia < best_inertia:
                best_inertia = inertia
                best_labels = labels
                best_centroids = centroids

        assert best_labels is not None
        assert best_centroids is not None
        return best_labels, best_centroids.astype(np.float32, copy=False)

    @staticmethod
    def _fit_kmeans_once(
        embeddings: np.ndarray,
        n_clusters: int,
        rng: np.random.RandomState,
        max_iter: int = 100,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """Run one Lloyd iteration sequence with random unique starts."""
        n_samples = len(embeddings)
        initial_indices = rng.choice(n_samples, size=n_clusters, replace=False)
        centroids = embeddings[initial_indices].copy()
        labels = np.zeros(n_samples, dtype=np.int32)

        for _ in range(max_iter):
            distances = np.linalg.norm(embeddings[:, None, :] - centroids[None, :, :], axis=2)
            new_labels = np.argmin(distances, axis=1).astype(np.int32)
            new_centroids = centroids.copy()

            for cluster_id in range(n_clusters):
                members = embeddings[new_labels == cluster_id]
                if len(members) == 0:
                    farthest_idx = int(np.argmax(np.min(distances, axis=1)))
                    new_centroids[cluster_id] = embeddings[farthest_idx]
                    new_labels[farthest_idx] = cluster_id
                    continue
                new_centroids[cluster_id] = members.mean(axis=0)

            if np.array_equal(new_labels, labels) and np.allclose(new_centroids, centroids):
                labels = new_labels
                centroids = new_centroids
                break

            labels = new_labels
            centroids = new_centroids

        final_distances = np.linalg.norm(embeddings - centroids[labels], axis=1)
        inertia = float(np.sum(final_distances**2))
        return labels, centroids, inertia

    def fit_hybrid(
        self,
        dense_embeddings: np.ndarray,
        sparse_vectors: dict[str, dict[int, float]],
        uids: list[str],
        n_clusters: int | None = None,
        sparse_weight: float = 0.3,
        svd_dims: int = 64,
    ) -> None:
        """Fit KMeans using combined dense + sparse features.

        Sparse vectors are converted to a feature matrix via truncated SVD,
        then concatenated with dense embeddings using weighted blending.

        Args:
            dense_embeddings: Dense embedding array (n_samples, n_features).
            sparse_vectors: {uid: {token_id: weight}} sparse vectors.
            uids: List of email UIDs corresponding to rows.
            n_clusters: Override number of clusters.
            sparse_weight: Weight for sparse features (0.0-1.0).
            svd_dims: Number of SVD dimensions for sparse features.
        """
        if len(dense_embeddings) < 3:
            logger.warning("Need at least 3 embeddings for clustering, got %d", len(dense_embeddings))
            self._is_fitted = False
            return

        sparse_matrix = self._sparse_to_svd(sparse_vectors, uids, svd_dims)

        if sparse_matrix is not None:
            # Normalize both feature sets
            dense_norm = self._l2_normalize(dense_embeddings)
            sparse_norm = self._l2_normalize(sparse_matrix)

            # Weighted concatenation
            alpha = 1.0 - sparse_weight
            combined = np.hstack(
                [
                    alpha * dense_norm,
                    sparse_weight * sparse_norm,
                ]
            )
            logger.info(
                "Hybrid features: dense=%d + sparse_svd=%d = %d dims (alpha=%.2f)",
                dense_embeddings.shape[1],
                svd_dims,
                combined.shape[1],
                alpha,
            )
        else:
            logger.info("No sparse vectors available, falling back to dense-only clustering")
            combined = dense_embeddings

        self.fit(combined, uids, n_clusters=n_clusters)

    @staticmethod
    def _sparse_to_svd(
        sparse_vectors: dict[str, dict[int, float]],
        uids: list[str],
        n_components: int,
    ) -> np.ndarray | None:
        """Convert sparse vectors to dense matrix via truncated SVD."""
        if not sparse_vectors:
            return None

        from scipy.sparse import lil_matrix
        from sklearn.decomposition import TruncatedSVD

        # Collect all token IDs
        all_tokens: set[int] = set()
        for sv in sparse_vectors.values():
            all_tokens.update(sv.keys())

        if not all_tokens:
            return None

        token_to_col = {tid: i for i, tid in enumerate(sorted(all_tokens))}
        n_cols = len(token_to_col)

        # Build sparse matrix
        matrix = lil_matrix((len(uids), n_cols), dtype=np.float32)
        for row_idx, uid in enumerate(uids):
            sv = sparse_vectors.get(uid, {})
            for token_id, weight in sv.items():
                if token_id in token_to_col:
                    matrix[row_idx, token_to_col[token_id]] = weight

        csr = matrix.tocsr()

        # Truncated SVD
        actual_components = min(n_components, n_cols - 1, len(uids) - 1)
        if actual_components < 1:
            return None

        svd = TruncatedSVD(n_components=actual_components, random_state=42)
        reduced = svd.fit_transform(csr)
        logger.info(
            "Sparse SVD: %d tokens -> %d dims (variance explained: %.1f%%)",
            n_cols,
            actual_components,
            svd.explained_variance_ratio_.sum() * 100,
        )
        return reduced

    @staticmethod
    def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
        """L2-normalize rows of a matrix."""
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        return matrix / norms

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def get_clusters(self) -> list[dict[str, Any]]:
        """Get cluster summaries.

        Returns:
            List of {cluster_id, size, representative_uid} dicts.
        """
        if not self._is_fitted:
            return []

        from collections import Counter

        counts = Counter(self._labels)
        clusters = []

        for cluster_id in sorted(counts.keys()):
            # Find representative (closest to centroid)
            mask = self._labels == cluster_id
            cluster_indices = np.where(mask)[0]
            cluster_embeddings = self._embeddings[cluster_indices]
            centroid = self._centroids[cluster_id]

            distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
            rep_idx = cluster_indices[np.argmin(distances)]

            clusters.append(
                {
                    "cluster_id": int(cluster_id),
                    "size": counts[cluster_id],
                    "representative_uid": self._uids[rep_idx],
                }
            )

        return clusters

    def get_assignments(self) -> list[tuple[str, int, float]]:
        """Get all email-to-cluster assignments.

        Returns:
            List of (uid, cluster_id, distance_to_centroid) tuples.
        """
        if not self._is_fitted:
            return []

        results = []
        for i, uid in enumerate(self._uids):
            cluster_id = int(self._labels[i])
            centroid = self._centroids[cluster_id]
            distance = float(np.linalg.norm(self._embeddings[i] - centroid))
            results.append((uid, cluster_id, round(distance, 4)))
        return results

    def find_similar(self, embedding: np.ndarray, top_k: int = 10) -> list[tuple[str, float]]:
        """Find most similar emails by cosine similarity.

        Args:
            embedding: Query embedding vector.
            top_k: Number of results.

        Returns:
            List of (uid, similarity_score) tuples.
        """
        if not self._is_fitted or len(self._embeddings) == 0:
            return []

        if top_k < 1:
            top_k = 1

        # Cosine similarity
        query_norm = embedding / (np.linalg.norm(embedding) + 1e-10)
        emb_norms = self._embeddings / (np.linalg.norm(self._embeddings, axis=1, keepdims=True) + 1e-10)
        similarities = emb_norms @ query_norm

        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [(self._uids[i], round(float(similarities[i]), 4)) for i in top_indices]

    def find_similar_by_uid(self, uid: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Find emails similar to a given email UID.

        Args:
            uid: Email UID to find similar emails for.
            top_k: Number of results.

        Returns:
            List of (uid, similarity_score) tuples, excluding the query email.
        """
        if not self._is_fitted or uid not in self._uids:
            return []

        idx = self._uids.index(uid)
        embedding = self._embeddings[idx]
        results = self.find_similar(embedding, top_k=top_k + 1)
        # Exclude the query email itself
        return [(u, s) for u, s in results if u != uid][:top_k]
