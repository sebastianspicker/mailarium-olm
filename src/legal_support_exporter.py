"""Portable export and delivery formats for shared legal-support products."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .formatting import write_html_or_pdf

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _csv_safe(value: Any) -> str:
    text = str(value) if value is not None else ""
    if text and text[0] in _CSV_FORMULA_PREFIXES:
        return f"'{text}"
    return text


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def _rendered_at() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _downgrade_markers(payload: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    for marker in _as_list(_as_dict(payload.get("case_scope_quality")).get("downgrade_reasons")):
        text = str(marker).strip()
        if text and text not in markers:
            markers.append(text)
    for marker in _as_list(_as_dict(payload.get("analysis_limits")).get("notes")):
        text = str(marker).strip()
        if text and text not in markers:
            markers.append(text)
    completeness_status = str(_as_dict(payload.get("matter_ingestion_report")).get("completeness_status") or "")
    if completeness_status and completeness_status != "complete":
        markers.append(f"matter_ingestion:{completeness_status}")
    coverage_status = str(_as_dict(_as_dict(payload.get("matter_coverage_ledger")).get("summary")).get("coverage_status") or "")
    if coverage_status and coverage_status != "complete":
        markers.append(f"coverage:{coverage_status}")
    return markers


def _export_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    persistence = _as_dict(payload.get("matter_persistence"))
    changes = _as_dict(persistence.get("changes_since_last_approved"))
    coverage_status = str(_as_dict(_as_dict(payload.get("matter_coverage_ledger")).get("summary")).get("coverage_status") or "")
    return {
        "generated_at": _rendered_at(),
        "snapshot_id": str(persistence.get("snapshot_id") or ""),
        "workspace_id": str(persistence.get("workspace_id") or ""),
        "matter_id": str(persistence.get("matter_id") or ""),
        "snapshot_review_state": str(persistence.get("review_state") or ""),
        "last_approved_snapshot_id": str(persistence.get("last_approved_snapshot_id") or ""),
        "changes_since_last_approved": (
            {
                "changed": bool(changes.get("changed")),
                "changed_registries": [str(item) for item in _as_list(changes.get("changed_registries")) if item],
            }
            if changes
            else None
        ),
        "coverage_status": coverage_status,
        "completeness_status": str(_as_dict(payload.get("matter_ingestion_report")).get("completeness_status") or ""),
        "review_classification": _as_dict(payload.get("review_classification")),
        "downgrade_markers": _downgrade_markers(payload),
    }


def _counsel_export_readiness(export_metadata: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    review_state = str(export_metadata.get("snapshot_review_state") or "")
    persisted_snapshot_present = any(
        str(export_metadata.get(field) or "").strip() for field in ("snapshot_id", "workspace_id", "matter_id")
    )
    required_review_states = ["human_verified", "export_approved"]
    recommended_internal_targets = ["dashboard", "exhibit_register"]
    if review_state in {"machine_extracted", "draft_only"}:
        policy_state = "internal_only"
        next_step = (
            "Promote the persisted snapshot to human_verified or export_approved after human review before "
            "counsel-facing export. Until then, use dashboard or exhibit_register for internal handoff."
        )
    elif review_state == "disputed":
        policy_state = "human_resolution_required"
        next_step = (
            "Resolve the disputed snapshot review state or publish a human_verified/export_approved snapshot "
            "before counsel-facing export."
        )
    elif review_state in {"human_verified", "export_approved"}:
        policy_state = "counsel_ready"
        next_step = "Counsel-facing export may proceed if completeness and coverage checks also pass."
    elif review_state == "approved":
        policy_state = "unsupported_review_state"
        next_step = (
            "Update the persisted snapshot review state to human_verified or export_approved before counsel-facing export."
        )
    elif not review_state and not persisted_snapshot_present:
        policy_state = "snapshot_missing"
        next_step = (
            "Persist the snapshot, complete human review, and promote it to human_verified or export_approved before "
            "counsel-facing export. Until then, use dashboard or exhibit_register for internal handoff."
        )
    else:
        policy_state = "review_state_missing"
        next_step = (
            "Persist and review the snapshot before counsel-facing export. Until then, use dashboard or exhibit_register "
            "for internal handoff."
        )
    if review_state not in {"human_verified", "export_approved"}:
        blockers.append(f"snapshot_review_state:{review_state or 'missing'}")
    completeness_status = str(export_metadata.get("completeness_status") or "")
    if completeness_status != "complete":
        blockers.append(f"completeness_status:{completeness_status or 'missing'}")
    coverage_status = str(export_metadata.get("coverage_status") or "")
    if coverage_status != "complete":
        blockers.append(f"coverage_status:{coverage_status or 'missing'}")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "policy_state": policy_state,
        "required_review_states": required_review_states,
        "recommended_internal_targets": recommended_internal_targets,
        "next_step": next_step,
    }


def _memo_lines(payload: dict[str, Any]) -> list[dict[str, Any]]:
    memo = _as_dict(payload.get("lawyer_briefing_memo"))
    sections = _as_dict(memo.get("sections"))
    return [item for item in _as_list(sections.get("executive_summary")) if isinstance(item, dict)]


def _dashboard_cards(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    cards = _as_dict(_as_dict(payload.get("case_dashboard")).get("cards"))
    return {
        key: [item for item in _as_list(value) if isinstance(item, dict)]
        for key, value in cards.items()
        if isinstance(value, list)
    }


def _issue_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("lawyer_issue_matrix")).get("rows")) if isinstance(row, dict)]


def _exhibit_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("matter_evidence_index")).get("rows")) if isinstance(row, dict)]


def _chronology_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in _as_list(_as_dict(payload.get("master_chronology")).get("entries")) if isinstance(entry, dict)]


def _conflict_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    summary = _as_dict(_as_dict(payload.get("master_chronology")).get("summary"))
    registry = _as_dict(summary.get("source_conflict_registry"))
    return [row for row in _as_list(registry.get("conflicts")) if isinstance(row, dict)]


class LegalSupportExporter:
    """Write durable legal-support artifacts from the shared case-analysis payload."""

    def __init__(self) -> None:
        self._env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

    def counsel_export_status(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        """Return counsel-export readiness plus export metadata for one payload."""
        export_metadata = _export_metadata(payload)
        export_metadata["counsel_export_readiness"] = _counsel_export_readiness(export_metadata)
        readiness = _as_dict(export_metadata.get("counsel_export_readiness"))
        return {
            "ready": bool(readiness.get("ready")),
            "blockers": [str(item) for item in _as_list(readiness.get("blockers")) if item],
            "export_metadata": export_metadata,
        }

    def export_file(
        self,
        *,
        payload: dict[str, Any],
        output_path: str,
        delivery_target: str,
        delivery_format: str,
    ) -> dict[str, Any]:
        """Write one delivery artifact to disk."""
        target = str(delivery_target or "").strip()
        fmt = str(delivery_format or "").strip()
        output = Path(output_path)
        if output.exists():
            raise ValueError(f"Output path already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        export_status = self.counsel_export_status(payload=payload)
        export_metadata = _as_dict(export_status.get("export_metadata"))

        if target == "counsel_handoff":
            if not bool(export_status.get("ready")):
                blockers = ", ".join(str(item) for item in _as_list(export_status.get("blockers")) if item)
                raise ValueError(f"Counsel-facing export blocked until readiness issues are resolved: {blockers}")
            html = self._render_counsel_handoff_html(payload, export_metadata=export_metadata)
            result = write_html_or_pdf(html, str(output), fmt)
            return {
                "workflow": "legal_support_export",
                "delivery_target": target,
                "delivery_format": result.get("format") or fmt,
                "output_path": str(result.get("output_path") or output),
                "analysis_query": str(payload.get("analysis_query") or ""),
                "note": result.get("note"),
                "export_metadata": export_metadata,
            }

        if target == "exhibit_register":
            if fmt == "json":
                text = _json_text(
                    {
                        "workflow": "legal_support_export",
                        "delivery_target": target,
                        "analysis_query": str(payload.get("analysis_query") or ""),
                        "export_metadata": export_metadata,
                        "matter_evidence_index": payload.get("matter_evidence_index"),
                    }
                )
                output.write_text(text, encoding="utf-8")
                row_count = int(_as_dict(payload.get("matter_evidence_index")).get("row_count") or 0)
                return {
                    "workflow": "legal_support_export",
                    "delivery_target": target,
                    "delivery_format": "json",
                    "output_path": str(output),
                    "row_count": row_count,
                    "spreadsheet_ready": False,
                    "export_metadata": export_metadata,
                }
            csv_text = self._exhibit_register_csv(payload, export_metadata=export_metadata)
            output.write_text(csv_text, encoding="utf-8")
            row_count = int(_as_dict(payload.get("matter_evidence_index")).get("row_count") or 0)
            return {
                "workflow": "legal_support_export",
                "delivery_target": target,
                "delivery_format": "csv",
                "output_path": str(output),
                "row_count": row_count,
                "spreadsheet_ready": True,
                "export_metadata": export_metadata,
            }

        if target == "dashboard":
            if fmt == "csv":
                csv_text = self._dashboard_csv(payload, export_metadata=export_metadata)
                output.write_text(csv_text, encoding="utf-8")
                card_count = sum(len(items) for items in _dashboard_cards(payload).values())
                return {
                    "workflow": "legal_support_export",
                    "delivery_target": target,
                    "delivery_format": "csv",
                    "output_path": str(output),
                    "card_count": card_count,
                    "spreadsheet_ready": True,
                    "export_metadata": export_metadata,
                }
            dashboard_payload = {
                "workflow": "legal_support_export",
                "delivery_target": target,
                "analysis_query": str(payload.get("analysis_query") or ""),
                "export_metadata": export_metadata,
                "case_dashboard": payload.get("case_dashboard"),
            }
            output.write_text(_json_text(dashboard_payload), encoding="utf-8")
            card_count = sum(len(items) for items in _dashboard_cards(payload).values())
            return {
                "workflow": "legal_support_export",
                "delivery_target": target,
                "delivery_format": "json",
                "output_path": str(output),
                "card_count": card_count,
                "spreadsheet_ready": False,
                "export_metadata": export_metadata,
            }

        if target == "counsel_handoff_bundle":
            if not bool(export_status.get("ready")):
                blockers = ", ".join(str(item) for item in _as_list(export_status.get("blockers")) if item)
                raise ValueError(f"Counsel-facing export blocked until readiness issues are resolved: {blockers}")
            manifest = self._write_bundle(payload, output, export_metadata=export_metadata)
            return {
                "workflow": "legal_support_export",
                "delivery_target": target,
                "delivery_format": "bundle",
                "output_path": str(output),
                "artifact_count": len(_as_list(manifest.get("artifacts"))),
                "manifest": manifest,
                "export_metadata": export_metadata,
            }

        raise ValueError(f"Unsupported delivery_target: {target}")

    def _render_counsel_handoff_html(self, payload: dict[str, Any], *, export_metadata: dict[str, Any]) -> str:
        template = self._env.get_template("legal_support_handoff.html")
        return template.render(
            title="Counsel Handoff",
            generated_at=export_metadata.get("generated_at") or _rendered_at(),
            analysis_query=str(payload.get("analysis_query") or ""),
            review_mode=str(payload.get("review_mode") or ""),
            privacy_guardrails=_as_dict(payload.get("privacy_guardrails")),
            case_scope_quality=_as_dict(payload.get("case_scope_quality")),
            matter_ingestion_report=_as_dict(payload.get("matter_ingestion_report")),
            export_metadata=export_metadata,
            memo_lines=_memo_lines(payload),
            dashboard_cards=_dashboard_cards(payload),
            issue_rows=_issue_rows(payload)[:6],
            exhibit_rows=_exhibit_rows(payload)[:12],
            chronology_entries=_chronology_entries(payload)[:10],
            conflict_rows=_conflict_rows(payload)[:6],
            checklist_groups=[
                group
                for group in _as_list(_as_dict(payload.get("document_request_checklist")).get("groups"))
                if isinstance(group, dict)
            ][:6],
        )

    def _exhibit_register_csv(self, payload: dict[str, Any], *, export_metadata: dict[str, Any]) -> str:
        rows = _exhibit_rows(payload)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "exhibit_id",
                "date",
                "document_type",
                "sender_or_author",
                "recipients",
                "short_description",
                "main_issue_tags",
                "why_it_matters",
                "reliability_strength",
                "reliability_readiness",
                "source_id",
                "source_conflict_status",
                "source_conflict_ids",
                "supporting_citation_ids",
                "follow_up_needed",
                "snapshot_id",
                "snapshot_review_state",
                "coverage_status",
                "downgrade_markers",
            ]
        )
        for row in rows:
            reliability = _as_dict(row.get("exhibit_reliability"))
            next_steps = _as_dict(reliability.get("next_step_logic"))
            writer.writerow(
                [
                    _csv_safe(row.get("exhibit_id")),
                    _csv_safe(row.get("date")),
                    _csv_safe(row.get("document_type")),
                    _csv_safe(row.get("sender_or_author")),
                    _csv_safe(", ".join(str(item) for item in _as_list(row.get("recipients")) if item)),
                    _csv_safe(row.get("short_description")),
                    _csv_safe(", ".join(str(item) for item in _as_list(row.get("main_issue_tags")) if item)),
                    _csv_safe(row.get("why_it_matters")),
                    _csv_safe(reliability.get("strength")),
                    _csv_safe(next_steps.get("readiness")),
                    _csv_safe(row.get("source_id")),
                    _csv_safe(row.get("source_conflict_status")),
                    _csv_safe(", ".join(str(item) for item in _as_list(row.get("source_conflict_ids")) if item)),
                    _csv_safe(", ".join(str(item) for item in _as_list(row.get("supporting_citation_ids")) if item)),
                    _csv_safe("; ".join(str(item) for item in _as_list(row.get("follow_up_needed")) if item)),
                    _csv_safe(export_metadata.get("snapshot_id")),
                    _csv_safe(export_metadata.get("snapshot_review_state")),
                    _csv_safe(export_metadata.get("coverage_status")),
                    _csv_safe(", ".join(str(item) for item in _as_list(export_metadata.get("downgrade_markers")) if item)),
                ]
            )
        return output.getvalue()

    def _dashboard_csv(self, payload: dict[str, Any], *, export_metadata: dict[str, Any]) -> str:
        cards = _dashboard_cards(payload)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "card_group",
                "entry_id",
                "title",
                "summary",
                "linked_ids",
                "citation_ids",
                "snapshot_id",
                "snapshot_review_state",
                "coverage_status",
                "downgrade_markers",
            ]
        )
        for group_name, items in cards.items():
            for item in items:
                linked_ids = []
                for key in ("supporting_exhibit_ids", "supporting_chronology_ids", "supporting_issue_ids"):
                    linked_ids.extend([str(value) for value in _as_list(item.get(key)) if str(value).strip()])
                citation_ids = [str(value) for value in _as_list(item.get("supporting_citation_ids")) if str(value).strip()]
                writer.writerow(
                    [
                        _csv_safe(group_name),
                        _csv_safe(item.get("entry_id")),
                        _csv_safe(item.get("title")),
                        _csv_safe(item.get("summary")),
                        _csv_safe(", ".join(linked_ids[:6])),
                        _csv_safe(", ".join(citation_ids[:6])),
                        _csv_safe(export_metadata.get("snapshot_id")),
                        _csv_safe(export_metadata.get("snapshot_review_state")),
                        _csv_safe(export_metadata.get("coverage_status")),
                        _csv_safe(", ".join(str(item) for item in _as_list(export_metadata.get("downgrade_markers")) if item)),
                    ]
                )
        return output.getvalue()

    def _bundle_manifest(
        self,
        payload: dict[str, Any],
        artifacts: list[dict[str, Any]],
        *,
        export_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "bundle_version": "1",
            "workflow": "legal_support_export",
            "delivery_target": "counsel_handoff_bundle",
            "generated_at": export_metadata.get("generated_at") or _rendered_at(),
            "analysis_query": str(payload.get("analysis_query") or ""),
            "review_mode": str(payload.get("review_mode") or ""),
            "privacy_guardrails": payload.get("privacy_guardrails"),
            "case_scope_quality": payload.get("case_scope_quality"),
            "matter_ingestion_report": payload.get("matter_ingestion_report"),
            "export_metadata": export_metadata,
            "artifacts": artifacts,
        }

    def _write_bundle(self, payload: dict[str, Any], output_path: Path, *, export_metadata: dict[str, Any]) -> dict[str, Any]:
        html = self._render_counsel_handoff_html(payload, export_metadata=export_metadata)
        exhibit_csv = self._exhibit_register_csv(payload, export_metadata=export_metadata)
        dashboard_payload = {"export_metadata": export_metadata, "case_dashboard": payload.get("case_dashboard")}
        memo_payload = {"export_metadata": export_metadata, "lawyer_briefing_memo": payload.get("lawyer_briefing_memo")}
        issue_payload = {"export_metadata": export_metadata, "lawyer_issue_matrix": payload.get("lawyer_issue_matrix")}
        report_payload = {
            "export_metadata": export_metadata,
            "investigation_report": payload.get("investigation_report"),
        }
        artifacts = [
            {"path": "counsel_handoff.html", "kind": "html"},
            {"path": "exhibit_register.csv", "kind": "csv"},
            {"path": "case_dashboard.json", "kind": "json"},
            {"path": "lawyer_briefing_memo.json", "kind": "json"},
            {"path": "lawyer_issue_matrix.json", "kind": "json"},
            {"path": "investigation_report.json", "kind": "json"},
        ]
        manifest = self._bundle_manifest(payload, artifacts, export_metadata=export_metadata)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json_text(manifest))
            archive.writestr("counsel_handoff.html", html)
            archive.writestr("exhibit_register.csv", exhibit_csv)
            archive.writestr("case_dashboard.json", _json_text(dashboard_payload))
            archive.writestr("lawyer_briefing_memo.json", _json_text(memo_payload))
            archive.writestr("lawyer_issue_matrix.json", _json_text(issue_payload))
            archive.writestr("investigation_report.json", _json_text(report_payload))
        return manifest
