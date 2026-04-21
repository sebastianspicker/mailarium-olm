"""Helper functions for the matter evidence index."""

from __future__ import annotations

import re
from typing import Any

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


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def adverse_action_text_hint(source: dict[str, Any]) -> str:
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


def compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def party_identity(value: Any, *, role: str, identity_source: str) -> dict[str, str]:
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


def issue_tags(case_bundle: dict[str, Any], source: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scope = as_dict(case_bundle.get("scope"))
    tag_lookup: dict[str, dict[str, Any]] = {str(entry["tag_id"]): dict(entry) for entry in employment_issue_tag_entries()}
    tags: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    documentary_support = as_dict(source.get("documentary_support"))
    format_profile = as_dict(documentary_support.get("format_profile"))
    extraction_quality = as_dict(documentary_support.get("extraction_quality"))
    weak_text_provenance = bool(
        as_dict(source.get("weak_format_semantics"))
        or str(source.get("promotability_status") or "") in {"lead_only_manual_review", "reference_only_not_promotable"}
        or bool(format_profile.get("manual_review_required"))
        or bool(extraction_quality.get("manual_review_required"))
        or str(documentary_support.get("evidence_strength") or "") == "weak_reference"
    )

    def append(tag_id: str, *, assignment_basis: str, evidence_status: str, reason: str) -> None:
        key = (tag_id, assignment_basis)
        if key in seen or tag_id not in tag_lookup:
            return
        seen.add(key)
        tag_entry = tag_lookup[tag_id]
        tags.append(
            {
                "tag_id": tag_id,
                "label": str(tag_entry["label"]),
                "assignment_basis": assignment_basis,
                "evidence_status": evidence_status,
                "assignment_reason": reason,
            }
        )

    for tag_id in normalize_issue_tag_ids([str(item) for item in as_list(scope.get("employment_issue_tags"))]):
        append(
            tag_id,
            assignment_basis="operator_supplied",
            evidence_status="operator_supplied",
            reason="Operator supplied this issue tag in structured intake.",
        )

    context_text = str(scope.get("context_notes") or "")
    for issue_track in as_list(scope.get("employment_issue_tracks")):
        for tag_id in issue_track_to_tag_ids(str(issue_track), context_text=context_text):
            append(
                tag_id,
                assignment_basis="bounded_inference",
                evidence_status="inferred",
                reason=f"Inferred from selected issue track {issue_track}.",
            )

    for tag_id in focus_to_issue_tag_ids([str(item) for item in as_list(scope.get("allegation_focus"))]):
        append(
            tag_id,
            assignment_basis="bounded_inference",
            evidence_status="inferred",
            reason="Inferred from the selected allegation focus.",
        )

    direct_text = " ".join(
        part
        for part in (
            str(source.get("title") or ""),
            str(source.get("snippet") or ""),
            str(source.get("searchable_text") or ""),
            str(as_dict(source.get("documentary_support")).get("text_preview") or ""),
            " ".join(
                str(item.get("occurrence_text") or item.get("entity_text") or "")
                for item in as_list(source.get("entity_occurrences"))
                if isinstance(item, dict)
            ),
        )
        if part
    )
    for tag_id in text_to_issue_tag_ids(direct_text):
        append(
            tag_id,
            assignment_basis="weak_recovered_text" if weak_text_provenance else "direct_document_content",
            evidence_status="review_required" if weak_text_provenance else "directly_supported",
            reason=(
                "Tag keywords are visible in recovered or weak-format text and need original-source review."
                if weak_text_provenance
                else "Tag keywords are directly visible in the current source text."
            ),
        )

    for occurrence in as_list(source.get("entity_occurrences")):
        if not isinstance(occurrence, dict):
            continue
        occurrence_text = str(occurrence.get("occurrence_text") or occurrence.get("entity_text") or "").strip()
        if not occurrence_text:
            continue
        occurrence_scope = str(occurrence.get("source_scope") or "")
        has_locator = any(
            occurrence.get(field) is not None and str(occurrence.get(field) or "").strip() != ""
            for field in ("segment_ordinal", "char_start", "char_end")
        )
        for tag_id in text_to_issue_tag_ids(occurrence_text):
            append(
                tag_id,
                assignment_basis=("entity_occurrence_locator" if has_locator else "entity_occurrence"),
                evidence_status=("directly_supported" if occurrence_scope == "authored_body" else "review_required"),
                reason=(
                    "Issue tag inferred from occurrence-level entity text with persisted locator provenance."
                    if has_locator
                    else "Issue tag inferred from occurrence-level entity text."
                ),
            )

    if any(str(finding.get("finding_scope") or "") == "comparative_treatment" for finding in findings):
        append(
            "comparator_evidence",
            assignment_basis="bounded_inference",
            evidence_status="inferred",
            reason="Current supporting findings include comparative-treatment evidence.",
        )

    return tags[:8]


def source_rows(multi_source_case_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [source for source in as_list(multi_source_case_bundle.get("sources")) if isinstance(source, dict)]


def source_by_id(multi_source_case_bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(source.get("source_id") or ""): source
        for source in source_rows(multi_source_case_bundle)
        if str(source.get("source_id") or "")
    }


def linked_source_ids(source_id: str, source_links: list[dict[str, Any]]) -> list[str]:
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
    by_key: dict[str, list[str]] = {}
    for finding in as_list(finding_evidence_index.get("findings")):
        if not isinstance(finding, dict):
            continue
        for citation in as_list(finding.get("supporting_evidence")):
            if not isinstance(citation, dict):
                continue
            citation_id = str(citation.get("citation_id") or "")
            if not citation_id:
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
                if citation_id not in by_key[key]:
                    by_key[key].append(citation_id)
    return by_key


def findings_by_uid(finding_evidence_index: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
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
    citation_map = citation_ids_by_support_key(finding_evidence_index)
    citation_ids: list[str] = []
    for key in _support_keys_for_source(source, source_lookup=source_lookup, source_links=source_links):
        for citation_id in citation_map.get(key, []):
            if citation_id not in citation_ids:
                citation_ids.append(citation_id)
    return citation_ids


def finding_ids(findings: list[dict[str, Any]]) -> list[str]:
    return [str(finding.get("finding_id") or "") for finding in findings if str(finding.get("finding_id") or "")]


def why_it_matters(source: dict[str, Any], findings: list[dict[str, Any]]) -> str:
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
    reliability = as_dict(source.get("source_reliability"))
    documentary_support = as_dict(source.get("documentary_support"))
    level = str(reliability.get("level") or "")
    basis = str(reliability.get("basis") or "")
    evidence_strength = str(documentary_support.get("evidence_strength") or "")
    if evidence_strength == "weak_reference":
        return f"{level or 'low'}:{basis or 'weak_reference'}"
    return f"{level or 'unknown'}:{basis or 'source'}"


def follow_up_needed(source: dict[str, Any], findings: list[dict[str, Any]]) -> list[str]:
    follow_up: list[str] = []
    documentary_support = as_dict(source.get("documentary_support"))
    extraction_quality = as_dict(documentary_support.get("extraction_quality"))
    format_profile = as_dict(documentary_support.get("format_profile"))
    review_recommendation = str(documentary_support.get("review_recommendation") or "").strip()
    if review_recommendation:
        follow_up.append(review_recommendation)
    for limitation in as_list(extraction_quality.get("visible_limitations")):
        text = str(limitation).strip()
        if text and text not in follow_up:
            follow_up.append(text)
    if bool(format_profile.get("manual_review_required")):
        label = str(format_profile.get("format_label") or "source file").strip()
        manual_step = f"Review the original {label} before relying on exact wording or layout-sensitive detail."
        if manual_step not in follow_up:
            follow_up.append(manual_step)
    for caveat in as_list(as_dict(source.get("source_reliability")).get("caveats")):
        text = str(caveat).strip()
        if text and text not in follow_up:
            follow_up.append(text)
    action_hint = adverse_action_text_hint(source)
    if action_hint:
        follow_up.append(f"Check whether this source should be linked as a dated adverse action candidate for {action_hint}.")
    if not findings:
        follow_up.append("Check whether this source should be linked to a current finding, chronology event, or issue track.")
    return follow_up[:3]


def exhibit_reliability(source: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    reliability = as_dict(source.get("source_reliability"))
    documentary_support = as_dict(source.get("documentary_support"))
    level = str(reliability.get("level") or "")
    basis = str(reliability.get("basis") or "")
    source_type = str(source.get("source_type") or "")
    extraction_state = str(documentary_support.get("extraction_state") or "")
    evidence_strength = str(documentary_support.get("evidence_strength") or "")
    ocr_used = bool(documentary_support.get("ocr_used"))
    text_available = bool(documentary_support.get("text_available")) or bool(source.get("snippet"))
    recommended_steps = follow_up_needed(source, findings)

    strength = "unknown"
    readiness = "manual_review_required"
    reason = "The current source does not expose enough reliability detail for serious legal-support use yet."
    if (
        evidence_strength == "weak_reference"
        or level == "low"
        or extraction_state in {"ocr_failed", "ocr_failure", "binary_only", "image_embedding_only", "extraction_failed"}
    ):
        strength = "weak"
        if source_type in {"attachment", "formal_document"}:
            reason = (
                "This exhibit is currently a weak documentary reference because reliable extracted text is unavailable "
                "or the extraction path failed."
            )
        else:
            reason = "This exhibit currently relies on low-reliability source semantics and needs manual corroboration."
    elif ocr_used or extraction_state == "ocr_text_extracted" or level == "medium":
        strength = "moderate"
        readiness = "usable_with_original_source_check"
        if source_type in {"attachment", "formal_document"} and text_available:
            reason = (
                "Usable text is available, but it depends on OCR or medium-reliability extraction and should be checked "
                "against the original file before serious reliance."
            )
        elif source_type == "chat_log":
            reason = (
                "This exhibit can corroborate context, but it remains operator supplied and less normalized than email evidence."
            )
        elif source_type == "meeting_note":
            reason = (
                "This exhibit supports chronology and process context, but it is "
                "metadata-derived rather than full authored narrative text."
            )
        else:
            reason = "This exhibit has usable text, but the current reliability basis still requires bounded source review."
    elif level == "high":
        strength = "strong"
        readiness = "usable_now"
        if source_type == "email":
            reason = "Direct authored email-body text is available from the current record with high source reliability."
        elif source_type == "formal_document":
            reason = "Native extracted formal-document text is available and currently carries high source reliability."
        elif source_type == "attachment":
            reason = "Extracted attachment text is available directly and currently carries high source reliability."
        elif source_type == "meeting_note":
            reason = (
                "This exhibit has high-reliability meeting metadata that can support chronology and participation sequencing."
            )
        else:
            reason = "This exhibit currently carries high source reliability and usable direct record content."

    blocking_points = [
        step
        for step in recommended_steps
        if "manual" in step.lower() or "check against the original" in step.lower() or "must be reviewed directly" in step.lower()
    ]
    if readiness == "usable_with_original_source_check" and not blocking_points:
        blocking_points.append("Check the original file or source context before relying on exact wording.")
    if readiness == "manual_review_required" and not blocking_points:
        blocking_points.append("Manual source review is required before serious legal-support use.")

    return {
        "strength": strength,
        "reason": reason,
        "source_basis": basis or "unknown",
        "next_step_logic": {
            "readiness": readiness,
            "recommended_steps": recommended_steps,
            "blocking_points": blocking_points[:2],
        },
    }


def sender_identity(
    source: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]] | None = None,
    source_links: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    source_type = str(source.get("source_type") or "")
    if source_type == "email":
        identity = party_identity(
            compact(source.get("sender_name")) or compact(source.get("sender_email")),
            role="sender",
            identity_source="email_metadata",
        )
        if identity and not identity.get("email"):
            fallback_email = compact(source.get("sender_email"))
            if fallback_email:
                identity["email"] = fallback_email.lower()
                identity["display"] = compact(identity.get("name") or fallback_email)
        return identity
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        identity = party_identity(source.get("author"), role="author", identity_source="document_metadata")
        if identity:
            return identity
    if source_type == "chat_log":
        participants = [str(item) for item in as_list(source.get("participants")) if compact(item)]
        return party_identity(participants[0], role="participant", identity_source="chat_participants") if participants else {}
    actor_id = compact(source.get("actor_id"))
    if actor_id:
        return {
            "name": "",
            "email": "",
            "display": actor_id,
            "role": "author_or_related_actor",
            "identity_source": "actor_id_fallback",
        }
    if source_lookup is not None and source_links is not None:
        source_id = str(source.get("source_id") or "")
        for linked_id in linked_source_ids(source_id, source_links):
            linked_source = as_dict(source_lookup.get(linked_id))
            if str(linked_source.get("source_type") or "") != "email":
                continue
            identity = party_identity(
                compact(linked_source.get("sender_name")) or compact(linked_source.get("sender_email")),
                role="sender",
                identity_source="linked_email_metadata",
            )
            if identity and not identity.get("email"):
                fallback_email = compact(linked_source.get("sender_email"))
                if fallback_email:
                    identity["email"] = fallback_email.lower()
                    identity["display"] = compact(identity.get("name") or fallback_email)
            if identity:
                return identity
    provenance = as_dict(source.get("provenance"))
    related_uid = compact(provenance.get("uid") or source.get("uid"))
    if related_uid:
        return {
            "name": "",
            "email": "",
            "display": related_uid,
            "role": "author_or_related_actor",
            "identity_source": "uid_fallback",
        }
    return {}


def sender_or_author(
    source: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]] | None = None,
    source_links: list[dict[str, Any]] | None = None,
) -> str:
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
    source_type = str(source.get("source_type") or "")
    if source_type == "email":
        return {
            "to": [
                identity
                for value in as_list(source.get("to"))
                if (identity := party_identity(value, role="to", identity_source="email_metadata"))
            ],
            "cc": [
                identity
                for value in as_list(source.get("cc"))
                if (identity := party_identity(value, role="cc", identity_source="email_metadata"))
            ],
            "bcc": [
                identity
                for value in as_list(source.get("bcc"))
                if (identity := party_identity(value, role="bcc", identity_source="email_metadata"))
            ],
        }
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        identities = {
            "to": [
                identity
                for value in as_list(source.get("recipients"))
                if (identity := party_identity(value, role="to", identity_source="document_metadata"))
            ],
            "cc": [
                identity
                for value in as_list(source.get("cc_recipients"))
                if (identity := party_identity(value, role="cc", identity_source="document_metadata"))
            ],
            "bcc": [
                identity
                for value in as_list(source.get("bcc_recipients"))
                if (identity := party_identity(value, role="bcc", identity_source="document_metadata"))
            ],
        }
        if any(group for group in identities.values()):
            return identities
    if source_type == "chat_log":
        identities = {
            "participants": [
                identity
                for value in as_list(source.get("participants"))
                if (identity := party_identity(value, role="participant", identity_source="chat_participants"))
            ]
        }
        if any(group for group in identities.values()):
            return identities
    if source_lookup is not None and source_links is not None:
        source_id = str(source.get("source_id") or "")
        for linked_id in linked_source_ids(source_id, source_links):
            linked_source = as_dict(source_lookup.get(linked_id))
            if str(linked_source.get("source_type") or "") != "email":
                continue
            identities = {
                "to": [
                    identity
                    for value in as_list(linked_source.get("to"))
                    if (identity := party_identity(value, role="to", identity_source="linked_email_metadata"))
                ],
                "cc": [
                    identity
                    for value in as_list(linked_source.get("cc"))
                    if (identity := party_identity(value, role="cc", identity_source="linked_email_metadata"))
                ],
                "bcc": [
                    identity
                    for value in as_list(linked_source.get("bcc"))
                    if (identity := party_identity(value, role="bcc", identity_source="linked_email_metadata"))
                ],
            }
            if any(group for group in identities.values()):
                return identities
    return {"to": [], "cc": [], "bcc": []}


def recipients(source: dict[str, Any], source_lookup: dict[str, dict[str, Any]], source_links: list[dict[str, Any]]) -> list[str]:
    identities = recipient_identities(source, source_lookup=source_lookup, source_links=source_links)
    values = [
        str(identity.get("display") or "")
        for group in identities.values()
        if isinstance(group, list)
        for identity in group
        if isinstance(identity, dict) and str(identity.get("display") or "").strip()
    ]
    if values:
        return values[:6]
    if str(source.get("source_type") or "") == "chat_log":
        return [str(item) for item in as_list(source.get("participants")) if str(item).strip()]
    source_id = str(source.get("source_id") or "")
    linked_ids = [
        str(link.get("to_source_id") or "")
        for link in source_links
        if isinstance(link, dict) and str(link.get("from_source_id") or "") == source_id
    ]
    titles = [str(source_lookup[linked_id].get("title") or "") for linked_id in linked_ids if linked_id in source_lookup]
    return [title for title in titles if title][:2]


def short_description(source: dict[str, Any]) -> str:
    title = str(source.get("title") or "").strip()
    snippet = " ".join(str(source.get("snippet") or "").split())
    if title and snippet:
        return f"{title}: {snippet[:140]}".strip()
    return title or snippet[:140]


def source_language(source: dict[str, Any]) -> str:
    documentary_support = as_dict(source.get("documentary_support"))
    return detect_source_language(
        source.get("language_hint_text"),
        source.get("text"),
        source.get("title"),
        source.get("snippet"),
        documentary_support.get("text_preview"),
    )


def top_exhibit_payload(row: dict[str, Any], *, source: dict[str, Any], rank: int, priority_score: int) -> dict[str, Any]:
    reliability = as_dict(row.get("exhibit_reliability"))
    next_step_logic = as_dict(reliability.get("next_step_logic"))
    return {
        "rank": rank,
        "exhibit_id": str(row.get("exhibit_id") or ""),
        "source_id": str(row.get("source_id") or ""),
        "source_type": str(row.get("source_type") or ""),
        "priority_score": priority_score,
        "strength": str(reliability.get("strength") or ""),
        "readiness": str(next_step_logic.get("readiness") or ""),
        "short_description": str(row.get("short_description") or ""),
        "why_prioritized": str(row.get("why_it_matters") or reliability.get("reason") or ""),
        "source_language": str(row.get("source_language") or "unknown"),
        "quoted_evidence": dict(row.get("quoted_evidence") or {}),
        "document_locator": dict(row.get("document_locator") or {}),
        "main_issue_tags": [str(tag) for tag in as_list(row.get("main_issue_tags")) if str(tag).strip()],
        "supporting_finding_ids": [str(item) for item in as_list(row.get("supporting_finding_ids")) if str(item).strip()],
        "supporting_citation_ids": [str(item) for item in as_list(row.get("supporting_citation_ids")) if str(item).strip()],
        "supporting_source_ids": [str(item) for item in as_list(row.get("supporting_source_ids")) if str(item).strip()],
        "supporting_evidence_handles": [
            str(item) for item in as_list(row.get("supporting_evidence_handles")) if str(item).strip()
        ],
        "source_conflict_status": str(row.get("source_conflict_status") or ""),
        "candidate_related_source_ids": [
            str(item) for item in as_list(row.get("candidate_related_source_ids")) if str(item).strip()
        ],
        "source_date": str(source.get("date") or row.get("date") or ""),
    }


def exhibit_priority_score(row: dict[str, Any], source: dict[str, Any]) -> int:
    reliability = as_dict(row.get("exhibit_reliability"))
    next_step_logic = as_dict(reliability.get("next_step_logic"))
    strength = str(reliability.get("strength") or "")
    readiness = str(next_step_logic.get("readiness") or "")
    issue_tags = [tag for tag in as_list(row.get("issue_tags")) if isinstance(tag, dict)]
    direct_tag_count = sum(1 for tag in issue_tags if str(tag.get("assignment_basis") or "") == "direct_document_content")
    issue_tag_count = len([tag for tag in as_list(row.get("main_issue_tags")) if str(tag).strip()])
    finding_count = len([item for item in as_list(row.get("supporting_finding_ids")) if str(item).strip()])
    citation_count = len([item for item in as_list(row.get("supporting_citation_ids")) if str(item).strip()])
    source_type = str(row.get("source_type") or source.get("source_type") or "")
    quoted_evidence = as_dict(row.get("quoted_evidence"))
    quoted_text = compact(
        quoted_evidence.get("original_text") or quoted_evidence.get("translated_text") or quoted_evidence.get("summary")
    )
    document_locator = as_dict(row.get("document_locator"))
    chronology_bonus = 6 if str(row.get("date") or "").strip() else 0
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        chronology_bonus += 4
    contradiction_bonus = 8 if bool(as_dict(source.get("source_weighting")).get("can_corroborate_or_contradict")) else 0
    readiness_bonus = {"usable_now": 8, "usable_with_original_source_check": 4, "manual_review_required": 0}.get(readiness, 0)
    strength_score = {"strong": 40, "moderate": 24, "weak": 8, "unknown": 4}.get(strength, 0)
    quote_bonus = 8 if len(quoted_text) >= 40 else 4 if quoted_text else 0
    locator_bonus = 4 if str(document_locator.get("evidence_handle") or "") else 0
    weak_text_penalty = 0
    if str(row.get("promotability_status") or "") in {"lead_only_manual_review", "reference_only_not_promotable"}:
        weak_text_penalty += 10
    if any(str(tag.get("assignment_basis") or "") == "weak_recovered_text" for tag in issue_tags):
        weak_text_penalty += 6
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


def make_quoted_evidence(row: dict[str, Any], *, source_language: str) -> dict[str, Any]:
    return quoted_evidence_payload(
        original_text=row.get("snippet"),
        source_language=source_language,
        document_locator=as_dict(row.get("document_locator")),
        evidence_handle=str(as_dict(row.get("provenance")).get("evidence_handle") or row.get("source_id") or ""),
        translated_summary_fields=["why_it_matters", "short_description"],
    )


def source_conflicts_by_source_id(master_chronology: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return _source_conflicts_by_source_id(master_chronology, as_dict=as_dict, as_list=as_list)


def missing_exhibit_rows(
    *, case_bundle: dict[str, Any], rows: list[dict[str, Any]], master_chronology: dict[str, Any], as_dict: Any, as_list: Any
) -> list[dict[str, Any]]:
    return _missing_exhibit_rows(
        case_bundle=case_bundle,
        rows=rows,
        master_chronology=master_chronology,
        as_dict=as_dict,
        as_list=as_list,
    )
