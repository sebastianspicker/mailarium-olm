from __future__ import annotations

import pytest

from src.case_operator_intake import build_manifest_from_materials_dir, ingest_chat_exports


def test_ingest_chat_exports_parses_common_speaker_time_lines(tmp_path) -> None:
    export_path = tmp_path / "teams-export.html"
    export_path.write_text(
        (
            "<html><body>"
            "[2025-03-01 09:10] employee: Please keep this off email for now.\n"
            "[2025-03-01 09:12] manager: We will discuss this later."
            "</body></html>"
        ),
        encoding="utf-8",
    )

    payload = ingest_chat_exports(
        [
            {
                "source_id": "chat-export-1",
                "source_path": str(export_path),
                "platform": "Teams",
                "title": "Teams export",
            }
        ]
    )

    assert payload["summary"]["ingested_chat_export_count"] == 1
    entry = payload["entries"][0]
    assert entry["date"] == "2025-03-01 09:10"
    assert entry["participants"] == ["employee", "manager"]
    assert entry["chat_message_count"] == 2
    assert entry["parsed_messages"][0]["speaker"] == "employee"
    assert entry["provenance"]["speaker_time_parsing"] == "common_line_patterns"


def test_build_manifest_from_materials_dir_excludes_operator_prompt_control_files(tmp_path) -> None:
    (tmp_path / "case_prompt.md").write_text(
        (
            "You are an evidence-focused legal-support and case-analysis agent.\n"
            "Core rules:\n"
            "- Work only from the provided materials.\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "live_prompt_2026-04-15.md").write_text(
        (
            "Review all uploaded documents, emails, attachments, notes, and time records in this matter.\n"
            "Output style:\n"
            "- concise but rigorous\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "meeting_note.txt").write_text("Meeting on 2025-03-10 with follow-up action items.", encoding="utf-8")

    manifest = build_manifest_from_materials_dir(str(tmp_path))

    artifact_titles = {artifact["title"] for artifact in manifest["artifacts"]}
    assert artifact_titles == {"meeting_note.txt"}


def test_ingest_chat_exports_marks_unauthorized_source_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    export_path = blocked_root / "teams-export.html"
    export_path.write_text("<html><body>Chat export</body></html>", encoding="utf-8")

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", str(allowed_root))

    payload = ingest_chat_exports(
        [
            {
                "source_id": "chat-export-1",
                "source_path": str(export_path),
                "platform": "Teams",
            }
        ]
    )

    assert payload["summary"]["ingested_chat_export_count"] == 0
    assert payload["warnings"][0]["reason"] == "source_path_not_authorized"


def test_build_manifest_from_materials_dir_rejects_unauthorized_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    (blocked_root / "meeting_note.txt").write_text("Meeting note", encoding="utf-8")

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", str(allowed_root))

    with pytest.raises(ValueError, match="allowed local read roots"):
        build_manifest_from_materials_dir(str(blocked_root))
