# mypy: disable-error-code=name-defined
# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split archive-harvest helpers (case_analysis_harvest_expansion_diagnostics)."""

from __future__ import annotations

from typing import Any

from .case_analysis_harvest_common import _EXPANSION_ERROR_SAMPLE_LIMIT


def _default_expansion_stage_diagnostics(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": "ok",
        "attempted_count": 0,
        "expanded_row_count": 0,
        "error_count": 0,
        "errors": [],
    }


def _coerce_expansion_stage_result(
    result: Any,
    *,
    stage: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diagnostics = _default_expansion_stage_diagnostics(stage)
    if isinstance(result, tuple) and len(result) == 2:
        rows = _coerce_row_list(result[0])
        if isinstance(result[1], dict):
            return rows, _normalize_expansion_stage_diagnostics(diagnostics, result[1], row_count=len(rows))
        diagnostics["expanded_row_count"] = len(rows)
        return rows, diagnostics
    rows = _coerce_row_list(result)
    diagnostics["expanded_row_count"] = len(rows)
    return rows, diagnostics


def _coerce_row_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _sample_error_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in list(value or [])[:_EXPANSION_ERROR_SAMPLE_LIMIT] if isinstance(item, dict)]


def _normalize_expansion_stage_diagnostics(
    defaults: dict[str, Any],
    diagnostics_payload: dict[str, Any],
    *,
    row_count: int,
) -> dict[str, Any]:
    diagnostics = {**defaults, **diagnostics_payload}
    diagnostics["errors"] = _sample_error_list(diagnostics.get("errors"))
    diagnostics["error_count"] = int(diagnostics.get("error_count") or len(diagnostics["errors"]))
    diagnostics["attempted_count"] = int(diagnostics.get("attempted_count") or 0)
    diagnostics["expanded_row_count"] = int(diagnostics.get("expanded_row_count") or row_count)
    diagnostics["status"] = "partial" if int(diagnostics.get("error_count") or 0) > 0 else "ok"
    return diagnostics


def _stage_error_count(round_entry: dict[str, Any], stage: str) -> int:
    stage_entry = round_entry.get(stage) or {}
    return int(stage_entry.get("error_count") or 0) if isinstance(stage_entry, dict) else 0


def _aggregate_expansion_diagnostics(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rounds = [round_entry for round_entry in rounds if isinstance(round_entry, dict)]
    thread_error_count = sum(_stage_error_count(round_entry, "thread_expansion") for round_entry in normalized_rounds)
    attachment_error_count = sum(_stage_error_count(round_entry, "attachment_expansion") for round_entry in normalized_rounds)
    total_error_count = thread_error_count + attachment_error_count
    return {
        "status": "partial" if total_error_count > 0 else "ok",
        "error_count": total_error_count,
        "thread_expansion_error_count": thread_error_count,
        "attachment_expansion_error_count": attachment_error_count,
        "rounds": normalized_rounds,
    }


__all__ = [
    "_aggregate_expansion_diagnostics",
    "_coerce_expansion_stage_result",
    "_default_expansion_stage_diagnostics",
]
