"""General MCP tool-registration coverage."""

import json
from types import SimpleNamespace

from mailarium.tools import register_all

from .helpers.repo_contracts import _mcp_tools


class _Module:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.calls = calls

    def register(self, _mcp, _deps) -> None:
        self.calls.append(self.name)


def test_register_all_registers_each_general_module(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("mailarium.tools._GENERAL_MODULES", [_Module("general", calls)])
    register_all(SimpleNamespace(), SimpleNamespace())

    assert calls == ["general"]


def test_registration_exposes_the_general_schema_only() -> None:
    tools = _mcp_tools()
    surface = json.dumps(
        {name: {"description": tool.description, "parameters": tool.parameters} for name, tool in tools.items()}
    ).lower()

    assert len(tools) == 54
    assert bool(tools["email_answer_context"].description) is True
    assert "collection_reference" in surface


def test_general_models_expose_open_categories_and_neutral_privacy_modes() -> None:
    from mailarium.mcp_models import EmailDossierInput, EmailReportInput, EvidenceAddInput

    report_schema = EmailReportInput.model_json_schema()
    report_modes = report_schema["properties"]["privacy_mode"]["enum"]
    assert report_modes == ["full_access", "contact_redacted", "sensitive_redacted", "strict_redaction"]

    evidence_schema = EvidenceAddInput.model_json_schema()["properties"]["category"]
    assert "enum" not in evidence_schema
    assert (
        EvidenceAddInput(
            email_uid="uid-1",
            category="migration_blocker",
            key_quote="The migration is blocked.",
            summary="Records the blocker.",
            relevance=4,
        ).category
        == "migration_blocker"
    )

    dossier_schema = EmailDossierInput.model_json_schema()["properties"]
    assert "collection_reference" in dossier_schema
    assert EmailDossierInput(collection_reference="collection-2026").collection_reference == "collection-2026"
