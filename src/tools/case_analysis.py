"""Dedicated workplace case-analysis MCP tool."""

from __future__ import annotations

from typing import Any

from ..case_analysis import build_case_analysis
from ..case_campaign_workflow import (
    execute_all_waves_payload,
    execute_wave_payload,
    gather_evidence_payload,
    stamp_execution_payload,
)
from ..case_full_pack import execute_case_full_pack
from ..case_prompt_intake import build_case_prompt_preflight
from ..mcp_models import (
    EmailCaseAnalysisInput,
    EmailCaseExecuteAllWavesInput,
    EmailCaseExecuteWaveInput,
    EmailCaseFullPackInput,
    EmailCaseGatherEvidenceInput,
    EmailCasePromptPreflightInput,
)
from .utils import ToolDepsProto, get_deps, json_response, run_serialized_case_tool

_deps: ToolDepsProto | None = None


def _d() -> ToolDepsProto:
    return get_deps(_deps)


async def email_case_analysis(params: EmailCaseAnalysisInput) -> str:
    """Run one exploratory retrieval-bounded workplace case-analysis workflow."""
    return await run_serialized_case_tool(lambda: build_case_analysis(_d(), params))


async def email_case_execute_wave(params: EmailCaseExecuteWaveInput) -> str:
    """Execute one documented question wave through the shared campaign workflow."""
    return await run_serialized_case_tool(lambda: _email_case_execute_wave_impl(params))


async def _email_case_execute_wave_impl(params: EmailCaseExecuteWaveInput) -> str:
    wave_id = params.wave_id
    if wave_id is None:
        raise ValueError("wave_id is required")
    payload = await execute_wave_payload(
        _d(),
        params,
        wave_id=wave_id,
        scan_id_prefix=params.scan_id_prefix,
    )
    return json_response(stamp_execution_payload(payload, surface="mcp_server", case_action="execute-wave"))


async def email_case_execute_all_waves(params: EmailCaseExecuteAllWavesInput) -> str:
    """Execute all documented question waves through the shared campaign workflow."""
    return await run_serialized_case_tool(lambda: _email_case_execute_all_waves_impl(params))


async def _email_case_execute_all_waves_impl(params: EmailCaseExecuteAllWavesInput) -> str:
    payload = await execute_all_waves_payload(
        _d(),
        params,
        scan_id_prefix=params.scan_id_prefix,
        include_payloads=params.include_payloads,
    )
    return json_response(stamp_execution_payload(payload, surface="mcp_server", case_action="execute-all-waves"))


async def email_case_gather_evidence(params: EmailCaseGatherEvidenceInput) -> str:
    """Execute all waves and persist harvested evidence candidates plus exact quote promotions."""
    return await run_serialized_case_tool(lambda: _email_case_gather_evidence_impl(params))


async def _email_case_gather_evidence_impl(params: EmailCaseGatherEvidenceInput) -> str:
    payload = await gather_evidence_payload(
        _d(),
        params,
        run_id=params.run_id,
        phase_id=params.phase_id,
        scan_id_prefix=params.scan_id_prefix,
        harvest_limit_per_wave=params.harvest_limit_per_wave,
        promote_limit_per_wave=params.promote_limit_per_wave,
        include_payloads=params.include_payloads,
    )
    return json_response(stamp_execution_payload(payload, surface="mcp_server", case_action="gather-evidence"))


async def email_case_prompt_preflight(params: EmailCasePromptPreflightInput) -> str:
    """Return a bounded draft intake plus missing-input guidance for prompt-only matter descriptions."""
    return json_response(build_case_prompt_preflight(params))


async def email_case_full_pack(params: EmailCaseFullPackInput) -> str:
    """Compile and execute the full-pack workflow from a matter prompt plus supplied materials."""
    return await run_serialized_case_tool(lambda: _email_case_full_pack_impl(params))


async def _email_case_full_pack_impl(params: EmailCaseFullPackInput) -> str:
    return json_response(await execute_case_full_pack(_d(), params))


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register the dedicated case-analysis MCP tool."""
    global _deps
    _deps = deps
    mcp_instance.tool(
        name="email_case_analysis_exploratory",
        annotations=deps.tool_annotations("Exploratory Workplace Case Analysis"),
    )(email_case_analysis)
    mcp_instance.tool(
        name="email_case_analysis",
        annotations=deps.tool_annotations("Exploratory Workplace Case Analysis (Compatibility Alias)"),
    )(email_case_analysis)
    mcp_instance.tool(
        name="email_case_execute_wave",
        annotations=deps.idempotent_write_annotations("Case Campaign Execute Wave"),
    )(email_case_execute_wave)
    mcp_instance.tool(
        name="email_case_execute_all_waves",
        annotations=deps.idempotent_write_annotations("Case Campaign Execute All Waves"),
    )(email_case_execute_all_waves)
    mcp_instance.tool(
        name="email_case_gather_evidence",
        annotations=deps.idempotent_write_annotations("Case Campaign Gather Evidence"),
    )(email_case_gather_evidence)
    mcp_instance.tool(name="email_case_prompt_preflight", annotations=deps.tool_annotations("Case Prompt Preflight"))(
        email_case_prompt_preflight
    )
    mcp_instance.tool(name="email_case_full_pack", annotations=deps.idempotent_write_annotations("Case Full Pack"))(
        email_case_full_pack
    )
