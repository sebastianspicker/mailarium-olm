# mypy: disable-error-code=name-defined
"""Split archive-harvest helpers (case_analysis_harvest_quality)."""

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

# ruff: noqa: F401,F821


def _seed_actor_keys(params: EmailCaseAnalysisInput) -> set[str]:
    case_scope = params.case_scope
    keys: set[str] = set()
    for person in [case_scope.target_person, *case_scope.suspected_actors, *case_scope.comparator_actors]:
        for value in (getattr(person, "name", ""), getattr(person, "email", ""), getattr(person, "role_hint", "")):
            compact = _compact(value).casefold()
            if compact:
                keys.add(compact)
    return keys


def _infer_actor_role(*, email: str, name: str, source: str) -> str:
    haystack = " ".join([_compact(email).casefold(), _compact(name).casefold(), _compact(source).casefold()])
    if any(token in haystack for token in ("personalrat", "betriebsrat", "sbv", "schwerbehindertenvertret", "vertret")):
        return "representation"
    if any(token in haystack for token in ("personal", "hr", "human resources")):
        return "hr"
    if any(token in haystack for token in ("leitung", "direktor", "dekan", "manager", "vorgesetzt", "leitungsteam")):
        return "management"
    if any(token in haystack for token in ("vergleich", "comparator", "peer", "kolleg", "kollegin")):
        return "comparator"
    if any(token in haystack for token in ("zeug", "witness", "beobacht")):
        return "witness"
    return "operational_peer"


def _keyword_terms(*values: Any) -> list[str]:
    terms: list[str] = []
    for value in values:
        for token in str(value or "").replace("|", " ").replace("_", " ").split():
            compact = "".join(char for char in token.casefold() if char.isalnum() or char in {"@", ".", "-"})
            if len(compact) >= 3 and compact not in terms:
                terms.append(compact)
    return terms


def _text_overlap_score(*, haystack: Any, terms: list[str]) -> int:
    normalized = _compact(haystack).casefold()
    if not normalized or not terms:
        return 0
    return sum(1 for term in terms if term and term in normalized)


def _seed_relevance_terms(row: dict[str, Any]) -> list[str]:
    return _keyword_terms(
        *(row.get("matched_query_queries") or []),
        *(row.get("matched_query_lanes") or []),
        row.get("subject"),
    )[:16]


def _actor_mentions(row: dict[str, Any]) -> list[dict[str, str]]:
    mentions: list[dict[str, str]] = []

    def _append(*, email: str = "", name: str = "", source: str) -> None:
        compact_email = _compact(email)
        compact_name = _compact(name)
        actor_key = (compact_email or compact_name).casefold()
        if not actor_key:
            return
        if any((item.get("sender_email") or item.get("sender_name") or "").casefold() == actor_key for item in mentions):
            return
        mentions.append({"sender_email": compact_email, "sender_name": compact_name, "source": source})

    _append(email=str(row.get("sender_email") or ""), name=str(row.get("sender_name") or ""), source="sender")
    recipients_summary = row.get("recipients_summary")
    if isinstance(recipients_summary, dict):
        for email in recipients_summary.get("visible_recipient_emails", []) or []:
            _append(email=str(email or ""), source="recipient")
    speaker_attribution = row.get("speaker_attribution")
    if isinstance(speaker_attribution, dict):
        for block in speaker_attribution.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            _append(email=str(block.get("speaker_email") or ""), source="quoted_speaker")
    for email in row.get("reply_context_emails", []) or []:
        _append(email=str(email or ""), source="reply_context")
    return mentions


def _actor_discovery_summary(*, evidence_bank: list[dict[str, Any]], params: EmailCaseAnalysisInput) -> dict[str, Any]:
    seed_keys = _seed_actor_keys(params)
    discovered: dict[str, dict[str, Any]] = {}
    for row in evidence_bank:
        for mention in _actor_mentions(row):
            sender_email = _compact(mention.get("sender_email"))
            sender_name = _compact(mention.get("sender_name"))
            actor_key = (sender_email or sender_name).casefold()
            if not actor_key or actor_key in seed_keys:
                continue
            entry = discovered.setdefault(
                actor_key,
                {
                    "sender_email": sender_email,
                    "sender_name": sender_name,
                    "role": _infer_actor_role(
                        email=sender_email,
                        name=sender_name,
                        source=" ".join([str(row.get("subject") or ""), str(mention.get("source") or "")]),
                    ),
                    "hit_count": 0,
                    "matched_query_lanes": set(),
                    "evidence_sources": set(),
                },
            )
            entry["hit_count"] = int(entry.get("hit_count") or 0) + 1
            entry["matched_query_lanes"].update(str(item) for item in row.get("matched_query_lanes", []) if _compact(item))
            entry["evidence_sources"].add(str(mention.get("source") or "sender"))
    rows = sorted(
        [
            {
                "sender_email": value["sender_email"],
                "sender_name": value["sender_name"],
                "role": value["role"],
                "hit_count": int(value["hit_count"]),
                "matched_query_lanes": sorted(value["matched_query_lanes"]),
                "evidence_sources": sorted(value.get("evidence_sources") or []),
            }
            for value in discovered.values()
        ],
        key=lambda item: (-int(str(item.get("hit_count") or 0)), str(item.get("sender_email") or item.get("sender_name") or "")),
    )
    role_counts: dict[str, int] = {}
    for row in rows:
        role = str(row.get("role") or "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    return {
        "discovered_actor_count": len(rows),
        "roles": role_counts,
        "top_discovered_actors": rows[:8],
    }


def _harvest_quality_summary(
    *,
    evidence_bank: list[dict[str, Any]],
    metrics: dict[str, Any],
    actor_discovery: dict[str, Any],
) -> dict[str, Any]:
    total = len(evidence_bank)
    if total <= 0:
        return {
            "status": "weak",
            "score": 0.0,
            "reasons": ["empty_evidence_bank"],
            "exact_quote_rate": 0.0,
            "attachment_rate": 0.0,
            "provenance_completeness_rate": 0.0,
            "actor_role_diversity": 0,
        }
    exact_hits = int(metrics.get("verified_exact_hits") or 0)
    attachment_hits = int(metrics.get("attachment_candidate_count") or 0)
    provenance_hits = int(metrics.get("provenance_complete_hits") or 0)
    actor_role_diversity = len((actor_discovery.get("roles") or {}).keys()) if isinstance(actor_discovery, dict) else 0
    exact_rate = exact_hits / total
    attachment_rate = attachment_hits / total
    provenance_rate = provenance_hits / total
    score = round(
        min(
            1.0,
            (exact_rate * 0.4)
            + (attachment_rate * 0.15)
            + (provenance_rate * 0.2)
            + (min(actor_role_diversity, 4) / 4.0 * 0.1)
            + (min(int(metrics.get("thread_expansion_hits") or 0), 6) / 6.0 * 0.15),
        ),
        4,
    )
    reasons: list[str] = []
    if exact_rate < 0.1:
        reasons.append("exact_quote_rate_low")
    if attachment_hits <= 0:
        reasons.append("attachment_candidates_missing")
    if provenance_rate < 0.8:
        reasons.append("provenance_incomplete")
    if actor_role_diversity <= 1:
        reasons.append("actor_role_diversity_low")
    status = "pass" if score >= 0.45 and not reasons[:2] else "weak"
    return {
        "status": status,
        "score": score,
        "reasons": reasons,
        "exact_quote_rate": round(exact_rate, 4),
        "attachment_rate": round(attachment_rate, 4),
        "provenance_completeness_rate": round(provenance_rate, 4),
        "actor_role_diversity": actor_role_diversity,
    }


def _mixed_source_identity_rows(source: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key in ("author", "sender_name", "sender_email"):
        value = _compact(source.get(key))
        if value:
            rows.append((value, value))
    for key in ("participants", "recipients", "to", "cc", "bcc"):
        for item in source.get(key, []) if isinstance(source.get(key), list) else []:
            value = _compact(item)
            if value:
                rows.append((value, value))
    return rows


def augment_mixed_source_harvest_summary(
    *,
    summary: dict[str, Any],
    multi_source_case_bundle: dict[str, Any] | None,
    params: EmailCaseAnalysisInput,
) -> dict[str, Any]:
    """Attach mixed-source coverage truth to the archive-harvest summary."""
    source_bundle = multi_source_case_bundle if isinstance(multi_source_case_bundle, dict) else {}
    source_basis = dict(summary.get("source_basis") or {})
    sources = [item for item in source_bundle.get("sources", []) if isinstance(item, dict)]
    source_links = [item for item in source_bundle.get("source_links", []) if isinstance(item, dict)]
    source_link_diagnostics = [item for item in source_bundle.get("source_link_diagnostics", []) if isinstance(item, dict)]
    non_email_sources = [item for item in sources if str(item.get("source_type") or "") != "email"]
    email_sources = [item for item in sources if str(item.get("source_type") or "") == "email"]
    linked_source_ids = {
        str(link.get("from_source_id") or "")
        for link in source_links
        if str(link.get("from_source_id") or "") and str(link.get("to_source_id") or "")
    } | {
        str(link.get("to_source_id") or "")
        for link in source_links
        if str(link.get("from_source_id") or "") and str(link.get("to_source_id") or "")
    }
    linked_non_email_sources = [source for source in non_email_sources if str(source.get("source_id") or "") in linked_source_ids]
    chronology_anchor_source_ids = {
        str(item.get("source_id") or "")
        for item in source_bundle.get("chronology_anchors", [])
        if isinstance(item, dict) and _compact(item.get("source_id")) and _compact(item.get("date"))
    }
    document_locator_complete_count = sum(
        1
        for source in non_email_sources
        if _compact((source.get("document_locator") or {}).get("evidence_handle"))
        and bool(
            (source.get("document_locator") or {}).get("snippet_locator")
            or (source.get("document_locator") or {}).get("text_locator")
            or _compact((source.get("document_locator") or {}).get("chunk_id"))
        )
    )
    chronology_anchor_complete_count = sum(
        1 for source in non_email_sources if str(source.get("source_id") or "") in chronology_anchor_source_ids
    )
    mixed_source_metrics = {
        "non_email_source_count": len(non_email_sources),
        "source_class_diversity": len(
            {str(source.get("source_type") or "") for source in non_email_sources if str(source.get("source_type") or "")}
        ),
        "linked_non_email_source_count": len(linked_non_email_sources),
        "unlinked_non_email_source_count": max(len(non_email_sources) - len(linked_non_email_sources), 0),
        "document_locator_complete_count": document_locator_complete_count,
        "chronology_anchor_complete_count": chronology_anchor_complete_count,
    }
    summary["mixed_source_metrics"] = mixed_source_metrics

    coverage_gate = dict(summary.get("coverage_gate") or {})
    quality_gate = dict(summary.get("quality_gate") or {})
    coverage_reasons = [str(item) for item in coverage_gate.get("reasons", []) if _compact(item)]
    coverage_recommendations = [str(item) for item in coverage_gate.get("recommendations", []) if _compact(item)]
    quality_reasons = [str(item) for item in quality_gate.get("reasons", []) if _compact(item)]
    manifest_primary = not bool(source_basis.get("email_archive_available")) and bool(non_email_sources)
    if manifest_primary:
        coverage_reasons = [
            reason
            for reason in coverage_reasons
            if reason
            not in {
                "unique_hits_below_threshold",
                "unique_threads_below_threshold",
                "unique_senders_below_threshold",
                "unique_months_below_threshold",
                "lane_coverage_below_threshold",
                "attachment_hits_below_threshold",
            }
        ]
        coverage_recommendations = [
            recommendation
            for recommendation in coverage_recommendations
            if recommendation
            not in {
                "Raise harvest breadth and widen actor-plus-issue query lanes.",
                "Expand the strongest hits with thread lookup and similar-message replay.",
                "Add actor-name variants and routing lanes across the archive.",
                "Widen the timeline window or add explicit dated event lanes.",
                "Add German orthographic fallback and lower-performing actor or issue lanes.",
                "Run attachment-first retrieval and search mixed-source records more aggressively.",
            }
        ]
        quality_reasons = [reason for reason in quality_reasons if reason != "empty_evidence_bank"]
        if non_email_sources and chronology_anchor_complete_count >= 3:
            quality_gate.setdefault("score", 0.6)
    if non_email_sources and email_sources and source_link_diagnostics and len(linked_non_email_sources) < len(non_email_sources):
        coverage_reasons.append("document_linking_incomplete")
        coverage_recommendations.append("Strengthen conservative document-email linking for manifest-backed records.")
    if non_email_sources and chronology_anchor_complete_count < min(len(non_email_sources), 3):
        coverage_reasons.append("chronology_anchor_coverage_incomplete")
        coverage_recommendations.append("Promote more document-backed dates into chronology anchors.")
    document_locator_floor = max(3, min(len(non_email_sources), (len(non_email_sources) + 4) // 5)) if non_email_sources else 0
    if non_email_sources and document_locator_complete_count < document_locator_floor:
        quality_reasons.append("document_locator_coverage_incomplete")
    if coverage_reasons:
        coverage_gate["status"] = "needs_more_harvest"
        coverage_gate["reasons"] = list(dict.fromkeys(coverage_reasons))
        coverage_gate["recommendations"] = list(dict.fromkeys(coverage_recommendations))
    elif manifest_primary and non_email_sources:
        coverage_gate["status"] = "pass"
        coverage_gate["reasons"] = []
        coverage_gate["recommendations"] = []
    if quality_reasons:
        quality_gate["status"] = "weak"
        quality_gate["reasons"] = list(dict.fromkeys(quality_reasons))
    elif manifest_primary and non_email_sources:
        quality_gate["status"] = "pass"
        quality_gate["reasons"] = []
    summary["coverage_gate"] = coverage_gate
    summary["quality_gate"] = quality_gate

    seed_keys = _seed_actor_keys(params)
    document_only: dict[str, dict[str, Any]] = {}
    for source in non_email_sources:
        for display_value, _identity_source in _mixed_source_identity_rows(source):
            actor_key = display_value.casefold()
            if not actor_key or actor_key in seed_keys:
                continue
            entry = document_only.setdefault(
                actor_key,
                {
                    "identity": display_value,
                    "role": _infer_actor_role(email=display_value, name=display_value, source=source.get("title") or ""),
                    "source_count": 0,
                    "source_types": set(),
                },
            )
            entry["source_count"] = int(entry.get("source_count") or 0) + 1
            entry["source_types"].add(str(source.get("source_type") or ""))
    actor_discovery = dict(summary.get("actor_discovery") or {})
    actor_discovery["document_only_actor_count"] = len(document_only)
    actor_discovery["top_document_only_actors"] = [
        {
            "identity": value["identity"],
            "role": value["role"],
            "source_count": int(value["source_count"]),
            "source_types": sorted(value["source_types"]),
        }
        for value in sorted(
            document_only.values(),
            key=lambda item: (-int(item.get("source_count") or 0), str(item.get("identity") or "")),
        )[:8]
    ]
    summary["actor_discovery"] = actor_discovery
    return summary


__all__ = [
    "_actor_discovery_summary",
    "_actor_mentions",
    "_harvest_quality_summary",
    "_infer_actor_role",
    "_keyword_terms",
    "_mixed_source_identity_rows",
    "_seed_actor_keys",
    "_seed_relevance_terms",
    "_text_overlap_score",
    "augment_mixed_source_harvest_summary",
]
