"""Tests for near-duplicate email detection."""

from unittest.mock import MagicMock

from src.dedup_detector import DuplicateDetector, _char_ngrams, _jaccard_similarity


def test_char_ngrams_basic():
    ngrams = _char_ngrams("hello")
    assert "hel" in ngrams
    assert "ell" in ngrams
    assert "llo" in ngrams


def test_char_ngrams_short():
    ngrams = _char_ngrams("ab")
    assert ngrams == {"ab"}


def test_char_ngrams_empty():
    assert _char_ngrams("") == set()
    assert _char_ngrams("   ") == set()


def test_char_ngrams_whitespace_collapse():
    ngrams1 = _char_ngrams("hello  world")
    ngrams2 = _char_ngrams("hello world")
    assert ngrams1 == ngrams2


def test_jaccard_identical():
    s = {"a", "b", "c"}
    assert _jaccard_similarity(s, s) == 1.0


def test_jaccard_disjoint():
    assert _jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial():
    sim = _jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
    assert 0.4 < sim < 0.6  # 2/4 = 0.5


def test_jaccard_empty():
    assert _jaccard_similarity(set(), set()) == 1.0
    assert _jaccard_similarity({"a"}, set()) == 0.0
    assert _jaccard_similarity(set(), {"a"}) == 0.0


def test_find_duplicates_empty():
    db = MagicMock()
    db.emails_by_base_subject.return_value = []
    detector = DuplicateDetector(db)
    assert detector.find_duplicates() == []


def test_find_duplicates_with_matches():
    db = MagicMock()
    # Two emails with nearly identical body text
    body1 = "This is a test email about the quarterly budget review meeting"
    body2 = "This is a test email about the quarterly budget review meeting today"
    db.emails_by_base_subject.return_value = [
        ("Budget Review", [("uid1", body1), ("uid2", body2)]),
    ]
    detector = DuplicateDetector(db, threshold=0.7)
    dupes = detector.find_duplicates()
    assert len(dupes) == 1
    assert dupes[0]["uid_a"] == "uid1"
    assert dupes[0]["uid_b"] == "uid2"
    assert dupes[0]["similarity"] >= 0.7


def test_find_duplicates_no_match_different_bodies():
    db = MagicMock()
    db.emails_by_base_subject.return_value = [
        (
            "Test",
            [
                ("uid1", "Alpha beta gamma delta epsilon zeta eta theta"),
                ("uid2", "Completely different text about something else entirely"),
            ],
        ),
    ]
    detector = DuplicateDetector(db, threshold=0.85)
    dupes = detector.find_duplicates()
    assert len(dupes) == 0


def test_find_duplicates_limit():
    db = MagicMock()
    body = "This is a repeated email body text for testing deduplication"
    db.emails_by_base_subject.return_value = [
        ("Test", [(f"uid{i}", body) for i in range(5)]),
    ]
    detector = DuplicateDetector(db, threshold=0.5)
    dupes = detector.find_duplicates(limit=3)
    assert len(dupes) <= 3


def test_find_duplicates_skips_short_bodies():
    db = MagicMock()
    db.emails_by_base_subject.return_value = [
        ("Test", [("uid1", "short"), ("uid2", "tiny")]),
    ]
    detector = DuplicateDetector(db)
    dupes = detector.find_duplicates()
    assert len(dupes) == 0  # Bodies too short (<20 chars)
