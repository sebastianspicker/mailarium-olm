"""Tests for writing style and readability analysis."""

from src.writing_analyzer import WritingAnalyzer, WritingMetrics, _get_words, _split_sentences


class TestHelpers:
    def test_split_sentences(self):
        sentences = _split_sentences("Hello world. How are you? I am fine.")
        assert len(sentences) >= 2

    def test_split_sentences_empty(self):
        assert _split_sentences("") == []
        assert _split_sentences(None) == []

    def test_get_words(self):
        words = _get_words("Hello World! How are you?")
        assert "hello" in words
        assert "world" in words
        assert len(words) == 5

    def test_get_words_handles_german_umlauts_and_sz(self):
        words = _get_words("Überprüfung für äußere Lösungen ist nötig.")
        assert words == ["überprüfung", "für", "äußere", "lösungen", "ist", "nötig"]

    def test_get_words_empty(self):
        assert _get_words("") == []


class TestWritingMetrics:
    def test_to_dict(self):
        m = WritingMetrics(
            readability_score=65.0,
            grade_level=8.5,
            avg_sentence_length=15.0,
            avg_word_length=4.5,
            vocabulary_richness=0.75,
            question_frequency=0.1,
            exclamation_frequency=0.05,
            formality_score=0.3,
            word_count=100,
            sentence_count=7,
        )
        d = m.to_dict()
        assert d["readability_score"] == 65.0
        assert d["grade_level"] == 8.5
        assert d["word_count"] == 100
        assert d["sentence_count"] == 7
        assert d["avg_sentence_length"] == 15.0
        assert d["vocabulary_richness"] == 0.75

    def test_default_metrics(self):
        m = WritingMetrics()
        d = m.to_dict()
        assert d["readability_score"] is None
        assert d["word_count"] == 0


class TestWritingAnalyzer:
    def setup_method(self):
        self.analyzer = WritingAnalyzer()

    def test_analyze_empty_text(self):
        m = self.analyzer.analyze_text("")
        assert m.word_count == 0
        assert m.sentence_count == 0

    def test_analyze_none_text(self):
        m = self.analyzer.analyze_text(None)
        assert m.word_count == 0

    def test_analyze_simple_text(self):
        text = (
            "The quarterly budget review is scheduled for next Monday. "
            "We need to prepare all financial reports before the meeting. "
            "Please ensure your department data is up to date."
        )
        m = self.analyzer.analyze_text(text)
        assert m.word_count > 0
        assert m.sentence_count >= 1
        assert m.avg_sentence_length > 0
        assert m.avg_word_length > 0
        assert 0 < m.vocabulary_richness <= 1.0

    def test_question_detection(self):
        text = "Are you coming to the meeting? What time does it start? I will be there."
        m = self.analyzer.analyze_text(text)
        assert m.question_frequency > 0

    def test_exclamation_detection(self):
        text = "Great work! Amazing results! Keep it up."
        m = self.analyzer.analyze_text(text)
        assert m.exclamation_frequency > 0

    def test_formality_with_long_words(self):
        formal_text = (
            "The organizational restructuring implementation necessitates "
            "comprehensive documentation and communication throughout "
            "the transformation process."
        )
        casual_text = "Hey how are you? I am good. See you soon!"
        formal_m = self.analyzer.analyze_text(formal_text)
        casual_m = self.analyzer.analyze_text(casual_text)
        # Formal text should have higher formality score
        assert formal_m.formality_score > casual_m.formality_score

    def test_vocabulary_richness(self):
        # Repetitive text should have low richness
        repetitive = "the the the the the the the the the the"
        m = self.analyzer.analyze_text(repetitive)
        assert m.vocabulary_richness < 0.2

        # Diverse text should have high richness
        diverse = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        m2 = self.analyzer.analyze_text(diverse)
        assert m2.vocabulary_richness > 0.8

    def test_word_count(self):
        text = "One two three four five six seven eight nine ten."
        m = self.analyzer.analyze_text(text)
        assert m.word_count == 10

    def test_word_count_supports_german_unicode_words(self):
        text = "Überprüfung für äußere Lösungen ist nötig."
        m = self.analyzer.analyze_text(text)
        assert m.word_count == 6

    def test_readability_without_textstat(self):
        # Force textstat to be unavailable
        analyzer = WritingAnalyzer()
        analyzer._textstat_checked = True
        analyzer._textstat = None
        text = "This is a simple test sentence. Another sentence here."
        m = analyzer.analyze_text(text)
        assert m.readability_score is None
        assert m.grade_level is None
        # Other metrics should still work
        assert m.word_count > 0


class TestSenderProfile:
    def test_sender_profile(self):
        texts = [
            (
                "This is test email with enough content "
                "to analyze writing style and readability metrics. "
                "The email discusses various topics including project "
                "management, budgets, and team coordination."
            ),
            (
                "Another email here about quarterly reviews. "
                "We need to prepare the financial reports before Friday. "
                "Please ensure all data is submitted on time."
            ),
        ]
        analyzer = WritingAnalyzer()
        profile = analyzer.analyze_sender_profile(texts, "alice@example.test")
        assert profile["sender_email"] == "alice@example.test"
        assert profile["emails_analyzed"] == 2
        assert profile["avg_sentence_length"] > 0
        assert profile["avg_word_length"] > 0
        assert profile["avg_vocabulary_richness"] > 0

    def test_sender_profile_empty_texts(self):
        analyzer = WritingAnalyzer()
        profile = analyzer.analyze_sender_profile([], "nobody@example.test")
        assert profile == {}

    def test_sender_profile_short_texts(self):
        # Texts too short to analyze
        analyzer = WritingAnalyzer()
        profile = analyzer.analyze_sender_profile(["hi", "ok"], "x@example.test")
        assert profile == {}

    def test_analyze_texts(self):
        texts = [
            "First email with enough words to analyze here.",
            "Second email also has enough content for analysis here.",
            "Short.",  # Too short, should be filtered
        ]
        analyzer = WritingAnalyzer()
        metrics = analyzer.analyze_texts(texts)
        assert len(metrics) == 2  # Short text filtered out


class TestMCPWritingTool:
    def test_writing_analysis_tool_importable(self):
        from src.tools import reporting  # email_writing_analysis lives in reporting module

        assert callable(reporting.register)
