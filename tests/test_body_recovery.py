"""Tests for empty/near-empty normalized body classification and recovery."""

from __future__ import annotations

from src.body_recovery import classify_body_state


def test_classify_body_state_recovers_image_only_html_from_preview():
    recovery = classify_body_state(
        raw_body_text='<!doctype html><html><body><img src="cid:1"></body></html>',
        raw_body_html='<html><body><img src="cid:1"></body></html>',
        raw_source="",
        preview_text="Scanned manual attached.",
        clean_body="",
        email_type="original",
        has_attachments=False,
    )

    assert recovery.body_kind == "content"
    assert recovery.body_empty_reason == "image_only"
    assert recovery.recovery_strategy == "preview"
    assert recovery.recovery_confidence == 0.7
    assert recovery.recovered_text == "Scanned manual attached."
    assert recovery.recovered_source == "preview"


def test_classify_body_state_marks_attachment_only_without_recovery():
    recovery = classify_body_state(
        raw_body_text="",
        raw_body_html="",
        raw_source="",
        preview_text="",
        clean_body="",
        email_type="original",
        has_attachments=True,
    )

    assert recovery.body_kind == "attachment_only"
    assert recovery.body_empty_reason == "attachment_only"
    assert recovery.recovery_strategy == ""
    assert recovery.recovery_confidence == 0.0
    assert recovery.recovered_text == ""


def test_classify_body_state_marks_metadata_only_reply_without_recovery():
    recovery = classify_body_state(
        raw_body_text="",
        raw_body_html="",
        raw_source="",
        preview_text="",
        clean_body="",
        email_type="reply",
        has_attachments=False,
    )

    assert recovery.body_kind == "content"
    assert recovery.body_empty_reason == "metadata_only_reply"
    assert recovery.recovery_strategy == "metadata_summary"
    assert recovery.recovered_text == "Metadata-only reply with no recoverable authored body text."
    assert recovery.recovered_source == "metadata_only_reply_summary"


def test_classify_body_state_recovers_from_source_when_preview_missing():
    recovery = classify_body_state(
        raw_body_text="",
        raw_body_html="<html><body><div></div></body></html>",
        raw_source="Subject: Shell\nContent-Type: text/plain; charset=utf-8\n\nVisible from source.",
        preview_text="",
        clean_body="",
        email_type="original",
        has_attachments=False,
    )

    assert recovery.body_kind == "content"
    assert recovery.body_empty_reason == "html_shell_only"
    assert recovery.recovery_strategy == "source"
    assert recovery.recovery_confidence == 0.5
    assert recovery.recovered_text == "Visible from source."
    assert recovery.recovered_source == "raw_source_text"


def test_classify_body_state_recovers_shell_only_original_with_summary_when_no_other_surface_exists():
    recovery = classify_body_state(
        raw_body_text="",
        raw_body_html=(
            "<html xmlns:o='urn:schemas-microsoft-com:office:office'>"
            "<head><meta name='Generator' content='Microsoft Word 15 (filtered medium)'></head>"
            "<body><div class='WordSection1'>&nbsp;</div></body></html>"
        ),
        raw_source="",
        preview_text="",
        clean_body="",
        email_type="original",
        has_attachments=False,
    )

    assert recovery.body_kind == "content"
    assert recovery.body_empty_reason == "html_shell_only"
    assert recovery.recovery_strategy == "shell_summary"
    assert recovery.recovery_confidence == 0.2
    assert recovery.recovered_text == "HTML shell message with no recoverable visible text."
    assert recovery.recovered_source == "html_shell_summary"


def test_classify_body_state_recovers_image_only_original_with_summary_when_no_preview_exists():
    recovery = classify_body_state(
        raw_body_text='<!doctype html><html><body><img src="cid:1"></body></html>',
        raw_body_html='<html><body><img src="cid:1"></body></html>',
        raw_source="",
        preview_text="",
        clean_body="",
        email_type="original",
        has_attachments=True,
    )

    assert recovery.body_kind == "content"
    assert recovery.body_empty_reason == "image_only"
    assert recovery.recovery_strategy == "image_summary"
    assert recovery.recovered_text == "Image-only message with attachments and no recoverable body text."
    assert recovery.recovered_source == "image_only_summary"


def test_classify_body_state_marks_source_shell_only_when_only_raw_source_exists_without_visible_body():
    recovery = classify_body_state(
        raw_body_text="",
        raw_body_html="",
        raw_source=(
            "Subject: Test\n"
            "Content-Type: multipart/signed; protocol=\"application/pkcs7-signature\"; boundary=\"abc\"\n\n"
            "--abc\n"
            "Content-Type: text/plain; charset=utf-8\n\n"
            "\n"
            "--abc\n"
            "Content-Type: application/pkcs7-signature\n\n"
            "<binary>\n"
            "--abc--\n"
        ),
        preview_text="",
        clean_body="",
        email_type="original",
        has_attachments=False,
    )

    assert recovery.body_kind == "content"
    assert recovery.body_empty_reason == "source_shell_only"
    assert recovery.recovery_strategy == "source_shell_summary"
    assert recovery.recovered_text == "Source-shell message with no recoverable visible body text."
    assert recovery.recovered_source == "source_shell_summary"
