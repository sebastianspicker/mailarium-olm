"""Focused regression contracts for repository security boundaries."""

from __future__ import annotations

import base64
import io
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree

from mailarium.ingestion.attachments.text import _extract_ods
from mailarium.ingestion.maintenance import _maintenance_sqlite_path
from mailarium.ingestion.olm import parser as olm_parser
from mailarium.ingestion.olm import xml_helpers
from mailarium.interfaces.cli.commands.search import render_plain
from mailarium.mailbox.ews.errors import EWSConfigurationError, EWSValidationError
from mailarium.mailbox.ews.transport import (
    _bounded_requests_adapter,
    _BoundedRawResponse,
    _RequestsSession,
)
from mailarium.model.html_text import html_to_text, strip_legal_disclaimer_tail
from mailarium.model.rfc2822 import extract_email_from_header, parse_address_list
from mailarium.platform.sanitization import apply_privacy_guardrails
from mailarium.retrieval.image_embedder import _validated_image
from mailarium.retrieval.reranker import CrossEncoderReranker
from scripts.release.privacy.privacy_scan_git import tracked_paths


def test_ods_inner_member_is_bounded_before_text_processing() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", b"x" * 2_000_001)
    assert _extract_ods(stream.getvalue()) is None


def test_olm_attachment_payloads_enforce_one_message_budget(monkeypatch) -> None:
    monkeypatch.setattr(xml_helpers, "MAX_TOTAL_ATTACHMENT_BYTES_PER_MESSAGE", 3)
    encoded = base64.b64encode(b"ab").decode("ascii")
    root = etree.fromstring(
        (
            "<root><OPFMessageCopyAttachmentList>"
            f"<messageAttachment><OPFAttachmentName>a.txt</OPFAttachmentName><OPFAttachmentContentData>{encoded}"
            "</OPFAttachmentContentData></messageAttachment>"
            f"<messageAttachment><OPFAttachmentName>b.txt</OPFAttachmentName><OPFAttachmentContentData>{encoded}"
            "</OPFAttachmentContentData></messageAttachment>"
            "</OPFMessageCopyAttachmentList></root>"
        ).encode()
    )
    with zipfile.ZipFile(io.BytesIO(), "w") as archive:
        payloads = xml_helpers._extract_attachment_payloads(root, {}, "message.xml", archive)
    assert payloads[0]["content"] == b"ab"
    assert payloads[1]["content"] is None
    assert payloads[1]["failure_reason"] == "attachment_content_exceeds_message_budget"


def test_failed_olm_members_still_consume_the_file_budget(tmp_path, monkeypatch) -> None:
    archive_path = tmp_path / "failed.olm"
    message_path = "Accounts/a/com.microsoft.__Messages/Inbox/message"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{message_path}-1.xml", b"one")
        archive.writestr(f"{message_path}-2.xml", b"two")
    calls = []
    monkeypatch.setattr(olm_parser, "MAX_XML_FILES", 1)
    monkeypatch.setattr(
        olm_parser,
        "_parse_archive_member",
        lambda *_args: (calls.append("attempt") and None, None, b""),
    )
    assert list(olm_parser.parse_olm(str(archive_path))) == []
    assert calls == ["attempt"]


def test_malformed_address_scans_preserve_first_address_semantics() -> None:
    assert extract_email_from_header(f"From: {'a' * 50_000}\n\nbody", "From") == "a" * 50_000
    assert parse_address_list('"Last, First" <first@example.test>; second@example.test') == [
        "first@example.test",
        "second@example.test",
    ]


def test_html_and_tail_cleanup_preserve_visible_semantics_for_malformed_input() -> None:
    assert html_to_text("<head>hidden</head><p>Visible</p><script>hidden</script>") == "Visible"
    assert html_to_text("<div hidden><p>hidden</div><p>Visible</p>") == "Visible"
    assert html_to_text("<head>" * 2_000 + "not visible") == ""
    assert html_to_text("<h1>" * 2_000 + "still visible") == "still visible"
    ordinary = "First\n\nSecond\n\nThird"
    assert strip_legal_disclaimer_tail(ordinary) == ordinary


def test_privacy_guardrails_redact_tuple_folders_and_sender_names() -> None:
    payload = {"folders": [("legal strategy alice@example.test", 1)], "sender_name": "Alice Example"}
    redacted, _summary = apply_privacy_guardrails(payload, privacy_mode="strict_redaction")
    assert isinstance(redacted["folders"][0], tuple)
    assert "alice@example.test" not in redacted["folders"][0][0]
    assert redacted["sender_name"] == "[REDACTED: participant_identity]"


def test_bounded_raw_response_stops_prebuffering() -> None:
    class Raw:
        closed = False

        def read(self, amt, **_kwargs):
            return b"x" * amt

        def close(self):
            self.closed = True

    raw = Raw()
    bounded = _BoundedRawResponse(raw, 4)
    with pytest.raises(EWSValidationError, match="size limit"):
        bounded.read()
    assert raw.closed is True


def test_bounded_requests_stream_and_reused_session_keep_one_adapter(monkeypatch) -> None:
    class Raw:
        closed = False

        def stream(self, _amt, **_kwargs):
            yield b"123"
            yield b"45"

        def close(self):
            self.closed = True

    raw = Raw()
    with pytest.raises(EWSValidationError, match="size limit"):
        list(_BoundedRawResponse(raw, 4).stream())
    assert raw.closed is True

    import requests

    response = SimpleNamespace(raw=Raw())
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", lambda *_args, **_kwargs: response)
    adapter = _bounded_requests_adapter(4)
    assert isinstance(adapter.send(object()).raw, _BoundedRawResponse)

    class FakeSession:
        def __init__(self) -> None:
            self.mounts = []

        def mount(self, prefix, mounted_adapter):
            self.mounts.append((prefix, mounted_adapter))

        def post(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=200, iter_content=lambda **_kwargs: iter((b"ok",)), close=lambda: None)

    fake = FakeSession()
    bounded_session = _RequestsSession(fake)
    for _ in range(2):
        response = bounded_session.post("https://example.test", data=b"", headers={}, timeout=1, max_response_bytes=4)
        assert response.content == b"ok"
    assert [prefix for prefix, _adapter in fake.mounts] == ["https://"]
    with pytest.raises(EWSConfigurationError, match="cannot change"):
        bounded_session.post("https://example.test", data=b"", headers={}, timeout=1, max_response_bytes=5)


def test_image_dimensions_are_rejected_before_decode(monkeypatch) -> None:
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (2, 2)).save(stream, format="PNG")

    def fail_load(_self, *_args, **_kwargs):
        raise AssertionError("oversized image was decoded")

    monkeypatch.setattr(Image.Image, "load", fail_load)
    with pytest.raises(ValueError, match="dimensions"):
        _validated_image(stream.getvalue(), max_pixels=1)


def test_cross_encoder_receives_local_only_policy(monkeypatch) -> None:
    captured = {}

    def fake_cross_encoder(model_name, **options):
        captured.update({"model_name": model_name, **options})
        return object()

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=fake_cross_encoder))
    reranker = CrossEncoderReranker("synthetic/model", local_files_only=True)
    assert reranker.model is not None
    assert captured == {"model_name": "synthetic/model", "local_files_only": True}


def test_maintenance_paths_require_an_allowed_runtime_root(tmp_path, monkeypatch) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside" / "archive.db"
    monkeypatch.setenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", str(allowed))
    assert Path(_maintenance_sqlite_path(str(allowed / "archive.db"))).is_relative_to(allowed)
    with pytest.raises(ValueError, match="allowed runtime roots"):
        _maintenance_sqlite_path(str(outside))


def test_plain_search_output_sanitizes_all_mail_metadata(capsys) -> None:
    result = SimpleNamespace(
        score=0.9,
        text="body",
        metadata={"subject": "bad\x1b]0;title\x07", "sender_name": "x\x1b[31m", "folder": "f\u202e"},
    )
    render_plain("query", [result])
    output = capsys.readouterr().out
    assert "\x1b" not in output
    assert "\u202e" not in output


def test_publication_git_paths_are_nul_delimited_and_unquoted(tmp_path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    unusual = "café\tmail.html"
    (tmp_path / unusual).write_text("synthetic", encoding="utf-8")
    subprocess.run(["git", "add", unusual], cwd=tmp_path, check=True)
    assert tracked_paths(tmp_path) == [unusual]
