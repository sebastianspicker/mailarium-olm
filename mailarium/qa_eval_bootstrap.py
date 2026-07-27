"""Bootstrap reviewable generic QA question sets from captured payloads."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .qa_eval_cases import _load_json
from .qa_eval_impl import _results_payload_map


def default_bootstrap_questions_path(questions_path: Path) -> Path:
    """Place sampled bootstrap cases beside their source questions file without overwriting it."""
    if questions_path.suffix != ".json":
        return questions_path.with_name(f"{questions_path.name}.sampled")
    return questions_path.with_name(f"{questions_path.stem}.sampled{questions_path.suffix}")


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _candidate_brief(candidate: dict[str, Any], *, source_lane: str, rank: int) -> dict[str, Any]:
    brief: dict[str, Any] = {"source_lane": source_lane, "rank": rank}
    for key in ("uid", "source_id", "score", "subject", "date", "sender", "folder", "snippet"):
        value = candidate.get(key)
        if value not in (None, "", [], {}):
            brief[key] = value
    return brief


def _normalize_case(case: dict[str, Any]) -> None:
    """Remove transient labels and normalize fields before a case enters review."""
    if str(case.get("status") or "").strip() in {"", "todo"}:
        case["status"] = "sampled"
    if "TODO(" in str(case.get("expected_answer") or ""):
        case["expected_answer"] = ""
    case["expected_support_uids"] = [str(uid) for uid in case.get("expected_support_uids", []) or []]
    case["expected_top_uid"] = str(case["expected_top_uid"]) if case.get("expected_top_uid") else None


def _bootstrap_case(case: dict[str, Any], payload: dict[str, Any], sample_size: int) -> dict[str, Any]:
    sampled = deepcopy(case)
    _normalize_case(sampled)
    candidates = _dict_items(payload.get("candidates"))
    attachments = _dict_items(payload.get("attachment_candidates"))
    quality = payload.get("answer_quality")
    quality = quality if isinstance(quality, dict) else {}
    sampled["bootstrap_label_status"] = "review_required"
    sampled["bootstrap_candidates"] = [
        *[
            _candidate_brief(item, source_lane="candidates", rank=index + 1)
            for index, item in enumerate(candidates[:sample_size])
        ],
        *[
            _candidate_brief(item, source_lane="attachment_candidates", rank=index + 1)
            for index, item in enumerate(attachments[:sample_size])
        ],
    ]
    sampled["bootstrap_observation"] = {
        "top_candidate_uid": str(quality.get("top_candidate_uid") or "") or None,
        "confidence_label": str(quality.get("confidence_label") or "") or None,
        "ambiguity_reason": str(quality.get("ambiguity_reason") or "") or None,
        "candidate_count": len(candidates),
        "attachment_candidate_count": len(attachments),
    }
    return sampled


def bootstrap_question_set(*, questions_path: Path, results_path: Path, sample_size: int = 3) -> dict[str, Any]:
    """Build normalized question cases seeded with bounded evidence from captured results."""
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    raw = _load_json(questions_path)
    case_items = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(case_items, list):
        raise ValueError("questions file must contain a list of cases")
    payloads = _results_payload_map(results_path)
    cases = [
        _bootstrap_case(case, payloads.get(str(case.get("id") or ""), {}), sample_size)
        for case in case_items
        if isinstance(case, dict)
    ]
    description = str(raw.get("description") or "") if isinstance(raw, dict) else ""
    suffix = "Bootstrapped sampled review set; confirm final labels before scored evaluation."
    return {
        "version": int(raw.get("version") or 1) if isinstance(raw, dict) else 1,
        "description": f"{description} {suffix}".strip(),
        "bootstrap_metadata": {
            "status": "review_required",
            "questions_path": str(questions_path),
            "results_path": str(results_path),
            "sample_size": sample_size,
        },
        "cases": cases,
    }
