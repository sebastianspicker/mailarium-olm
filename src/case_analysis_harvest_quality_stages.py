"""Typed stages for harvest quality and mixed-source coverage augmentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._utils import _compact
from .mcp_models import EmailCaseAnalysisInput


def actor_mentions_stage(row: dict[str, Any]) -> list[dict[str, str]]:
    """Collect distinct sender, recipient, quoted-speaker, and reply actors."""
    mentions: list[dict[str, str]] = []
    _append_mention(mentions, email=row.get("sender_email"), name=row.get("sender_name"), source="sender")
    recipients = row.get("recipients_summary")
    if isinstance(recipients, dict):
        for email in recipients.get("visible_recipient_emails", []) or []:
            _append_mention(mentions, email=email, source="recipient")
    speakers = row.get("speaker_attribution")
    if isinstance(speakers, dict):
        _append_quoted_speakers(mentions, speakers)
    for email in row.get("reply_context_emails", []) or []:
        _append_mention(mentions, email=email, source="reply_context")
    return mentions


def _append_quoted_speakers(mentions: list[dict[str, str]], speakers: dict[str, Any]) -> None:
    for block in speakers.get("quoted_blocks", []) or []:
        if isinstance(block, dict):
            _append_mention(mentions, email=block.get("speaker_email"), source="quoted_speaker")


def _append_mention(mentions: list[dict[str, str]], *, email: Any = "", name: Any = "", source: str) -> None:
    compact_email, compact_name = _compact(email), _compact(name)
    actor_key = (compact_email or compact_name).casefold()
    if not actor_key or actor_key in {_mention_key(item) for item in mentions}:
        return
    mentions.append({"sender_email": compact_email, "sender_name": compact_name, "source": source})


def _mention_key(item: dict[str, str]) -> str:
    return (item.get("sender_email") or item.get("sender_name") or "").casefold()


def actor_discovery_stage(*, evidence_bank: list[dict[str, Any]], params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Summarize non-seed actors without changing ranking or output fields."""
    from .case_analysis_harvest_quality import _seed_actor_keys

    seed_keys = _seed_actor_keys(params)
    discovered: dict[str, dict[str, Any]] = {}
    for row in evidence_bank:
        for mention in actor_mentions_stage(row):
            _record_discovered_actor(discovered, seed_keys, row, mention)
    rows = _discovered_actor_rows(discovered)
    roles: dict[str, int] = {}
    for row in rows:
        role = str(row.get("role") or "unknown")
        roles[role] = roles.get(role, 0) + 1
    return {"discovered_actor_count": len(rows), "roles": roles, "top_discovered_actors": rows[:8]}


def _record_discovered_actor(
    discovered: dict[str, dict[str, Any]],
    seed_keys: set[str],
    row: dict[str, Any],
    mention: dict[str, str],
) -> None:
    from .case_analysis_harvest_quality import _infer_actor_role

    email, name = _compact(mention.get("sender_email")), _compact(mention.get("sender_name"))
    actor_key = (email or name).casefold()
    if not actor_key or actor_key in seed_keys:
        return
    entry = discovered.setdefault(
        actor_key,
        {
            "sender_email": email,
            "sender_name": name,
            "role": _infer_actor_role(
                email=email,
                name=name,
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


def _discovered_actor_rows(discovered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "sender_email": value["sender_email"],
            "sender_name": value["sender_name"],
            "role": value["role"],
            "hit_count": int(value["hit_count"]),
            "matched_query_lanes": sorted(value["matched_query_lanes"]),
            "evidence_sources": sorted(value.get("evidence_sources") or []),
        }
        for value in discovered.values()
    ]
    return sorted(rows, key=lambda item: (-int(item["hit_count"]), str(item["sender_email"] or item["sender_name"])))


def harvest_quality_stage(
    *, evidence_bank: list[dict[str, Any]], metrics: dict[str, Any], actor_discovery: dict[str, Any]
) -> dict[str, Any]:
    """Calculate the stable harvest quality score and reasons."""
    total = len(evidence_bank)
    if total <= 0:
        return _empty_quality()
    exact_hits = int(metrics.get("verified_exact_hits") or 0)
    attachment_hits = int(metrics.get("attachment_candidate_count") or 0)
    provenance_hits = int(metrics.get("provenance_complete_hits") or 0)
    role_diversity = len((actor_discovery.get("roles") or {}).keys())
    exact_rate, attachment_rate, provenance_rate = exact_hits / total, attachment_hits / total, provenance_hits / total
    score = _quality_score(exact_rate, attachment_rate, provenance_rate, role_diversity, metrics)
    reasons = _quality_reasons(exact_rate, attachment_hits, provenance_rate, role_diversity)
    return {
        "status": "pass" if score >= 0.45 and not reasons[:2] else "weak",
        "score": score,
        "reasons": reasons,
        "exact_quote_rate": round(exact_rate, 4),
        "attachment_rate": round(attachment_rate, 4),
        "provenance_completeness_rate": round(provenance_rate, 4),
        "actor_role_diversity": role_diversity,
    }


def _empty_quality() -> dict[str, Any]:
    return {
        "status": "weak",
        "score": 0.0,
        "reasons": ["empty_evidence_bank"],
        "exact_quote_rate": 0.0,
        "attachment_rate": 0.0,
        "provenance_completeness_rate": 0.0,
        "actor_role_diversity": 0,
    }


def _quality_score(
    exact_rate: float, attachment_rate: float, provenance_rate: float, role_diversity: int, metrics: dict[str, Any]
) -> float:
    thread_score = min(int(metrics.get("thread_expansion_hits") or 0), 6) / 6.0 * 0.15
    return round(
        min(
            1.0,
            exact_rate * 0.4 + attachment_rate * 0.15 + provenance_rate * 0.2 + min(role_diversity, 4) / 4.0 * 0.1 + thread_score,
        ),
        4,
    )


def _quality_reasons(exact_rate: float, attachment_hits: int, provenance_rate: float, role_diversity: int) -> list[str]:
    checks = (
        (exact_rate < 0.1, "exact_quote_rate_low"),
        (attachment_hits <= 0, "attachment_candidates_missing"),
        (provenance_rate < 0.8, "provenance_incomplete"),
        (role_diversity <= 1, "actor_role_diversity_low"),
    )
    return [reason for failed, reason in checks if failed]


@dataclass(slots=True)
class MixedSourceHarvestContext:
    """Normalized data used to augment archive coverage with manifest truth."""

    summary: dict[str, Any]
    params: EmailCaseAnalysisInput
    bundle: dict[str, Any]
    sources: list[dict[str, Any]]
    non_email_sources: list[dict[str, Any]]
    email_sources: list[dict[str, Any]]
    links: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    linked_ids: set[str]
    chronology_ids: set[str]
    locator_count: int
    chronology_count: int


def augment_mixed_source_stage(
    *, summary: dict[str, Any], multi_source_case_bundle: dict[str, Any] | None, params: EmailCaseAnalysisInput
) -> dict[str, Any]:
    """Attach mixed-source metrics, gates, and document-only actor discovery."""
    context = _mixed_source_context(summary, multi_source_case_bundle, params)
    summary["mixed_source_metrics"] = _mixed_source_metrics(context)
    _apply_mixed_source_gates(context)
    _apply_document_actor_discovery(context)
    return summary


def _mixed_source_context(
    summary: dict[str, Any], bundle: dict[str, Any] | None, params: EmailCaseAnalysisInput
) -> MixedSourceHarvestContext:
    source_bundle = bundle if isinstance(bundle, dict) else {}
    sources = _dict_rows(source_bundle, "sources")
    non_email, emails = _partition_sources(sources)
    links = _dict_rows(source_bundle, "source_links")
    diagnostics = _dict_rows(source_bundle, "source_link_diagnostics")
    linked_ids = _linked_source_ids(links)
    chronology_ids = _chronology_source_ids(source_bundle)
    locator_count = sum(1 for source in non_email if _complete_document_locator(source))
    chronology_count = sum(1 for source in non_email if str(source.get("source_id") or "") in chronology_ids)
    return MixedSourceHarvestContext(
        summary,
        params,
        source_bundle,
        sources,
        non_email,
        emails,
        links,
        diagnostics,
        linked_ids,
        chronology_ids,
        locator_count,
        chronology_count,
    )


def _dict_rows(bundle: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in bundle.get(key, []) if isinstance(item, dict)]


def _partition_sources(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    non_email = [item for item in sources if str(item.get("source_type") or "") != "email"]
    emails = [item for item in sources if str(item.get("source_type") or "") == "email"]
    return non_email, emails


def _chronology_source_ids(bundle: dict[str, Any]) -> set[str]:
    return {
        str(item.get("source_id") or "")
        for item in _dict_rows(bundle, "chronology_anchors")
        if _compact(item.get("source_id")) and _compact(item.get("date"))
    }


def _linked_source_ids(links: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for link in links:
        from_id, to_id = str(link.get("from_source_id") or ""), str(link.get("to_source_id") or "")
        if from_id and to_id:
            ids.update((from_id, to_id))
    return ids


def _complete_document_locator(source: dict[str, Any]) -> bool:
    locator = source.get("document_locator") or {}
    return bool(
        _compact(locator.get("evidence_handle"))
        and (locator.get("snippet_locator") or locator.get("text_locator") or _compact(locator.get("chunk_id")))
    )


def _mixed_source_metrics(context: MixedSourceHarvestContext) -> dict[str, int]:
    linked = sum(1 for source in context.non_email_sources if str(source.get("source_id") or "") in context.linked_ids)
    return {
        "non_email_source_count": len(context.non_email_sources),
        "source_class_diversity": len(
            {str(source.get("source_type") or "") for source in context.non_email_sources if str(source.get("source_type") or "")}
        ),
        "linked_non_email_source_count": linked,
        "unlinked_non_email_source_count": max(len(context.non_email_sources) - linked, 0),
        "document_locator_complete_count": context.locator_count,
        "chronology_anchor_complete_count": context.chronology_count,
    }


def _apply_mixed_source_gates(context: MixedSourceHarvestContext) -> None:
    coverage = dict(context.summary.get("coverage_gate") or {})
    quality = dict(context.summary.get("quality_gate") or {})
    coverage_reasons = [str(item) for item in coverage.get("reasons", []) if _compact(item)]
    recommendations = [str(item) for item in coverage.get("recommendations", []) if _compact(item)]
    quality_reasons = [str(item) for item in quality.get("reasons", []) if _compact(item)]
    manifest_primary = not bool((context.summary.get("source_basis") or {}).get("email_archive_available")) and bool(
        context.non_email_sources
    )
    coverage_reasons, recommendations, quality_reasons = _apply_manifest_primary_adjustments(
        context,
        quality,
        manifest_primary,
        coverage_reasons,
        recommendations,
        quality_reasons,
    )
    _append_mixed_source_reasons(context, coverage_reasons, recommendations, quality_reasons)
    _finalize_gate(coverage, coverage_reasons, recommendations, manifest_primary, bool(context.non_email_sources))
    _finalize_quality_gate(quality, quality_reasons, manifest_primary, bool(context.non_email_sources))
    context.summary["coverage_gate"], context.summary["quality_gate"] = coverage, quality


def _apply_manifest_primary_adjustments(
    context: MixedSourceHarvestContext,
    quality: dict[str, Any],
    manifest_primary: bool,
    coverage_reasons: list[str],
    recommendations: list[str],
    quality_reasons: list[str],
) -> tuple[list[str], list[str], list[str]]:
    if not manifest_primary:
        return coverage_reasons, recommendations, quality_reasons
    adjusted = _manifest_primary_reasons(coverage_reasons, recommendations, quality_reasons)
    if context.non_email_sources and context.chronology_count >= 3:
        quality.setdefault("score", 0.6)
    return adjusted


def _manifest_primary_reasons(
    coverage: list[str], recommendations: list[str], quality: list[str]
) -> tuple[list[str], list[str], list[str]]:
    ignored_reasons = {
        "unique_hits_below_threshold",
        "unique_threads_below_threshold",
        "unique_senders_below_threshold",
        "unique_months_below_threshold",
        "lane_coverage_below_threshold",
        "attachment_hits_below_threshold",
    }
    ignored_recommendations = {
        "Raise harvest breadth and widen actor-plus-issue query lanes.",
        "Expand the strongest hits with thread lookup and similar-message replay.",
        "Add actor-name variants and routing lanes across the archive.",
        "Widen the timeline window or add explicit dated event lanes.",
        "Add German orthographic fallback and lower-performing actor or issue lanes.",
        "Run attachment-first retrieval and search mixed-source records more aggressively.",
    }
    return (
        [item for item in coverage if item not in ignored_reasons],
        [item for item in recommendations if item not in ignored_recommendations],
        [item for item in quality if item != "empty_evidence_bank"],
    )


def _append_mixed_source_reasons(
    context: MixedSourceHarvestContext, coverage: list[str], recommendations: list[str], quality: list[str]
) -> None:
    linked_count = sum(1 for source in context.non_email_sources if str(source.get("source_id") or "") in context.linked_ids)
    if (
        context.non_email_sources
        and context.email_sources
        and context.diagnostics
        and linked_count < len(context.non_email_sources)
    ):
        coverage.append("document_linking_incomplete")
        recommendations.append("Strengthen conservative document-email linking for manifest-backed records.")
    if context.non_email_sources and context.chronology_count < min(len(context.non_email_sources), 3):
        coverage.append("chronology_anchor_coverage_incomplete")
        recommendations.append("Promote more document-backed dates into chronology anchors.")
    locator_floor = (
        max(3, min(len(context.non_email_sources), (len(context.non_email_sources) + 4) // 5)) if context.non_email_sources else 0
    )
    if context.non_email_sources and context.locator_count < locator_floor:
        quality.append("document_locator_coverage_incomplete")


def _finalize_gate(
    gate: dict[str, Any], reasons: list[str], recommendations: list[str], manifest_primary: bool, has_sources: bool
) -> None:
    if reasons:
        gate.update(
            status="needs_more_harvest",
            reasons=list(dict.fromkeys(reasons)),
            recommendations=list(dict.fromkeys(recommendations)),
        )
    elif manifest_primary and has_sources:
        gate.update(status="pass", reasons=[], recommendations=[])


def _finalize_quality_gate(gate: dict[str, Any], reasons: list[str], manifest_primary: bool, has_sources: bool) -> None:
    if reasons:
        gate.update(status="weak", reasons=list(dict.fromkeys(reasons)))
    elif manifest_primary and has_sources:
        gate.update(status="pass", reasons=[])


def _apply_document_actor_discovery(context: MixedSourceHarvestContext) -> None:
    from .case_analysis_harvest_quality import _infer_actor_role, _mixed_source_identity_rows, _seed_actor_keys

    seed_keys = _seed_actor_keys(context.params)
    actors: dict[str, dict[str, Any]] = {}
    for source in context.non_email_sources:
        for identity, _identity_source in _mixed_source_identity_rows(source):
            _record_document_actor(actors, seed_keys, source, identity, _infer_actor_role)
    discovery = dict(context.summary.get("actor_discovery") or {})
    values = sorted(actors.values(), key=lambda item: (-int(item.get("source_count") or 0), str(item.get("identity") or "")))[:8]
    discovery["document_only_actor_count"] = len(actors)
    discovery["top_document_only_actors"] = [
        {
            "identity": value["identity"],
            "role": value["role"],
            "source_count": int(value["source_count"]),
            "source_types": sorted(value["source_types"]),
        }
        for value in values
    ]
    context.summary["actor_discovery"] = discovery


def _record_document_actor(
    actors: dict[str, dict[str, Any]], seed_keys: set[str], source: dict[str, Any], identity: str, role_resolver: Any
) -> None:
    key = identity.casefold()
    if not key or key in seed_keys:
        return
    entry = actors.setdefault(
        key,
        {
            "identity": identity,
            "role": role_resolver(email=identity, name=identity, source=source.get("title") or ""),
            "source_count": 0,
            "source_types": set(),
        },
    )
    entry["source_count"] = int(entry.get("source_count") or 0) + 1
    entry["source_types"].add(str(source.get("source_type") or ""))
