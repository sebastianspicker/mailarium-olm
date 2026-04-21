"""Structural seam tests for the R7 parse_olm refactor."""

from __future__ import annotations

import logging
from dataclasses import replace
from zipfile import ZipFile

from src.parse_olm import Email, _parse_email_xml, _ParsedEmailEnrichments, parse_olm
from src.parse_olm_xml_parser import parse_olm_archive_impl


def test_parse_email_xml_delegates_postprocessing_helpers(monkeypatch):
    calls: list[str] = []

    def fake_apply_source(parts):
        calls.append("source")
        parts.subject = "source subject"

    def fake_finalize(parts):
        calls.append("finalize")
        parts.subject = "final subject"

    def fake_derive(parts, source_path):
        calls.append(f"derive:{source_path}")
        return _ParsedEmailEnrichments(
            forensic_body_text="forensic",
            forensic_body_source="raw_body_text",
            email_type="original",
        )

    def fake_build(parts, enrichments):
        calls.append("build")
        return Email(
            message_id=parts.message_id,
            subject=parts.subject,
            sender_name="",
            sender_email="",
            to=[],
            cc=[],
            bcc=[],
            date="",
            body_text="",
            body_html="",
            folder=parts.folder,
            has_attachments=False,
            forensic_body_text=enrichments.forensic_body_text,
            forensic_body_source=enrichments.forensic_body_source,
        )

    monkeypatch.setattr("src.parse_olm._apply_source_header_fallbacks", fake_apply_source)
    monkeypatch.setattr("src.parse_olm._finalize_parsed_email_parts", fake_finalize)
    monkeypatch.setattr("src.parse_olm._derive_email_enrichments", fake_derive)
    monkeypatch.setattr("src.parse_olm._build_parsed_email_from_parts", fake_build)

    xml = b"<email><OPFMessageCopySubject>hello</OPFMessageCopySubject></email>"
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")

    assert parsed is not None
    assert parsed.subject == "final subject"
    assert parsed.forensic_body_text == "forensic"
    assert calls == [
        "source",
        "finalize",
        "derive:Accounts/a/com.microsoft.__Messages/Inbox/msg.xml",
        "build",
    ]


def test_email_normalized_body_base_delegates_normalization_helpers(monkeypatch):
    calls: list[str] = []

    def fake_select(body_text: str, body_html: str):
        calls.append(f"select:{body_text}:{body_html}")
        from src.parse_olm import NormalizedBody

        return NormalizedBody("normalized", "body_text")

    def fake_strip_quoted(text: str, email_type: str):
        calls.append(f"quoted:{text}:{email_type}")
        return "quoted-stripped"

    def fake_strip_reply(text: str, email_type: str):
        calls.append(f"reply:{text}:{email_type}")
        return "reply-stripped"

    def fake_strip_forward(text: str, email_type: str):
        calls.append(f"forward:{text}:{email_type}")
        return "forward-stripped"

    monkeypatch.setattr("src.parse_olm._select_normalized_body", fake_select)
    monkeypatch.setattr("src.parse_olm._strip_normalized_quoted_content", fake_strip_quoted)
    monkeypatch.setattr("src.parse_olm._strip_normalized_reply_header_tail", fake_strip_reply)
    monkeypatch.setattr("src.parse_olm._strip_normalized_leading_forward_header_block", fake_strip_forward)

    email = Email(
        message_id="m1",
        subject="FW: test",
        sender_name="Sender",
        sender_email="sender@example.com",
        to=[],
        cc=[],
        bcc=[],
        date="2026-01-01T00:00:00Z",
        body_text="plain",
        body_html="<p>html</p>",
        folder="Inbox",
        has_attachments=False,
    )

    normalized = email._normalized_body_base

    assert normalized == replace(normalized, text="forward-stripped", source="body_text")
    assert calls == [
        "select:plain:<p>html</p>",
        "quoted:normalized:forward",
        "reply:quoted-stripped:forward",
        "forward:reply-stripped:forward",
    ]


def test_parse_olm_delegates_archive_traversal(monkeypatch, tmp_path):
    calls: list[tuple[object, ...]] = []

    olm_path = tmp_path / "sample.olm"
    olm_path.write_bytes(b"olm")

    def fake_archive(olm_path_arg, **kwargs):
        calls.append((olm_path_arg, kwargs["extract_attachments"], kwargs["parse_email_xml_fn"].__name__))
        return iter([])

    monkeypatch.setattr("src.parse_olm._parse_olm_archive_impl", fake_archive)

    list(parse_olm(str(olm_path), extract_attachments=True))

    assert calls == [(str(olm_path), True, "_parse_email_xml")]


def test_parse_archive_keeps_email_when_attachment_extraction_fails(monkeypatch, tmp_path):
    from lxml import etree

    olm_path = tmp_path / "sample.olm"
    with ZipFile(olm_path, "w") as zip_file:
        zip_file.writestr("Accounts/a/com.microsoft.__Messages/Inbox/msg.xml", "<root/>")

    email = Email(
        message_id="m1",
        subject="Subject",
        sender_name="Sender",
        sender_email="sender@example.com",
        to=[],
        cc=[],
        bcc=[],
        date="2026-01-01T00:00:00Z",
        body_text="body",
        body_html="",
        folder="Inbox",
        has_attachments=True,
        attachments=[{"name": "scan.pdf"}],
        attachment_contents=[],
    )
    root_attr = "_olm_root"
    ns_attr = "_olm_ns"
    setattr(email, root_attr, etree.Element("Email"))
    setattr(email, ns_attr, {})

    monkeypatch.setattr(
        "src.parse_olm_xml_parser._extract_attachment_payloads",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("payload failure")),
    )

    warnings: list[str] = []
    logger = logging.getLogger("tests.parse_olm_refactor_seams")
    monkeypatch.setattr(
        logger,
        "warning",
        lambda message, *args: warnings.append(str(message) % args if args else str(message)),
    )

    parsed = list(
        parse_olm_archive_impl(
            str(olm_path),
            extract_attachments=True,
            max_xml_files=10,
            max_total_xml_bytes=1024 * 1024,
            max_xml_bytes=1024 * 1024,
            logger=logger,
            parse_email_xml_fn=lambda _xml, _path: email,
        )
    )

    assert parsed == [email]
    assert parsed[0].attachment_contents == []
    assert bool(getattr(parsed[0], "_attachment_payload_extraction_failed", False)) is True
    assert "payload failure" in str(getattr(parsed[0], "_attachment_payload_extraction_error", ""))
    assert not hasattr(parsed[0], "_olm_root")
    assert not hasattr(parsed[0], "_olm_ns")
    assert any("Attachment extraction failed" in entry for entry in warnings)
