from __future__ import annotations

import json

import pytest

from src.legal_support_acceptance_fixtures import build_fixture_answer_context, build_fixture_full_pack_input
from tests.helpers.mcp_tool_extended_fakes import _register_module


def test_registers_email_case_full_pack_tool() -> None:
    from src.tools import case_analysis

    fake_mcp = _register_module(case_analysis)

    assert "email_case_full_pack" in fake_mcp._tools


def test_registers_exploratory_case_analysis_aliases() -> None:
    from src.tools import case_analysis

    fake_mcp = _register_module(case_analysis)

    assert "email_case_analysis_exploratory" in fake_mcp._tools
    assert "email_case_analysis" in fake_mcp._tools


def test_registers_shared_campaign_wave_tools() -> None:
    from src.tools import case_analysis

    fake_mcp = _register_module(case_analysis)

    assert "email_case_execute_wave" in fake_mcp._tools
    assert "email_case_execute_all_waves" in fake_mcp._tools


@pytest.mark.asyncio
async def test_email_case_execute_wave_returns_shared_authority(monkeypatch) -> None:
    from src.mcp_models import EmailCaseExecuteWaveInput
    from src.tools import case_analysis

    fake_mcp = _register_module(case_analysis)
    fn = fake_mcp._tools["email_case_execute_wave"]

    async def fake_execute_wave_payload(_deps, _params, *, wave_id, scan_id_prefix):
        return {
            "workflow": "case_analysis",
            "wave_execution": {
                "wave_id": wave_id,
                "scan_id": f"{scan_id_prefix}:{wave_id}",
                "query_lanes": ["lane one", "lane two"],
            },
        }

    monkeypatch.setattr(case_analysis, "execute_wave_payload", fake_execute_wave_payload)

    result = await fn(
        EmailCaseExecuteWaveInput.model_validate(
            {
                "case_scope": {
                    "target_person": {"name": "employee"},
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
                "wave_id": "wave_1",
                "scan_id_prefix": "batch-1",
            }
        )
    )
    data = json.loads(result)

    assert data["wave_execution"]["wave_id"] == "wave_1"
    assert data["execution_authority"]["status"] == "shared_campaign_execution_surface"
    assert data["execution_authority"]["surface"] == "mcp_server"


@pytest.mark.asyncio
async def test_email_case_full_pack_returns_execution_payload(monkeypatch, tmp_path) -> None:
    from src.mcp_models import EmailCaseFullPackInput
    from src.tools import case_analysis

    fake_mcp = _register_module(case_analysis)
    fn = fake_mcp._tools["email_case_full_pack"]
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")

    async def fake_execute_case_full_pack(_deps, params):
        assert params.materials_dir == str(materials_dir)
        return {
            "workflow": "case_full_pack",
            "status": "completed",
            "execution": {"status": "completed"},
        }

    monkeypatch.setattr(case_analysis, "execute_case_full_pack", fake_execute_case_full_pack)

    result = await fn(
        EmailCaseFullPackInput.model_validate(
            {
                "prompt_text": "Claimant: employee. Review retaliation from 2025-01-01 to 2025-06-30.",
                "materials_dir": str(materials_dir),
            }
        )
    )
    data = json.loads(result)

    assert data["workflow"] == "case_full_pack"
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_email_case_full_pack_executes_realistic_fixture(monkeypatch) -> None:
    from src.tools import case_analysis

    fake_mcp = _register_module(case_analysis)
    fn = fake_mcp._tools["email_case_full_pack"]

    async def fake_build_answer_context_payload(_deps, _params, **kwargs):
        return build_fixture_answer_context("retaliation_rights_assertion")

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.tools.case_analysis.json_response", lambda data: json.dumps(data))

    result = await fn(
        build_fixture_full_pack_input(
            "retaliation_rights_assertion",
        )
    )
    data = json.loads(result)

    assert data["workflow"] == "case_full_pack"
    assert data["status"] == "completed"
    assert data["full_case_analysis"]["retaliation_analysis"]["retaliation_point_count"] == 1
    assert data["export_result"] is None
