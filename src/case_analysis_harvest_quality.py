# mypy: disable-error-code=name-defined
# pylint: disable=too-many-locals,too-many-statements


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split archive-harvest helpers (case_analysis_harvest_quality)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._utils import _compact
from .mcp_models import EmailCaseAnalysisInput

if TYPE_CHECKING:
    pass


def _seed_actor_keys(params: EmailCaseAnalysisInput) -> set[str]:
    """Extract normalized actor keys from case scope for actor discovery.

    Returns a set of casefolded, compacted strings from target_person,
    suspected_actors, and comparator_actors name/email/role_hint fields.
    """
    case_scope = params.case_scope
    keys: set[str] = set()
    for person in [case_scope.target_person, *case_scope.suspected_actors, *case_scope.comparator_actors]:
        for value in (getattr(person, "name", ""), getattr(person, "email", ""), getattr(person, "role_hint", "")):
            compact = _compact(value).casefold()
            if compact:
                keys.add(compact)
    return keys


def _infer_actor_role(*, email: str, name: str, source: str) -> str:
    """Infer an actor's role from email, name, and source text.

    Returns a role string based on keywords found in the combined haystack:
    - representation: personalrat, betriebsrat, sbv, schwerbehindertenvertret
    - hr: personal, hr, human resources
    - management: leitung, direktor, dekan, manager, vorgesetzt
    - comparator: vergleich, comparator, peer, kolleg
    - witness: zeug, witness, beobacht
    - operational_peer: default fallback
    """
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
    """Extract normalized keyword terms from values.

    Returns a list of unique, compacted, casefolded terms (min length 3) extracted
    from the input values. Splits on whitespace and common separators.
    """
    terms: list[str] = []
    for value in values:
        for token in str(value or "").replace("|", " ").replace("_", " ").split():
            compact = "".join(char for char in token.casefold() if char.isalnum() or char in {"@", ".", "-"})
            if len(compact) >= 3 and compact not in terms:
                terms.append(compact)
    return terms


def _text_overlap_score(*, haystack: Any, terms: list[str]) -> int:
    """Calculate how many terms from the list appear in the haystack.

    Returns the count of terms that are found in the normalized, casefolded haystack.
    """
    normalized = _compact(haystack).casefold()
    if not normalized or not terms:
        return 0
    return sum(1 for term in terms if term and term in normalized)


def _seed_relevance_terms(row: dict[str, Any]) -> list[str]:
    """Extract relevance terms from an evidence row for scoring.

    Returns up to 16 keyword terms extracted from matched_query_queries,
    matched_query_lanes, and subject fields.
    """
    return _keyword_terms(
        *(row.get("matched_query_queries") or []),
        *(row.get("matched_query_lanes") or []),
        row.get("subject"),
    )[:16]


def _actor_mentions(row: dict[str, Any]) -> list[dict[str, str]]:
    """Extract actor mentions from an evidence row.

    Returns a list of unique actor mention dictionaries with sender_email,
    sender_name, and source fields. Deduplicates by casefolded email/name key.
    Checks sender, recipients, speaker_attribution, and reply_context_emails.
    """
    from .case_analysis_harvest_quality_stages import actor_mentions_stage

    return actor_mentions_stage(row)


def _actor_discovery_summary(*, evidence_bank: list[dict[str, Any]], params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Summarize actors discovered in evidence bank beyond seed actors.

    Returns a summary with discovered_actor_count, roles breakdown, and
    top_discovered_actors sorted by hit count and email/name.
    """
    from .case_analysis_harvest_quality_stages import actor_discovery_stage

    return actor_discovery_stage(evidence_bank=evidence_bank, params=params)


def _harvest_quality_summary(
    *,
    evidence_bank: list[dict[str, Any]],
    metrics: dict[str, Any],
    actor_discovery: dict[str, Any],
) -> dict[str, Any]:
    from .case_analysis_harvest_quality_stages import harvest_quality_stage

    return harvest_quality_stage(evidence_bank=evidence_bank, metrics=metrics, actor_discovery=actor_discovery)


def _mixed_source_identity_rows(source: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract identity rows from a mixed source for actor discovery.

    Returns a list of (display_value, identity_source) tuples from various
    source fields including author, sender_name, sender_email, participants,
    recipients, to, cc, bcc.
    """
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
    from .case_analysis_harvest_quality_stages import augment_mixed_source_stage

    return augment_mixed_source_stage(
        summary=summary,
        multi_source_case_bundle=multi_source_case_bundle,
        params=params,
    )


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
