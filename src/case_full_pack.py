"""Compile-only full-pack intake for prompt plus materials workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .case_analysis import build_case_analysis_payload
from .case_material_intake import build_case_material_preflight
from .case_operator_intake import build_manifest_from_materials_dir, matter_manifest_has_mixed_artifacts
from .case_prompt_intake import build_case_prompt_preflight
from .case_prompt_preflight_normalization import normalize_prompt_preflight_case_input
from .legal_support_exporter import LegalSupportExporter
from .matter_file_ingestion import enrich_matter_manifest, infer_matter_manifest_authorized_roots
from .mcp_models import (
    EmailCaseFullPackInput,
    EmailCasePromptPreflightInput,
    EmailLegalSupportExportInput,
    EmailLegalSupportInput,
)

FULL_PACK_VERSION = "1"


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Return a recursive dict merge where override values win."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(_as_dict(merged[key]), value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _build_preflight(params: EmailCaseFullPackInput) -> dict[str, Any]:
    return build_case_prompt_preflight(
        EmailCasePromptPreflightInput.model_validate(
            {
                "prompt_text": params.prompt_text,
                "output_language": params.output_language,
                "default_source_scope": params.default_source_scope,
                "assume_date_to_today": params.assume_date_to_today,
                "today": params.today,
            }
        )
    )


def _derive_source_scope(
    *,
    compiled_input: dict[str, object],
    preflight: dict[str, Any],
    manifest: dict[str, Any],
    explicit_override: bool,
) -> str:
    has_chat_entries = bool(_as_list(compiled_input.get("chat_log_entries")))
    has_chat_exports = bool(_as_list(compiled_input.get("chat_exports")))
    has_mixed_support = has_chat_entries or has_chat_exports or matter_manifest_has_mixed_artifacts(manifest)
    override_scope = str(compiled_input.get("source_scope") or "").strip()
    if explicit_override and override_scope:
        if override_scope == "mixed_case_file" and not has_mixed_support:
            return "emails_and_attachments"
        return override_scope
    if has_mixed_support:
        return "mixed_case_file"
    if override_scope == "mixed_case_file":
        return "emails_and_attachments"
    if override_scope:
        return override_scope
    recommended_scope = str(preflight.get("recommended_source_scope") or "emails_and_attachments")
    if recommended_scope == "mixed_case_file":
        return "emails_and_attachments"
    return recommended_scope


def _conditional_blockers(case_scope: dict[str, object]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    allegation_focus = {str(item).strip() for item in _as_list(case_scope.get("allegation_focus")) if str(item).strip()}
    issue_tracks = {str(item).strip() for item in _as_list(case_scope.get("employment_issue_tracks")) if str(item).strip()}
    if "retaliation" in allegation_focus and not _as_list(case_scope.get("trigger_events")):
        blockers.append(
            {
                "field": "case_scope.trigger_events",
                "severity": "blocking",
                "reason": "Retaliation review requires explicit dated trigger events before a full-pack run can proceed.",
            }
        )
    if "retaliation_after_protected_event" in issue_tracks and not _as_list(case_scope.get("alleged_adverse_actions")):
        blockers.append(
            {
                "field": "case_scope.alleged_adverse_actions",
                "severity": "blocking",
                "reason": (
                    "Retaliation timeline review also needs structured dated adverse actions before a full-pack run can proceed."
                ),
            }
        )
    if allegation_focus & {"unequal_treatment", "discrimination"} and not _as_list(case_scope.get("comparator_actors")):
        blockers.append(
            {
                "field": "case_scope.comparator_actors",
                "severity": "blocking",
                "reason": "Comparator-based review requires explicit comparator actors before a full-pack run can proceed.",
            }
        )
    return blockers


def _sanitize_case_scope_for_validation(case_scope: dict[str, object]) -> dict[str, object]:
    """Drop prompt-preflight helper keys that are not part of the strict case-scope schema."""
    sanitized = deepcopy(case_scope)

    def _sanitize_party(value: object) -> dict[str, object]:
        party = deepcopy(_as_dict(value))
        party.pop("extraction_basis", None)
        return party

    sanitized["target_person"] = _sanitize_party(sanitized.get("target_person"))
    sanitized["suspected_actors"] = [_sanitize_party(item) for item in _as_list(sanitized.get("suspected_actors"))]
    sanitized["comparator_actors"] = [_sanitize_party(item) for item in _as_list(sanitized.get("comparator_actors"))]
    sanitized["trigger_events"] = [
        {key: value for key, value in _as_dict(item).items() if key != "date_confidence"}
        for item in _as_list(sanitized.get("trigger_events"))
    ]
    return sanitized


def _required_blockers(case_scope: dict[str, object]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    target_person = _as_dict(case_scope.get("target_person"))
    if not str(target_person.get("name") or "").strip():
        blockers.append(
            {
                "field": "case_scope.target_person",
                "severity": "blocking",
                "reason": "The compiled intake does not identify the target person clearly enough for a full-pack run.",
            }
        )
    if not str(case_scope.get("date_from") or "").strip():
        blockers.append(
            {
                "field": "case_scope.date_from",
                "severity": "blocking",
                "reason": "The compiled intake does not contain a bounded review start date.",
            }
        )
    if not str(case_scope.get("date_to") or "").strip():
        blockers.append(
            {
                "field": "case_scope.date_to",
                "severity": "blocking",
                "reason": "The compiled intake does not contain a bounded review end date.",
            }
        )
    return blockers


def _unique_blockers(blockers: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for blocker in blockers:
        field = str(blocker.get("field") or "").strip()
        reason = str(blocker.get("reason") or "").strip()
        if not field or not reason:
            continue
        deduped[(field, reason)] = {
            "field": field,
            "severity": str(blocker.get("severity") or "blocking"),
            "reason": reason,
        }
    return list(deduped.values())


def _repair_candidates(
    *,
    field: str,
    candidate_structures: dict[str, Any],
    draft_case_scope: dict[str, Any],
) -> list[dict[str, Any]]:
    if field == "case_scope.target_person":
        target_person = _as_dict(draft_case_scope.get("target_person"))
        if str(target_person.get("name") or "").strip():
            return [
                {
                    "candidate_id": "draft_case_scope.target_person",
                    "confidence": "medium",
                    "candidate_value": target_person,
                    "source": "draft_case_scope.target_person",
                }
            ]
        return [
            {
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "candidate_value": item["candidate_value"],
                "source_span": item.get("source_span"),
                "source_artifact": item.get("source_artifact"),
                "warning": item["warning"],
            }
            for item in candidate_structures.get("target_person_candidates", [])
            if _as_dict(item.get("candidate_value")).get("name")
        ]
    if field == "case_scope.date_from":
        value = str(draft_case_scope.get("date_from") or "").strip()
        if value:
            return [{"candidate_id": "draft_case_scope.date_from", "confidence": "medium", "candidate_value": value}]
        return [
            {
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "candidate_value": item["candidate_value"],
                "source_span": item.get("source_span"),
                "source_artifact": item.get("source_artifact"),
                "warning": item["warning"],
            }
            for item in candidate_structures.get("date_from_candidates", [])
            if str(item.get("candidate_value") or "").strip()
        ]
    if field == "case_scope.date_to":
        value = str(draft_case_scope.get("date_to") or "").strip()
        if value:
            return [{"candidate_id": "draft_case_scope.date_to", "confidence": "medium", "candidate_value": value}]
        return [
            {
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "candidate_value": item["candidate_value"],
                "source_span": item.get("source_span"),
                "source_artifact": item.get("source_artifact"),
                "warning": item["warning"],
            }
            for item in candidate_structures.get("date_to_candidates", [])
            if str(item.get("candidate_value") or "").strip()
        ]
    if field == "case_scope.trigger_events":
        return [
            {
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "candidate_value": item["candidate_value"],
                "source_span": item["source_span"],
                "warning": item["warning"],
            }
            for item in candidate_structures.get("trigger_event_candidates", [])
            if str(item.get("confidence") or "") in {"medium", "high"}
        ]
    if field == "case_scope.alleged_adverse_actions":
        return [
            {
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "candidate_value": item["candidate_value"],
                "source_span": item["source_span"],
                "warning": item["warning"],
            }
            for item in candidate_structures.get("adverse_action_candidates", [])
            if str(item.get("confidence") or "") in {"medium", "high"}
        ]
    if field == "case_scope.comparator_actors":
        return [
            {
                "candidate_id": item["candidate_id"],
                "confidence": item["confidence"],
                "candidate_value": item["candidate_value"],
                "source_span": item["source_span"],
                "warning": item["warning"],
            }
            for item in candidate_structures.get("comparator_candidates", [])
            if str(item.get("confidence") or "") in {"medium", "high"}
        ]
    return []


def _minimal_override_example(*, field: str, candidate_values: list[dict[str, Any]]) -> dict[str, Any] | None:
    required_value_by_field: dict[str, Any] = {
        "case_scope.target_person": {"name": None},
        "case_scope.date_from": None,
        "case_scope.date_to": None,
        "case_scope.trigger_events": {"trigger_type": None, "date": None},
        "case_scope.alleged_adverse_actions": {"action_type": None, "date": None},
        "case_scope.comparator_actors": {"name": None},
    }
    if field == "case_scope.target_person":
        value = candidate_values[0]["candidate_value"] if candidate_values else required_value_by_field[field]
        return {"case_scope": {"target_person": value}}
    if field == "case_scope.date_from":
        value = candidate_values[0]["candidate_value"] if candidate_values else required_value_by_field[field]
        return {"case_scope": {"date_from": value}}
    if field == "case_scope.date_to":
        value = candidate_values[0]["candidate_value"] if candidate_values else required_value_by_field[field]
        return {"case_scope": {"date_to": value}}
    if field == "case_scope.trigger_events":
        value = candidate_values[0]["candidate_value"] if candidate_values else required_value_by_field[field]
        return {"case_scope": {"trigger_events": [value]}}
    if field == "case_scope.alleged_adverse_actions":
        value = candidate_values[0]["candidate_value"] if candidate_values else required_value_by_field[field]
        return {"case_scope": {"alleged_adverse_actions": [value]}}
    if field == "case_scope.comparator_actors":
        value = candidate_values[0]["candidate_value"] if candidate_values else required_value_by_field[field]
        return {"case_scope": {"comparator_actors": [value]}}
    return None


def _required_fields(field: str) -> list[str]:
    mapping = {
        "case_scope.target_person": ["name"],
        "case_scope.date_from": ["date_from"],
        "case_scope.date_to": ["date_to"],
        "case_scope.trigger_events": ["trigger_type", "date"],
        "case_scope.alleged_adverse_actions": ["action_type", "date"],
        "case_scope.comparator_actors": ["name"],
    }
    return mapping.get(field, [])


def _override_suggestions(
    *,
    blockers: list[dict[str, str]],
    compilation_support: dict[str, Any],
) -> dict[str, Any]:
    draft_case_scope = _as_dict(compilation_support.get("draft_case_scope"))
    candidate_structures = _as_dict(compilation_support.get("candidate_structures"))
    suggestions: list[dict[str, Any]] = []
    for blocker in blockers:
        field = str(blocker.get("field") or "").strip()
        if not field.startswith("case_scope."):
            continue
        candidate_values = _repair_candidates(
            field=field,
            candidate_structures=candidate_structures,
            draft_case_scope=draft_case_scope,
        )
        suggestions.append(
            {
                "field": field,
                "reason": blocker["reason"],
                "required_fields": _required_fields(field),
                "candidate_values": candidate_values,
                "candidate_values_adequate": bool(candidate_values),
                "minimal_override_example": _minimal_override_example(field=field, candidate_values=candidate_values),
            }
        )
    example_override_json: dict[str, Any] = {}
    for item in suggestions:
        example = item.get("minimal_override_example")
        if isinstance(example, dict):
            example_override_json = _deep_merge(example_override_json, example)
    return {
        "version": "1",
        "repair_mode": "explicit_override_required",
        "blocked_fields": [item["field"] for item in suggestions],
        "suggestions": suggestions,
        "example_override_json": example_override_json,
    }


def _merge_candidate_structures(*candidate_structures: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    keys = (
        "target_person_candidates",
        "date_from_candidates",
        "date_to_candidates",
        "trigger_event_candidates",
        "adverse_action_candidates",
        "comparator_candidates",
        "protected_context_candidates",
        "missing_record_candidates",
    )
    for key in keys:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate_structure in candidate_structures:
            for item in _as_list(candidate_structure.get(key)):
                if not isinstance(item, dict):
                    continue
                fingerprint = str(item.get("candidate_id") or "") or str(item.get("candidate_value") or "")
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                rows.append(item)
        if rows:
            merged[key] = rows
    merged["summary"] = {
        "target_person_candidate_count": len(_as_list(merged.get("target_person_candidates"))),
        "date_from_candidate_count": len(_as_list(merged.get("date_from_candidates"))),
        "date_to_candidate_count": len(_as_list(merged.get("date_to_candidates"))),
        "trigger_event_candidate_count": len(_as_list(merged.get("trigger_event_candidates"))),
        "adverse_action_candidate_count": len(_as_list(merged.get("adverse_action_candidates"))),
        "comparator_candidate_count": len(_as_list(merged.get("comparator_candidates"))),
        "protected_context_candidate_count": len(_as_list(merged.get("protected_context_candidates"))),
        "missing_record_candidate_count": len(_as_list(merged.get("missing_record_candidates"))),
    }
    return merged


def build_case_full_pack(params: EmailCaseFullPackInput) -> dict[str, Any]:
    """Compile prompt preflight plus manifest intake into a blocked-or-ready full-pack draft."""
    preflight = _build_preflight(params)
    manifest = build_manifest_from_materials_dir(params.materials_dir)
    enriched_manifest = enrich_matter_manifest(
        manifest,
        approved_roots=infer_matter_manifest_authorized_roots(manifest),
    )
    materials_preflight = build_case_material_preflight(enriched_manifest)
    normalized_preflight_input = normalize_prompt_preflight_case_input(preflight)

    compiled_input: dict[str, object] = {
        **deepcopy(normalized_preflight_input),
        "review_mode": "exhaustive_matter_review",
        "matter_manifest": manifest,
        "privacy_mode": params.privacy_mode,
        "output_language": params.output_language,
        "translation_mode": params.translation_mode,
    }
    compiled_input["case_scope"] = _deep_merge(
        _as_dict(compiled_input.get("case_scope")),
        _as_dict(materials_preflight.get("auto_fill_case_scope")),
    )
    compiled_input = _deep_merge(compiled_input, params.intake_overrides)
    compiled_input["source_scope"] = _derive_source_scope(
        compiled_input=compiled_input,
        preflight=preflight,
        manifest=manifest,
        explicit_override="source_scope" in params.intake_overrides,
    )
    case_scope = _sanitize_case_scope_for_validation(_as_dict(compiled_input.get("case_scope")))
    compiled_input["case_scope"] = case_scope

    blockers = [
        *_required_blockers(case_scope),
        *_conditional_blockers(case_scope),
    ]
    if not _as_list(manifest.get("artifacts")):
        blockers.append(
            {
                "field": "matter_manifest.artifacts",
                "severity": "blocking",
                "reason": "The supplied materials directory does not contain any files for exhaustive matter review.",
            }
        )

    validation_errors: list[str] = []
    if not blockers:
        try:
            validated = EmailLegalSupportInput.model_validate(compiled_input)
        except ValueError as exc:
            validation_errors.append(str(exc))
            blockers.append(
                {
                    "field": "compiled_legal_support_input",
                    "severity": "blocking",
                    "reason": str(exc),
                }
            )
        else:
            compiled_input = validated.model_dump(mode="json")

    blockers = _unique_blockers(blockers)
    status = "blocked" if blockers else "ready"
    override_suggestions = (
        _override_suggestions(
            blockers=blockers,
            compilation_support={
                "draft_case_scope": case_scope,
                "candidate_structures": _merge_candidate_structures(
                    _as_dict(preflight.get("candidate_structures")),
                    _as_dict(materials_preflight.get("candidate_structures")),
                ),
            },
        )
        if blockers
        else None
    )
    return {
        "version": FULL_PACK_VERSION,
        "workflow": "case_full_pack",
        "status": status,
        "blockers": blockers,
        "intake_compilation": {
            "prompt_preflight": preflight,
            "materials_preflight": materials_preflight,
            "applied_overrides": params.intake_overrides,
            "supports_exhaustive_run": status == "ready",
            "validation_error_count": len(validation_errors),
            "validation_errors": validation_errors,
            "override_suggestions": override_suggestions,
        },
        "matter_manifest": manifest,
        "compiled_legal_support_input": compiled_input,
        "next_step": (
            "Run the compiled legal-support input through the downstream exhaustive case-analysis workflow."
            if status == "ready"
            else "Resolve the blockers before attempting the exhaustive full-pack workflow."
        ),
    }


def _record_export_result(
    *,
    deps: Any,
    payload: dict[str, Any],
    result: dict[str, Any],
    params: EmailCaseFullPackInput,
) -> dict[str, Any]:
    """Persist export lineage when the current deps expose the matter snapshot store."""
    persistence = _as_dict(payload.get("matter_persistence"))
    snapshot_id = str(persistence.get("snapshot_id") or "")
    workspace_id = str(persistence.get("workspace_id") or "")
    if not snapshot_id or not workspace_id:
        return result
    get_email_db = getattr(deps, "get_email_db", None)
    email_db = get_email_db() if callable(get_email_db) else None
    email_db_any: Any = email_db
    record_matter_export = getattr(email_db_any, "record_matter_export", None)
    if email_db_any is None or not callable(record_matter_export):
        return result
    result["recorded_export"] = record_matter_export(
        snapshot_id=snapshot_id,
        workspace_id=workspace_id,
        delivery_target=params.delivery_target,
        delivery_format=params.delivery_format,
        output_path=str(result.get("output_path") or params.output_path or ""),
        review_state=str(persistence.get("review_state") or ""),
        details={"export_metadata": result.get("export_metadata")},
    )
    return result


async def execute_case_full_pack(deps: Any, params: EmailCaseFullPackInput) -> dict[str, Any]:
    """Execute the full-pack workflow after compile/gate validation."""
    compiled = build_case_full_pack(params)
    if compiled["status"] != "ready" or params.compile_only:
        if params.compile_only and compiled["status"] == "ready":
            compiled["execution"] = {
                "status": "not_run",
                "reason": "compile_only_requested",
            }
        return compiled

    legal_support_params = EmailLegalSupportInput.model_validate(compiled["compiled_legal_support_input"])
    full_params = legal_support_params.model_copy(update={"output_mode": "full_report"})
    full_case_analysis = await build_case_analysis_payload(deps, full_params)

    result: dict[str, Any] = {
        **compiled,
        "status": "completed",
        "execution": {
            "status": "completed",
            "review_mode": full_params.review_mode,
            "source_scope": full_params.source_scope,
            "export_requested": bool(params.output_path),
        },
        "full_case_analysis": full_case_analysis,
    }

    if params.output_path is not None:
        export_params = EmailLegalSupportExportInput.model_validate(
            compiled["compiled_legal_support_input"]
            | {
                "delivery_target": params.delivery_target,
                "delivery_format": params.delivery_format,
                "output_path": params.output_path,
            }
        )
        exporter = LegalSupportExporter()
        try:
            export_result = exporter.export_file(
                payload=full_case_analysis,
                output_path=export_params.output_path,
                delivery_target=export_params.delivery_target,
                delivery_format=export_params.delivery_format,
            )
        except ValueError as exc:
            if str(exc).startswith("Counsel-facing export blocked until readiness issues are resolved:"):
                export_status = exporter.counsel_export_status(payload=full_case_analysis)
                result["status"] = "blocked"
                result["execution"] = {
                    "status": "blocked",
                    "review_mode": full_params.review_mode,
                    "source_scope": full_params.source_scope,
                    "export_requested": True,
                    "reason": "export_readiness_gate_blocked",
                }
                result["export_result"] = None
                result["export_readiness"] = export_status
                result["next_step"] = "Resolve the export-readiness blockers before attempting the counsel-facing artifact."
                return result
            raise
        result["export_result"] = _record_export_result(
            deps=deps,
            payload=full_case_analysis,
            result=export_result,
            params=params,
        )
    else:
        result["export_result"] = None

    result["next_step"] = (
        "Review the full case-analysis payload and exported artifact."
        if params.output_path is not None
        else "Review the full case-analysis payload or provide output_path to export an artifact."
    )
    return result
