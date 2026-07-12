"""Helper functions for the matter evidence index."""
# pylint: disable=too-many-branches,too-many-locals,too-many-return-statements,redefined-outer-name

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ._utils import as_dict, as_list, compact
from .behavioral_taxonomy import (
    employment_issue_tag_entries,
    focus_to_issue_tag_ids,
    issue_track_to_tag_ids,
    normalize_issue_tag_ids,
    text_to_issue_tag_ids,
)
from .bilingual_workflows import detect_source_language, quoted_evidence_payload
from .matter_evidence_index_missing import (
    missing_exhibit_rows as _missing_exhibit_rows,
)
from .matter_evidence_index_missing import source_conflicts_by_source_id as _source_conflicts_by_source_id

_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_ADVERSE_ACTION_TEXT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("task withdrawal", ("task withdrawal", "aufgabenentzug", "td fixation")),
    ("project removal", ("project removal", "removed from project", "projekt entzogen")),
    ("mobile-work restriction", ("home office", "mobile work", "remote work denied")),
    ("participation exclusion", ("without sbv", "ohne sbv", "excluded from process", "not included")),
    ("attendance control", ("time system", "attendance control", "worktime control", "arbeitszeitkontrolle")),
)


def adverse_action_text_hint(source: dict[str, Any]) -> str:
    """Detect adverse action hints from source text content.

    Checks the source's title, snippet, searchable_text, and documentary support
    for keywords indicating specific adverse employment actions (e.g., task withdrawal,
    project removal, mobile-work restriction, participation exclusion, attendance control).

    Args:
        source: A dictionary containing source metadata and content.

    Returns:
        A label string for the detected adverse action type, or empty string if none detected.
    """
    text = " ".join(
        part
        for part in (
            str(source.get("title") or ""),
            str(source.get("snippet") or ""),
            str(source.get("searchable_text") or ""),
            str(as_dict(source.get("documentary_support")).get("text_preview") or ""),
        )
        if part
    ).lower()
    for label, keywords in _ADVERSE_ACTION_TEXT_HINTS:
        if any(keyword in text for keyword in keywords):
            return label
    return ""


def party_identity(value: Any, *, role: str, identity_source: str) -> dict[str, str]:
    """Extract party identity information from a value.

    Parses email addresses and names from the value, handling various formats
    including plain email, "Name <email>" format, and plain text.

    Args:
        value: The value containing identity information (email, name, etc.).
        role: The role of this party (e.g., "sender", "author", "to", "cc").
        identity_source: The source of the identity information (e.g., "email_metadata").

    Returns:
        A dictionary with keys: name, email, display, role, identity_source.
        Returns empty dict if value is empty or invalid.
    """
    text = compact(value)
    if not text:
        return {}
    match = _EMAIL_RE.search(text)
    email = match.group(1).lower() if match else ""
    name = text
    if email and "<" in text and ">" in text:
        name = compact(text.split("<", 1)[0].strip(' "'))
    elif email and text.lower() == email:
        name = ""
    display = compact(name or email or text)
    return {
        "name": name,
        "email": email,
        "display": display,
        "role": role,
        "identity_source": identity_source,
    }


@dataclass
class _IssueTags:
    lookup: dict[str, dict[str, Any]]
    values: list[dict[str, Any]] = field(default_factory=list)
    seen: set[tuple[str, str]] = field(default_factory=set)

    def append(self, tag_id: str, *, assignment_basis: str, evidence_status: str, reason: str) -> None:
        key = (tag_id, assignment_basis)
        if key in self.seen or tag_id not in self.lookup:
            return
        self.seen.add(key)
        tag_entry = self.lookup[tag_id]
        self.values.append(
            {
                "tag_id": tag_id,
                "label": str(tag_entry["label"]),
                "assignment_basis": assignment_basis,
                "evidence_status": evidence_status,
                "assignment_reason": reason,
            }
        )


def _weak_text_provenance(source: dict[str, Any]) -> bool:
    documentary_support = as_dict(source.get("documentary_support"))
    format_profile = as_dict(documentary_support.get("format_profile"))
    extraction_quality = as_dict(documentary_support.get("extraction_quality"))
    return bool(
        as_dict(source.get("weak_format_semantics"))
        or str(source.get("promotability_status") or "") in {"lead_only_manual_review", "reference_only_not_promotable"}
        or bool(format_profile.get("manual_review_required"))
        or bool(extraction_quality.get("manual_review_required"))
        or str(documentary_support.get("evidence_strength") or "") == "weak_reference"
    )


def _append_scope_issue_tags(tags: _IssueTags, scope: dict[str, Any]) -> None:
    for tag_id in normalize_issue_tag_ids([str(item) for item in as_list(scope.get("employment_issue_tags"))]):
        tags.append(
            tag_id,
            assignment_basis="operator_supplied",
            evidence_status="operator_supplied",
            reason="Operator supplied this issue tag in structured intake.",
        )
    context_text = str(scope.get("context_notes") or "")
    for issue_track in as_list(scope.get("employment_issue_tracks")):
        for tag_id in issue_track_to_tag_ids(str(issue_track), context_text=context_text):
            tags.append(
                tag_id,
                assignment_basis="bounded_inference",
                evidence_status="inferred",
                reason=f"Inferred from selected issue track {issue_track}.",
            )
    for tag_id in focus_to_issue_tag_ids([str(item) for item in as_list(scope.get("allegation_focus"))]):
        tags.append(
            tag_id,
            assignment_basis="bounded_inference",
            evidence_status="inferred",
            reason="Inferred from the selected allegation focus.",
        )


def _direct_issue_text(source: dict[str, Any]) -> str:
    occurrence_text = " ".join(
        str(item.get("occurrence_text") or item.get("entity_text") or "")
        for item in as_list(source.get("entity_occurrences"))
        if isinstance(item, dict)
    )
    return " ".join(
        part
        for part in (
            str(source.get("title") or ""),
            str(source.get("snippet") or ""),
            str(source.get("searchable_text") or ""),
            str(as_dict(source.get("documentary_support")).get("text_preview") or ""),
            occurrence_text,
        )
        if part
    )


def _append_direct_issue_tags(tags: _IssueTags, source: dict[str, Any]) -> None:
    weak_provenance = _weak_text_provenance(source)
    for tag_id in text_to_issue_tag_ids(_direct_issue_text(source)):
        tags.append(
            tag_id,
            assignment_basis="weak_recovered_text" if weak_provenance else "direct_document_content",
            evidence_status="review_required" if weak_provenance else "directly_supported",
            reason=(
                "Tag keywords are visible in recovered or weak-format text and need original-source review."
                if weak_provenance
                else "Tag keywords are directly visible in the current source text."
            ),
        )


def _append_occurrence_issue_tags(tags: _IssueTags, source: dict[str, Any]) -> None:
    for occurrence_value in as_list(source.get("entity_occurrences")):
        occurrence = as_dict(occurrence_value)
        occurrence_text = str(occurrence.get("occurrence_text") or occurrence.get("entity_text") or "").strip()
        if not occurrence_text:
            continue
        has_locator = any(_has_occurrence_locator(occurrence, field_name) for field_name in _OCCURRENCE_LOCATOR_FIELDS)
        _append_occurrence_text_tags(tags, occurrence, occurrence_text, has_locator=has_locator)


_OCCURRENCE_LOCATOR_FIELDS = ("segment_ordinal", "char_start", "char_end")


def _has_occurrence_locator(occurrence: dict[str, Any], field_name: str) -> bool:
    return occurrence.get(field_name) is not None and str(occurrence.get(field_name) or "").strip() != ""


def _append_occurrence_text_tags(
    tags: _IssueTags, occurrence: dict[str, Any], occurrence_text: str, *, has_locator: bool
) -> None:
    directly_supported = str(occurrence.get("source_scope") or "") == "authored_body"
    for tag_id in text_to_issue_tag_ids(occurrence_text):
        tags.append(
            tag_id,
            assignment_basis="entity_occurrence_locator" if has_locator else "entity_occurrence",
            evidence_status="directly_supported" if directly_supported else "review_required",
            reason=(
                "Issue tag inferred from occurrence-level entity text with persisted locator provenance."
                if has_locator
                else "Issue tag inferred from occurrence-level entity text."
            ),
        )


def issue_tags(case_bundle: dict[str, Any], source: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract and assign issue tags for a source based on case bundle, source content, and findings.

    Aggregates issue tags from multiple sources:
    - Operator-supplied employment_issue_tags from case bundle scope
    - Issue track to tag IDs mapping
    - Allegation focus to tag IDs mapping
    - Direct text content analysis (from title, snippet, searchable_text, etc.)
    - Entity occurrences in the source
    - Comparative treatment findings

    Tags are deduplicated and limited to 8 results.

    Args:
        case_bundle: The case bundle containing scope with issue tags and tracks.
        source: The source dictionary with content and metadata.
        findings: List of finding dictionaries for comparative treatment detection.

    Returns:
        A list of issue tag dictionaries, each containing tag_id, label,
        assignment_basis, evidence_status, and assignment_reason.
    """
    scope = as_dict(case_bundle.get("scope"))
    tags = _IssueTags({str(entry["tag_id"]): dict(entry) for entry in employment_issue_tag_entries()})
    _append_scope_issue_tags(tags, scope)
    _append_direct_issue_tags(tags, source)
    _append_occurrence_issue_tags(tags, source)
    if any(str(finding.get("finding_scope") or "") == "comparative_treatment" for finding in findings):
        tags.append(
            "comparator_evidence",
            assignment_basis="bounded_inference",
            evidence_status="inferred",
            reason="Current supporting findings include comparative-treatment evidence.",
        )

    return tags.values[:8]


def source_rows(multi_source_case_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract valid source dictionaries from a multi-source case bundle.

    Args:
        multi_source_case_bundle: A case bundle dictionary containing a sources list.

    Returns:
        A list of source dictionaries from the bundle, filtered to valid dict items.
    """
    return [source for source in as_list(multi_source_case_bundle.get("sources")) if isinstance(source, dict)]


def source_by_id(multi_source_case_bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Create a lookup dictionary of sources keyed by source_id.

    Args:
        multi_source_case_bundle: A case bundle dictionary containing a sources list.

    Returns:
        A dictionary mapping source_id strings to source dictionaries.
    """
    return {
        str(source.get("source_id") or ""): source
        for source in source_rows(multi_source_case_bundle)
        if str(source.get("source_id") or "")
    }


def linked_source_ids(source_id: str, source_links: list[dict[str, Any]]) -> list[str]:
    """Find all source IDs linked to a given source ID via source links.

    Args:
        source_id: The source ID to find links for.
        source_links: A list of source link dictionaries with from_source_id and to_source_id.

    Returns:
        A list of linked source ID strings (both from and to directions).
    """
    linked: list[str] = []
    for link in source_links:
        if not isinstance(link, dict):
            continue
        from_source_id = str(link.get("from_source_id") or "")
        to_source_id = str(link.get("to_source_id") or "")
        if from_source_id == source_id and to_source_id and to_source_id not in linked:
            linked.append(to_source_id)
        elif to_source_id == source_id and from_source_id and from_source_id not in linked:
            linked.append(from_source_id)
    return linked


def _support_keys_for_source(
    source: dict[str, Any],
    *,
    source_lookup: dict[str, dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> list[str]:
    """Extract all support keys for a source including linked sources.

    Collects source_id, uid, and evidence_handle from the source itself and
    all linked sources.

    Args:
        source: The source dictionary to extract keys from.
        source_lookup: A dictionary mapping source IDs to source dictionaries.
        source_links: A list of source link dictionaries.

    Returns:
        A list of unique support key strings.
    """
    observed: list[str] = []

    def _add(source_row: dict[str, Any]) -> None:
        if not isinstance(source_row, dict):
            return
        for value in (
            source_row.get("source_id"),
            source_row.get("uid"),
            as_dict(source_row.get("provenance")).get("evidence_handle"),
            as_dict(source_row.get("document_locator")).get("evidence_handle"),
        ):
            compact = str(value or "").strip()
            if compact and compact not in observed:
                observed.append(compact)

    _add(source)
    source_id = str(source.get("source_id") or "")
    for linked_id in linked_source_ids(source_id, source_links):
        linked_source = as_dict(source_lookup.get(linked_id))
        if linked_source:
            _add(linked_source)
        elif linked_id and linked_id not in observed:
            observed.append(linked_id)
    return observed


def findings_by_support_key(finding_evidence_index: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Index findings by their support keys for efficient lookup.

    Creates a mapping from various support key types (source_id, message_or_document_id,
    evidence_handle) to the findings that reference them.

    Args:
        finding_evidence_index: The finding evidence index dictionary containing findings.

    Returns:
        A dictionary mapping support key strings to lists of finding dictionaries.
    """
    by_key: dict[str, list[dict[str, Any]]] = {}
    for finding in as_list(finding_evidence_index.get("findings")):
        if not isinstance(finding, dict):
            continue
        for citation in as_list(finding.get("supporting_evidence")):
            if not isinstance(citation, dict):
                continue
            provenance = as_dict(citation.get("provenance"))
            keys = [
                str(citation.get("source_id") or ""),
                str(citation.get("message_or_document_id") or ""),
                str(citation.get("evidence_handle") or ""),
                str(provenance.get("evidence_handle") or ""),
            ]
            for key in keys:
                if not key:
                    continue
                by_key.setdefault(key, [])
                if finding not in by_key[key]:
                    by_key[key].append(finding)
    return by_key


def citation_ids_by_support_key(finding_evidence_index: dict[str, Any]) -> dict[str, list[str]]:
    """Index citation IDs by their support keys for efficient lookup.

    Creates a mapping from various support key types to the citation IDs that
    reference them.

    Args:
        finding_evidence_index: The finding evidence index dictionary containing findings.

    Returns:
        A dictionary mapping support key strings to lists of citation ID strings.
    """
    by_key: dict[str, list[str]] = {}
    for finding in as_list(finding_evidence_index.get("findings")):
        _index_finding_citation_ids(by_key, as_dict(finding))
    return by_key


def _index_finding_citation_ids(by_key: dict[str, list[str]], finding: dict[str, Any]) -> None:
    for citation_value in as_list(finding.get("supporting_evidence")):
        citation = as_dict(citation_value)
        citation_id = str(citation.get("citation_id") or "")
        if citation_id:
            _index_citation_id(by_key, citation, citation_id)


def _index_citation_id(by_key: dict[str, list[str]], citation: dict[str, Any], citation_id: str) -> None:
    provenance = as_dict(citation.get("provenance"))
    keys = (
        citation.get("source_id"),
        citation.get("message_or_document_id"),
        citation.get("evidence_handle"),
        provenance.get("evidence_handle"),
    )
    for value in keys:
        key = str(value or "")
        if key and citation_id not in by_key.setdefault(key, []):
            by_key[key].append(citation_id)


def findings_by_uid(finding_evidence_index: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Index findings by message_or_document_id (UID) for efficient lookup.

    Args:
        finding_evidence_index: The finding evidence index dictionary containing findings.

    Returns:
        A dictionary mapping UID strings to lists of finding dictionaries.
    """
    by_uid: dict[str, list[dict[str, Any]]] = {}
    for finding in as_list(finding_evidence_index.get("findings")):
        if not isinstance(finding, dict):
            continue
        for citation in as_list(finding.get("supporting_evidence")):
            if not isinstance(citation, dict):
                continue
            uid = str(citation.get("message_or_document_id") or "")
            if not uid:
                continue
            by_uid.setdefault(uid, [])
            if finding not in by_uid[uid]:
                by_uid[uid].append(finding)
    return by_uid


def citation_ids_for_uid(finding_evidence_index: dict[str, Any], uid: str) -> list[str]:
    """Get all citation IDs for a specific UID from the finding evidence index.

    Args:
        finding_evidence_index: The finding evidence index dictionary containing findings.
        uid: The message_or_document_id to look up.

    Returns:
        A list of citation ID strings that reference the given UID.
    """
    citation_ids: list[str] = []
    for finding in as_list(finding_evidence_index.get("findings")):
        if not isinstance(finding, dict):
            continue
        for citation in as_list(finding.get("supporting_evidence")):
            if not isinstance(citation, dict):
                continue
            if str(citation.get("message_or_document_id") or "") != uid:
                continue
            citation_id = str(citation.get("citation_id") or "")
            if citation_id and citation_id not in citation_ids:
                citation_ids.append(citation_id)
    return citation_ids


def findings_for_source(
    finding_evidence_index: dict[str, Any],
    source: dict[str, Any],
    *,
    source_lookup: dict[str, dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Get all findings that are supported by a given source.

    Uses support keys from the source (including linked sources) to look up
    findings in the finding evidence index.

    Args:
        finding_evidence_index: The finding evidence index dictionary.
        source: The source dictionary to find findings for.
        source_lookup: A dictionary mapping source IDs to source dictionaries.
        source_links: A list of source link dictionaries.

    Returns:
        A list of finding dictionaries that reference the source or its linked sources.
    """
    findings_map = findings_by_support_key(finding_evidence_index)
    findings: list[dict[str, Any]] = []
    for key in _support_keys_for_source(source, source_lookup=source_lookup, source_links=source_links):
        for finding in findings_map.get(key, []):
            if finding not in findings:
                findings.append(finding)
    return findings


def citation_ids_for_source(
    finding_evidence_index: dict[str, Any],
    source: dict[str, Any],
    *,
    source_lookup: dict[str, dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> list[str]:
    """Get all citation IDs that reference a given source.

    Uses support keys from the source (including linked sources) to look up
    citation IDs in the finding evidence index.

    Args:
        finding_evidence_index: The finding evidence index dictionary.
        source: The source dictionary to find citation IDs for.
        source_lookup: A dictionary mapping source IDs to source dictionaries.
        source_links: A list of source link dictionaries.

    Returns:
        A list of citation ID strings that reference the source or its linked sources.
    """
    citation_map = citation_ids_by_support_key(finding_evidence_index)
    citation_ids: list[str] = []
    for key in _support_keys_for_source(source, source_lookup=source_lookup, source_links=source_links):
        for citation_id in citation_map.get(key, []):
            if citation_id not in citation_ids:
                citation_ids.append(citation_id)
    return citation_ids


def finding_ids(findings: list[dict[str, Any]]) -> list[str]:
    """Extract finding IDs from a list of finding dictionaries.

    Args:
        findings: A list of finding dictionaries.

    Returns:
        A list of finding_id strings from the findings.
    """
    return [str(finding.get("finding_id") or "") for finding in findings if str(finding.get("finding_id") or "")]


def why_it_matters(source: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    """Generate a human-readable explanation of why a source matters to the case.

    Prioritizes finding labels if available, otherwise checks for adverse action
    hints, and falls back to source-type-specific explanations.

    Args:
        source: The source dictionary with metadata.
        findings: List of finding dictionaries that the source supports.

    Returns:
        A string explaining the source's significance.
    """
    labels = [
        str(finding.get("finding_label") or "").strip() for finding in findings if str(finding.get("finding_label") or "").strip()
    ]
    if labels:
        return "Supports current review areas: " + ", ".join(labels[:3]) + "."
    action_hint = adverse_action_text_hint(source)
    if action_hint:
        return f"May anchor adverse-action review for {action_hint} on the current record."
    source_type = str(source.get("source_type") or "")
    if source_type == "formal_document":
        return "Provides documentary support that can corroborate or contradict email-derived interpretations."
    if source_type == "meeting_note":
        return "Acts as a chronology anchor for meeting-related process events."
    if source_type == "chat_log":
        return "Adds mixed-source context that may corroborate or challenge the email-only narrative."
    if source_type == "attachment":
        return "Provides attachment-level corroboration or a documentary follow-up lead."
    return "Provides direct record material relevant to the synthetic matter review."


def reliability_label(source: dict[str, Any]) -> str:
    """Generate a reliability label string for a source.

    Combines reliability level and basis, with special handling for weak_reference
    evidence strength.

    Args:
        source: The source dictionary containing reliability and documentary support info.

    Returns:
        A string in format "level:basis" or "low:weak_reference" for weak evidence.
    """
    reliability = as_dict(source.get("source_reliability"))
    documentary_support = as_dict(source.get("documentary_support"))
    level = str(reliability.get("level") or "")
    basis = str(reliability.get("basis") or "")
    evidence_strength = str(documentary_support.get("evidence_strength") or "")
    if evidence_strength == "weak_reference":
        return f"{level or 'low'}:{basis or 'weak_reference'}"
    return f"{level or 'unknown'}:{basis or 'source'}"


def follow_up_needed(source: dict[str, Any], findings: list[dict[str, Any]]) -> list[str]:
    """Identify follow-up actions needed for a source.

    Aggregates follow-up items from multiple sources:
    - Documentary support review recommendations
    - Extraction quality visible limitations
    - Format profile manual review requirements
    - Source reliability caveats
    - Adverse action text hints
    - Missing finding links

    Results are deduplicated and limited to 3 items.

    Args:
        source: The source dictionary with documentary support and reliability info.
        findings: List of finding dictionaries that the source supports.

    Returns:
        A list of follow-up action strings.
    """
    follow_up: list[str] = []
    documentary_support = as_dict(source.get("documentary_support"))
    _append_document_followups(follow_up, documentary_support)
    _append_text_values(follow_up, as_dict(source.get("source_reliability")).get("caveats"))
    action_hint = adverse_action_text_hint(source)
    if action_hint:
        _append_unique(
            follow_up, f"Check whether this source should be linked as a dated adverse action candidate for {action_hint}."
        )
    if not findings:
        _append_unique(
            follow_up, "Check whether this source should be linked to a current finding, chronology event, or issue track."
        )
    return follow_up[:3]


def _append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _append_text_values(values: list[str], source_values: Any) -> None:
    for value in as_list(source_values):
        _append_unique(values, value)


def _append_document_followups(follow_up: list[str], documentary_support: dict[str, Any]) -> None:
    _append_unique(follow_up, documentary_support.get("review_recommendation"))
    extraction_quality = as_dict(documentary_support.get("extraction_quality"))
    _append_text_values(follow_up, extraction_quality.get("visible_limitations"))
    format_profile = as_dict(documentary_support.get("format_profile"))
    if bool(format_profile.get("manual_review_required")):
        label = str(format_profile.get("format_label") or "source file").strip()
        _append_unique(follow_up, f"Review the original {label} before relying on exact wording or layout-sensitive detail.")


@dataclass(frozen=True)
class _ReliabilityOutcome:
    strength: str
    readiness: str
    reason: str


def _weak_reliability_reason(source_type: str) -> str:
    if source_type in {"attachment", "formal_document"}:
        return (
            "This exhibit is currently a weak documentary reference because reliable extracted text is unavailable "
            "or the extraction path failed."
        )
    return "This exhibit currently relies on low-reliability source semantics and needs manual corroboration."


def _moderate_reliability_reason(source_type: str, *, text_available: bool) -> str:
    if source_type in {"attachment", "formal_document"} and text_available:
        return (
            "Usable text is available, but it depends on OCR or medium-reliability extraction and should be checked "
            "against the original file before serious reliance."
        )
    if source_type == "chat_log":
        return "This exhibit can corroborate context, but it remains operator supplied and less normalized than email evidence."
    if source_type == "meeting_note":
        return (
            "This exhibit supports chronology and process context, but it is metadata-derived "
            "rather than full authored narrative text."
        )
    return "This exhibit has usable text, but the current reliability basis still requires bounded source review."


def _strong_reliability_reason(source_type: str) -> str:
    return {
        "email": "Direct authored email-body text is available from the current record with high source reliability.",
        "formal_document": "Native extracted formal-document text is available and currently carries high source reliability.",
        "attachment": "Extracted attachment text is available directly and currently carries high source reliability.",
        "meeting_note": (
            "This exhibit has high-reliability meeting metadata that can support chronology and participation sequencing."
        ),
    }.get(source_type, "This exhibit currently carries high source reliability and usable direct record content.")


def _reliability_outcome(source: dict[str, Any], reliability: dict[str, Any], support: dict[str, Any]) -> _ReliabilityOutcome:
    level = str(reliability.get("level") or "")
    source_type = str(source.get("source_type") or "")
    extraction_state = str(support.get("extraction_state") or "")
    weak_states = {"ocr_failed", "ocr_failure", "binary_only", "image_embedding_only", "extraction_failed"}
    if _is_weak_reliability(level, extraction_state, support, weak_states):
        return _ReliabilityOutcome("weak", "manual_review_required", _weak_reliability_reason(source_type))
    if _is_moderate_reliability(level, extraction_state, support):
        text_available = bool(support.get("text_available")) or bool(source.get("snippet"))
        reason = _moderate_reliability_reason(source_type, text_available=text_available)
        return _ReliabilityOutcome("moderate", "usable_with_original_source_check", reason)
    if level == "high":
        return _ReliabilityOutcome("strong", "usable_now", _strong_reliability_reason(source_type))
    return _ReliabilityOutcome(
        "unknown",
        "manual_review_required",
        "The current source does not expose enough reliability detail for serious legal-support use yet.",
    )


def _is_weak_reliability(level: str, extraction_state: str, support: dict[str, Any], weak_states: set[str]) -> bool:
    return str(support.get("evidence_strength") or "") == "weak_reference" or level == "low" or extraction_state in weak_states


def _is_moderate_reliability(level: str, extraction_state: str, support: dict[str, Any]) -> bool:
    return bool(support.get("ocr_used")) or extraction_state == "ocr_text_extracted" or level == "medium"


def _is_blocking_step(step: str) -> bool:
    normalized = step.lower()
    return "manual" in normalized or "check against the original" in normalized or "must be reviewed directly" in normalized


def _blocking_points(recommended_steps: list[str], readiness: str) -> list[str]:
    blocking_points = [step for step in recommended_steps if _is_blocking_step(step)]
    if readiness == "usable_with_original_source_check" and not blocking_points:
        blocking_points.append("Check the original file or source context before relying on exact wording.")
    if readiness == "manual_review_required" and not blocking_points:
        blocking_points.append("Manual source review is required before serious legal-support use.")
    return blocking_points[:2]


def exhibit_reliability(source: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess the reliability of a source as an exhibit.

    Evaluates multiple factors to determine exhibit strength and readiness:
    - Evidence strength (weak_reference, OCR status, extraction state)
    - Reliability level (low, medium, high)
    - Source type (email, formal_document, attachment, meeting_note, chat_log)
    - Extraction state and text availability
    - Follow-up steps needed

    Args:
        source: The source dictionary with reliability and documentary support info.
        findings: List of finding dictionaries that the source supports.

    Returns:
        A dictionary containing:
        - strength: "weak", "moderate", "strong", or "unknown"
        - reason: Human-readable explanation of the reliability assessment
        - source_basis: The basis of the reliability assessment
        - next_step_logic: Dictionary with readiness, recommended_steps, and blocking_points
    """
    reliability = as_dict(source.get("source_reliability"))
    documentary_support = as_dict(source.get("documentary_support"))
    basis = str(reliability.get("basis") or "")
    recommended_steps = follow_up_needed(source, findings)
    outcome = _reliability_outcome(source, reliability, documentary_support)

    return {
        "strength": outcome.strength,
        "reason": outcome.reason,
        "source_basis": basis or "unknown",
        "next_step_logic": {
            "readiness": outcome.readiness,
            "recommended_steps": recommended_steps,
            "blocking_points": _blocking_points(recommended_steps, outcome.readiness),
        },
    }


def sender_identity(
    source: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]] | None = None,
    source_links: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Extract sender identity information from a source.

    Handles different source types (email, formal_document, chat_log, etc.) and
    falls back to linked sources or provenance information when direct extraction
    is not possible.

    Args:
        source: The source dictionary to extract sender identity from.
        source_lookup: Optional dictionary mapping source IDs to source dictionaries.
        source_links: Optional list of source link dictionaries for finding linked sources.

    Returns:
        A dictionary with keys: name, email, display, role, identity_source.
        Returns empty dict if no identity can be determined.
    """
    direct = _direct_sender_identity(source)
    if direct is not None:
        return direct
    actor_identity = _fallback_actor_identity(source, "actor_id", "actor_id_fallback")
    if actor_identity:
        return actor_identity
    if source_lookup is not None and source_links is not None:
        linked_identity = _linked_sender_identity(source, source_lookup, source_links)
        if linked_identity:
            return linked_identity
    return _fallback_actor_identity(as_dict(source.get("provenance")), "uid", "uid_fallback", fallback=source.get("uid"))


def _email_sender_identity(source: dict[str, Any], identity_source: str) -> dict[str, str]:
    identity = party_identity(
        compact(source.get("sender_name")) or compact(source.get("sender_email")),
        role="sender",
        identity_source=identity_source,
    )
    fallback_email = compact(source.get("sender_email"))
    if identity and not identity.get("email") and fallback_email:
        identity["email"] = fallback_email.lower()
        identity["display"] = compact(identity.get("name") or fallback_email)
    return identity


def _direct_sender_identity(source: dict[str, Any]) -> dict[str, str] | None:
    source_type = str(source.get("source_type") or "")
    if source_type == "email":
        return _email_sender_identity(source, "email_metadata")
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        identity = party_identity(source.get("author"), role="author", identity_source="document_metadata")
        return identity or None
    if source_type == "chat_log":
        participants = _string_values(source.get("participants"))
        return party_identity(participants[0], role="participant", identity_source="chat_participants") if participants else {}
    return None


def _fallback_actor_identity(source: dict[str, Any], key: str, identity_source: str, *, fallback: Any = None) -> dict[str, str]:
    display = compact(source.get(key) or fallback)
    if not display:
        return {}
    return {
        "name": "",
        "email": "",
        "display": display,
        "role": "author_or_related_actor",
        "identity_source": identity_source,
    }


def _linked_sender_identity(
    source: dict[str, Any], source_lookup: dict[str, dict[str, Any]], source_links: list[dict[str, Any]]
) -> dict[str, str]:
    source_id = str(source.get("source_id") or "")
    for linked_id in linked_source_ids(source_id, source_links):
        linked_source = as_dict(source_lookup.get(linked_id))
        if str(linked_source.get("source_type") or "") == "email":
            identity = _email_sender_identity(linked_source, "linked_email_metadata")
            if identity:
                return identity
    return {}


def sender_or_author(
    source: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]] | None = None,
    source_links: list[dict[str, Any]] | None = None,
) -> str:
    """Get a display string for the sender or author of a source.

    Extracts the display name from sender_identity, or falls back to actor_id
    or provenance UID.

    Args:
        source: The source dictionary to extract sender/author from.
        source_lookup: Optional dictionary mapping source IDs to source dictionaries.
        source_links: Optional list of source link dictionaries.

    Returns:
        A string representing the sender or author, or "unknown" if not determined.
    """
    identity = sender_identity(source, source_lookup=source_lookup, source_links=source_links)
    if identity:
        return str(identity.get("display") or "")
    actor_id = str(source.get("actor_id") or "").strip()
    if actor_id:
        return actor_id
    provenance = as_dict(source.get("provenance"))
    related_uid = str(provenance.get("uid") or source.get("uid") or "").strip()
    return related_uid or "unknown"


def recipient_identities(
    source: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]] | None = None,
    source_links: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Extract recipient identity information from a source.

    Handles different source types (email, formal_document, chat_log, etc.) and
    falls back to linked sources when direct extraction is not possible.

    Args:
        source: The source dictionary to extract recipient identities from.
        source_lookup: Optional dictionary mapping source IDs to source dictionaries.
        source_links: Optional list of source link dictionaries for finding linked sources.

    Returns:
        A dictionary with keys "to", "cc", "bcc" (and "participants" for chat_log)
        mapping to lists of identity dictionaries. Returns empty lists if no
        recipients can be determined.
    """
    direct = _direct_recipient_identities(source)
    if direct:
        return direct
    if source_lookup is not None and source_links is not None:
        linked = _linked_recipient_identities(source, source_lookup, source_links)
        if linked:
            return linked
    return {"to": [], "cc": [], "bcc": []}


def _party_identities(values: Any, *, role: str, identity_source: str) -> list[dict[str, str]]:
    identities: list[dict[str, str]] = []
    for value in as_list(values):
        identity = party_identity(value, role=role, identity_source=identity_source)
        if identity:
            identities.append(identity)
    return identities


def _email_recipient_identities(source: dict[str, Any], identity_source: str) -> dict[str, list[dict[str, str]]]:
    return {
        "to": _party_identities(source.get("to"), role="to", identity_source=identity_source),
        "cc": _party_identities(source.get("cc"), role="cc", identity_source=identity_source),
        "bcc": _party_identities(source.get("bcc"), role="bcc", identity_source=identity_source),
    }


def _direct_recipient_identities(source: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    source_type = str(source.get("source_type") or "")
    if source_type == "email":
        return _email_recipient_identities(source, "email_metadata")
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        identities = {
            "to": _party_identities(source.get("recipients"), role="to", identity_source="document_metadata"),
            "cc": _party_identities(source.get("cc_recipients"), role="cc", identity_source="document_metadata"),
            "bcc": _party_identities(source.get("bcc_recipients"), role="bcc", identity_source="document_metadata"),
        }
        return identities if any(identities.values()) else {}
    if source_type == "chat_log":
        participants = _party_identities(source.get("participants"), role="participant", identity_source="chat_participants")
        return {"participants": participants} if participants else {}
    return {}


def _linked_recipient_identities(
    source: dict[str, Any], source_lookup: dict[str, dict[str, Any]], source_links: list[dict[str, Any]]
) -> dict[str, list[dict[str, str]]]:
    source_id = str(source.get("source_id") or "")
    for linked_id in linked_source_ids(source_id, source_links):
        linked_source = as_dict(source_lookup.get(linked_id))
        if str(linked_source.get("source_type") or "") == "email":
            identities = _email_recipient_identities(linked_source, "linked_email_metadata")
            if any(identities.values()):
                return identities
    return {}


def recipients(source: dict[str, Any], source_lookup: dict[str, dict[str, Any]], source_links: list[dict[str, Any]]) -> list[str]:
    """Get a list of recipient display strings for a source.

    Extracts display names from recipient_identities, with special handling for
    chat_log sources and linked sources.

    Args:
        source: The source dictionary to extract recipients from.
        source_lookup: A dictionary mapping source IDs to source dictionaries.
        source_links: A list of source link dictionaries.

    Returns:
        A list of recipient display strings, limited to 6 items.
    """
    identities = recipient_identities(source, source_lookup=source_lookup, source_links=source_links)
    values = _recipient_display_values(identities)
    if values:
        return values[:6]
    if str(source.get("source_type") or "") == "chat_log":
        return _string_values(source.get("participants"))
    source_id = str(source.get("source_id") or "")
    linked_ids = _forward_linked_ids(source_id, source_links)
    return _linked_source_titles(linked_ids, source_lookup)[:2]


def _string_values(values: Any) -> list[str]:
    return [text for value in as_list(values) if (text := str(value).strip())]


def _recipient_display_values(identities: dict[str, list[dict[str, str]]]) -> list[str]:
    values: list[str] = []
    for group in identities.values():
        for identity in group:
            display = str(identity.get("display") or "").strip()
            if display:
                values.append(display)
    return values


def _forward_linked_ids(source_id: str, source_links: list[dict[str, Any]]) -> list[str]:
    return [
        str(link.get("to_source_id") or "")
        for link in source_links
        if isinstance(link, dict) and str(link.get("from_source_id") or "") == source_id
    ]


def _linked_source_titles(linked_ids: list[str], source_lookup: dict[str, dict[str, Any]]) -> list[str]:
    return [
        title
        for linked_id in linked_ids
        if linked_id in source_lookup
        if (title := str(source_lookup[linked_id].get("title") or ""))
    ]


def short_description(source: dict[str, Any]) -> str:
    """Generate a short description for a source.

    Combines title and snippet, truncating to 140 characters.

    Args:
        source: The source dictionary with title and/or snippet.

    Returns:
        A short description string (title: snippet prefix or just title/snippet).
    """
    title = str(source.get("title") or "").strip()
    snippet = " ".join(str(source.get("snippet") or "").split())
    if title and snippet:
        return f"{title}: {snippet[:140]}".strip()
    return title or snippet[:140]


def source_language(source: dict[str, Any]) -> str:
    """Detect the language of a source.

    Uses the bilingual workflows detect_source_language function to analyze
    multiple text fields from the source.

    Args:
        source: The source dictionary with various text fields.

    Returns:
        A string representing the detected language, or "unknown" if not determined.
    """
    documentary_support = as_dict(source.get("documentary_support"))
    return detect_source_language(
        source.get("language_hint_text"),
        source.get("text"),
        source.get("title"),
        source.get("snippet"),
        documentary_support.get("text_preview"),
    )


def top_exhibit_payload(row: dict[str, Any], *, source: dict[str, Any], rank: int, priority_score: int) -> dict[str, Any]:
    """Create a top exhibit payload dictionary from a row and source.

    Extracts and formats exhibit information for display, including reliability
    assessment, priority scoring, and supporting evidence references.

    Args:
        row: The exhibit row dictionary containing exhibit metadata.
        source: The source dictionary for additional metadata.
        rank: The rank of this exhibit in the prioritized list.
        priority_score: The computed priority score for this exhibit.

    Returns:
        A dictionary containing formatted exhibit information for display.
    """
    reliability = as_dict(row.get("exhibit_reliability"))
    next_step_logic = as_dict(reliability.get("next_step_logic"))
    return {
        "rank": rank,
        "exhibit_id": _text_value(row, "exhibit_id"),
        "source_id": _text_value(row, "source_id"),
        "source_type": _text_value(row, "source_type"),
        "priority_score": priority_score,
        "strength": _text_value(reliability, "strength"),
        "readiness": _text_value(next_step_logic, "readiness"),
        "short_description": _text_value(row, "short_description"),
        "why_prioritized": _first_text(row.get("why_it_matters"), reliability.get("reason")),
        "source_language": _text_value(row, "source_language", default="unknown"),
        "quoted_evidence": as_dict(row.get("quoted_evidence")),
        "document_locator": as_dict(row.get("document_locator")),
        "main_issue_tags": _string_values(row.get("main_issue_tags")),
        "supporting_finding_ids": _string_values(row.get("supporting_finding_ids")),
        "supporting_citation_ids": _string_values(row.get("supporting_citation_ids")),
        "supporting_source_ids": _string_values(row.get("supporting_source_ids")),
        "supporting_evidence_handles": _string_values(row.get("supporting_evidence_handles")),
        "source_conflict_status": _text_value(row, "source_conflict_status"),
        "candidate_related_source_ids": _string_values(row.get("candidate_related_source_ids")),
        "source_date": _first_text(source.get("date"), row.get("date")),
    }


def _text_value(values: dict[str, Any], key: str, *, default: str = "") -> str:
    value = values.get(key)
    return str(value) if value else default


def _first_text(*values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def exhibit_priority_score(row: dict[str, Any], source: dict[str, Any]) -> int:
    """Calculate a priority score for an exhibit row.

    Computes a weighted score based on multiple factors:
    - Reliability strength (strong=40, moderate=24, weak=8, unknown=4)
    - Readiness level (usable_now=8, usable_with_original_source_check=4, manual_review_required=0)
    - Issue tag count (up to 18 points)
    - Direct tag count (up to 12 points)
    - Finding count (up to 10 points)
    - Citation count (up to 12 points)
    - Chronology bonus (6-10 points for dated sources)
    - Contradiction bonus (8 points if source can corroborate or contradict)
    - Quote bonus (4-8 points for quoted text)
    - Locator bonus (4 points for evidence handle)
    - Weak text penalty (-6 to -10 for weak text provenance)

    Args:
        row: The exhibit row dictionary containing exhibit metadata.
        source: The source dictionary for additional metadata.

    Returns:
        An integer priority score.
    """
    reliability = as_dict(row.get("exhibit_reliability"))
    next_step_logic = as_dict(reliability.get("next_step_logic"))
    strength = str(reliability.get("strength") or "")
    readiness = str(next_step_logic.get("readiness") or "")
    issue_tags = [tag for tag in as_list(row.get("issue_tags")) if isinstance(tag, dict)]
    direct_tag_count = _direct_tag_count(issue_tags)
    issue_tag_count = len(_string_values(row.get("main_issue_tags")))
    finding_count = len(_string_values(row.get("supporting_finding_ids")))
    citation_count = len(_string_values(row.get("supporting_citation_ids")))
    source_type = str(row.get("source_type") or source.get("source_type") or "")
    quoted_evidence = as_dict(row.get("quoted_evidence"))
    quoted_text = compact(
        quoted_evidence.get("original_text") or quoted_evidence.get("translated_text") or quoted_evidence.get("summary")
    )
    document_locator = as_dict(row.get("document_locator"))
    chronology_bonus = _chronology_bonus(row, source_type)
    contradiction_bonus = 8 * bool(as_dict(source.get("source_weighting")).get("can_corroborate_or_contradict"))
    readiness_bonus = {"usable_now": 8, "usable_with_original_source_check": 4, "manual_review_required": 0}.get(readiness, 0)
    strength_score = {"strong": 40, "moderate": 24, "weak": 8, "unknown": 4}.get(strength, 0)
    quote_bonus = _quote_bonus(quoted_text)
    locator_bonus = 4 * bool(str(document_locator.get("evidence_handle") or ""))
    weak_text_penalty = _weak_text_penalty(row, issue_tags)
    return (
        strength_score
        + readiness_bonus
        + min(issue_tag_count * 6, 18)
        + min(direct_tag_count * 6, 12)
        + min(finding_count * 5, 10)
        + min(citation_count * 4, 12)
        + chronology_bonus
        + contradiction_bonus
        + quote_bonus
        + locator_bonus
        - weak_text_penalty
    )


def _direct_tag_count(issue_tags: list[dict[str, Any]]) -> int:
    return sum(str(tag.get("assignment_basis") or "") == "direct_document_content" for tag in issue_tags)


def _chronology_bonus(row: dict[str, Any], source_type: str) -> int:
    dated_bonus = 6 * bool(str(row.get("date") or "").strip())
    documentary_bonus = 4 * (
        source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}
    )
    return dated_bonus + documentary_bonus


def _quote_bonus(quoted_text: str) -> int:
    if len(quoted_text) >= 40:
        return 8
    return 4 if quoted_text else 0


def _weak_text_penalty(row: dict[str, Any], issue_tags: list[dict[str, Any]]) -> int:
    penalty = 10 * (str(row.get("promotability_status") or "") in {"lead_only_manual_review", "reference_only_not_promotable"})
    weak_tag = any(str(tag.get("assignment_basis") or "") == "weak_recovered_text" for tag in issue_tags)
    return penalty + 6 * weak_tag


def make_quoted_evidence(row: dict[str, Any], *, source_language: str) -> dict[str, Any]:
    """Create a quoted evidence payload from a row.

    Uses the bilingual workflows quoted_evidence_payload function to create
    a structured quoted evidence dictionary with translation support.

    Args:
        row: The source row dictionary containing snippet and locator info.
        source_language: The detected language of the source.

    Returns:
        A quoted evidence dictionary with original text, translations, and metadata.
    """
    return quoted_evidence_payload(
        original_text=row.get("snippet"),
        source_language=source_language,
        document_locator=as_dict(row.get("document_locator")),
        evidence_handle=str(as_dict(row.get("provenance")).get("evidence_handle") or row.get("source_id") or ""),
        translated_summary_fields=["why_it_matters", "short_description"],
    )


def source_conflicts_by_source_id(master_chronology: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract source conflicts from master chronology grouped by source ID.

    This is a convenience wrapper around the internal _source_conflicts_by_source_id
    function that uses the local as_dict and as_list helpers.

    Args:
        master_chronology: The master chronology dictionary containing summary data.

    Returns:
        A dictionary mapping source IDs to lists of conflict dictionaries.
    """
    return _source_conflicts_by_source_id(master_chronology, as_dict=as_dict, as_list=as_list)


def missing_exhibit_rows(
    *, case_bundle: dict[str, Any], rows: list[dict[str, Any]], master_chronology: dict[str, Any], as_dict: Any, as_list: Any
) -> list[dict[str, Any]]:
    """Identify missing exhibit rows based on issue track checklists and current coverage.

    This is a convenience wrapper around the internal _missing_exhibit_rows function
    that uses the local as_dict and as_list helpers.

    Args:
        case_bundle: The case bundle dictionary containing scope information.
        rows: List of current evidence rows for coverage analysis.
        master_chronology: The master chronology dictionary for gap analysis.
        as_dict: Callable to safely convert values to dictionaries.
        as_list: Callable to safely convert values to lists.

    Returns:
        A list of prioritized missing exhibit row dictionaries.
    """
    return _missing_exhibit_rows(
        case_bundle=case_bundle,
        rows=rows,
        master_chronology=master_chronology,
        as_dict=as_dict,
        as_list=as_list,
    )
