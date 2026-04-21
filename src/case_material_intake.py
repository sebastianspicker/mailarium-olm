"""Deterministic intake extraction from supplied matter materials."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .case_prompt_intake_helpers import _adverse_action_candidates, _candidate_confidence, _trigger_event_candidates

CASE_MATERIAL_PREFLIGHT_VERSION = "1"
_NAME_FRAGMENT = r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.'’-]*(?: +[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.'’-]*){1,4}"
_TARGET_PATTERNS = (
    re.compile(rf"(?i)beweisdossier\s+({_NAME_FRAGMENT})"),
    re.compile(rf"(?i)target person[:\s-]+({_NAME_FRAGMENT})"),
    re.compile(rf"(?i)claimant[:\s-]+({_NAME_FRAGMENT})"),
    re.compile(rf"(?i)employee[:\s-]+({_NAME_FRAGMENT})"),
)
_EMAIL_RE = re.compile(r"(?i)\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b")
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_DOT_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b")
_COMPARATOR_PATTERNS = (
    re.compile(rf"(?i)(?:vergleichsperson|comparator|peer|kolleg(?:e|in))[:\s-]+({_NAME_FRAGMENT})"),
    re.compile(r"(?i)(?:gutermuth|richter|preis|kotarra)(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.'’-]+)?"),
)
_ALLOWED_TRIGGER_TYPES = {
    "complaint",
    "illness_disability_disclosure",
    "escalation_to_hr",
    "objection_refusal",
    "boundary_assertion",
    "other",
}
_ALLOWED_ACTION_TYPES = {
    "task_withdrawal",
    "project_removal",
    "mobile_work_restriction",
    "discipline_warning",
    "attendance_control",
    "participation_exclusion",
    "job_downgrade",
    "other",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _artifact_ref(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": _compact(artifact.get("source_id")),
        "title": _compact(artifact.get("title") or artifact.get("filename")),
        "source_class": _compact(artifact.get("source_class")),
        "source_path": _compact(artifact.get("source_path")),
    }


def _artifact_text(artifact: dict[str, Any]) -> str:
    for key in ("text_source_path", "source_path"):
        raw_path = _compact(artifact.get(key))
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if path.suffix.lower() not in {".md", ".txt", ".html", ".htm"}:
            continue
        try:
            raw_text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if raw_text:
            return raw_text
    return "\n".join(
        part
        for part in (
            _compact(artifact.get("title") or artifact.get("filename")),
            str(artifact.get("text") or "").strip(),
            str(artifact.get("summary") or "").strip(),
        )
        if part
    )


def _normalized_name(value: Any) -> str:
    return _compact(value).casefold()


def _material_candidate_entry(
    *,
    candidate_id: str,
    candidate_kind: str,
    candidate_value: Any,
    confidence: str,
    source_span: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_kind": candidate_kind,
        "candidate_value": candidate_value,
        "confidence": confidence,
        "source_span": _compact(source_span),
        "source_artifact": _artifact_ref(artifact),
        "warning": "Candidate extracted from supplied materials. Only auto-apply when it is unambiguous.",
    }


def _find_email_near_text(text: str, *, name: str) -> str:
    compact_name = _compact(name)
    if not compact_name:
        return ""
    lowered = text.casefold()
    index = lowered.find(compact_name.casefold())
    window = text[max(0, index - 120) : index + len(compact_name) + 240] if index >= 0 else text[:240]
    match = _EMAIL_RE.search(window)
    return _compact(match.group(1)) if match else ""


def _target_person_candidates(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact in artifacts:
        text = _artifact_text(artifact)
        if not text:
            continue
        for pattern in _TARGET_PATTERNS:
            for match in pattern.finditer(text):
                name = re.sub(r"\bStand$", "", _compact(match.group(1))).strip()
                if not name:
                    continue
                normalized = _normalized_name(name)
                if normalized in seen:
                    continue
                seen.add(normalized)
                confidence = "high" if len(name.split()) >= 2 else "medium"
                candidates.append(
                    _material_candidate_entry(
                        candidate_id=f"material:target_person:{len(candidates) + 1}",
                        candidate_kind="target_person_candidate",
                        candidate_value={
                            "name": name,
                            "email": _find_email_near_text(text, name=name) or None,
                        },
                        confidence=confidence,
                        source_span=match.group(0),
                        artifact=artifact,
                    )
                )
    return candidates


def _all_dates(text: str) -> list[str]:
    dated: list[tuple[int, str]] = []
    for match in _ISO_DATE_RE.finditer(text):
        dated.append((match.start(), match.group(1)))
    for match in _DOT_DATE_RE.finditer(text):
        dated.append((match.start(), f"{match.group(3)}-{match.group(2)}-{match.group(1)}"))
    return [value for _, value in sorted(dated)]


def _date_candidates(artifacts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dated_artifacts: list[tuple[str, dict[str, Any], str]] = []
    for artifact in artifacts:
        text = _artifact_text(artifact)
        for date_value in _all_dates(text):
            dated_artifacts.append((date_value, artifact, date_value))
    if not dated_artifacts:
        return ([], [])
    dated_artifacts.sort(key=lambda item: item[0])
    earliest, latest = dated_artifacts[0], dated_artifacts[-1]
    date_from_candidates = [
        _material_candidate_entry(
            candidate_id="material:date_from:1",
            candidate_kind="date_from_candidate",
            candidate_value=earliest[0],
            confidence="high",
            source_span=earliest[2],
            artifact=earliest[1],
        )
    ]
    date_to_candidates = [
        _material_candidate_entry(
            candidate_id="material:date_to:1",
            candidate_kind="date_to_candidate",
            candidate_value=latest[0],
            confidence="high",
            source_span=latest[2],
            artifact=latest[1],
        )
    ]
    return date_from_candidates, date_to_candidates


def _material_event_candidates(
    *,
    artifacts: list[dict[str, Any]],
    candidate_builder: Any,
    candidate_kind: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for artifact in artifacts:
        text = _artifact_text(artifact)
        if not text:
            continue
        text = "\n".join(line for line in text.splitlines() if not re.match(r"(?i)^\s*stand\s*:", line))
        normalized_text = _DOT_DATE_RE.sub(
            lambda match: f"{match.group(3)}-{match.group(2)}-{match.group(1)}",
            text,
        )
        for candidate in candidate_builder(normalized_text):
            value = _as_dict(candidate.get("candidate_value"))
            key = (
                _compact(value.get("trigger_type") or value.get("action_type") or value.get("name")),
                _compact(value.get("date")),
                _compact(candidate.get("source_span")),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    **candidate,
                    "candidate_id": f"material:{candidate_kind}:{len(candidates) + 1}",
                    "source_artifact": _artifact_ref(artifact),
                    "warning": "Candidate extracted from supplied materials. Only auto-apply when it is unambiguous.",
                }
            )
    return candidates


def _comparator_candidates(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact in artifacts:
        text = _artifact_text(artifact)
        if not text:
            continue
        for pattern in _COMPARATOR_PATTERNS:
            for match in pattern.finditer(text):
                name = _compact(match.group(1) if match.lastindex else match.group(0))
                if not name or _normalized_name(name) in seen:
                    continue
                seen.add(_normalized_name(name))
                candidates.append(
                    _material_candidate_entry(
                        candidate_id=f"material:comparator:{len(candidates) + 1}",
                        candidate_kind="comparator_candidate",
                        candidate_value={"name": name},
                        confidence=_candidate_confidence(local_date=None, explicit_name=True),
                        source_span=match.group(0),
                        artifact=artifact,
                    )
                )
    return candidates


def _dedupe_actor_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = _as_dict(row.get("candidate_value"))
        name = _compact(value.get("name"))
        if not name:
            continue
        normalized = _normalized_name(name)
        existing = deduped.get(normalized)
        if existing is None or str(row.get("confidence") or "") == "high":
            deduped[normalized] = row
    return list(deduped.values())


def _auto_fill_case_scope(candidate_structures: dict[str, Any]) -> dict[str, Any]:
    auto_fill: dict[str, Any] = {}
    target_candidates = _dedupe_actor_rows(
        [item for item in _as_list(candidate_structures.get("target_person_candidates")) if isinstance(item, dict)]
    )
    if len(target_candidates) == 1 and str(target_candidates[0].get("confidence") or "") == "high":
        auto_fill["target_person"] = _as_dict(target_candidates[0].get("candidate_value"))

    date_from_candidates = [item for item in _as_list(candidate_structures.get("date_from_candidates")) if isinstance(item, dict)]
    if date_from_candidates:
        auto_fill["date_from"] = str(date_from_candidates[0].get("candidate_value") or "")
    date_to_candidates = [item for item in _as_list(candidate_structures.get("date_to_candidates")) if isinstance(item, dict)]
    if date_to_candidates:
        auto_fill["date_to"] = str(date_to_candidates[0].get("candidate_value") or "")

    for field, key_name in (
        ("trigger_events", "trigger_event_candidates"),
        ("alleged_adverse_actions", "adverse_action_candidates"),
        ("comparator_actors", "comparator_candidates"),
    ):
        rows = [
            _as_dict(item.get("candidate_value")) if isinstance(item, dict) else {}
            for item in _as_list(candidate_structures.get(key_name))
            if isinstance(item, dict) and str(item.get("confidence") or "") in {"medium", "high"}
        ]
        normalized_rows: list[dict[str, Any]] = []
        seen: set[tuple[tuple[str, Any], ...]] = set()
        for row in rows:
            compacted = {key: value for key, value in row.items() if value not in (None, "", [], {})}
            if field == "trigger_events" and compacted.get("trigger_type") not in _ALLOWED_TRIGGER_TYPES:
                continue
            if field == "alleged_adverse_actions" and compacted.get("action_type") not in _ALLOWED_ACTION_TYPES:
                continue
            if field == "comparator_actors" and not compacted.get("name"):
                continue
            dedupe_key = tuple(sorted(compacted.items()))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_rows.append(compacted)
        if not normalized_rows:
            continue
        if field == "comparator_actors":
            if len(normalized_rows) <= 3:
                auto_fill[field] = normalized_rows
            continue
        normalized_rows.sort(
            key=lambda item: (
                str(item.get("date") or ""),
                str(item.get("trigger_type") or item.get("action_type") or ""),
            )
        )
        auto_fill[field] = normalized_rows[:12]
    return auto_fill


def build_case_material_preflight(matter_manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Return bounded case-intake candidates from enriched supplied materials."""
    manifest = _as_dict(matter_manifest)
    artifacts = [item for item in _as_list(manifest.get("artifacts")) if isinstance(item, dict)]
    reviewed_artifacts = [artifact for artifact in artifacts if _artifact_text(artifact)]
    date_from_candidates, date_to_candidates = _date_candidates(reviewed_artifacts)
    candidate_structures = {
        "target_person_candidates": _target_person_candidates(reviewed_artifacts),
        "date_from_candidates": date_from_candidates,
        "date_to_candidates": date_to_candidates,
        "trigger_event_candidates": _material_event_candidates(
            artifacts=reviewed_artifacts,
            candidate_builder=_trigger_event_candidates,
            candidate_kind="trigger_event_candidate",
        ),
        "adverse_action_candidates": _material_event_candidates(
            artifacts=reviewed_artifacts,
            candidate_builder=_adverse_action_candidates,
            candidate_kind="adverse_action_candidate",
        ),
        "comparator_candidates": _comparator_candidates(reviewed_artifacts),
    }
    summary = {
        "target_person_candidate_count": len(candidate_structures["target_person_candidates"]),
        "date_from_candidate_count": len(candidate_structures["date_from_candidates"]),
        "date_to_candidate_count": len(candidate_structures["date_to_candidates"]),
        "trigger_event_candidate_count": len(candidate_structures["trigger_event_candidates"]),
        "adverse_action_candidate_count": len(candidate_structures["adverse_action_candidates"]),
        "comparator_candidate_count": len(candidate_structures["comparator_candidates"]),
    }
    return {
        "version": CASE_MATERIAL_PREFLIGHT_VERSION,
        "workflow": "case_material_preflight",
        "manifest_id": _compact(manifest.get("manifest_id")),
        "reviewed_artifact_count": len(reviewed_artifacts),
        "candidate_structures": {**candidate_structures, "summary": summary},
        "auto_fill_case_scope": _auto_fill_case_scope(candidate_structures),
    }
