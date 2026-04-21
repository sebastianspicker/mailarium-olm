"""Promise-versus-action, omission, and contradiction analysis for mixed-source records."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

PROMISE_CONTRADICTION_ANALYSIS_VERSION = "1"
_PROMISE_SOURCE_TYPES = {"meeting_note", "note_record", "email", "formal_document", "participation_record"}
_SUMMARY_SOURCE_TYPES = {"meeting_note", "note_record", "email", "formal_document", "participation_record"}
_PROMISE_CUE_RE = re.compile(
    r"(?i)\b("
    r"will|would|shall|agreed to|agree to|promised to|promise to|follow up|next step|"
    r"will send|will provide|will share|will review|will schedule|will invite|will include|"
    r"wird|werden|zugesagt|vereinbart|nachreichen|prüfen|pruefen|einladen|beteiligen|informieren"
    r")\b"
)
_NEGATION_RE = re.compile(r"(?i)\b(no|not|without|never|did not|didn't|kein|keine|ohne|nicht)\b")
_ACTION_TAGS: dict[str, tuple[str, ...]] = {
    "provide_documents": ("provide", "send", "share", "submit", "nachreichen", "senden", "teilen", "provide the", "send the"),
    "schedule_or_meet": ("schedule", "meeting", "invite", "calendar", "termin", "einladen", "besprechung"),
    "review_or_decide": ("review", "decide", "approval", "approve", "prüfen", "entscheidung", "freigabe"),
    "participation_or_consultation": (
        "consult",
        "participation",
        "sbv",
        "personalrat",
        "betriebsrat",
        "beteilig",
        "consultation",
    ),
    "include_or_inform": ("include", "inform", "copy", "cc", "einbeziehen", "informieren"),
}
_TITLE_TOKEN_RE = re.compile(r"[a-zA-ZäöüÄÖÜß]{4,}")
_TOPIC_TOKEN_RE = re.compile(r"[a-zA-ZäöüÄÖÜß]{3,}")
_TOPIC_STOPWORDS = {
    "and",
    "the",
    "that",
    "this",
    "with",
    "about",
    "from",
    "into",
    "will",
    "would",
    "shall",
    "agreed",
    "agree",
    "promised",
    "promise",
    "follow",
    "next",
    "step",
    "send",
    "provide",
    "share",
    "review",
    "schedule",
    "invite",
    "include",
    "wird",
    "werden",
    "zugesagt",
    "vereinbart",
    "nachreichen",
    "prüfen",
    "pruefen",
    "einladen",
    "beteiligen",
    "informieren",
    "inform",
    "written",
    "summary",
    "und",
    "der",
    "die",
    "das",
    "einer",
    "einem",
    "einen",
    "noch",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_text(source: dict[str, Any]) -> str:
    documentary = _as_dict(source.get("documentary_support"))
    return " ".join(
        part
        for part in (
            _compact(source.get("title")),
            _compact(source.get("snippet")),
            _compact(documentary.get("text_preview")),
        )
        if part
    )


def _content_text(source: dict[str, Any]) -> str:
    documentary = _as_dict(source.get("documentary_support"))
    return " ".join(
        part
        for part in (
            _compact(source.get("snippet")),
            _compact(documentary.get("text_preview")),
        )
        if part
    )


def _source_date(source: dict[str, Any]) -> str:
    chronology_anchor = _as_dict(source.get("chronology_anchor"))
    return str(chronology_anchor.get("date") or source.get("date") or "")


def _source_locator_payload(source: dict[str, Any]) -> dict[str, Any]:
    locator = _as_dict(source.get("document_locator"))
    if locator:
        return locator
    provenance = _as_dict(source.get("provenance"))
    if _as_dict(provenance.get("document_locator")):
        return _as_dict(provenance.get("document_locator"))
    evidence_handle = str(provenance.get("evidence_handle") or source.get("source_id") or "")
    if not evidence_handle:
        return {}
    return {
        "kind": "source_reference",
        "evidence_handle": evidence_handle,
        "source_id": str(source.get("source_id") or ""),
        "uid": str(source.get("uid") or ""),
    }


def _parse_ordering_datetime(value: str) -> datetime | None:
    raw = _compact(value)
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            parsed_date = date.fromisoformat(raw)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_stitched_thread_export(source: dict[str, Any]) -> bool:
    if str(source.get("source_type") or "") != "formal_document":
        return False
    source_id = _compact(source.get("source_id")).lower()
    title = _compact(source.get("title")).lower()
    if "thread" in source_id or "thread" in title:
        return True
    text = _source_text(source).lower()
    return text.count("from:") >= 2 or text.count("subject:") >= 2


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    normalized = re.sub(r"[\r\n]+", ". ", text)
    parts = re.split(r"(?<=[.!?;])\s+", normalized)
    return [part.strip(" .;") for part in parts if _compact(part)]


def _title_tokens(value: Any) -> set[str]:
    return {match.group(0).lower() for match in _TITLE_TOKEN_RE.finditer(_compact(value))}


def _action_tags(text: str) -> list[str]:
    lowered = _compact(text).lower()
    return [action_tag for action_tag, keywords in _ACTION_TAGS.items() if any(keyword in lowered for keyword in keywords)]


def _topic_tokens(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in _TOPIC_TOKEN_RE.finditer(_compact(text))
        if match.group(0).lower() not in _TOPIC_STOPWORDS
    }


def _promise_candidates(source: dict[str, Any]) -> list[dict[str, Any]]:
    if str(source.get("source_type") or "") not in _PROMISE_SOURCE_TYPES:
        return []
    if _is_stitched_thread_export(source):
        return []
    text = _source_text(source)
    rows: list[dict[str, Any]] = []
    for sentence in _split_sentences(text):
        if not _PROMISE_CUE_RE.search(sentence):
            continue
        tags = _action_tags(sentence)
        if not tags:
            continue
        rows.append(
            {
                "statement": sentence,
                "action_tags": tags,
                "source_id": str(source.get("source_id") or ""),
                "uid": str(source.get("uid") or ""),
                "actor_id": str(source.get("actor_id") or ""),
                "date": _source_date(source),
                "source_type": str(source.get("source_type") or ""),
                "title": str(source.get("title") or ""),
            }
        )
    return rows


def _related_sources(
    promise: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    promise_source_id = str(promise.get("source_id") or "")
    promise_uid = str(promise.get("uid") or "")
    promise_actor_id = str(promise.get("actor_id") or "")
    promise_date = str(promise.get("date") or "")
    promise_date_key = _parse_ordering_datetime(promise_date)
    promise_title_tokens = _title_tokens(promise.get("title"))
    linked_source_ids = {
        str(link.get("to_source_id") or "")
        for link in source_links
        if str(link.get("from_source_id") or "") == promise_source_id and str(link.get("to_source_id") or "")
    }
    linked_source_ids.update(
        {
            str(link.get("from_source_id") or "")
            for link in source_links
            if str(link.get("to_source_id") or "") == promise_source_id and str(link.get("from_source_id") or "")
        }
    )
    for source in sources:
        if str(source.get("source_id") or "") == promise_source_id:
            continue
        source_type = str(source.get("source_type") or "")
        if source_type not in _SUMMARY_SOURCE_TYPES and source_type not in {"time_record"}:
            continue
        source_date = _source_date(source)
        source_date_key = _parse_ordering_datetime(source_date)
        if promise_date_key is not None and source_date_key is not None and source_date_key < promise_date_key:
            continue
        relation_basis = ""
        relation_strength = 0
        if promise_uid and str(source.get("uid") or "") == promise_uid:
            relation_basis = "shared_uid"
            relation_strength = 3
        elif str(source.get("source_id") or "") in linked_source_ids:
            relation_basis = "explicit_source_link"
            relation_strength = 3
        elif promise_title_tokens and len(promise_title_tokens & _title_tokens(source.get("title"))) >= 2:
            relation_basis = "shared_title_tokens"
            relation_strength = 2
        elif promise_actor_id and str(source.get("actor_id") or "") == promise_actor_id:
            relation_basis = "same_actor_id"
            relation_strength = 1
        if relation_basis:
            related.append(
                {
                    **source,
                    "_relation_basis": relation_basis,
                    "_relation_strength": relation_strength,
                }
            )
    return related


def _matching_action_source(promise: dict[str, Any], related_sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    action_tags = set(_as_list(promise.get("action_tags")))
    promise_topics = _topic_tokens(str(promise.get("statement") or ""))
    for source in related_sources:
        text = _content_text(source)
        tags = set(_action_tags(text))
        relation_basis = str(source.get("_relation_basis") or "")
        relation_strength = int(source.get("_relation_strength") or 0)
        topic_overlap = sorted(promise_topics & _topic_tokens(text))
        if action_tags & tags and (
            topic_overlap or relation_basis in {"explicit_source_link", "shared_uid"} or relation_strength >= 3
        ):
            source = dict(source)
            source["_topic_overlap"] = topic_overlap
            return source
    return None


def _significance_for_tags(action_tags: list[str]) -> str:
    tag_set = set(action_tags)
    if "participation_or_consultation" in tag_set:
        return "May matter for participation, consultation, or prevention-step review."
    if "review_or_decide" in tag_set:
        return "May matter for decision-flow, approval responsibility, or gatekeeper analysis."
    if "include_or_inform" in tag_set:
        return "May matter for whether promised inclusion or notice actually occurred."
    if "schedule_or_meet" in tag_set:
        return "May matter for chronology credibility and whether promised meetings or follow-up steps happened."
    return "May matter for whether promised follow-up or document production actually occurred."


def build_promise_contradiction_analysis(
    *,
    case_bundle: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return source-linked promise, omission, and contradiction analysis."""
    if not isinstance(case_bundle, dict):
        return None

    sources = [source for source in _as_list(_as_dict(multi_source_case_bundle).get("sources")) if isinstance(source, dict)]
    source_links = [link for link in _as_list(_as_dict(multi_source_case_bundle).get("source_links")) if isinstance(link, dict)]
    promises = [candidate for source in sources for candidate in _promise_candidates(source)]
    promise_action_rows: list[dict[str, Any]] = []
    omission_rows: list[dict[str, Any]] = []
    contradiction_rows: list[dict[str, Any]] = []

    for index, promise in enumerate(promises, start=1):
        related_sources = _related_sources(promise, sources, source_links=source_links)
        matched_source = _matching_action_source(promise, related_sources)
        if matched_source is not None:
            later_text = _source_text(matched_source)
            contradiction_detected = bool(_NEGATION_RE.search(later_text)) and bool(
                _as_list(matched_source.get("_topic_overlap"))
                or str(matched_source.get("_relation_basis") or "") in {"explicit_source_link", "shared_uid"}
            )
            promise_action_rows.append(
                {
                    "row_id": f"promise_action:{index}",
                    "original_statement_or_promise": str(promise.get("statement") or ""),
                    "later_action": later_text,
                    "original_source_id": str(promise.get("source_id") or ""),
                    "later_source_id": str(matched_source.get("source_id") or ""),
                    "likely_significance": _significance_for_tags(list(_as_list(promise.get("action_tags")))),
                    "confidence_level": (
                        "high"
                        if str(promise.get("source_type") or "") in {"meeting_note", "note_record"}
                        and bool(matched_source.get("source_weighting"))
                        else "medium"
                    ),
                    "action_alignment": "apparent_contradiction" if contradiction_detected else "possible_follow_up_match",
                    "supporting_uids": [str(uid) for uid in (promise.get("uid"), matched_source.get("uid")) if _compact(uid)],
                    "supporting_locators": [
                        locator
                        for locator in (_source_locator_payload(promise), _source_locator_payload(matched_source))
                        if locator
                    ],
                }
            )
            if contradiction_detected:
                original_locator = _source_locator_payload(promise)
                later_locator = _source_locator_payload(matched_source)
                contradiction_rows.append(
                    {
                        "row_id": f"contradiction:promise_action:{index}",
                        "original_statement_or_promise": str(promise.get("statement") or ""),
                        "later_action": later_text,
                        "original_source_id": str(promise.get("source_id") or ""),
                        "later_source_id": str(matched_source.get("source_id") or ""),
                        "likely_significance": _significance_for_tags(list(_as_list(promise.get("action_tags")))),
                        "confidence_level": "medium",
                        "contradiction_kind": "promise_vs_later_action",
                        "supporting_uids": [str(uid) for uid in (promise.get("uid"), matched_source.get("uid")) if _compact(uid)],
                        "source_locator_pair": {
                            "original": original_locator,
                            "later": later_locator,
                        },
                        "supporting_locators": [locator for locator in (original_locator, later_locator) if locator],
                    }
                )
        elif related_sources:
            omission_rows.append(
                {
                    "row_id": f"omission:{index}",
                    "original_statement_or_promise": str(promise.get("statement") or ""),
                    "later_summary_context": (
                        "Later related summaries or follow-up records were found, "
                        "but this promise/action topic was not clearly repeated."
                    ),
                    "original_source_id": str(promise.get("source_id") or ""),
                    "later_source_ids": [
                        str(source.get("source_id") or "") for source in related_sources[:4] if str(source.get("source_id") or "")
                    ],
                    "likely_significance": (
                        "May matter if a later summary or follow-up omits a promised step that should have remained visible."
                    ),
                    "confidence_level": "low",
                    "omission_type": "later_summary_omits_prior_promise",
                    "supporting_uids": [
                        str(uid)
                        for uid in [promise.get("uid"), *[source.get("uid") for source in related_sources[:3]]]
                        if _compact(uid)
                    ],
                    "supporting_locators": [
                        locator
                        for locator in [
                            _source_locator_payload(promise),
                            *[_source_locator_payload(source) for source in related_sources[:3]],
                        ]
                        if locator
                    ],
                }
            )

    chronology_contradictions = [
        item
        for item in _as_list(_as_dict(_as_dict(master_chronology).get("summary")).get("sequence_breaks_and_contradictions"))
        if isinstance(item, dict)
    ]
    for index, item in enumerate(chronology_contradictions, start=1):
        contradiction_rows.append(
            {
                "row_id": f"contradiction:chronology:{index}",
                "original_statement_or_promise": (
                    f"Recorded source date {item.get('source_recorded_date') or ''} differs from extracted event date "
                    f"{item.get('event_date') or ''}."
                ).strip(),
                "later_action": str(item.get("summary") or ""),
                "original_source_id": str(item.get("source_id") or ""),
                "later_source_id": "",
                "likely_significance": "May matter for chronology reliability or later contradiction review.",
                "confidence_level": "medium",
                "contradiction_kind": "source_date_vs_event_date",
                "supporting_uids": [str(item.get("uid") or "")] if str(item.get("uid") or "") else [],
                "source_locator_pair": {
                    "original": _as_dict(item.get("source_locator")),
                    "later": {},
                },
                "supporting_locators": [
                    locator
                    for locator in (
                        _as_dict(item.get("source_locator")),
                        _as_dict(item.get("event_locator")),
                    )
                    if locator
                ],
            }
        )

    contradiction_rows = [
        row
        for row in contradiction_rows
        if len([item for item in _as_list(row.get("supporting_locators")) if isinstance(item, dict) and item]) >= 2
    ]
    contradiction_rows.sort(key=lambda row: str(row.get("row_id") or ""))
    omission_rows.sort(key=lambda row: str(row.get("row_id") or ""))
    promise_action_rows.sort(key=lambda row: str(row.get("row_id") or ""))
    usable_sources = [
        source
        for source in sources
        if str(source.get("source_type") or "") in _PROMISE_SOURCE_TYPES and not _is_stitched_thread_export(source)
    ]
    has_result_rows = bool(promise_action_rows or omission_rows or contradiction_rows)
    summary_status = "supported" if has_result_rows else "insufficient_source_material"
    insufficiency_reason = ""
    if not has_result_rows:
        insufficiency_reason = (
            "No usable meeting-note, note-record, or comparable follow-up source pair survived "
            "the current record well enough for promise/contradiction analysis."
            if not usable_sources
            else "No source-linked promise, omission, or contradiction pair was confirmed on the current record."
        )
    return {
        "version": PROMISE_CONTRADICTION_ANALYSIS_VERSION,
        "summary": {
            "promise_action_row_count": len(promise_action_rows),
            "omission_row_count": len(omission_rows),
            "contradiction_row_count": len(contradiction_rows),
            "status": summary_status,
            "insufficiency_reason": insufficiency_reason,
            "usable_source_count": len(usable_sources),
            "locator_backed_contradiction_count": sum(
                1 for row in contradiction_rows if len([item for item in _as_list(row.get("supporting_locators")) if item]) >= 2
            ),
        },
        "promises_vs_actions": promise_action_rows,
        "omission_rows": omission_rows,
        "contradiction_table": contradiction_rows,
    }
