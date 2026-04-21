"""Canonical prompt-preflight normalization helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CASE_PROMPT_PREFLIGHT_HELPER_KEYS = frozenset({"extraction_basis", "date_confidence"})


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(_as_dict(merged[key]), value)
        else:
            merged[key] = deepcopy(value)
    return merged


def normalize_prompt_preflight_case_input(preflight_payload: Any) -> dict[str, Any]:
    """Return the canonical machine-facing case input for a prompt-preflight payload."""
    if not isinstance(preflight_payload, dict):
        raise ValueError("prompt-preflight payload must be a JSON object")

    normalized: dict[str, Any] = {}
    if "draft_case_analysis_input" in preflight_payload:
        draft_input = preflight_payload.get("draft_case_analysis_input")
        if not isinstance(draft_input, dict):
            raise ValueError("prompt-preflight payload draft_case_analysis_input must be a JSON object")
        normalized = deepcopy(draft_input)

    if "draft_case_scope" in preflight_payload:
        draft_case_scope = preflight_payload.get("draft_case_scope")
        if not isinstance(draft_case_scope, dict):
            raise ValueError("prompt-preflight payload draft_case_scope must be a JSON object")
        normalized["case_scope"] = _deep_merge(_as_dict(normalized.get("case_scope")), draft_case_scope)

    if "recommended_source_scope" in preflight_payload:
        normalized["source_scope"] = deepcopy(preflight_payload.get("recommended_source_scope"))

    if "matter_factual_context" in preflight_payload:
        normalized["matter_factual_context"] = deepcopy(preflight_payload.get("matter_factual_context"))

    if not isinstance(normalized.get("case_scope"), dict):
        raise ValueError("prompt-preflight payload is missing case_scope data")
    if "source_scope" not in normalized:
        raise ValueError("prompt-preflight payload is missing source_scope data")
    if not str(normalized.get("review_mode") or "").strip():
        normalized["review_mode"] = "retrieval_only"
    return normalized


def normalize_preflight_case_input(preflight_payload: Any) -> dict[str, Any]:
    """Backward-compatible alias for the prompt-preflight normalizer."""
    return normalize_prompt_preflight_case_input(preflight_payload)


def sanitize_case_payload(value: Any) -> Any:
    """Drop prompt-preflight helper keys from nested case payloads."""
    if isinstance(value, dict):
        return {key: sanitize_case_payload(item) for key, item in value.items() if key not in CASE_PROMPT_PREFLIGHT_HELPER_KEYS}
    if isinstance(value, list):
        return [sanitize_case_payload(item) for item in value]
    return value
