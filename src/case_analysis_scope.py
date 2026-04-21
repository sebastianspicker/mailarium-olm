"""Scope and classification helpers for case-analysis payloads."""

from __future__ import annotations

from typing import Any

from .case_analysis_common import as_dict, warning
from .case_intake import build_case_intake_guidance
from .case_operator_intake import matter_manifest_has_chat_artifacts, matter_manifest_has_mixed_artifacts
from .mcp_models import EmailCaseAnalysisInput
from .question_execution_waves import derive_wave_query_lanes, shared_wave_vocabulary

_PROMPT_CRITICAL_SURFACES: tuple[tuple[str, str], ...] = (
    ("case_patterns", "corpus_behavioral_review"),
    ("finding_evidence_index", "finding_evidence_index"),
    ("investigation_report", "investigation_report"),
)


def _manifest_artifacts(params: EmailCaseAnalysisInput) -> list[dict[str, Any]]:
    if params.matter_manifest is None:
        return []
    return [dict(item) for item in params.matter_manifest.model_dump(mode="json").get("artifacts", []) if isinstance(item, dict)]


def _expected_manifest_artifact_classes(params: EmailCaseAnalysisInput) -> list[str]:
    tags = {str(item).casefold() for item in params.case_scope.employment_issue_tags}
    tracks = {str(item).casefold() for item in params.case_scope.employment_issue_tracks}
    combined = tags | tracks
    expected = ["formal_document"]
    if any(token in " ".join(combined) for token in ("time system", "worktime", "time", "zeiterfassung")):
        expected.append("time_record")
    if any(token in " ".join(combined) for token in ("mobile", "bem", "sbv", "participation", "calendar", "pr_")):
        expected.append("calendar_record")
    if any(token in " ".join(combined) for token in ("eingruppierung", "eg12", "tarif", "classification")):
        expected.append("classification_record")
    if any(token in " ".join(combined) for token in ("comparator", "unequal", "disadvantage")):
        expected.append("comparator_record")
    if any(token in " ".join(combined) for token in ("bem", "prevention", "sgb_ix", "medical")):
        expected.append("medical_or_bem_record")
    seen: set[str] = set()
    normalized: list[str] = []
    for item in expected:
        if item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _artifact_matches_expected_class(artifact: dict[str, Any], expected_class: str) -> bool:
    source_class = str(artifact.get("source_class") or "").casefold()
    filename = str(artifact.get("filename") or artifact.get("title") or "").casefold()
    text = " ".join(
        str(artifact.get(field) or "").casefold() for field in ("title", "filename", "summary", "source_path", "text")
    )
    if expected_class == "formal_document":
        return bool(
            source_class in {"formal_document", "meeting_note", "note_record"} or filename.endswith((".html", ".pdf", ".docx"))
        )
    if expected_class == "calendar_record":
        return bool(
            source_class in {"calendar_export", "calendar_record"}
            or filename.endswith((".ics", ".vcs"))
            or any(token in text for token in ("calendar", "invite", "einladung", "termin"))
        )
    if expected_class == "time_record":
        return bool(
            source_class in {"time_record", "spreadsheet"}
            or filename.endswith((".csv", ".xlsx", ".xls"))
            or any(token in text for token in ("time system", "timesheet", "arbeitszeit", "zeiterfassung"))
        )
    if expected_class == "classification_record":
        return any(token in text for token in ("eg12", "e12", "eingruppierung", "tarif", "payroll", "entgelt"))
    if expected_class == "comparator_record":
        return any(token in text for token in ("vergleich", "comparator", "kolleg", "peer"))
    if expected_class == "medical_or_bem_record":
        return any(token in text for token in ("bem", "prävention", "prevention", "medizin", "medical", "sgb ix"))
    return False


def manifest_sufficiency(params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Return machine-readable sufficiency diagnostics for the supplied manifest."""
    artifacts = _manifest_artifacts(params)
    if params.review_mode != "exhaustive_matter_review":
        return {"status": "not_applicable", "artifact_count": len(artifacts)}
    if not artifacts:
        return {
            "status": "absent",
            "artifact_count": 0,
            "source_class_count": 0,
            "source_classes": [],
            "expected_artifact_classes": _expected_manifest_artifact_classes(params),
            "present_expected_artifact_classes": [],
            "missing_expected_artifact_classes": _expected_manifest_artifact_classes(params),
        }

    source_classes = sorted(
        {str(item.get("source_class") or "").strip() for item in artifacts if str(item.get("source_class") or "").strip()}
    )
    expected_classes = _expected_manifest_artifact_classes(params)
    present_expected = [
        expected_class
        for expected_class in expected_classes
        if any(_artifact_matches_expected_class(artifact, expected_class) for artifact in artifacts)
    ]
    missing_expected = [expected_class for expected_class in expected_classes if expected_class not in present_expected]
    is_thin = len(artifacts) < 3 or len(source_classes) < 2 or bool(missing_expected)
    return {
        "status": "thin" if is_thin else "sufficient",
        "artifact_count": len(artifacts),
        "source_class_count": len(source_classes),
        "source_classes": source_classes,
        "expected_artifact_classes": expected_classes,
        "present_expected_artifact_classes": present_expected,
        "missing_expected_artifact_classes": missing_expected,
    }


def _has_surface_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return True
    if isinstance(value, list):
        return bool(value)
    return True


def _surface_omissions(
    *,
    answer_payload: dict[str, Any],
    final_payload: dict[str, Any] | None = None,
) -> list[str]:
    payload = final_payload if isinstance(final_payload, dict) else answer_payload
    omitted: list[str] = []
    for surface_id, _label in _PROMPT_CRITICAL_SURFACES:
        if not _has_surface_payload(payload.get(surface_id)):
            omitted.append(surface_id)
    return omitted


def _institutional_actor_query_bits(actor: Any) -> list[str]:
    terms: list[str] = []
    label = str(getattr(actor, "label", "") or "").strip()
    email = str(getattr(actor, "email", "") or "").strip()
    function = str(getattr(actor, "function", "") or "").strip()
    if label:
        terms.append(label)
    if email:
        terms.append(email)
    if function:
        terms.append(function)
    return terms


def derive_case_analysis_query(params: EmailCaseAnalysisInput) -> str:
    """Return a conservative retrieval query for one case-analysis run."""
    if params.analysis_query:
        return params.analysis_query.strip()

    case_scope = params.case_scope
    target = case_scope.target_person
    focus = ", ".join(case_scope.allegation_focus)
    target_bits = [target.name.strip()]
    if target.email:
        target_bits.append(target.email.strip())

    actor_bits = [
        " ".join(part for part in [actor.name.strip(), (actor.email or "").strip()] if part).strip()
        for actor in case_scope.suspected_actors[:3]
    ]
    comparator_bits = [
        " ".join(part for part in [actor.name.strip(), (actor.email or "").strip()] if part).strip()
        for actor in case_scope.comparator_actors[:3]
    ]
    context_people_bits = [
        " ".join(part for part in [actor.name.strip(), (actor.email or "").strip()] if part).strip()
        for actor in getattr(case_scope, "context_people", [])[:4]
    ]
    institutional_bits = [
        " ".join(_institutional_actor_query_bits(actor)[:2]).strip()
        for actor in getattr(case_scope, "institutional_actors", [])[:4]
        if _institutional_actor_query_bits(actor)
    ]
    context = " ".join((case_scope.context_notes or "").split())
    if len(context) > 180:
        context = context[:177].rstrip() + "..."

    use_german = str(params.output_language or "").strip().lower() == "de"
    query_parts = (
        [
            "arbeitsrechtliche fallanalyse",
            f"zielperson {' '.join(bit for bit in target_bits if bit)}",
            f"fokus {focus}",
        ]
        if use_german
        else [
            "workplace case analysis",
            f"target {' '.join(bit for bit in target_bits if bit)}",
            f"focus {focus}",
        ]
    )
    if actor_bits:
        prefix = "vermutete akteure " if use_german else "suspected actors "
        query_parts.append(prefix + "; ".join(bit for bit in actor_bits if bit))
    if comparator_bits:
        prefix = "vergleichspersonen " if use_german else "comparators "
        query_parts.append(prefix + "; ".join(bit for bit in comparator_bits if bit))
    if context_people_bits:
        prefix = "weitere akteure " if use_german else "additional actors "
        query_parts.append(prefix + "; ".join(bit for bit in context_people_bits if bit))
    if institutional_bits:
        prefix = "institutionelle routen " if use_german else "institutional routes "
        query_parts.append(prefix + "; ".join(bit for bit in institutional_bits if bit))
    if case_scope.trigger_events:
        trigger_types = [
            str(event.trigger_type).replace("_", " ")
            for event in case_scope.trigger_events[:3]
            if getattr(event, "trigger_type", None)
        ]
        if trigger_types:
            prefix = "ausloesende ereignisse " if use_german else "trigger events "
            query_parts.append(prefix + ", ".join(trigger_types))
    if case_scope.employment_issue_tracks:
        prefix = "themenstraenge " if use_german else "issue tracks "
        track_terms = [
            value
            for track in case_scope.employment_issue_tracks[:4]
            if str(track).strip()
            for value in [str(track).replace("_", " ").strip(), str(track).strip()]
            if value
        ]
        query_parts.append(prefix + ", ".join(track_terms))
    if case_scope.employment_issue_tags:
        prefix = "themenstichworte " if use_german else "issue tags "
        query_parts.append(prefix + ", ".join(case_scope.employment_issue_tags[:6]))
    if context:
        query_parts.append(context)
    return ". ".join(part for part in query_parts if part)


def derive_case_analysis_query_lanes(params: EmailCaseAnalysisInput) -> list[str]:
    """Return multi-lane retrieval queries for one case-analysis run."""
    if params.query_lanes:
        return list(params.query_lanes)

    if params.wave_id:
        return derive_wave_query_lanes(params, params.wave_id)

    base_query = derive_case_analysis_query(params)
    case_scope = params.case_scope
    use_german = str(params.output_language or "").strip().lower() == "de"
    target = case_scope.target_person
    actor_terms = [
        item
        for actor in [
            *case_scope.suspected_actors[:4],
            *case_scope.comparator_actors[:2],
            *getattr(case_scope, "context_people", [])[:4],
        ]
        for item in (
            actor.name.strip() if actor.name and actor.name.strip() else "",
            (actor.email or "").strip(),
            (actor.role_hint or "").strip(),
        )
        if item
    ]
    institutional_terms = [
        item
        for actor in getattr(case_scope, "institutional_actors", [])[:4]
        for item in _institutional_actor_query_bits(actor)[:2]
        if item
    ]
    track_terms = [str(item).replace("_", " ").strip() for item in case_scope.employment_issue_tracks[:6] if str(item).strip()]
    tag_terms = [str(item).strip() for item in case_scope.employment_issue_tags[:8] if str(item).strip()]
    trigger_terms = [
        " ".join(
            part
            for part in (
                str(getattr(event, "date", "") or ""),
                str(getattr(event, "trigger_type", "") or "").replace("_", " "),
            )
            if part
        ).strip()
        for event in case_scope.trigger_events[:3]
    ]
    issue_sweep_terms = (
        [
            "BEM",
            "Prävention",
            "SBV",
            "Personalrat",
            "mobiles Arbeiten",
            "Homeoffice",
            "time system",
            "Zeiterfassung",
            "EG12",
            "Eingruppierung",
            "Belastung",
            "AU",
            "Aufgabenentzug",
        ]
        if use_german
        else [
            "BEM",
            "prevention",
            "participation",
            "mobile work",
            "calendar",
            "time system",
            "attendance",
            "EG12",
            "classification",
            "workload",
            "medical",
            "task withdrawal",
        ]
    )
    issue_sweep_terms = list(dict.fromkeys([*issue_sweep_terms, *shared_wave_vocabulary(limit=12)]))
    source_terms = (
        ["Protokoll", "Kalender", "Anlage", "BEM", "time system", "Einladung"]
        if use_german
        else ["meeting note", "calendar", "attachment", "BEM", "time system", "invite"]
    )
    counter_terms = (
        ["keine Antwort", "keine Rückmeldung", "abgelehnt", "widerrufen", "ohne Umsetzung"]
        if use_german
        else ["no reply", "no response", "rejected", "withdrawn", "not implemented"]
    )
    lanes = [
        base_query,
        " ".join([target.name.strip(), *actor_terms[:4], *institutional_terms[:2], *track_terms[:3], *tag_terms[:2]]).strip(),
        " ".join([*issue_sweep_terms[:5], *track_terms[:3], *tag_terms[:2]]).strip(),
        " ".join([target.name.strip(), *trigger_terms[:3], *track_terms[:2], *tag_terms[:2]]).strip(),
        " ".join(
            [target.name.strip(), *source_terms[:4], *institutional_terms[:2], *counter_terms[:2], *track_terms[:2]]
        ).strip(),
    ]
    if use_german:
        lanes.append(
            " ".join(
                [
                    item.replace("ä", "ae")
                    .replace("ö", "oe")
                    .replace("ü", "ue")
                    .replace("Ä", "Ae")
                    .replace("Ö", "Oe")
                    .replace("Ü", "Ue")
                    .replace("ß", "ss")
                    for item in issue_sweep_terms[:4] + track_terms[:2] + tag_terms[:2]
                ]
            ).strip()
        )
    else:
        lanes.append(" ".join(["workplace case analysis", target.name.strip(), *track_terms[:2], *tag_terms[:2]]).strip())

    normalized: list[str] = []
    seen: set[str] = set()
    for lane in lanes:
        compact = " ".join(str(lane or "").split()).strip()
        lowered = compact.casefold()
        if not compact or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(compact[:500])
        if len(normalized) >= 5:
            break
    return normalized


def case_scope_quality(params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Return machine-readable scope quality and downgrade markers."""
    case_scope = params.case_scope
    required_fields_present = [
        "target_person",
        "allegation_focus",
        "analysis_goal",
        "date_from",
        "date_to",
    ]
    missing_required_fields: list[str] = []
    guidance = build_case_intake_guidance(case_scope)
    recommended_presence = {
        field: field not in set(guidance.get("missing_recommended_fields", []))
        for field in ("suspected_actors", "comparator_actors", "trigger_events", "org_context", "context_notes")
    }
    missing_recommended_fields = [field for field, present in recommended_presence.items() if not present]
    warnings = [dict(item) for item in guidance.get("warnings", []) if isinstance(item, dict)]
    manifest_sufficiency_payload = manifest_sufficiency(params)
    if (
        params.source_scope == "mixed_case_file"
        and not params.chat_log_entries
        and not params.chat_exports
        and not matter_manifest_has_mixed_artifacts(
            params.matter_manifest.model_dump(mode="json") if params.matter_manifest is not None else None
        )
    ):
        warnings.append(
            warning(
                code="mixed_case_file_declared_without_mixed_record_support",
                severity="info",
                message=(
                    "Mixed case files need structured chat rows, native chat exports, "
                    "or manifest-backed non-email matter artifacts."
                ),
                affects=["multi_source_case_bundle", "analysis_limits"],
            )
        )
    if params.review_mode == "exhaustive_matter_review" and str(manifest_sufficiency_payload.get("status") or "") == "thin":
        warnings.append(
            warning(
                code="exhaustive_review_manifest_is_materially_thin",
                severity="warning",
                message=(
                    "Exhaustive review remains materially thin because the supplied manifest lacks enough artifact breadth "
                    "for the declared issue tracks."
                ),
                affects=["analysis_limits", "review_classification", "overall_assessment"],
            )
        )

    status = "complete"
    if missing_required_fields:
        status = "insufficient"
    elif warnings or missing_recommended_fields:
        status = "degraded"

    return {
        "status": status,
        "required_fields_present": required_fields_present,
        "missing_required_fields": missing_required_fields,
        "recommended_fields_present": list(guidance.get("recommended_fields_present", [])),
        "missing_recommended_fields": missing_recommended_fields,
        "downgrade_reasons": [str(item["code"]) for item in warnings],
        "warnings": warnings,
        "recommended_next_inputs": [dict(item) for item in guidance.get("recommended_next_inputs", []) if isinstance(item, dict)],
        "supports_retaliation_analysis": bool(guidance.get("supports_retaliation_analysis")),
        "supports_comparator_analysis": bool(guidance.get("supports_comparator_analysis")),
        "supports_power_analysis": bool(guidance.get("supports_power_analysis")),
        "review_mode": params.review_mode,
        "has_matter_manifest": params.matter_manifest is not None,
        "manifest_sufficiency": manifest_sufficiency_payload,
    }


def inject_scope_warnings_into_report(
    report: dict[str, Any] | None,
    case_scope_quality_payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Mirror structured scope warnings into the visible missing-information section."""
    if not isinstance(report, dict):
        return report
    warnings = [item for item in case_scope_quality_payload.get("warnings", []) if isinstance(item, dict)]
    if not warnings:
        return report

    report_copy = dict(report)
    sections = dict(report_copy.get("sections") or {})
    missing_information = dict(sections.get("missing_information") or {})
    entries = list(missing_information.get("entries") or [])
    existing_ids = {str(entry.get("entry_id") or "") for entry in entries if isinstance(entry, dict)}
    for item in warnings:
        entry_id = f"scope_warning:{item['code']}"
        if entry_id in existing_ids:
            continue
        entries.append(
            {
                "entry_id": entry_id,
                "statement": str(item.get("message") or ""),
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
                "warning_code": str(item.get("code") or ""),
                "warning_severity": str(item.get("severity") or ""),
                "affects": [str(affect) for affect in item.get("affects", []) if affect],
            }
        )
    missing_information["entries"] = entries
    missing_information["status"] = "supported" if entries else missing_information.get("status", "insufficient_evidence")
    missing_information["insufficiency_reason"] = "" if entries else missing_information.get("insufficiency_reason", "")
    sections["missing_information"] = missing_information
    report_copy["sections"] = sections
    summary = dict(report_copy.get("summary") or {})
    if summary:
        summary["supported_section_count"] = sum(
            1 for section in sections.values() if isinstance(section, dict) and section.get("status") == "supported"
        )
        summary["insufficient_section_count"] = (
            int(summary.get("section_count") or len(sections)) - summary["supported_section_count"]
        )
        report_copy["summary"] = summary
    return report_copy


def analysis_limits(
    params: EmailCaseAnalysisInput,
    payload: dict[str, Any],
    case_scope_quality_payload: dict[str, Any],
    final_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return explicit analysis-limit disclosures."""
    multi_source = payload.get("multi_source_case_bundle")
    missing_source_types: list[str] = []
    if isinstance(multi_source, dict):
        summary = multi_source.get("summary")
        if isinstance(summary, dict):
            missing_source_types = [str(item) for item in summary.get("missing_source_types", []) if item]

    notes: list[str] = []
    if (
        params.source_scope == "mixed_case_file"
        and not params.chat_log_entries
        and not params.chat_exports
        and not matter_manifest_has_mixed_artifacts(
            params.matter_manifest.model_dump(mode="json") if params.matter_manifest is not None else None
        )
    ):
        notes.append("mixed_case_file_declared_but_no_mixed_record_support_was_supplied")
    if "chat_log" in missing_source_types and not (
        params.chat_log_entries
        or params.chat_exports
        or matter_manifest_has_chat_artifacts(
            params.matter_manifest.model_dump(mode="json") if params.matter_manifest is not None else None
        )
    ):
        notes.append("chat_log_source_type_missing_without_chat_support")
    if params.review_mode == "retrieval_only":
        notes.append("review_mode_is_retrieval_only")
    elif payload.get("matter_ingestion_report") is None:
        notes.append("exhaustive_review_requested_without_matter_ingestion_report")
    packing = as_dict(payload.get("_packed"))
    case_surface_compaction = as_dict(payload.get("_case_surface_compaction"))
    omitted_surfaces = _surface_omissions(answer_payload=payload, final_payload=final_payload)
    if bool(packing.get("applied")):
        notes.append("payload_packing_applied")
    if int(case_surface_compaction.get("removed_count") or 0) > 0:
        notes.append("case_surface_compaction_removed_surfaces")
    if omitted_surfaces:
        notes.append("prompt_critical_surfaces_omitted")

    return {
        "source_scope": params.source_scope,
        "review_mode": params.review_mode,
        "missing_source_types": missing_source_types,
        "manifest_sufficiency": manifest_sufficiency(params),
        "downgrade_reasons": list(case_scope_quality_payload.get("downgrade_reasons", [])),
        "scope_warnings": [dict(item) for item in case_scope_quality_payload.get("warnings", []) if isinstance(item, dict)],
        "matter_manifest_supplied": params.matter_manifest is not None,
        "completeness_status": str(as_dict(payload.get("matter_ingestion_report")).get("completeness_status") or ""),
        "packing": {
            "applied": bool(packing.get("applied")),
            "budget_chars": int(packing.get("budget_chars") or 0),
            "estimated_chars_before": int(packing.get("estimated_chars_before") or 0),
            "estimated_chars_after": int(packing.get("estimated_chars_after") or 0),
            "truncated": dict(packing.get("truncated") or {}),
            "deduplicated": dict(packing.get("deduplicated") or {}),
        },
        "case_surface_compaction": {
            "removed_count": int(case_surface_compaction.get("removed_count") or 0),
            "removed": [str(item) for item in case_surface_compaction.get("removed", []) if str(item).strip()],
        },
        "omitted_case_analysis_surfaces": omitted_surfaces,
        "prompt_complete_behavioral_review": not omitted_surfaces,
        "notes": notes,
    }


def review_classification(
    params: EmailCaseAnalysisInput,
    payload: dict[str, Any],
    *,
    final_payload: dict[str, Any] | None = None,
    analysis_limits_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable classification for review truthfulness."""
    completeness_status = str(as_dict(payload.get("matter_ingestion_report")).get("completeness_status") or "")
    manifest_supplied = params.matter_manifest is not None
    is_exhaustive_review = params.review_mode == "exhaustive_matter_review"
    manifest_sufficiency_payload = as_dict((analysis_limits_payload or {}).get("manifest_sufficiency"))
    manifest_sufficiency_status = str(manifest_sufficiency_payload.get("status") or "")
    may_present_as_full_review = (
        is_exhaustive_review
        and manifest_supplied
        and completeness_status == "complete"
        and manifest_sufficiency_status in {"", "sufficient", "not_applicable"}
    )
    omission_summary = analysis_limits_payload or {}
    omitted_surfaces = [str(item) for item in omission_summary.get("omitted_case_analysis_surfaces", []) if str(item).strip()]

    if is_exhaustive_review and manifest_supplied and completeness_status == "complete" and omitted_surfaces:
        classification = "compacted_exhaustive_review_with_omitted_critical_surfaces"
        reason = (
            "Manifest-backed exhaustive review completed with complete supplied-artifact accounting, "
            "but packed compaction omitted prompt-critical analytical surfaces: " + ", ".join(omitted_surfaces) + "."
        )
        may_present_as_full_review = False
    elif (
        is_exhaustive_review and manifest_supplied and completeness_status == "complete" and manifest_sufficiency_status == "thin"
    ):
        classification = "manifest_backed_but_materially_thin"
        reason = (
            "Exhaustive review completed with a supplied manifest, but the manifest remains materially thin for the "
            "declared issue tracks and must not be presented as a full matter-file review."
        )
    elif may_present_as_full_review:
        classification = "counsel_grade_exhaustive_review"
        reason = "Manifest-backed exhaustive review completed with complete supplied-artifact accounting."
    elif is_exhaustive_review and manifest_supplied:
        classification = "manifest_backed_but_not_yet_complete"
        reason = "Exhaustive review was requested with a supplied matter manifest, but completeness accounting is not complete."
    elif is_exhaustive_review:
        classification = "exhaustive_requested_without_manifest"
        reason = "Exhaustive review was requested, but no matter manifest was supplied."
    else:
        classification = "retrieval_bounded_exploratory_review"
        reason = "The current run is retrieval-bounded and must not be presented as a full matter-file review."

    return {
        "review_mode": params.review_mode,
        "classification": classification,
        "is_exhaustive_review": is_exhaustive_review,
        "matter_manifest_supplied": manifest_supplied,
        "completeness_status": completeness_status,
        "may_be_presented_as_full_matter_review": may_present_as_full_review,
        "counsel_use_status": (
            "counsel_grade_exhaustive_review" if may_present_as_full_review else "bounded_or_incomplete_review_only"
        ),
        "reason": reason,
    }
