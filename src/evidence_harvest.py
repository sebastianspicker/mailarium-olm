"""Wave-driven evidence harvest and promotion helpers."""

from __future__ import annotations

from typing import Any

from .question_execution_waves import get_wave_definition


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _coerce_non_negative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _find_snippet_bounds(body_text: str, snippet: str) -> tuple[int | None, int | None]:
    """Locate *snippet* in *body_text*, tolerating collapsed whitespace."""
    if not body_text or not snippet:
        return None, None
    exact_start = body_text.find(snippet)
    if exact_start >= 0:
        return exact_start, exact_start + len(snippet)

    body_chars: list[str] = []
    body_map: list[int] = []
    prev_space = False
    for idx, char in enumerate(body_text):
        if char.isspace():
            if prev_space:
                continue
            body_chars.append(" ")
            body_map.append(idx)
            prev_space = True
        else:
            body_chars.append(char)
            body_map.append(idx)
            prev_space = False
    normalized_body = "".join(body_chars)
    normalized_snippet = " ".join(snippet.split())
    collapsed_start = normalized_body.find(normalized_snippet)
    if collapsed_start < 0:
        return None, None
    start = body_map[collapsed_start]
    end = body_map[collapsed_start + len(normalized_snippet) - 1] + 1
    return start, end


def _wave_meta(payload: dict[str, Any]) -> dict[str, Any]:
    wave_execution = _as_dict(payload.get("wave_execution"))
    wave_id = _clean_text(wave_execution.get("wave_id"))
    if not wave_id:
        raise ValueError("wave_execution.wave_id is required for evidence harvest")
    definition = get_wave_definition(wave_id)
    label = _clean_text(wave_execution.get("label")) or definition.label
    questions = [
        _clean_text(item)
        for item in (_as_list(wave_execution.get("questions")) or list(definition.question_ids))
        if _clean_text(item)
    ]
    return {
        "wave_id": definition.wave_id,
        "wave_label": label,
        "question_ids": questions,
        "scan_id": _clean_text(wave_execution.get("scan_id")),
    }


def _raw_archive_candidates(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    archive_harvest = _as_dict(payload.get("archive_harvest"))
    evidence_bank = [row for row in _as_list(archive_harvest.get("evidence_bank")) if isinstance(row, dict)]
    rows: list[tuple[str, dict[str, Any]]] = []
    for row in evidence_bank:
        candidate_kind = _clean_text(row.get("candidate_kind")) or "body"
        rows.append((candidate_kind, dict(row)))
    return rows


def _candidate_rows(payload: dict[str, Any], *, harvest_limit_per_wave: int) -> list[tuple[str, dict[str, Any]]]:
    raw_rows = _raw_archive_candidates(payload)
    if raw_rows:
        return raw_rows[:harvest_limit_per_wave]
    body = [row for row in _as_list(payload.get("candidates")) if isinstance(row, dict)][:harvest_limit_per_wave]
    attachments = [row for row in _as_list(payload.get("attachment_candidates")) if isinstance(row, dict)][
        :harvest_limit_per_wave
    ]
    return [("body", row) for row in body] + [("attachment", row) for row in attachments]


def _candidate_summary(*, wave_label: str, question_ids: list[str], candidate_kind: str, rank: int) -> str:
    joined_questions = ", ".join(question_ids[:4]) if question_ids else "unmapped questions"
    if candidate_kind == "attachment":
        return f"{wave_label}: harvested attachment candidate for {joined_questions} (rank {rank})."
    return f"{wave_label}: harvested exact-quote candidate for {joined_questions} (rank {rank})."


def _candidate_context(
    *,
    candidate: dict[str, Any],
    candidate_kind: str,
    wave_id: str,
    question_ids: list[str],
    scan_id: str,
) -> dict[str, Any]:
    attachment = _as_dict(candidate.get("attachment")) if candidate_kind == "attachment" else {}
    provenance = _as_dict(candidate.get("provenance"))
    support_type = _clean_text(candidate.get("support_type"))
    return {
        "wave_id": wave_id,
        "question_ids": list(question_ids),
        "scan_id": scan_id,
        "candidate_kind": candidate_kind,
        "match_reason": _clean_text(candidate.get("match_reason")),
        "attachment_filename": _clean_text(attachment.get("filename")),
        "attachment_mime_type": _clean_text(attachment.get("mime_type")),
        "harvest_source": _clean_text(candidate.get("harvest_source")),
        "body_render_source": _clean_text(candidate.get("body_render_source") or provenance.get("body_render_source")),
        "verification_status": _clean_text(candidate.get("verification_status")),
        "language": _clean_text(candidate.get("detected_language")),
        "language_confidence": _clean_text(candidate.get("detected_language_confidence")),
        "matched_query_lanes": [item for item in _as_list(candidate.get("matched_query_lanes")) if _clean_text(item)],
        "matched_query_queries": [item for item in _as_list(candidate.get("matched_query_queries")) if _clean_text(item)],
        "thread_group_id": _clean_text(candidate.get("thread_group_id")),
        "thread_group_source": _clean_text(candidate.get("thread_group_source")),
        "segment_type": _clean_text(candidate.get("segment_type") or provenance.get("segment_type")),
        "segment_ordinal": int(candidate.get("segment_ordinal") or provenance.get("segment_ordinal") or 0),
        "support_type": support_type,
        "counterevidence": support_type == "counterevidence",
        "comparator_evidence": support_type == "comparator",
    }


def _notes_for_promoted_candidate(
    *,
    run_id: str,
    phase_id: str,
    wave_id: str,
    question_ids: list[str],
    candidate: dict[str, Any],
) -> str:
    lanes = ", ".join(_clean_text(item) for item in _as_list(candidate.get("matched_query_lanes")) if _clean_text(item))
    evidence_handle = _clean_text(_as_dict(candidate.get("provenance")).get("evidence_handle"))
    notes = [
        "Auto-promoted from wave-driven evidence harvest.",
        f"run_id={run_id}",
        f"phase_id={phase_id}",
        f"wave_id={wave_id}",
    ]
    if question_ids:
        notes.append(f"questions={','.join(question_ids)}")
    if lanes:
        notes.append(f"matched_query_lanes={lanes}")
    if evidence_handle:
        notes.append(f"evidence_handle={evidence_handle}")
    verification_status = _clean_text(candidate.get("verification_status"))
    if verification_status:
        notes.append(f"verification_status={verification_status}")
    harvest_source = _clean_text(candidate.get("harvest_source"))
    if harvest_source:
        notes.append(f"harvest_source={harvest_source}")
    candidate_kind = _clean_text(candidate.get("candidate_kind"))
    if candidate_kind:
        notes.append(f"candidate_kind={candidate_kind}")
    support_type = _clean_text(candidate.get("support_type"))
    if support_type:
        notes.append(f"support_type={support_type}")
    segment_type = _clean_text(candidate.get("segment_type"))
    if segment_type:
        notes.append(f"segment_type={segment_type}")
    return " | ".join(notes)


def _relevance_for_candidate(*, rank: int) -> int:
    if rank <= 1:
        return 5
    if rank <= 3:
        return 4
    return 3


def _exact_quote_from_surface(snippet: str, surface_text: str) -> str:
    surface = str(surface_text or "")
    compact_snippet = _clean_text(snippet)
    if not compact_snippet or not surface.strip():
        return ""
    start, end = _find_snippet_bounds(surface, compact_snippet)
    if start is None or end is None:
        return ""
    exact = surface[start:end].strip()
    return exact or ""


def _segment_exact_quote(db: Any, *, uid: str, candidate: dict[str, Any]) -> str:
    conn = getattr(db, "conn", None)
    if conn is None or not uid:
        return ""
    provenance = _as_dict(candidate.get("provenance"))
    segment_ordinal = int(candidate.get("segment_ordinal") or provenance.get("segment_ordinal") or 0)
    segment_type = _clean_text(candidate.get("segment_type") or provenance.get("segment_type"))
    rows = conn.execute(
        """SELECT ordinal, segment_type, text
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
        (uid,),
    ).fetchall()
    snippet = _clean_text(candidate.get("snippet"))
    for row in rows:
        if segment_ordinal and int(row["ordinal"] or 0) != segment_ordinal:
            continue
        if segment_type and _clean_text(row["segment_type"]) != segment_type:
            continue
        exact = _exact_quote_from_surface(snippet, str(row["text"] or ""))
        if exact:
            return exact
    for row in rows:
        if segment_type and _clean_text(row["segment_type"]) != segment_type:
            continue
        exact = _exact_quote_from_surface(snippet, str(row["text"] or ""))
        if exact:
            return exact
    return ""


def _attachment_exact_quote(db: Any, *, uid: str, candidate: dict[str, Any]) -> str:
    if db is None or not uid or not hasattr(db, "attachments_for_email"):
        return ""
    attachment = _as_dict(candidate.get("attachment"))
    filename = _clean_text(attachment.get("filename") or candidate.get("attachment_filename"))
    attachment_id = _clean_text(attachment.get("attachment_id") or candidate.get("attachment_id"))
    snippet = _clean_text(candidate.get("snippet"))
    for record in db.attachments_for_email(uid):
        if (
            attachment_id
            and _clean_text(record.get("attachment_id"))
            and _clean_text(record.get("attachment_id")) != attachment_id
        ):
            continue
        record_name = _clean_text(record.get("name"))
        if filename and record_name and record_name != filename:
            continue
        for field in ("extracted_text", "text_preview"):
            exact = _exact_quote_from_surface(snippet, str(record.get(field) or ""))
            if exact:
                return exact
    return ""


def _body_exact_quote(db: Any, *, uid: str, candidate: dict[str, Any]) -> str:
    if db is None or not uid or not hasattr(db, "get_emails_full_batch"):
        return ""
    snippet = _clean_text(candidate.get("snippet"))
    full_batch = db.get_emails_full_batch([uid])
    full_email = dict(full_batch.get(uid) or {}) if isinstance(full_batch, dict) else {}
    for field in ("forensic_body_text", "body_text", "raw_body_text", "subject"):
        exact = _exact_quote_from_surface(snippet, str(full_email.get(field) or ""))
        if exact:
            return exact
    return _segment_exact_quote(db, uid=uid, candidate=candidate)


def _recover_exact_quote(db: Any, *, candidate_kind: str, candidate: dict[str, Any]) -> str:
    uid = _clean_text(candidate.get("uid"))
    if not uid:
        return ""
    locator_exact = _locator_exact_quote(db, candidate_kind=candidate_kind, candidate=candidate)
    if locator_exact:
        return locator_exact
    if candidate_kind == "attachment":
        return _attachment_exact_quote(db, uid=uid, candidate=candidate)
    segment_exact = _segment_exact_quote(db, uid=uid, candidate=candidate)
    if segment_exact:
        return segment_exact
    return _body_exact_quote(db, uid=uid, candidate=candidate)


def _locator_slice(text: str, *, start: int | None, end: int | None) -> str:
    if not text:
        return ""
    if start is None or end is None:
        return ""
    if start < 0 or end <= start:
        return ""
    if start >= len(text):
        return ""
    bounded_end = min(end, len(text))
    return text[start:bounded_end].strip()


def _body_surface_for_locator(full_email: dict[str, Any], body_render_source: str) -> str:
    normalized_source = _clean_text(body_render_source).casefold()
    if normalized_source in {"forensic_body_text", "quoted_reply", "message_segments"}:
        return str(full_email.get("forensic_body_text") or "")
    if normalized_source in {"raw_body_text", "raw_source"}:
        return str(full_email.get("raw_body_text") or "")
    return str(full_email.get("body_text") or full_email.get("forensic_body_text") or full_email.get("raw_body_text") or "")


def _locator_exact_quote(db: Any, *, candidate_kind: str, candidate: dict[str, Any]) -> str:
    uid = _clean_text(candidate.get("uid"))
    if not uid:
        return ""
    provenance = _as_dict(candidate.get("provenance"))
    start = _coerce_non_negative_int(candidate.get("snippet_start") or provenance.get("snippet_start"))
    end = _coerce_non_negative_int(candidate.get("snippet_end") or provenance.get("snippet_end"))
    if start is None or end is None:
        return ""
    if candidate_kind == "attachment":
        attachment = _as_dict(candidate.get("attachment"))
        filename = _clean_text(attachment.get("filename") or candidate.get("attachment_filename"))
        attachment_id = _clean_text(attachment.get("attachment_id") or candidate.get("attachment_id"))
        if db is None or not hasattr(db, "attachments_for_email"):
            return ""
        for record in db.attachments_for_email(uid):
            if (
                attachment_id
                and _clean_text(record.get("attachment_id"))
                and _clean_text(record.get("attachment_id")) != attachment_id
            ):
                continue
            record_name = _clean_text(record.get("name"))
            if filename and record_name and record_name != filename:
                continue
            quote = _locator_slice(str(record.get("extracted_text") or ""), start=start, end=end)
            if quote:
                return quote
        return ""

    if db is None or not hasattr(db, "get_emails_full_batch"):
        return ""
    full_batch = db.get_emails_full_batch([uid])
    full_email = dict(full_batch.get(uid) or {}) if isinstance(full_batch, dict) else {}
    if not full_email:
        return ""
    body_render_source = _clean_text(candidate.get("body_render_source") or provenance.get("body_render_source"))
    surface = _body_surface_for_locator(full_email, body_render_source)
    return _locator_slice(surface, start=start, end=end)


def _document_locator_for_candidate(*, candidate_kind: str, candidate: dict[str, Any]) -> dict[str, Any]:
    provenance = _as_dict(candidate.get("provenance"))
    locator = {
        "evidence_handle": _clean_text(provenance.get("evidence_handle")),
        "chunk_id": _clean_text(provenance.get("chunk_id")),
        "snippet_start": provenance.get("snippet_start"),
        "snippet_end": provenance.get("snippet_end"),
        "segment_type": _clean_text(candidate.get("segment_type") or provenance.get("segment_type")),
        "source_scope": _clean_text(provenance.get("source_scope") or candidate.get("source_scope")),
        "char_start": provenance.get("char_start"),
        "char_end": provenance.get("char_end"),
        "surface_hash": _clean_text(provenance.get("surface_hash") or candidate.get("surface_hash")),
        "body_render_source": _clean_text(candidate.get("body_render_source") or provenance.get("body_render_source")),
    }
    segment_ordinal = int(candidate.get("segment_ordinal") or provenance.get("segment_ordinal") or 0)
    if segment_ordinal > 0:
        locator["segment_ordinal"] = segment_ordinal
    if candidate_kind == "attachment":
        attachment = _as_dict(candidate.get("attachment"))
        locator.update(
            {
                "attachment_filename": _clean_text(attachment.get("filename") or candidate.get("attachment_filename")),
                "attachment_mime_type": _clean_text(attachment.get("mime_type")),
                "attachment_id": _clean_text(
                    attachment.get("attachment_id") or candidate.get("attachment_id") or provenance.get("attachment_id")
                ),
                "content_sha256": _clean_text(
                    attachment.get("content_sha256") or candidate.get("content_sha256") or provenance.get("content_sha256")
                ),
                "locator_version": int(
                    attachment.get("locator_version")
                    or candidate.get("locator_version")
                    or provenance.get("locator_version")
                    or 1
                ),
                "text_locator": _as_dict(attachment.get("text_locator")),
            }
        )
    return {key: value for key, value in locator.items() if value not in (None, "", {})}


def harvest_wave_payload(
    db: Any,
    *,
    payload: dict[str, Any],
    run_id: str,
    phase_id: str,
    harvest_limit_per_wave: int,
    promote_limit_per_wave: int,
) -> dict[str, Any]:
    """Persist harvested candidates for one wave and auto-promote exact body quotes."""
    if db is None:
        return {
            "status": "db_unavailable",
            "candidate_count": 0,
            "body_candidate_count": 0,
            "attachment_candidate_count": 0,
            "exact_body_candidate_count": 0,
            "duplicate_candidate_count": 0,
            "promoted_count": 0,
            "linked_existing_evidence_count": 0,
            "promoted_evidence_ids": [],
        }

    meta = _wave_meta(payload)
    harvested = _candidate_rows(payload, harvest_limit_per_wave=harvest_limit_per_wave)
    candidate_count = 0
    body_candidate_count = 0
    attachment_candidate_count = 0
    exact_body_candidate_count = 0
    duplicate_candidate_count = 0
    promoted_count = 0
    linked_existing_evidence_count = 0
    promoted_evidence_ids: list[int] = []

    for candidate_kind, candidate in harvested:
        recovered_exact_quote = _recover_exact_quote(db, candidate_kind=candidate_kind, candidate=candidate)
        quote_candidate = recovered_exact_quote or _clean_text(candidate.get("snippet"))
        if not quote_candidate:
            continue
        if candidate_kind == "body":
            body_candidate_count += 1
        else:
            attachment_candidate_count += 1
        verification_status = _clean_text(candidate.get("verification_status"))
        verified_exact = bool(recovered_exact_quote)
        if candidate_kind == "body" and verified_exact:
            exact_body_candidate_count += 1

        stored = db.add_evidence_candidate(
            run_id=run_id,
            phase_id=phase_id,
            wave_id=meta["wave_id"],
            wave_label=meta["wave_label"],
            question_ids=meta["question_ids"],
            email_uid=_clean_text(candidate.get("uid")) or None,
            candidate_kind=candidate_kind,
            quote_candidate=quote_candidate,
            summary=_candidate_summary(
                wave_label=meta["wave_label"],
                question_ids=meta["question_ids"],
                candidate_kind=candidate_kind,
                rank=int(candidate.get("rank") or 0),
            ),
            category_hint="general",
            rank=int(candidate.get("rank") or 0),
            score=float(candidate.get("score") or 0.0),
            verification_status=verification_status,
            verified_exact=verified_exact,
            subject=_clean_text(candidate.get("subject")),
            sender_name=_clean_text(candidate.get("sender_name")),
            sender_email=_clean_text(candidate.get("sender_email")),
            date=_clean_text(candidate.get("date")),
            conversation_id=_clean_text(candidate.get("conversation_id")),
            matched_query_lanes=[
                _clean_text(item) for item in _as_list(candidate.get("matched_query_lanes")) if _clean_text(item)
            ],
            matched_query_queries=[
                _clean_text(item) for item in _as_list(candidate.get("matched_query_queries")) if _clean_text(item)
            ],
            provenance=_as_dict(candidate.get("provenance")),
            context=_candidate_context(
                candidate=candidate,
                candidate_kind=candidate_kind,
                wave_id=meta["wave_id"],
                question_ids=meta["question_ids"],
                scan_id=meta["scan_id"],
            ),
        )
        if stored.get("inserted"):
            candidate_count += 1
        else:
            duplicate_candidate_count += 1
            continue

        if not verified_exact or promoted_count >= promote_limit_per_wave:
            continue
        email_uid = _clean_text(candidate.get("uid"))
        if not email_uid:
            continue
        document_locator = _document_locator_for_candidate(candidate_kind=candidate_kind, candidate=candidate)
        find_with_artifact = getattr(db, "find_evidence_by_email_artifact_quote", None)
        if callable(find_with_artifact):
            existing = find_with_artifact(
                email_uid=email_uid,
                key_quote=quote_candidate,
                candidate_kind=candidate_kind,
                document_locator=document_locator,
            )
        else:
            existing = db.find_evidence_by_email_quote(email_uid=email_uid, key_quote=quote_candidate)
        if existing:
            stored_id = int(_as_dict(stored).get("id") or 0)
            existing_id = int(_as_dict(existing).get("id") or 0)
            if stored_id and existing_id:
                db.mark_evidence_candidate_promoted(stored_id, evidence_id=existing_id)
            linked_existing_evidence_count += 1
            continue
        evidence = db.add_evidence(
            email_uid=email_uid,
            category="general",
            key_quote=quote_candidate,
            summary=f"{meta['wave_label']}: auto-promoted exact quote from archive harvest.",
            relevance=_relevance_for_candidate(rank=int(candidate.get("rank") or 0)),
            notes=_notes_for_promoted_candidate(
                run_id=run_id,
                phase_id=phase_id,
                wave_id=meta["wave_id"],
                question_ids=meta["question_ids"],
                candidate=candidate,
            ),
            candidate_kind=candidate_kind,
            provenance=_as_dict(candidate.get("provenance")),
            document_locator=document_locator,
            context=_candidate_context(
                candidate=candidate,
                candidate_kind=candidate_kind,
                wave_id=meta["wave_id"],
                question_ids=meta["question_ids"],
                scan_id=meta["scan_id"],
            ),
        )
        stored_id = int(_as_dict(stored).get("id") or 0)
        evidence_id = int(_as_dict(evidence).get("id") or 0)
        if stored_id and evidence_id:
            db.mark_evidence_candidate_promoted(stored_id, evidence_id=evidence_id)
            promoted_count += 1
            promoted_evidence_ids.append(evidence_id)

    return {
        "status": "completed",
        "run_id": run_id,
        "phase_id": phase_id,
        "wave_id": meta["wave_id"],
        "wave_label": meta["wave_label"],
        "question_ids": list(meta["question_ids"]),
        "candidate_count": candidate_count,
        "body_candidate_count": body_candidate_count,
        "attachment_candidate_count": attachment_candidate_count,
        "exact_body_candidate_count": exact_body_candidate_count,
        "duplicate_candidate_count": duplicate_candidate_count,
        "promoted_count": promoted_count,
        "linked_existing_evidence_count": linked_existing_evidence_count,
        "promoted_evidence_ids": promoted_evidence_ids,
    }
