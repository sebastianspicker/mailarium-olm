# mypy: disable-error-code=name-defined
"""Split archive-harvest helpers (case_analysis_harvest_common)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, cast

from .case_analysis_scope import derive_case_analysis_query
from .case_operator_intake import ingest_chat_exports
from .matter_file_ingestion import enrich_matter_manifest, infer_matter_manifest_authorized_roots
from .mcp_models import EmailAnswerContextInput, EmailCaseAnalysisInput
from .multi_source_case_bundle import build_standalone_mixed_source_bundle, promotable_mixed_source_evidence_rows
from .question_execution_waves import derive_wave_query_lane_specs, get_wave_definition

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto

# ruff: noqa: F401


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _coerce_month_bucket(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return ""


def _date_span_days(params: EmailCaseAnalysisInput) -> int:
    try:
        start = date.fromisoformat(str(params.case_scope.date_from))
        end = date.fromisoformat(str(params.case_scope.date_to))
    except Exception:
        return 0
    return max((end - start).days, 0)


def _source_basis_summary(
    *,
    params: EmailCaseAnalysisInput,
    email_archive_available: bool,
) -> dict[str, Any]:
    manifest_artifact_count = len(params.matter_manifest.artifacts) if params.matter_manifest is not None else 0
    primary_source = "matter_manifest_primary"
    note = "Only the supplied matter manifest is available to the current run."
    if email_archive_available and params.source_scope == "mixed_case_file" and manifest_artifact_count:
        primary_source = "email_archive_primary_manifest_supplement"
        note = "The indexed mailbox is the primary evidence substrate; the manifest supplements non-email records."
    elif email_archive_available:
        primary_source = "email_archive_primary"
        note = "The indexed mailbox is the primary evidence substrate for this run."
    return {
        "primary_source": primary_source,
        "email_archive_available": email_archive_available,
        "manifest_artifact_count": manifest_artifact_count,
        "source_scope": params.source_scope,
        "review_mode": params.review_mode,
        "note": note,
    }


def _archive_size_hint(retriever: Any) -> dict[str, Any]:
    stats_fn = getattr(retriever, "stats", None)
    if not callable(stats_fn):
        return {"total_emails": 0}
    try:
        stats = stats_fn()
    except Exception:
        return {"total_emails": 0}
    if not isinstance(stats, dict):
        return {"total_emails": 0}
    return {"total_emails": int(stats.get("total_emails") or 0)}


def _mixed_source_harvest_inputs(params: EmailCaseAnalysisInput) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    normalized_chat_log_entries = [entry.model_dump(mode="json") for entry in params.chat_log_entries]
    if params.chat_exports:
        chat_export_ingestion_report = ingest_chat_exports([entry.model_dump(mode="json") for entry in params.chat_exports])
        normalized_chat_log_entries.extend(
            [entry for entry in chat_export_ingestion_report.get("entries", []) if isinstance(entry, dict)]
        )
    manifest_payload: dict[str, Any] | None = None
    if params.matter_manifest is not None:
        manifest_dict = params.matter_manifest.model_dump(mode="json")
        manifest_payload = enrich_matter_manifest(
            manifest_dict,
            approved_roots=infer_matter_manifest_authorized_roots(manifest_dict),
        )
    bundle = build_standalone_mixed_source_bundle(
        matter_manifest=manifest_payload,
        chat_log_entries=normalized_chat_log_entries,
    )
    return bundle, normalized_chat_log_entries


def _row_identity(row: dict[str, Any]) -> str:
    raw_provenance = row.get("provenance")
    provenance: dict[str, Any] = cast(dict[str, Any], raw_provenance) if isinstance(raw_provenance, dict) else {}
    raw_locator = row.get("document_locator")
    locator: dict[str, Any] = cast(dict[str, Any], raw_locator) if isinstance(raw_locator, dict) else {}
    candidate_kind = _compact(row.get("candidate_kind"))
    attachment_filename = _compact(row.get("attachment_filename"))
    uid = _compact(row.get("uid"))
    segment_marker = _compact(row.get("segment_type")) or str(int(row.get("segment_ordinal") or 0) or "")
    for value in (
        row.get("result_key"),
        provenance.get("evidence_handle"),
        locator.get("evidence_handle"),
        f"attachment:{uid or _compact(row.get('source_id'))}:{attachment_filename}"
        if candidate_kind == "attachment" and attachment_filename
        else "",
        f"segment:{uid}:{segment_marker}" if segment_marker else "",
        row.get("source_id"),
        uid,
        row.get("chunk_id"),
    ):
        compact = _compact(value)
        if compact:
            return compact
    return ""


def _dedupe_evidence_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for row in rows:
        key = _row_identity(row)
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = dict(row)
            ordered_keys.append(key)
            continue
        if float(row.get("score") or 0.0) > float(existing.get("score") or 0.0):
            preserved_round = min(int(existing.get("harvest_round") or 0), int(row.get("harvest_round") or 0))
            deduped[key] = {**existing, **dict(row), "harvest_round": preserved_round}
    return [deduped[key] for key in ordered_keys]


def _annotate_round(rows: list[dict[str, Any]], *, prior_rows: list[dict[str, Any]], round_index: int) -> list[dict[str, Any]]:
    prior_round_by_key = {key: int(item.get("harvest_round") or 0) for item in prior_rows if (key := _row_identity(item))}
    annotated: list[dict[str, Any]] = []
    for row in rows:
        key = _row_identity(row)
        effective_round = prior_round_by_key.get(key, round_index)
        annotated.append({**dict(row), "harvest_round": effective_round})
    return annotated


def _round_recovered_keys(current_rows: list[dict[str, Any]], prior_rows: list[dict[str, Any]]) -> list[str]:
    prior_keys = {_row_identity(item) for item in prior_rows if _row_identity(item)}
    recovered: list[str] = []
    for row in current_rows:
        key = _row_identity(row)
        if key and key not in prior_keys and key not in recovered:
            recovered.append(key)
    return recovered


def _coverage_signature(metrics: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    return (
        int(metrics.get("unique_hits") or 0),
        int(metrics.get("unique_messages") or 0),
        int(metrics.get("unique_threads") or 0),
        int(metrics.get("unique_attachments") or 0),
        int(metrics.get("unique_segments") or 0),
        int(metrics.get("lane_coverage") or 0),
    )


def _adaptive_harvest_plan(
    *,
    params: EmailCaseAnalysisInput,
    query_lane_count: int,
    selected_top_k: int,
    total_emails: int,
    coverage_escalation: bool,
) -> dict[str, Any]:
    span_days = _date_span_days(params)
    corpus_bonus = 0
    if total_emails >= 15000:
        corpus_bonus = 8
    elif total_emails >= 5000:
        corpus_bonus = 5
    elif total_emails >= 1000:
        corpus_bonus = 2
    span_bonus = 0
    if span_days >= 730:
        span_bonus = 6
    elif span_days >= 365:
        span_bonus = 4
    elif span_days >= 180:
        span_bonus = 2
    lane_bonus = max(query_lane_count - 3, 0) * 2
    review_bonus = 2 if params.review_mode == "exhaustive_matter_review" else 0
    wave_bonus = 2 if params.wave_id else 0
    escalation_bonus = 8 if coverage_escalation else 0
    adaptive_bonus = corpus_bonus + span_bonus + lane_bonus + review_bonus + wave_bonus + escalation_bonus
    lane_top_k = min(60, max(selected_top_k * 2, 12, selected_top_k + adaptive_bonus))
    merge_budget = min(120, max(lane_top_k * 2, selected_top_k * 3, 24 + adaptive_bonus * 2))
    reserve_per_lane = 2 if query_lane_count >= 4 else 1
    if total_emails >= 15000 or span_days >= 365:
        reserve_per_lane = max(reserve_per_lane, 3)
    if coverage_escalation:
        reserve_per_lane = max(reserve_per_lane, 3)
    return {
        "total_emails": total_emails,
        "date_span_days": span_days,
        "adaptive_bonus": adaptive_bonus,
        "coverage_escalation": coverage_escalation,
        "lane_top_k": lane_top_k,
        "merge_budget": merge_budget,
        "reserve_per_lane": reserve_per_lane,
    }


__all__ = [
    "_adaptive_harvest_plan",
    "_annotate_round",
    "_archive_size_hint",
    "_coerce_month_bucket",
    "_compact",
    "_coverage_signature",
    "_date_span_days",
    "_dedupe_evidence_rows",
    "_mixed_source_harvest_inputs",
    "_round_recovered_keys",
    "_row_identity",
    "_source_basis_summary",
]
