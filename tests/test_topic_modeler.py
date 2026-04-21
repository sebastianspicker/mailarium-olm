"""Tests for NMF topic modeling."""

import os
import tempfile

from src.topic_modeler import TopicModeler

# Minimal corpus for testing
_CORPUS = [
    "The quarterly budget report shows increased spending on cloud services",
    "Budget allocation for infrastructure projects in Q3",
    "Financial review of departmental budget allocations",
    "Cloud infrastructure migration plan and timeline",
    "Server migration to cloud computing platform",
    "Infrastructure upgrade proposal for data center",
    "Team meeting notes about project management",
    "Project timeline and milestone review meeting",
    "Meeting agenda for weekly standup and sprint planning",
    "Customer support ticket analysis and resolution",
    "Support team performance metrics and KPIs",
    "Customer satisfaction survey results summary",
]


class TestTopicModeler:
    def test_fit_creates_topics(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        assert modeler.is_fitted
        topics = modeler.get_topics()
        assert len(topics) == 3

    def test_topics_have_structure(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        topics = modeler.get_topics(top_words=5)
        for topic in topics:
            assert "id" in topic
            assert "label" in topic
            assert "top_words" in topic
            assert isinstance(topic["top_words"], list)
            assert len(topic["top_words"]) <= 5

    def test_topic_labels_auto_generated(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        topics = modeler.get_topics()
        for topic in topics:
            assert topic["label"]
            assert " / " in topic["label"]  # Auto-label from top-3 words

    def test_predict_single_document(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        dist = modeler.predict("Budget review for quarterly planning")
        assert len(dist) > 0
        # Should be (topic_id, weight) tuples
        for topic_id, weight in dist:
            assert isinstance(topic_id, int)
            assert isinstance(weight, float)
            assert weight > 0

    def test_predict_batch(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        texts = [
            "Budget review meeting",
            "Cloud infrastructure plan",
        ]
        results = modeler.predict_batch(texts)
        assert len(results) == 2
        for dist in results:
            assert isinstance(dist, list)

    def test_predict_empty_text(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        dist = modeler.predict("")
        assert dist == []

    def test_not_fitted(self):
        modeler = TopicModeler()
        assert not modeler.is_fitted
        assert modeler.get_topics() == []
        assert modeler.predict("test") == []

    def test_too_few_documents(self):
        modeler = TopicModeler(n_topics=5)
        modeler.fit(["single doc"])
        assert not modeler.is_fitted

    def test_save_and_load(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        topics_before = modeler.get_topics()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "model.pkl")
            modeler.save(path)
            assert os.path.exists(path)

            loaded = TopicModeler.load(path)
            assert loaded.is_fitted
            topics_after = loaded.get_topics()
            assert len(topics_after) == len(topics_before)

            # Verify prediction works on loaded model
            dist = loaded.predict("Budget review")
            assert len(dist) > 0

    def test_save_unfitted_raises(self):
        modeler = TopicModeler()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "model.pkl")
            try:
                modeler.save(path)
                raise AssertionError("Should have raised ValueError")
            except ValueError:
                pass

    def test_auto_adjust_topics(self):
        """n_topics is adjusted when corpus is smaller than requested."""
        modeler = TopicModeler(n_topics=50)
        small_corpus = _CORPUS[:5]
        modeler.fit(small_corpus)
        assert modeler.is_fitted
        topics = modeler.get_topics()
        assert len(topics) < 50
        assert len(topics) >= 2

    def test_predict_sorted_by_weight(self):
        modeler = TopicModeler(n_topics=3)
        modeler.fit(_CORPUS)
        dist = modeler.predict("Budget review for quarterly planning")
        if len(dist) > 1:
            weights = [w for _, w in dist]
            assert weights == sorted(weights, reverse=True)


# ── SQLite integration tests ─────────────────────────────────


class TestKeywordTopicSQLite:
    def _make_db(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        email = Email(
            message_id="<m1@test>",
            subject="Budget Review",
            sender_name="Alice",
            sender_email="alice@example.test",
            to=["bob@example.test"],
            cc=[],
            bcc=[],
            date="2024-01-15T10:00:00",
            body_text="Quarterly budget review discussion",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
        db.insert_email(email)
        return db, email

    def test_insert_and_query_keywords(self):
        db, email = self._make_db()
        db.insert_keywords_batch(
            email.uid,
            [
                ("budget", 0.85),
                ("quarterly", 0.72),
                ("review", 0.65),
            ],
        )
        keywords = db.top_keywords(limit=5)
        assert len(keywords) == 3
        assert keywords[0]["keyword"] == "budget"

    def test_keywords_filtered_by_sender(self):
        db, email = self._make_db()
        db.insert_keywords_batch(email.uid, [("budget", 0.85)])
        result = db.top_keywords(sender="alice@example.test")
        assert len(result) == 1
        result2 = db.top_keywords(sender="other@example.test")
        assert len(result2) == 0

    def test_keywords_filtered_by_folder(self):
        db, email = self._make_db()
        db.insert_keywords_batch(email.uid, [("budget", 0.85)])
        result = db.top_keywords(folder="Inbox")
        assert len(result) == 1
        result2 = db.top_keywords(folder="Sent")
        assert len(result2) == 0

    def test_insert_and_query_topics(self):
        db, email = self._make_db()
        db.insert_topics(
            [
                {"id": 0, "label": "budget / review", "top_words": ["budget", "review", "quarterly"]},
                {"id": 1, "label": "cloud / infrastructure", "top_words": ["cloud", "infra", "server"]},
            ]
        )
        db.insert_email_topics_batch(email.uid, [(0, 0.92), (1, 0.15)])

        dist = db.topic_distribution()
        assert len(dist) == 2
        assert dist[0]["email_count"] == 1

    def test_emails_by_topic(self):
        db, email = self._make_db()
        db.insert_topics(
            [
                {"id": 0, "label": "budget", "top_words": ["budget"]},
            ]
        )
        db.insert_email_topics_batch(email.uid, [(0, 0.9)])

        results = db.emails_by_topic(0)
        assert len(results) == 1
        assert results[0]["subject"] == "Budget Review"

    def test_topic_distribution_with_json(self):
        db, _ = self._make_db()
        db.insert_topics(
            [
                {"id": 0, "label": "test", "top_words": ["word1", "word2"]},
            ]
        )
        dist = db.topic_distribution()
        assert dist[0]["top_words"] == ["word1", "word2"]

    def test_empty_keywords(self):
        db, _ = self._make_db()
        assert db.top_keywords() == []

    def test_empty_topics(self):
        db, _ = self._make_db()
        assert db.topic_distribution() == []


# ── MCP tool tests ───────────────────────────────────────────


class TestMCPTopicTools:
    def test_topics_tool_importable(self):
        from src.tools import topics

        assert callable(topics.register)

    def test_search_by_topic_tool_importable(self):
        from src.tools import topics

        assert callable(topics.register)

    def test_keywords_tool_importable(self):
        from src.tools import topics

        assert callable(topics.register)
