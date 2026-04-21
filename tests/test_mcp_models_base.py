from __future__ import annotations

import json

import pytest

from src.mcp_models import EmailCaseAnalysisInput, EvidenceUpdateInput
from src.mcp_models_evidence import EvidenceExportInput
from src.mcp_models_search import EmailExportInput, EmailIngestInput
from src.repo_paths import repo_root

from .helpers.case_analysis_fixtures import case_payload


def test_evidence_update_input_accepts_json_object_string() -> None:
    params = EvidenceUpdateInput.model_validate(
        json.dumps(
            {
                "evidence_id": 7,
                "summary": "Updated from serialized MCP payload",
                "relevance": 4,
            }
        )
    )

    assert params.evidence_id == 7
    assert params.summary == "Updated from serialized MCP payload"
    assert params.relevance == 4


def test_email_case_analysis_input_accepts_json_object_string() -> None:
    payload = case_payload()
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

    params = EmailCaseAnalysisInput.model_validate(json.dumps(payload))

    assert params.source_scope == "mixed_case_file"
    assert params.matter_manifest is not None


def test_email_export_input_rejects_pdf_without_output_path() -> None:
    with pytest.raises(ValueError, match="pdf export requires output_path"):
        EmailExportInput.model_validate({"uid": "uid-1", "format": "pdf"})


def test_email_export_input_rejects_output_paths_outside_allowed_roots() -> None:
    with pytest.raises(ValueError, match="allowed output roots"):
        EmailExportInput.model_validate({"uid": "uid-1", "output_path": "/etc/report.html"})


def test_email_export_input_rejects_tracked_repo_output_paths() -> None:
    with pytest.raises(ValueError, match="allowed output roots"):
        EmailExportInput.model_validate({"uid": "uid-1", "output_path": "src/config.py"})


def test_evidence_export_input_rejects_tracked_repo_output_paths() -> None:
    with pytest.raises(ValueError, match="allowed output roots"):
        EvidenceExportInput.model_validate({"output_path": "README.md"})


@pytest.mark.parametrize(
    "output_path",
    [
        "data/live-export.html",
        "docs/screenshots/email-export.html",
    ],
)
def test_export_inputs_reject_publicish_default_output_roots(output_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", raising=False)

    with pytest.raises(ValueError, match="allowed output roots"):
        EmailExportInput.model_validate({"uid": "uid-1", "output_path": output_path})
    with pytest.raises(ValueError, match="allowed output roots"):
        EvidenceExportInput.model_validate({"output_path": output_path})


def test_email_export_input_accepts_output_path_inside_allowlisted_root() -> None:
    allowed = repo_root() / "private" / "reports" / "report.html"
    params = EmailExportInput.model_validate({"uid": "uid-1", "output_path": str(allowed)})
    assert params.output_path == str(allowed)


def test_email_ingest_input_accepts_absolute_readable_olm_path(tmp_path) -> None:
    olm_path = tmp_path / "archive.olm"
    olm_path.write_text("olm", encoding="utf-8")
    params = EmailIngestInput.model_validate({"olm_path": str(olm_path)})
    assert params.olm_path == str(olm_path)


def test_email_ingest_input_rejects_readable_files_outside_local_read_roots() -> None:
    with pytest.raises(ValueError, match="allowed local read roots"):
        EmailIngestInput.model_validate({"olm_path": "/etc/hosts"})


def test_email_ingest_input_rejects_non_olm_files_inside_local_read_roots(tmp_path) -> None:
    text_path = tmp_path / "not-an-archive.txt"
    text_path.write_text("not an archive", encoding="utf-8")

    with pytest.raises(ValueError, match=r"\.olm archive"):
        EmailIngestInput.model_validate({"olm_path": str(text_path)})


def test_email_ingest_input_rejects_runtime_paths_outside_runtime_roots(tmp_path) -> None:
    olm_path = tmp_path / "archive.olm"
    olm_path.write_text("olm", encoding="utf-8")

    with pytest.raises(ValueError, match="allowed runtime roots"):
        EmailIngestInput.model_validate({"olm_path": str(olm_path), "sqlite_path": "/etc/passwd"})
