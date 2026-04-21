"""Tests for TF-IDF keyword extraction."""

from src.keyword_extractor import KeywordExtractor


class TestKeywordExtractor:
    def test_extract_keywords_single_doc(self):
        extractor = KeywordExtractor()
        keywords = extractor.extract_keywords("The quarterly budget report shows increased spending on cloud infrastructure")
        assert len(keywords) >= 1
        # Should return (keyword, score) tuples
        assert all(isinstance(kw, str) and isinstance(score, float) for kw, score in keywords)

    def test_extract_keywords_top_n(self):
        extractor = KeywordExtractor()
        keywords = extractor.extract_keywords(
            "Machine learning artificial intelligence deep learning neural networks "
            "data science algorithms training models predictions",
            top_n=3,
        )
        assert len(keywords) <= 3

    def test_extract_keywords_empty(self):
        extractor = KeywordExtractor()
        assert extractor.extract_keywords("") == []
        assert extractor.extract_keywords("   ") == []

    def test_extract_keywords_stopwords_only(self):
        extractor = KeywordExtractor()
        keywords = extractor.extract_keywords("the and or but is was are")
        assert keywords == []

    def test_extract_keywords_bigrams(self):
        extractor = KeywordExtractor(ngram_range=(1, 2))
        keywords = extractor.extract_keywords("quarterly report quarterly report budget review budget review")
        kw_texts = [kw for kw, _ in keywords]
        # Should find bigrams like "quarterly report" or "budget review"
        assert len(kw_texts) > 0, "Should extract keywords"
        assert any(" " in kw for kw in kw_texts), "Should include bigrams"

    def test_extract_keywords_scores_sorted(self):
        extractor = KeywordExtractor()
        keywords = extractor.extract_keywords("project management project timeline project milestones schedule deadlines")
        assert len(keywords) > 1, "Should extract multiple keywords from varied text"
        scores = [s for _, s in keywords]
        assert scores == sorted(scores, reverse=True)

    def test_extract_corpus_keywords(self):
        extractor = KeywordExtractor(min_df=1)
        texts = [
            "Budget review for quarterly planning session",
            "Infrastructure upgrade proposal for cloud services",
            "Team meeting notes about project timeline",
            "Budget allocation for new infrastructure projects",
        ]
        keywords = extractor.extract_corpus_keywords(texts, top_n=5)
        assert 1 <= len(keywords) <= 5

    def test_extract_corpus_keywords_empty(self):
        extractor = KeywordExtractor()
        assert extractor.extract_corpus_keywords([]) == []
        assert extractor.extract_corpus_keywords(["", "  "]) == []

    def test_extract_per_document(self):
        extractor = KeywordExtractor(min_df=1)
        texts = [
            "Machine learning algorithms for prediction",
            "Database optimization and query performance",
            "Cloud computing services and deployment",
        ]
        results = extractor.extract_per_document(texts, top_n=3)
        assert len(results) == 3
        for doc_keywords in results:
            assert len(doc_keywords) <= 3

    def test_custom_stopwords(self):
        custom_stops = frozenset({"hello", "world"})
        extractor = KeywordExtractor(stop_words=custom_stops)
        keywords = extractor.extract_keywords("hello world hello world python code")
        kw_texts = {kw for kw, _ in keywords}
        assert "hello" not in kw_texts
        assert "world" not in kw_texts
