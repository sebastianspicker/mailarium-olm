"""Tests for sentiment analysis."""

from src.sentiment_analyzer import analyze


def test_positive_text():
    result = analyze("Thank you for the excellent work. We are very pleased with the results.")
    assert result.sentiment == "positive"
    assert result.score > 0
    assert result.positive_count > 0


def test_negative_text():
    result = analyze("Unfortunately there is a critical problem. The system has failed completely.")
    assert result.sentiment == "negative"
    assert result.score < 0
    assert result.negative_count > 0


def test_neutral_text():
    result = analyze("Please find attached the quarterly report for your review. Best regards.")
    assert result.sentiment == "neutral"


def test_empty_text():
    result = analyze("")
    assert result.sentiment == "neutral"
    assert result.score == 0.0
    assert result.positive_count == 0
    assert result.negative_count == 0


def test_negation_handling():
    result = analyze("This is not good at all. I am not happy with the outcome.")
    # "not good" → negative, "not happy" → negative
    assert result.negative_count > 0


def test_mixed_sentiment():
    result = analyze("Thank you for the update, but unfortunately the deadline has been delayed.")
    assert result.positive_count > 0
    assert result.negative_count > 0


def test_score_range():
    for text in [
        "Great excellent wonderful fantastic amazing",
        "Problem error failed broken critical",
        "Regular meeting scheduled for Friday",
    ]:
        result = analyze(text)
        assert -1.0 <= result.score <= 1.0


def test_all_positive_words():
    result = analyze("great excellent wonderful happy love")
    assert result.sentiment == "positive"
    assert result.positive_count == 5
    assert result.negative_count == 0
    assert result.score == 1.0


def test_all_negative_words():
    result = analyze("problem error failed broken sorry")
    assert result.sentiment == "negative"
    assert result.negative_count == 5
    assert result.positive_count == 0
    assert result.score == -1.0
