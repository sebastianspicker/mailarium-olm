"""Topics/cluster build command implementation for the CLI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)


def _get_email_db_and_texts(db: EmailDatabase) -> tuple[list[str], list[str]]:
    """Return (uids, texts) for all emails with non-empty body text."""
    rows = db.conn.execute("SELECT uid, COALESCE(body_text, '') FROM emails WHERE TRIM(COALESCE(body_text, '')) != ''").fetchall()
    uids = [str(r[0]) for r in rows]
    texts = [str(r[1]) for r in rows]
    return uids, texts


def run_topics_build_impl(
    get_email_db: Any,
    *,
    n_topics: int = 20,
    n_clusters: int | None = None,
    skip_topics: bool = False,
    skip_clusters: bool = False,
) -> None:
    """Build topic model and clusters, then persist results to the database.

    Args:
        get_email_db: Callable returning an EmailDatabase instance.
        n_topics: Number of NMF topics to extract.
        n_clusters: Fixed number of clusters (None = auto-detect).
        skip_topics: Skip NMF topic modeling.
        skip_clusters: Skip KMeans clustering.
    """
    db = get_email_db()
    uids, texts = _get_email_db_and_texts(db)

    if len(uids) < 2:
        print("Not enough emails for topic/cluster analysis (need at least 2).")
        return

    print(f"  {len(uids)} emails loaded for analysis.")

    if not skip_topics:
        _build_topics(db, uids, texts, n_topics=n_topics)

    if not skip_clusters:
        _build_clusters(db, uids, texts, n_clusters=n_clusters)


def _build_topics(db: EmailDatabase, uids: list[str], texts: list[str], *, n_topics: int) -> None:
    """Fit NMF topic model and persist topics + email-topic assignments."""
    from .topic_modeler import TopicModeler

    print(f"  Fitting NMF topic model (up to {n_topics} topics)…")
    modeler = TopicModeler(n_topics=n_topics)
    modeler.fit(texts)

    if not modeler.is_fitted:
        print("  Topic model could not be fitted (corpus too small or uniform).")
        return

    topics = modeler.get_topics(top_words=10)
    print(f"  Discovered {len(topics)} topics.")

    db.insert_topics(topics)

    inserted = 0
    for uid, text in zip(uids, texts, strict=True):
        weights = modeler.predict(text)
        if weights:
            db.insert_email_topics_batch(uid, weights)
            inserted += 1

    db.conn.commit()
    print(f"  Topics stored. Email-topic assignments: {inserted}/{len(uids)} emails.")


def _build_clusters(db: EmailDatabase, uids: list[str], texts: list[str], *, n_clusters: int | None) -> None:
    """Fit TF-IDF KMeans cluster model and persist cluster assignments."""
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    if len(uids) < 3:
        print("  Skipping clusters: need at least 3 emails.")
        return

    print("  Fitting TF-IDF cluster model…")
    vectorizer = TfidfVectorizer(max_features=5000, stop_words="english", sublinear_tf=True)
    tfidf = vectorizer.fit_transform(texts)

    if n_clusters is None:
        # Simple heuristic: sqrt(n/2), capped 5–30
        n_clusters = max(5, min(30, int((len(uids) / 2) ** 0.5)))

    actual_clusters = min(n_clusters, len(uids))
    print(f"  Using {actual_clusters} clusters for {len(uids)} emails.")

    km = KMeans(n_clusters=actual_clusters, random_state=42, n_init="auto")
    km.fit(tfidf)

    labels: list[int] = km.labels_.tolist()

    # Build cluster info
    cluster_labels: dict[int, list[str]] = {}
    for uid, label in zip(uids, labels, strict=True):
        cluster_labels.setdefault(label, []).append(uid)

    feature_names = vectorizer.get_feature_names_out()
    cluster_info = []
    for cluster_id, center in enumerate(km.cluster_centers_):
        top_indices = center.argsort()[::-1][:5]
        top_words = [feature_names[i] for i in top_indices]
        label_str = " / ".join(top_words[:3])
        cluster_info.append(
            {
                "id": cluster_id,
                "label": label_str,
                "size": len(cluster_labels.get(cluster_id, [])),
                "top_words": top_words,
            }
        )

    db.insert_cluster_info(cluster_info)

    # Build assignments: (uid, cluster_id, distance_to_centroid)
    assignments: list[tuple[str, int, float]] = []
    for uid, label in zip(uids, labels, strict=True):
        assignments.append((uid, int(label), 0.0))  # distance not critical

    db.insert_clusters_batch(assignments)
    db.conn.commit()
    print(f"  Clusters stored: {actual_clusters} clusters, {len(assignments)} assignments.")
