# ruff: noqa: F401, F403
from __future__ import annotations

import pytest

from src.case_analysis import (
    build_case_analysis_payload,
    derive_case_analysis_query,
    transform_case_analysis_payload,
)
from src.case_analysis_harvest import _coverage_metrics, _split_evidence_bank_layers, build_archive_harvest_bundle
from src.mcp_models import EmailCaseAnalysisInput, EmailCaseFullPackInput, EmailLegalSupportInput
from src.question_execution_waves import derive_wave_query_lane_specs

from ._case_analysis_integration_cases import *
from .helpers.case_analysis_fixtures import case_payload as _case_payload


def test_email_case_analysis_input_requires_case_dates() -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["case_scope"].pop("date_from")
    with pytest.raises(ValueError, match=r"case_scope\.date_from is required"):
        EmailCaseAnalysisInput.model_validate(payload)


def test_email_case_analysis_input_requires_mixed_records_for_mixed_case_file() -> None:
    payload = _case_payload()
    payload["source_scope"] = "mixed_case_file"
    with pytest.raises(
        ValueError,
        match="mixed_case_file requires at least one of chat_log_entries, chat_exports, or matter_manifest artifacts",
    ):
        EmailCaseAnalysisInput.model_validate(payload)


def test_email_case_analysis_input_accepts_manifest_backed_non_email_records_for_mixed_case_file() -> None:
    payload = _case_payload()
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:calendar:1",
                "source_class": "calendar_export",
                "title": "Meeting invite",
                "text": "SUMMARY: BEM review DTSTART:2025-03-10T10:00:00",
            }
        ],
    }

    params = EmailCaseAnalysisInput.model_validate(payload)

    assert params.source_scope == "mixed_case_file"
    assert params.matter_manifest is not None


def test_email_case_analysis_input_requires_manifest_for_exhaustive_review() -> None:
    payload = _case_payload()
    payload["review_mode"] = "exhaustive_matter_review"
    with pytest.raises(ValueError, match="exhaustive_matter_review requires matter_manifest"):
        EmailCaseAnalysisInput.model_validate(payload)


def test_email_case_analysis_input_defaults_to_german_source_only() -> None:
    payload = _case_payload()
    payload.pop("output_language")
    payload.pop("translation_mode")
    params = EmailCaseAnalysisInput.model_validate(payload)

    assert params.output_language == "de"
    assert params.translation_mode == "source_only"


def test_email_case_analysis_input_accepts_preserved_matter_factual_context() -> None:
    payload = _case_payload()
    payload["matter_factual_context"] = "## Formal Notice\n\n- `2026-03-12`: AU to `HR mailbox`."

    params = EmailCaseAnalysisInput.model_validate(payload)

    assert params.matter_factual_context == payload["matter_factual_context"]


def test_email_case_analysis_input_accepts_context_people_and_institutional_actors() -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["case_scope"]["context_people"] = [{"name": "Lara Langer", "email": "lara.langer@example.test"}]
    payload["case_scope"]["institutional_actors"] = [
        {
            "label": "HR mailbox",
            "actor_type": "shared_mailbox",
            "email": "hr-mailbox@example.test",
            "function": "HR gatekeeper and notice route",
        }
    ]

    params = EmailCaseAnalysisInput.model_validate(payload)

    assert params.case_scope.context_people[0].email == "lara.langer@example.test"
    assert params.case_scope.institutional_actors[0].email == "hr-mailbox@example.test"


def test_email_legal_support_input_defaults_to_exhaustive_review_and_requires_manifest() -> None:
    payload = _case_payload()
    with pytest.raises(ValueError, match="exhaustive_matter_review requires matter_manifest"):
        EmailLegalSupportInput.model_validate(payload)


def test_email_legal_support_input_accepts_preserved_matter_factual_context() -> None:
    payload = _case_payload()
    payload["matter_factual_context"] = "## Formal Notice\n\n- `2026-03-12`: AU to `HR mailbox`."
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:email:1",
                "source_class": "formal_document",
                "title": "Notice chain",
                "text": "Document text.",
            }
        ],
    }

    params = EmailLegalSupportInput.model_validate(payload)

    assert params.matter_factual_context == payload["matter_factual_context"]


def test_email_legal_support_input_accepts_context_people_and_institutional_actors() -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["case_scope"]["context_people"] = [{"name": "Lara Langer", "email": "lara.langer@example.test"}]
    payload["case_scope"]["institutional_actors"] = [
        {
            "label": "HR mailbox",
            "actor_type": "shared_mailbox",
            "email": "hr-mailbox@example.test",
        }
    ]
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:email:1",
                "source_class": "formal_document",
                "title": "Notice chain",
                "text": "Document text.",
            }
        ],
    }

    params = EmailLegalSupportInput.model_validate(payload)

    assert params.case_scope.context_people[0].name == "Lara Langer"
    assert params.case_scope.institutional_actors[0].label == "HR mailbox"


def test_email_legal_support_input_rejects_retrieval_only_mode() -> None:
    payload = _case_payload()
    payload["review_mode"] = "retrieval_only"
    payload["matter_manifest"] = {
        "manifest_id": "matter-legal-1",
        "artifacts": [
            {
                "source_id": "manifest:email:1",
                "source_class": "formal_document",
                "title": "Case summary",
                "date": "2025-03-10",
                "text": "Document text.",
            }
        ],
    }
    with pytest.raises(ValueError, match="Dedicated legal-support tools require review_mode='exhaustive_matter_review'"):
        EmailLegalSupportInput.model_validate(payload)


def test_email_case_analysis_input_accepts_native_chat_exports_for_mixed_case_file(tmp_path) -> None:
    payload = _case_payload()
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
    payload["source_scope"] = "mixed_case_file"
    payload["chat_exports"] = [
        {
            "source_path": str(export_path),
            "platform": "Teams",
            "title": "Teams export",
        }
    ]
    params = EmailCaseAnalysisInput.model_validate(payload)
    assert len(params.chat_exports) == 1
    assert params.chat_exports[0].platform == "Teams"


def test_email_case_analysis_input_rejects_chat_exports_outside_allowlisted_read_roots(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _case_payload()
    blocked_root = tmp_path / "blocked"
    allowed_root = tmp_path / "allowed"
    blocked_root.mkdir()
    allowed_root.mkdir()
    export_path = blocked_root / "teams-export.html"
    export_path.write_text("<html><body>Chat export</body></html>", encoding="utf-8")
    payload["source_scope"] = "mixed_case_file"
    payload["chat_exports"] = [{"source_path": str(export_path), "platform": "Teams"}]

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", str(allowed_root))

    with pytest.raises(ValueError, match="allowed local read roots"):
        EmailCaseAnalysisInput.model_validate(payload)


def test_email_case_analysis_input_rejects_manifest_paths_outside_allowlisted_read_roots(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _case_payload()
    blocked_root = tmp_path / "blocked"
    allowed_root = tmp_path / "allowed"
    blocked_root.mkdir()
    allowed_root.mkdir()
    note_path = blocked_root / "meeting-note.txt"
    note_path.write_text("Meeting note", encoding="utf-8")
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:file:1",
                "source_class": "formal_document",
                "source_path": str(note_path),
            }
        ],
    }

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", str(allowed_root))

    with pytest.raises(ValueError, match="allowed local read roots"):
        EmailCaseAnalysisInput.model_validate(payload)


def test_email_case_full_pack_input_rejects_materials_dir_outside_allowlisted_read_roots(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked_root = tmp_path / "blocked"
    allowed_root = tmp_path / "allowed"
    blocked_root.mkdir()
    allowed_root.mkdir()
    (blocked_root / "record.txt").write_text("Meeting note.", encoding="utf-8")

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", str(allowed_root))

    with pytest.raises(ValueError, match="allowed local read roots"):
        EmailCaseFullPackInput.model_validate(
            {
                "prompt_text": "Review retaliation concerns from 2025-01-01 to 2025-06-30.",
                "materials_dir": str(blocked_root),
            }
        )
