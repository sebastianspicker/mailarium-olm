"""Tests for query expansion."""

import numpy as np

from src.query_expander import QueryExpander, legal_support_query_profile


class _FakeModel:
    """Minimal mock of MultiVectorEmbedder for testing."""

    def encode_dense(self, texts):
        # Return deterministic embeddings based on text content
        embeddings = []
        for text in texts:
            # Simple hash-based embedding
            rng = np.random.RandomState(hash(text) % 2**31)
            embeddings.append(rng.randn(8).astype(np.float32).tolist())
        return embeddings


class TestQueryExpander:
    def test_legal_support_query_profile_detects_participation_and_contradiction(self):
        profile = legal_support_query_profile("Need SBV participation contradiction timeline after the complaint")

        assert profile["is_legal_support"] is True
        assert "participation" in profile["intents"]
        assert "contradiction" in profile["intents"]
        assert "chronology" in profile["intents"]
        assert "personalrat" in profile["suggested_terms"]

    def test_expand_adds_terms(self):
        vocab = ["quarterly report", "budget review", "team meeting", "project deadline", "sales forecast"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        result = expander.expand("budget", n_terms=2)
        # Should add terms from vocabulary
        assert "budget" in result
        # Original query should be preserved
        assert result.startswith("budget")
        # Should have more content than original
        assert len(result) > len("budget")

    def test_expand_skips_existing_terms(self):
        vocab = ["budget review", "quarterly report", "financial plan"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        result = expander.expand("budget review", n_terms=2)
        # "budget review" should not be duplicated
        count = result.lower().count("budget review")
        assert count == 1

    def test_expand_empty_query(self):
        expander = QueryExpander(model=_FakeModel(), vocabulary=["a", "b"])
        assert expander.expand("") == ""
        assert expander.expand(None) is None

    def test_expand_no_vocabulary(self):
        expander = QueryExpander(model=_FakeModel(), vocabulary=[])
        assert expander.expand("test query") == "test query"

    def test_expand_no_model(self):
        expander = QueryExpander(model=None, vocabulary=["a", "b"])
        assert expander.expand("test") == "test"

    def test_set_vocabulary(self):
        expander = QueryExpander(model=_FakeModel())
        expander.set_vocabulary(["alpha", "bravo", "charlie"])
        result = expander.expand("hello world", n_terms=2)
        assert len(result) > len("hello world")

    def test_get_related_terms(self):
        vocab = ["quarterly report", "budget plan", "team sync", "product launch", "customer feedback"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        terms = expander.get_related_terms("budget", n_terms=3)
        assert len(terms) <= 3
        for term, score in terms:
            assert isinstance(term, str)
            assert isinstance(score, float)

    def test_get_related_terms_empty(self):
        expander = QueryExpander(model=_FakeModel())
        assert expander.get_related_terms("test") == []

    def test_get_related_terms_no_model(self):
        expander = QueryExpander(model=None, vocabulary=["a"])
        assert expander.get_related_terms("test") == []

    def test_n_terms_respected(self):
        vocab = [f"term_{i}" for i in range(20)]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        result = expander.expand("query", n_terms=1)
        # Original + 1 expanded term
        parts = result.split()
        assert len(parts) <= 3  # "query" + up to 1 term (which could be multi-word)

    def test_short_terms_skipped(self):
        vocab = ["ab", "xy", "project management", "deadline"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        terms = expander.get_related_terms("planning", n_terms=5)
        # Terms shorter than 3 chars should be skipped
        for term, _ in terms:
            assert len(term) >= 3

    def test_expand_no_substring_skip(self):
        """Query 'art' should not skip 'artificial' — word boundary check required."""
        vocab = ["artificial intelligence", "artwork gallery", "art history"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        result = expander.expand("art", n_terms=5)
        # "artificial intelligence" should not be skipped just because "art" is a substring
        # At minimum, the result should expand beyond just "art"
        assert len(result) > len("art")

    def test_expand_adds_deterministic_legal_support_terms_before_semantic_vocab(self):
        vocab = ["calendar invite", "attendance table", "peer review"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        result = expander.expand("Need SBV participation contradiction review", n_terms=4)

        assert "personalrat" in result or "betriebsrat" in result
        assert "contradiction" in result

    def test_expand_lanes_returns_distinct_query_lanes(self):
        vocab = ["Stufenvorweggewährung", "Massregelung", "calendar invite", "BEM review"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        lanes = expander.expand_lanes("Stufenvorweggewährung Maßregelung", n_terms=2, max_lanes=4)

        assert lanes
        assert lanes[0] == "Stufenvorweggewährung Maßregelung"
        assert len(lanes) >= 2
        assert any("Stufenvorweggewaehrung" in lane for lane in lanes)

    def test_expand_lanes_splits_multi_intent_legal_support_queries_into_intent_scoped_lanes(self):
        vocab = ["calendar invite", "attendance table", "peer review"]
        expander = QueryExpander(model=_FakeModel(), vocabulary=vocab)
        lanes = expander.expand_lanes(
            "Need SBV participation contradiction timeline after the complaint",
            n_terms=2,
            max_lanes=6,
        )

        assert any("personalrat" in lane or "betriebsrat" in lane for lane in lanes[1:])
        assert any("contradiction" in lane or "widerspruch" in lane for lane in lanes[1:])
        assert any("timeline" in lane or "chronology" in lane for lane in lanes[1:])

    def test_legal_support_query_profile_picks_up_wave_domain_intents(self):
        profile = legal_support_query_profile("Need EG12 time system task withdrawal role ownership evidence")

        assert "classification" in profile["intents"]
        assert "timekeeping" in profile["intents"]
        assert "task_ownership" in profile["intents"]

    def test_legal_support_query_profile_detects_agg_intent(self):
        profile = legal_support_query_profile("Need AGG equal treatment comparator evidence")

        assert "anti_discrimination" in profile["intents"]
        assert "Gleichbehandlung" in profile["suggested_terms"]

    def test_expand_lanes_adds_compound_variant_lane(self):
        expander = QueryExpander(model=_FakeModel(), vocabulary=["Stufenvorweggewährung", "TV-L"])

        lanes = expander.expand_lanes("Stufenvorweggewährung TV-L", n_terms=2, max_lanes=6)

        assert any("stufenvorweggewaehrung" in lane.lower() for lane in lanes)


class TestMCPSmartSearch:
    def test_smart_search_tool_importable(self):
        from src.tools import threads  # email_smart_search lives in threads module

        assert callable(threads.register)

    def test_structured_search_has_topic_id(self):
        from src.mcp_models import EmailSearchStructuredInput

        inp = EmailSearchStructuredInput(query="test", topic_id=3, cluster_id=5, expand_query=True)
        assert inp.topic_id == 3
        assert inp.cluster_id == 5
        assert inp.expand_query is True

    def test_structured_search_defaults(self):
        from src.mcp_models import EmailSearchStructuredInput

        inp = EmailSearchStructuredInput(query="test")
        assert inp.topic_id is None
        assert inp.cluster_id is None
        assert inp.expand_query is False


class TestCLINewFlags:
    def test_topic_flag(self):
        from src.cli import parse_args

        args = parse_args(["--query", "test", "--topic", "5"])
        assert args.topic == 5

    def test_cluster_id_flag(self):
        from src.cli import parse_args

        args = parse_args(["--query", "test", "--cluster-id", "3"])
        assert args.cluster_id == 3

    def test_expand_query_flag(self):
        from src.cli import parse_args

        args = parse_args(["--query", "test", "--expand-query"])
        assert args.expand_query is True

    def test_flags_require_query(self):
        import pytest

        from src.cli import parse_args

        with pytest.raises(SystemExit):
            parse_args(["--topic", "5"])

        with pytest.raises(SystemExit):
            parse_args(["--expand-query"])


class TestHasAttachmentsFilterCoercion:
    """Bug 2: has_attachments stored as str in ChromaDB, but callers may pass bool."""

    def test_matches_has_attachments_str_true(self):
        from src.result_filters import _matches_has_attachments
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="c1", text="t", metadata={"has_attachments": "True"}, distance=0.1)
        assert _matches_has_attachments(r, True) is True
        assert _matches_has_attachments(r, False) is False

    def test_matches_has_attachments_bool_true(self):
        from src.result_filters import _matches_has_attachments
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="c1", text="t", metadata={"has_attachments": True}, distance=0.1)
        assert _matches_has_attachments(r, True) is True
        assert _matches_has_attachments(r, False) is False

    def test_matches_priority_str_and_int(self):
        from src.result_filters import _matches_priority
        from src.retriever import SearchResult

        r_str = SearchResult(chunk_id="c1", text="t", metadata={"priority": "3"}, distance=0.1)
        r_int = SearchResult(chunk_id="c2", text="t", metadata={"priority": 3}, distance=0.1)
        assert _matches_priority(r_str, 3) is True
        assert _matches_priority(r_int, 3) is True
        assert _matches_priority(r_str, 4) is False
        assert _matches_priority(r_int, 4) is False


class TestRetrieverSemanticFilters:
    def test_matches_allowed_uids(self):
        from src.result_filters import _matches_allowed_uids
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="c1", text="test", metadata={"uid": "abc"}, distance=0.1)
        assert _matches_allowed_uids(r, None) is True
        assert _matches_allowed_uids(r, {"abc", "def"}) is True
        assert _matches_allowed_uids(r, {"xyz"}) is False
        assert _matches_allowed_uids(r, set()) is False
