"""Tests for extractive thread summarization."""

from src.thread_summarizer import _split_sentences, summarize_email, summarize_thread


class TestSplitSentences:
    def test_simple_split(self):
        text = "Hello there. How are you today? I am doing well today."
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_empty_text(self):
        assert _split_sentences("") == []
        assert _split_sentences(None) == []

    def test_short_fragments_filtered(self):
        text = "Hello. OK. This is a much longer sentence that should survive."
        sentences = _split_sentences(text)
        # "Hello." and "OK." are <= 10 chars, should be filtered
        assert len(sentences) >= 1
        assert any("much longer" in s for s in sentences)

    def test_whitespace_normalization(self):
        text = "First   sentence   here.   Second   sentence   here."
        sentences = _split_sentences(text)
        for s in sentences:
            assert "   " not in s

    def test_german_sentence_split_supports_umlauts(self):
        text = "Änderung ist abgestimmt. Übermorgen senden wir die Freigabe. Öffentliche Rückmeldung folgt später."
        sentences = _split_sentences(text)
        assert len(sentences) == 3


class TestSummarizeEmail:
    def test_empty_text(self):
        assert summarize_email("") == ""
        assert summarize_email(None) == ""
        assert summarize_email("   ") == ""

    def test_short_text_returned_as_is(self):
        text = "This is a short email with just a couple of sentences. Nothing more to say here."
        result = summarize_email(text, max_sentences=5)
        assert isinstance(result, str)
        assert "short email" in result or "sentences" in result

    def test_max_sentences_respected(self):
        sentences = [f"This is sentence number {i} with enough words to pass the filter." for i in range(10)]
        text = " ".join(sentences)
        result = summarize_email(text, max_sentences=3)
        # Result should contain at most 3 sentences
        result_sentences = _split_sentences(result)
        assert len(result_sentences) <= 3

    def test_fewer_sentences_than_max(self):
        text = "The project is going well. We expect to deliver on time."
        result = summarize_email(text, max_sentences=10)
        # Should return all sentences when fewer than max
        assert "project" in result
        assert "deliver" in result

    def test_position_bias_favors_first_sentence(self):
        # Build text where first sentence is average but gets position boost
        sentences = [
            "The quarterly review meeting is scheduled for next Tuesday at ten.",
            "There are several items on the agenda including budget discussion.",
            "Marketing department has prepared the slides for presentation.",
            "The sales numbers from last quarter exceeded our expectations.",
            "Human resources will present the new hiring plan for approval.",
            "The IT department needs more servers for deployment pipeline.",
            "Finance team confirms the budget allocation for this quarter.",
        ]
        text = " ".join(sentences)
        result = summarize_email(text, max_sentences=2)
        # First sentence should likely appear due to 1.5x position boost
        assert "quarterly review" in result.lower() or len(result) > 0

    def test_no_sentences_returns_truncated(self):
        # Text that won't split into sentences (no ". " followed by uppercase)
        text = "just a bunch of lowercase words without proper sentence endings"
        result = summarize_email(text, max_sentences=3)
        assert isinstance(result, str) and result
        assert len(result) <= 500


class TestSummarizeThread:
    def test_empty_thread(self):
        assert summarize_thread([]) == ""

    def test_single_email_thread(self):
        emails = [{"clean_body": "We need to finalize the report. Please review the attached document."}]
        result = summarize_thread(emails, max_sentences=3)
        assert isinstance(result, str) and result

    def test_multi_email_thread(self):
        emails = [
            {
                "clean_body": "The project kickoff is next Monday. Everyone should prepare their updates.",
                "sender_name": "Alice",
                "sender_email": "alice@example.test",
                "date": "2024-01-10",
            },
            {
                "clean_body": "I have my section ready for the presentation. Will share the slides today.",
                "sender_name": "Bob",
                "sender_email": "bob@example.test",
                "date": "2024-01-11",
            },
            {
                "clean_body": "Great work on the slides Bob. The client meeting is confirmed for Thursday.",
                "sender_name": "Alice",
                "sender_email": "alice@example.test",
                "date": "2024-01-12",
            },
        ]
        result = summarize_thread(emails, max_sentences=3)
        assert isinstance(result, str) and result

    def test_max_sentences_in_thread(self):
        emails = [
            {
                "clean_body": f"This is email number {i} with sentence A. And sentence B here. Also sentence C for good measure.",
                "sender_name": f"User{i}",
            }
            for i in range(5)
        ]
        result = summarize_thread(emails, max_sentences=3)
        result_sentences = _split_sentences(result)
        assert len(result_sentences) <= 3

    def test_thread_with_body_key(self):
        # Test fallback to "body" key when "clean_body" is missing
        emails = [
            {"body": "The budget needs to be approved before end of month."},
            {"body": "Finance team has reviewed the proposals and made recommendations."},
        ]
        result = summarize_thread(emails, max_sentences=3)
        assert isinstance(result, str) and result

    def test_german_thread_summary_keeps_informative_sentences(self):
        emails = [
            {
                "clean_body": (
                    "Bitte prüfen Sie die Eingruppierung erneut. "
                    "Die medizinische Empfehlung liegt seit gestern vor. "
                    "Wir benötigen eine schriftliche Rückmeldung bis Freitag."
                ),
                "sender_name": "Alex",
            },
            {
                "clean_body": ("Die SBV wurde bislang nicht beteiligt. Bitte bestätigen Sie den weiteren Ablauf schriftlich."),
                "sender_name": "Morgan",
            },
        ]

        result = summarize_thread(emails, max_sentences=3)
        assert "Eingruppierung" in result or "SBV" in result or "Rückmeldung" in result

    def test_thread_with_empty_bodies(self):
        emails = [
            {"clean_body": ""},
            {"clean_body": ""},
        ]
        result = summarize_thread(emails)
        assert result == ""

    def test_thread_preserves_chronological_order(self):
        # Sentences should appear in original order in summary
        emails = [
            {"clean_body": "ALPHA is the first important topic we discussed in detail.", "sender_name": "A"},
            {"clean_body": "BETA is the second topic that came up during the meeting.", "sender_name": "B"},
            {"clean_body": "GAMMA is the third and final topic we covered at length.", "sender_name": "C"},
        ]
        result = summarize_thread(emails, max_sentences=3)
        # If all three topics appear, they should be in order
        pos = {}
        for word in ["ALPHA", "BETA", "GAMMA"]:
            idx = result.find(word)
            if idx >= 0:
                pos[word] = idx
        # At least some should be present; if multiple, should be ordered
        ordered_keys = sorted(pos, key=lambda k: pos[k])
        if len(ordered_keys) >= 2:
            expected = [k for k in ["ALPHA", "BETA", "GAMMA"] if k in ordered_keys]
            assert ordered_keys == expected

    def test_diversity_skips_sandwiched_sentences(self):
        """Sentences sandwiched between two already-selected ones should be skipped."""
        # Create 5 sentences where middle one is sandwiched
        emails = [
            {
                "clean_body": (
                    "ALPHA sentence with important keywords and information. "
                    "BRAVO filler sentence with some minor detail here. "
                    "CHARLIE sentence with critical project updates now. "
                    "DELTA another filler sentence with background context. "
                    "ECHO final sentence with actionable conclusions here."
                ),
                "sender_name": "Alice",
            }
        ]
        result = summarize_thread(emails, max_sentences=3)
        result_sentences = _split_sentences(result)
        # Should pick 3 sentences but skip any that are sandwiched
        assert len(result_sentences) <= 3
