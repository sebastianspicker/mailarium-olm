"""Parity and linear-time regressions for CODACY-WC-036 parser replacements."""

import time

from src.case_prompt_intake_helpers import _extract_dates, _named_people
from src.chunker import strip_quoted_content, strip_signature
from src.conversation_segments import _find_forward_separator, _parse_quote_line
from src.db_evidence_queries import _normalize_near_exact
from src.multi_source_case_bundle_common import _DATE_RANGE_RE, _ICAL_DATETIME_RE, _INLINE_EMAIL_RE
from src.promise_contradiction_analysis import _PROMISE_CUES, _contains_bounded_phrase
from src.reply_context import _is_reply_separator_line, _is_reply_wrapper_line, _parse_reply_context_line


def test_bounded_parsers_preserve_representative_matches() -> None:
    dates = _extract_dates("From January 2024 through 03.02.2025", today="2026-07-11", assume_date_to_today=False)
    assert dates["explicit_dates"] == ["2024-01-01", "2025-02-03"]
    assert _named_people("Employee: Alice Smith <alice@example.com>")["target_person"][0]["name"] == "Alice Smith"
    assert _contains_bounded_phrase("We will provide the records.", _PROMISE_CUES)
    assert not _contains_bounded_phrase("The goodwill remains.", _PROMISE_CUES)
    assert _normalize_near_exact("inter-\n national") == "international"
    assert strip_signature("Body\n\nMit freundlichen Grüßen,\nAlice") == ("Body", True)
    assert strip_quoted_content("Lead\n--- Original Message ---\nQuoted", "reply") == ("Lead", 2)
    assert _find_forward_separator("Lead\n-- Forwarded message --\nBody") == (5, 28, "-- Forwarded message --")
    assert _parse_quote_line("> > quoted") == (2, "quoted")
    assert _DATE_RANGE_RE.search("2024-01-02 through 2025-03-04").groups() == ("2024-01-02", "2025-03-04")
    assert _ICAL_DATETIME_RE.search("20250711T123045Z").groups() == ("2025", "07", "11", "12", "30", "45")
    assert _INLINE_EMAIL_RE.search("Alice <alice@example.com>").group(1) == "alice@example.com"
    assert _parse_reply_context_line("From: Alice") == ("from", "Alice")
    assert _is_reply_wrapper_line("On Friday Alice wrote:")
    assert _is_reply_separator_line("--- Original Message ---")


def test_bounded_parsers_complete_quickly_on_adversarial_input() -> None:
    adversarial = ("a-" * 50_000) + "\n" + ("> " * 50_000)
    started = time.perf_counter()
    _extract_dates(adversarial, today="2026-07-11", assume_date_to_today=True)
    _named_people(adversarial)
    _normalize_near_exact(adversarial)
    _find_forward_separator(adversarial)
    _DATE_RANGE_RE.search(adversarial)
    _INLINE_EMAIL_RE.search(adversarial)
    _parse_reply_context_line(adversarial)
    # Shared CI runners vary substantially under load. Three seconds still
    # distinguishes these bounded linear parsers from catastrophic backtracking
    # while avoiding a false failure on an otherwise successful full-suite run.
    assert time.perf_counter() - started < 3.0
