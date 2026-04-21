from __future__ import annotations

from pathlib import Path

from src.html_converter import html_to_text

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "html_normalization"


def _fixture_text(name: str, suffix: str) -> str:
    return (FIXTURE_DIR / f"{name}.{suffix}").read_text(encoding="utf-8").strip()


def test_html_normalization_fixtures_match_golden_outputs():
    fixture_names = [
        "apple_mail_quote_tail",
        "gmail_quote_tail",
        "hidden_preheader_newsletter",
        "legal_disclaimer_tail",
        "newsletter_boilerplate_tail",
        "outlook_reply_wrapper_tail",
        "visible_footer_preserved",
        "yahoo_quote_tail",
    ]

    for name in fixture_names:
        html = _fixture_text(name, "html")
        expected = _fixture_text(name, "txt")
        assert html_to_text(html) == expected
