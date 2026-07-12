"""Scope and classification helpers for case-analysis payloads."""
# pylint: disable=too-many-locals,too-many-return-statements

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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

_MANIFEST_EXPECTATION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("time_record", ("time system", "worktime", "time", "zeiterfassung")),
    ("calendar_record", ("mobile", "bem", "sbv", "participation", "calendar", "pr_")),
    ("classification_record", ("eingruppierung", "eg12", "tarif", "classification")),
    ("comparator_record", ("comparator", "unequal", "disadvantage")),
    ("medical_or_bem_record", ("bem", "prevention", "sgb_ix", "medical")),
)


@dataclass(frozen=True)
class _ArtifactSignals:
    source_class: str
    filename: str
    text: str


def _manifest_artifacts(params: EmailCaseAnalysisInput) -> list[dict[str, Any]]:
    """Extract artifact list from matter manifest.

    Returns a list of artifact dictionaries from the matter manifest,
    or an empty list if manifest is None.
    """
    if params.matter_manifest is None:
        return []
    return [dict(item) for item in params.matter_manifest.model_dump(mode="json").get("artifacts", []) if isinstance(item, dict)]


def _expected_manifest_artifact_classes(params: EmailCaseAnalysisInput) -> list[str]:
    """Determine expected artifact classes based on case scope tags and tracks.

    Returns a normalized list of expected artifact class strings based on
    employment issue tags and tracks. Checks for keywords related to:
    - Time systems and records
    - Calendar records
    - Classification records
    - Comparator records
    - Medical/BEM records
    """
    combined = " ".join(
        {
            *(str(item).casefold() for item in params.case_scope.employment_issue_tags),
            *(str(item).casefold() for item in params.case_scope.employment_issue_tracks),
        }
    )
    expected = ["formal_document"]
    for artifact_class, tokens in _MANIFEST_EXPECTATION_RULES:
        if any(token in combined for token in tokens):
            expected.append(artifact_class)
    return list(dict.fromkeys(expected))


def _artifact_matches_expected_class(artifact: dict[str, Any], expected_class: str) -> bool:
    """Check if an artifact matches the expected artifact class.

    Uses multiple criteria to match:
    - source_class field
    - filename extension
    - Text content analysis for keywords
    """
    signals = _ArtifactSignals(
        source_class=str(artifact.get("source_class") or "").casefold(),
        filename=str(artifact.get("filename") or artifact.get("title") or "").casefold(),
        text=" ".join(
            str(artifact.get(field) or "").casefold() for field in ("title", "filename", "summary", "source_path", "text")
        ),
    )
    matcher = _artifact_class_matchers().get(expected_class)
    return matcher(signals) if matcher is not None else False


def _artifact_class_matchers() -> dict[str, Callable[[_ArtifactSignals], bool]]:
    return {
        "formal_document": lambda item: any(
            (
                item.source_class in {"formal_document", "meeting_note", "note_record"},
                item.filename.endswith((".html", ".pdf", ".docx")),
            )
        ),
        "calendar_record": lambda item: any(
            (
                item.source_class in {"calendar_export", "calendar_record"},
                item.filename.endswith((".ics", ".vcs")),
                any(token in item.text for token in ("calendar", "invite", "einladung", "termin")),
            )
        ),
        "time_record": lambda item: any(
            (
                item.source_class in {"time_record", "spreadsheet"},
                item.filename.endswith((".csv", ".xlsx", ".xls")),
                any(token in item.text for token in ("time system", "timesheet", "arbeitszeit", "zeiterfassung")),
            )
        ),
        "classification_record": lambda item: any(
            token in item.text for token in ("eg12", "e12", "eingruppierung", "tarif", "payroll", "entgelt")
        ),
        "comparator_record": lambda item: any(token in item.text for token in ("vergleich", "comparator", "kolleg", "peer")),
        "medical_or_bem_record": lambda item: any(
            token in item.text for token in ("bem", "prävention", "prevention", "medizin", "medical", "sgb ix")
        ),
    }


def manifest_sufficiency(params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Return machine-readable sufficiency diagnostics for the supplied manifest."""
    artifacts = _manifest_artifacts(params)
    if params.review_mode != "exhaustive_matter_review":
        return {"status": "not_applicable", "artifact_count": len(artifacts)}
    if not artifacts:
        return _absent_manifest_sufficiency(params)
    source_classes = _manifest_source_classes(artifacts)
    expected_classes = _expected_manifest_artifact_classes(params)
    present_expected = [
        expected_class
        for expected_class in expected_classes
        if any(_artifact_matches_expected_class(artifact, expected_class) for artifact in artifacts)
    ]
    missing_expected = [expected_class for expected_class in expected_classes if expected_class not in present_expected]
    is_thin = any((len(artifacts) < 3, len(source_classes) < 2, bool(missing_expected)))
    return {
        "status": "thin" if is_thin else "sufficient",
        "artifact_count": len(artifacts),
        "source_class_count": len(source_classes),
        "source_classes": source_classes,
        "expected_artifact_classes": expected_classes,
        "present_expected_artifact_classes": present_expected,
        "missing_expected_artifact_classes": missing_expected,
    }


def _absent_manifest_sufficiency(params: EmailCaseAnalysisInput) -> dict[str, Any]:
    expected = _expected_manifest_artifact_classes(params)
    return {
        "status": "absent",
        "artifact_count": 0,
        "source_class_count": 0,
        "source_classes": [],
        "expected_artifact_classes": expected,
        "present_expected_artifact_classes": [],
        "missing_expected_artifact_classes": expected,
    }


def _manifest_source_classes(artifacts: list[dict[str, Any]]) -> list[str]:
    values = {str(item.get("source_class") or "").strip() for item in artifacts}
    return sorted(value for value in values if value)


def _has_surface_payload(value: Any) -> bool:
    """Check if a value represents a non-empty surface payload.

    Returns True if value is a non-empty dict, non-empty list, or truthy non-None value.
    """
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
    """Extract query-relevant terms from an institutional actor.

    Returns a list of non-empty string terms from the actor's label, email, and function fields.
    """
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


@dataclass(frozen=True)
class _CaseQueryContext:
    use_german: bool
    target_bits: list[str]
    focus: str
    actor_bits: list[str]
    comparator_bits: list[str]
    context_people_bits: list[str]
    institutional_bits: list[str]
    trigger_types: list[str]
    track_terms: list[str]
    issue_tags: list[str]
    context_notes: str
    has_trigger_events: bool
    has_issue_tracks: bool
    has_issue_tags: bool


@dataclass(frozen=True)
class _CaseLaneContext:
    base_query: str
    use_german: bool
    target_name: str
    actor_terms: list[str]
    institutional_terms: list[str]
    track_terms: list[str]
    tag_terms: list[str]
    trigger_terms: list[str]
    issue_sweep_terms: list[str]
    source_terms: list[str]
    counter_terms: list[str]


def derive_case_analysis_query(params: EmailCaseAnalysisInput) -> str:
    """Return a conservative retrieval query for one case-analysis run."""
    if params.analysis_query:
        return params.analysis_query.strip()
    context = _case_query_context(params)
    query_parts = _base_query_parts(context)
    query_parts.extend(_optional_query_parts(context))
    return ". ".join(part for part in query_parts if part)


def _case_query_context(params: EmailCaseAnalysisInput) -> _CaseQueryContext:
    scope = params.case_scope
    target = scope.target_person
    context_notes = " ".join((scope.context_notes or "").split())
    if len(context_notes) > 180:
        context_notes = context_notes[:177].rstrip() + "..."
    return _CaseQueryContext(
        use_german=str(params.output_language or "").strip().lower() == "de",
        target_bits=[target.name.strip(), *([target.email.strip()] if target.email else [])],
        focus=", ".join(scope.allegation_focus),
        actor_bits=_party_query_bits(scope.suspected_actors[:3]),
        comparator_bits=_party_query_bits(scope.comparator_actors[:3]),
        context_people_bits=_party_query_bits(getattr(scope, "context_people", [])[:4]),
        institutional_bits=[
            " ".join(_institutional_actor_query_bits(actor)[:2]).strip()
            for actor in getattr(scope, "institutional_actors", [])[:4]
            if _institutional_actor_query_bits(actor)
        ],
        trigger_types=[
            str(event.trigger_type).replace("_", " ")
            for event in scope.trigger_events[:3]
            if getattr(event, "trigger_type", None)
        ],
        track_terms=_issue_track_query_terms(scope.employment_issue_tracks[:4]),
        issue_tags=list(scope.employment_issue_tags[:6]),
        context_notes=context_notes,
        has_trigger_events=bool(scope.trigger_events),
        has_issue_tracks=bool(scope.employment_issue_tracks),
        has_issue_tags=bool(scope.employment_issue_tags),
    )


def _party_query_bits(actors: list[Any]) -> list[str]:
    return [" ".join(part for part in [actor.name.strip(), (actor.email or "").strip()] if part).strip() for actor in actors]


def _issue_track_query_terms(tracks: list[Any]) -> list[str]:
    return [
        value
        for track in tracks
        if str(track).strip()
        for value in [str(track).replace("_", " ").strip(), str(track).strip()]
        if value
    ]


def _base_query_parts(context: _CaseQueryContext) -> list[str]:
    if context.use_german:
        return [
            "arbeitsrechtliche fallanalyse",
            f"zielperson {' '.join(bit for bit in context.target_bits if bit)}",
            f"fokus {context.focus}",
        ]
    return [
        "workplace case analysis",
        f"target {' '.join(bit for bit in context.target_bits if bit)}",
        f"focus {context.focus}",
    ]


def _optional_query_parts(context: _CaseQueryContext) -> list[str]:
    labels = _query_labels(context.use_german)
    localized = (
        (context.actor_bits, labels["actors"]),
        (context.comparator_bits, labels["comparators"]),
        (context.context_people_bits, labels["context_people"]),
        (context.institutional_bits, labels["institutional"]),
    )
    parts = [prefix + "; ".join(bit for bit in values if bit) for values, prefix in localized if values]
    if context.has_trigger_events and context.trigger_types:
        parts.append(labels["triggers"] + ", ".join(context.trigger_types))
    if context.has_issue_tracks:
        parts.append(labels["tracks"] + ", ".join(context.track_terms))
    if context.has_issue_tags:
        parts.append(labels["tags"] + ", ".join(context.issue_tags))
    if context.context_notes:
        parts.append(context.context_notes)
    return parts


def _query_labels(use_german: bool) -> dict[str, str]:
    if use_german:
        return {
            "actors": "vermutete akteure ",
            "comparators": "vergleichspersonen ",
            "context_people": "weitere akteure ",
            "institutional": "institutionelle routen ",
            "triggers": "ausloesende ereignisse ",
            "tracks": "themenstraenge ",
            "tags": "themenstichworte ",
        }
    return {
        "actors": "suspected actors ",
        "comparators": "comparators ",
        "context_people": "additional actors ",
        "institutional": "institutional routes ",
        "triggers": "trigger events ",
        "tracks": "issue tracks ",
        "tags": "issue tags ",
    }


def derive_case_analysis_query_lanes(params: EmailCaseAnalysisInput) -> list[str]:
    """Return multi-lane retrieval queries for one case-analysis run."""
    if params.query_lanes:
        return list(params.query_lanes)

    if params.wave_id:
        return derive_wave_query_lanes(params, params.wave_id)
    context = _case_lane_context(params)
    lanes = _raw_case_query_lanes(context)
    lanes.append(_localized_fallback_lane(context))
    return _normalized_query_lanes(lanes)


def _case_lane_context(params: EmailCaseAnalysisInput) -> _CaseLaneContext:
    scope = params.case_scope
    use_german = str(params.output_language or "").strip().lower() == "de"
    actors = [
        *scope.suspected_actors[:4],
        *scope.comparator_actors[:2],
        *getattr(scope, "context_people", [])[:4],
    ]
    issue_sweep_terms = _issue_sweep_terms(use_german)
    return _CaseLaneContext(
        base_query=derive_case_analysis_query(params),
        use_german=use_german,
        target_name=scope.target_person.name.strip(),
        actor_terms=_lane_actor_terms(actors),
        institutional_terms=[
            item
            for actor in getattr(scope, "institutional_actors", [])[:4]
            for item in _institutional_actor_query_bits(actor)[:2]
            if item
        ],
        track_terms=[str(item).replace("_", " ").strip() for item in scope.employment_issue_tracks[:6] if str(item).strip()],
        tag_terms=[str(item).strip() for item in scope.employment_issue_tags[:8] if str(item).strip()],
        trigger_terms=_lane_trigger_terms(scope.trigger_events[:3]),
        issue_sweep_terms=list(dict.fromkeys([*issue_sweep_terms, *shared_wave_vocabulary(limit=12)])),
        source_terms=(
            ["Protokoll", "Kalender", "Anlage", "BEM", "time system", "Einladung"]
            if use_german
            else ["meeting note", "calendar", "attachment", "BEM", "time system", "invite"]
        ),
        counter_terms=(
            ["keine Antwort", "keine Rückmeldung", "abgelehnt", "widerrufen", "ohne Umsetzung"]
            if use_german
            else ["no reply", "no response", "rejected", "withdrawn", "not implemented"]
        ),
    )


def _lane_actor_terms(actors: list[Any]) -> list[str]:
    return [
        item
        for actor in actors
        for item in (
            actor.name.strip() if actor.name and actor.name.strip() else "",
            (actor.email or "").strip(),
            (actor.role_hint or "").strip(),
        )
        if item
    ]


def _lane_trigger_terms(events: list[Any]) -> list[str]:
    return [
        " ".join(
            part
            for part in (
                str(getattr(event, "date", "") or ""),
                str(getattr(event, "trigger_type", "") or "").replace("_", " "),
            )
            if part
        ).strip()
        for event in events
    ]


def _issue_sweep_terms(use_german: bool) -> list[str]:
    if use_german:
        return [
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
    return [
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


def _raw_case_query_lanes(context: _CaseLaneContext) -> list[str]:
    return [
        context.base_query,
        " ".join(
            [
                context.target_name,
                *context.actor_terms[:4],
                *context.institutional_terms[:2],
                *context.track_terms[:3],
                *context.tag_terms[:2],
            ]
        ).strip(),
        " ".join([*context.issue_sweep_terms[:5], *context.track_terms[:3], *context.tag_terms[:2]]).strip(),
        " ".join([context.target_name, *context.trigger_terms[:3], *context.track_terms[:2], *context.tag_terms[:2]]).strip(),
        " ".join(
            [
                context.target_name,
                *context.source_terms[:4],
                *context.institutional_terms[:2],
                *context.counter_terms[:2],
                *context.track_terms[:2],
            ]
        ).strip(),
    ]


def _localized_fallback_lane(context: _CaseLaneContext) -> str:
    if context.use_german:
        return " ".join(
            _ascii_german(item) for item in context.issue_sweep_terms[:4] + context.track_terms[:2] + context.tag_terms[:2]
        ).strip()
    return " ".join(["workplace case analysis", context.target_name, *context.track_terms[:2], *context.tag_terms[:2]]).strip()


def _ascii_german(value: str) -> str:
    return (
        value.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("Ä", "Ae")
        .replace("Ö", "Oe")
        .replace("Ü", "Ue")
        .replace("ß", "ss")
    )


def _normalized_query_lanes(lanes: list[str]) -> list[str]:
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
    warnings.extend(_scope_quality_warnings(params, manifest_sufficiency_payload))
    status = _scope_quality_status(missing_required_fields, missing_recommended_fields, warnings)

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


def _scope_quality_warnings(params: EmailCaseAnalysisInput, manifest_sufficiency_payload: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if _mixed_case_support_missing(params):
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
    if _thin_exhaustive_manifest(params, manifest_sufficiency_payload):
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
    return warnings


def _manifest_payload(params: EmailCaseAnalysisInput) -> dict[str, Any] | None:
    return params.matter_manifest.model_dump(mode="json") if params.matter_manifest is not None else None


def _mixed_case_support_missing(params: EmailCaseAnalysisInput) -> bool:
    support_supplied = any(
        (params.chat_log_entries, params.chat_exports, matter_manifest_has_mixed_artifacts(_manifest_payload(params)))
    )
    return params.source_scope == "mixed_case_file" and not support_supplied


def _thin_exhaustive_manifest(params: EmailCaseAnalysisInput, sufficiency: dict[str, Any]) -> bool:
    return all((params.review_mode == "exhaustive_matter_review", str(sufficiency.get("status") or "") == "thin"))


def _scope_quality_status(missing_required: list[str], missing_recommended: list[str], warnings: list[dict[str, Any]]) -> str:
    if missing_required:
        return "insufficient"
    if warnings or missing_recommended:
        return "degraded"
    return "complete"


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
    entries = _scope_warning_entries(list(missing_information.get("entries") or []), warnings)
    missing_information["entries"] = entries
    missing_information["status"] = "supported" if entries else missing_information.get("status", "insufficient_evidence")
    missing_information["insufficiency_reason"] = "" if entries else missing_information.get("insufficiency_reason", "")
    sections["missing_information"] = missing_information
    report_copy["sections"] = sections
    _update_scope_report_summary(report_copy, sections)
    return report_copy


def _scope_warning_entries(entries: list[Any], warnings: list[dict[str, Any]]) -> list[Any]:
    existing_ids = {str(entry.get("entry_id") or "") for entry in entries if isinstance(entry, dict)}
    for item in warnings:
        entry_id = f"scope_warning:{item['code']}"
        if entry_id in existing_ids:
            continue
        entries.append(_scope_warning_entry(entry_id, item))
    return entries


def _scope_warning_entry(entry_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "statement": str(item.get("message") or ""),
        "supporting_finding_ids": [],
        "supporting_citation_ids": [],
        "supporting_uids": [],
        "warning_code": str(item.get("code") or ""),
        "warning_severity": str(item.get("severity") or ""),
        "affects": [str(affect) for affect in item.get("affects", []) if affect],
    }


def _update_scope_report_summary(report: dict[str, Any], sections: dict[str, Any]) -> None:
    summary = dict(report.get("summary") or {})
    if not summary:
        return
    summary["supported_section_count"] = sum(
        1 for section in sections.values() if isinstance(section, dict) and section.get("status") == "supported"
    )
    summary["insufficient_section_count"] = (
        int(summary.get("section_count") or len(sections)) - summary["supported_section_count"]
    )
    report["summary"] = summary


def analysis_limits(
    params: EmailCaseAnalysisInput,
    payload: dict[str, Any],
    case_scope_quality_payload: dict[str, Any],
    final_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return explicit analysis-limit disclosures."""
    context = _analysis_limit_context(params, payload, final_payload)

    return {
        "source_scope": params.source_scope,
        "review_mode": params.review_mode,
        "missing_source_types": context.missing_source_types,
        "manifest_sufficiency": manifest_sufficiency(params),
        "downgrade_reasons": list(case_scope_quality_payload.get("downgrade_reasons", [])),
        "scope_warnings": [dict(item) for item in case_scope_quality_payload.get("warnings", []) if isinstance(item, dict)],
        "matter_manifest_supplied": params.matter_manifest is not None,
        "completeness_status": str(as_dict(payload.get("matter_ingestion_report")).get("completeness_status") or ""),
        "packing": {
            "applied": bool(context.packing.get("applied")),
            "budget_chars": int(context.packing.get("budget_chars") or 0),
            "estimated_chars_before": int(context.packing.get("estimated_chars_before") or 0),
            "estimated_chars_after": int(context.packing.get("estimated_chars_after") or 0),
            "truncated": dict(context.packing.get("truncated") or {}),
            "deduplicated": dict(context.packing.get("deduplicated") or {}),
        },
        "case_surface_compaction": {
            "removed_count": int(context.compaction.get("removed_count") or 0),
            "removed": [str(item) for item in context.compaction.get("removed", []) if str(item).strip()],
        },
        "omitted_case_analysis_surfaces": context.omitted_surfaces,
        "prompt_complete_behavioral_review": not context.omitted_surfaces,
        "notes": context.notes,
    }


@dataclass(frozen=True)
class _AnalysisLimitContext:
    missing_source_types: list[str]
    packing: dict[str, Any]
    compaction: dict[str, Any]
    omitted_surfaces: list[str]
    notes: list[str]


def _analysis_limit_context(
    params: EmailCaseAnalysisInput, payload: dict[str, Any], final_payload: dict[str, Any] | None
) -> _AnalysisLimitContext:
    missing_source_types = _missing_source_types(payload)
    packing = as_dict(payload.get("_packed"))
    compaction = as_dict(payload.get("_case_surface_compaction"))
    omitted_surfaces = _surface_omissions(answer_payload=payload, final_payload=final_payload)
    notes = [
        *_source_limit_notes(params, missing_source_types),
        *_review_limit_notes(params, payload),
        *_packing_limit_notes(packing, compaction, omitted_surfaces),
    ]
    return _AnalysisLimitContext(missing_source_types, packing, compaction, omitted_surfaces, notes)


def _missing_source_types(payload: dict[str, Any]) -> list[str]:
    multi_source = payload.get("multi_source_case_bundle")
    if not isinstance(multi_source, dict):
        return []
    summary = multi_source.get("summary")
    if not isinstance(summary, dict):
        return []
    return [str(item) for item in summary.get("missing_source_types", []) if item]


def _source_limit_notes(params: EmailCaseAnalysisInput, missing_source_types: list[str]) -> list[str]:
    notes: list[str] = []
    if _mixed_case_support_missing(params):
        notes.append("mixed_case_file_declared_but_no_mixed_record_support_was_supplied")
    chat_support = any(
        (params.chat_log_entries, params.chat_exports, matter_manifest_has_chat_artifacts(_manifest_payload(params)))
    )
    if "chat_log" in missing_source_types and not chat_support:
        notes.append("chat_log_source_type_missing_without_chat_support")
    return notes


def _review_limit_notes(params: EmailCaseAnalysisInput, payload: dict[str, Any]) -> list[str]:
    if params.review_mode == "retrieval_only":
        return ["review_mode_is_retrieval_only"]
    if payload.get("matter_ingestion_report") is None:
        return ["exhaustive_review_requested_without_matter_ingestion_report"]
    return []


def _packing_limit_notes(packing: dict[str, Any], compaction: dict[str, Any], omitted_surfaces: list[str]) -> list[str]:
    notes: list[str] = []
    if bool(packing.get("applied")):
        notes.append("payload_packing_applied")
    if int(compaction.get("removed_count") or 0) > 0:
        notes.append("case_surface_compaction_removed_surfaces")
    if omitted_surfaces:
        notes.append("prompt_critical_surfaces_omitted")
    return notes


def review_classification(
    params: EmailCaseAnalysisInput,
    payload: dict[str, Any],
    *,
    final_payload: dict[str, Any] | None = None,
    analysis_limits_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable classification for review truthfulness."""
    context = _review_context(params, payload, analysis_limits_payload)
    classification, reason, may_present_as_full_review = _review_outcome(context)
    return {
        "review_mode": params.review_mode,
        "classification": classification,
        "is_exhaustive_review": context.is_exhaustive_review,
        "matter_manifest_supplied": context.manifest_supplied,
        "completeness_status": context.completeness_status,
        "may_be_presented_as_full_matter_review": may_present_as_full_review,
        "counsel_use_status": (
            "counsel_grade_exhaustive_review" if may_present_as_full_review else "bounded_or_incomplete_review_only"
        ),
        "reason": reason,
    }


@dataclass(frozen=True)
class _ReviewContext:
    completeness_status: str
    manifest_supplied: bool
    is_exhaustive_review: bool
    manifest_sufficiency_status: str
    omitted_surfaces: list[str]
    may_present_as_full_review: bool


def _review_context(
    params: EmailCaseAnalysisInput,
    payload: dict[str, Any],
    analysis_limits_payload: dict[str, Any] | None,
) -> _ReviewContext:
    completeness_status = str(as_dict(payload.get("matter_ingestion_report")).get("completeness_status") or "")
    manifest_supplied = params.matter_manifest is not None
    is_exhaustive_review = params.review_mode == "exhaustive_matter_review"
    manifest_sufficiency_payload = as_dict((analysis_limits_payload or {}).get("manifest_sufficiency"))
    manifest_sufficiency_status = str(manifest_sufficiency_payload.get("status") or "")
    may_present_as_full_review = all(
        (
            is_exhaustive_review,
            manifest_supplied,
            completeness_status == "complete",
            manifest_sufficiency_status in {"", "sufficient", "not_applicable"},
        )
    )
    omission_summary = analysis_limits_payload or {}
    omitted_surfaces = [str(item) for item in omission_summary.get("omitted_case_analysis_surfaces", []) if str(item).strip()]
    return _ReviewContext(
        completeness_status,
        manifest_supplied,
        is_exhaustive_review,
        manifest_sufficiency_status,
        omitted_surfaces,
        may_present_as_full_review,
    )


def _review_outcome(context: _ReviewContext) -> tuple[str, str, bool]:
    complete_manifest_review = all(
        (context.is_exhaustive_review, context.manifest_supplied, context.completeness_status == "complete")
    )
    if complete_manifest_review and context.omitted_surfaces:
        return (
            "compacted_exhaustive_review_with_omitted_critical_surfaces",
            "Manifest-backed exhaustive review completed with complete supplied-artifact accounting, "
            "but packed compaction omitted prompt-critical analytical surfaces: " + ", ".join(context.omitted_surfaces) + ".",
            False,
        )
    if complete_manifest_review and context.manifest_sufficiency_status == "thin":
        return (
            "manifest_backed_but_materially_thin",
            "Exhaustive review completed with a supplied manifest, but the manifest remains materially thin for the "
            "declared issue tracks and must not be presented as a full matter-file review.",
            False,
        )
    if context.may_present_as_full_review:
        return (
            "counsel_grade_exhaustive_review",
            "Manifest-backed exhaustive review completed with complete supplied-artifact accounting.",
            True,
        )
    if context.is_exhaustive_review and context.manifest_supplied:
        return (
            "manifest_backed_but_not_yet_complete",
            "Exhaustive review was requested with a supplied matter manifest, but completeness accounting is not complete.",
            False,
        )
    if context.is_exhaustive_review:
        return (
            "exhaustive_requested_without_manifest",
            "Exhaustive review was requested, but no matter manifest was supplied.",
            False,
        )
    return (
        "retrieval_bounded_exploratory_review",
        "The current run is retrieval-bounded and must not be presented as a full matter-file review.",
        False,
    )
