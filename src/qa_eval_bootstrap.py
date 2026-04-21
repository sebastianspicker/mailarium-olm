"""Bootstrap reviewable QA eval question sets from templates plus sampled payloads."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .qa_eval_cases import _load_json
from .qa_eval_impl import _results_payload_map


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _normalized_haystack(parts: list[Any]) -> str:
    return "\n".join(_normalized_text(part) for part in parts if _normalized_text(part))


def _contains_all_terms(text: str, terms: list[str]) -> bool:
    normalized_terms = [_normalized_text(term) for term in terms if _normalized_text(term)]
    return bool(normalized_terms) and all(term in text for term in normalized_terms)


def _source_bundle_haystack(payload: dict[str, Any]) -> str:
    bundle = _as_dict(payload.get("multi_source_case_bundle"))
    parts: list[Any] = []
    for source in _as_list(bundle.get("sources")):
        if not isinstance(source, dict):
            continue
        parts.extend(
            [
                source.get("source_id"),
                source.get("title"),
                source.get("snippet"),
                source.get("author"),
                source.get("sender_name"),
                source.get("sender_email"),
                " ".join(str(item) for item in _as_list(source.get("participants")) if str(item).strip()),
                " ".join(str(item) for item in _as_list(source.get("recipients")) if str(item).strip()),
            ]
        )
    return _normalized_haystack(parts)


def _report_haystack(payload: dict[str, Any]) -> str:
    report = _as_dict(payload.get("investigation_report"))
    return _normalized_haystack([report])


def _structured_actor_haystack(payload: dict[str, Any]) -> str:
    parts: list[Any] = []
    archive_harvest = _as_dict(payload.get("archive_harvest"))
    for row in _as_list(archive_harvest.get("evidence_bank")):
        if not isinstance(row, dict):
            continue
        parts.extend([row.get("sender_name"), row.get("sender_email"), row.get("subject"), row.get("source_id")])
    for actor in _as_list(_as_dict(payload.get("actor_identity_graph")).get("actors")):
        if not isinstance(actor, dict):
            continue
        parts.extend([actor.get("actor_id"), actor.get("name"), actor.get("primary_email")])
    for source in _as_list(_as_dict(payload.get("multi_source_case_bundle")).get("sources")):
        if not isinstance(source, dict):
            continue
        parts.extend(
            [
                source.get("source_id"),
                source.get("title"),
                source.get("author"),
                source.get("sender_name"),
                source.get("sender_email"),
                " ".join(str(item) for item in _as_list(source.get("participants")) if str(item).strip()),
            ]
        )
    for entry in _as_list(_as_dict(payload.get("master_chronology")).get("entries")):
        if not isinstance(entry, dict):
            continue
        parts.extend([entry.get("title"), entry.get("description")])
        parts.extend(_as_list(entry.get("people_involved")))
    return _normalized_haystack(parts)


def _structured_issue_haystack(payload: dict[str, Any]) -> str:
    parts: list[Any] = []
    archive_harvest = _as_dict(payload.get("archive_harvest"))
    for row in _as_list(archive_harvest.get("evidence_bank")):
        if not isinstance(row, dict):
            continue
        parts.extend([row.get("subject"), row.get("snippet"), row.get("attachment_filename")])
    for row in _as_list(_as_dict(payload.get("matter_evidence_index")).get("rows")):
        if not isinstance(row, dict):
            continue
        parts.extend(
            [
                row.get("source_id"),
                row.get("short_description"),
                row.get("why_it_matters"),
                " ".join(str(item) for item in _as_list(row.get("main_issue_tags")) if str(item).strip()),
                " ".join(str(item) for item in _as_list(row.get("all_issue_tags")) if str(item).strip()),
            ]
        )
    for row in _as_list(_as_dict(payload.get("lawyer_issue_matrix")).get("rows")):
        if not isinstance(row, dict):
            continue
        parts.extend([row.get("issue_id"), row.get("title"), row.get("relevant_facts"), row.get("missing_proof")])
    for entry in _as_list(_as_dict(payload.get("master_chronology")).get("entries")):
        if not isinstance(entry, dict):
            continue
        parts.extend([entry.get("title"), entry.get("description")])
        matrix = _as_dict(entry.get("event_support_matrix"))
        for read_id, matrix_item in matrix.items():
            if not isinstance(matrix_item, dict):
                continue
            parts.extend([read_id, matrix_item.get("status"), matrix_item.get("reason")])
            parts.extend(_as_list(matrix_item.get("linked_issue_tags")))
    report = _as_dict(payload.get("investigation_report"))
    sections = _as_dict(report.get("sections"))
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        parts.extend([section_id, section.get("title"), section.get("status"), section])
    return _normalized_haystack([*parts, _source_bundle_haystack(payload)])


def _chronology_anchor_recovery(*, benchmark_pack: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    markers = [item for item in _as_list(benchmark_pack.get("chronology_anchor_markers")) if isinstance(item, dict)]
    entries = [item for item in _as_list(_as_dict(payload.get("master_chronology")).get("entries")) if isinstance(item, dict)]
    recovered: list[dict[str, Any]] = []
    for marker in markers:
        marker_date = str(marker.get("date") or "")
        title_terms = [str(item) for item in _as_list(marker.get("title_terms")) if str(item).strip()]
        description_terms = [str(item) for item in _as_list(marker.get("description_terms")) if str(item).strip()]
        for entry in entries:
            title_haystack = _normalized_haystack([entry.get("title")])
            description_haystack = _normalized_haystack([entry.get("description")])
            if marker_date and str(entry.get("date") or "") != marker_date:
                continue
            if title_terms and not _contains_all_terms(title_haystack, title_terms):
                continue
            if description_terms and not _contains_all_terms(description_haystack, description_terms):
                continue
            recovered.append(
                {
                    "date": marker_date,
                    "title": str(entry.get("title") or ""),
                    "chronology_id": str(entry.get("chronology_id") or ""),
                }
            )
            break
    return {
        "total": len(markers),
        "recovered": len(recovered),
        "coverage": round((len(recovered) / len(markers)), 4) if markers else 0.0,
        "recovered_items": recovered,
    }


def _manifest_link_recovery(*, benchmark_pack: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    targets = [item for item in _as_list(benchmark_pack.get("manifest_link_targets")) if isinstance(item, dict)]
    bundle = _as_dict(payload.get("multi_source_case_bundle"))
    sources = {
        str(source.get("source_id") or ""): source
        for source in _as_list(bundle.get("sources"))
        if isinstance(source, dict) and str(source.get("source_id") or "")
    }
    links = [item for item in _as_list(bundle.get("source_links")) if isinstance(item, dict)]
    recovered: list[dict[str, Any]] = []
    for target in targets:
        doc_source_id = str(target.get("document_source_id") or "")
        email_source_id = str(target.get("email_source_id") or "")
        doc_terms = [str(item) for item in _as_list(target.get("document_title_terms")) if str(item).strip()]
        email_terms = [str(item) for item in _as_list(target.get("email_title_terms")) if str(item).strip()]
        for link in links:
            left_id = str(link.get("from_source_id") or "")
            right_id = str(link.get("to_source_id") or "")
            left = _as_dict(sources.get(left_id))
            right = _as_dict(sources.get(right_id))
            left_title = _normalized_haystack([left.get("title")])
            right_title = _normalized_haystack([right.get("title")])
            ids_match = (not doc_source_id or doc_source_id in {left_id, right_id}) and (
                not email_source_id or email_source_id in {left_id, right_id}
            )
            titles_match = (
                not doc_terms or _contains_all_terms(left_title, doc_terms) or _contains_all_terms(right_title, doc_terms)
            ) and (
                not email_terms or _contains_all_terms(left_title, email_terms) or _contains_all_terms(right_title, email_terms)
            )
            if not ids_match or not titles_match:
                continue
            recovered.append(
                {
                    "from_source_id": left_id,
                    "to_source_id": right_id,
                    "link_type": str(link.get("link_type") or ""),
                    "confidence": str(link.get("confidence") or ""),
                }
            )
            break
    return {
        "total": len(targets),
        "recovered": len(recovered),
        "coverage": round((len(recovered) / len(targets)), 4) if targets else 0.0,
        "recovered_items": recovered,
    }


def _report_completeness(*, benchmark_pack: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    required_sections = [str(item) for item in _as_list(benchmark_pack.get("required_report_sections")) if str(item).strip()]
    sections = _as_dict(_as_dict(payload.get("investigation_report")).get("sections"))
    recovered = [
        section_id
        for section_id in required_sections
        if isinstance(sections.get(section_id), dict)
        and str(_as_dict(sections.get(section_id)).get("status") or "") == "supported"
    ]
    return {
        "total": len(required_sections),
        "recovered": len(recovered),
        "coverage": round((len(recovered) / len(required_sections)), 4) if required_sections else 0.0,
        "recovered_sections": recovered,
    }


def default_bootstrap_questions_path(questions_path: Path) -> Path:
    """Return the default output path for a bootstrapped sampled question set."""
    if questions_path.suffix != ".json":
        return questions_path.with_name(f"{questions_path.name}.sampled")
    return questions_path.with_name(f"{questions_path.stem}.sampled{questions_path.suffix}")


def _bootstrap_candidate_brief(candidate: dict[str, Any], *, source_lane: str, rank: int) -> dict[str, Any]:
    brief: dict[str, Any] = {
        "source_lane": source_lane,
        "rank": rank,
    }
    for key in ("uid", "score", "subject", "date", "sender", "folder", "snippet", "source_type"):
        value = candidate.get(key)
        if value not in (None, "", [], {}):
            brief[key] = value
    return brief


def _sanitize_case_for_bootstrap(case: dict[str, Any], *, payload: dict[str, Any], sample_size: int) -> dict[str, Any]:
    bootstrapped = deepcopy(case)
    if str(bootstrapped.get("status") or "").strip() in {"", "todo"}:
        bootstrapped["status"] = "sampled"
    expected_answer = str(bootstrapped.get("expected_answer") or "")
    if "TODO(" in expected_answer:
        bootstrapped["expected_answer"] = ""
    bootstrapped["expected_support_uids"] = [str(uid) for uid in _as_list(bootstrapped.get("expected_support_uids"))]
    bootstrapped["expected_top_uid"] = str(bootstrapped["expected_top_uid"]) if bootstrapped.get("expected_top_uid") else None

    candidates = [item for item in _as_list(payload.get("candidates")) if isinstance(item, dict)]
    attachment_candidates = [item for item in _as_list(payload.get("attachment_candidates")) if isinstance(item, dict)]
    bootstrapped["bootstrap_label_status"] = "review_required"
    bootstrapped["bootstrap_candidates"] = [
        *[
            _bootstrap_candidate_brief(item, source_lane="candidates", rank=index + 1)
            for index, item in enumerate(candidates[:sample_size])
        ],
        *[
            _bootstrap_candidate_brief(item, source_lane="attachment_candidates", rank=index + 1)
            for index, item in enumerate(attachment_candidates[:sample_size])
        ],
    ]
    answer_quality = _as_dict(payload.get("answer_quality"))
    bootstrapped["bootstrap_observation"] = {
        "top_candidate_uid": str(answer_quality.get("top_candidate_uid") or "") or None,
        "confidence_label": str(answer_quality.get("confidence_label") or "") or None,
        "ambiguity_reason": str(answer_quality.get("ambiguity_reason") or "") or None,
        "candidate_count": len(candidates),
        "attachment_candidate_count": len(attachment_candidates),
    }
    return bootstrapped


def bootstrap_question_set(*, questions_path: Path, results_path: Path, sample_size: int = 3) -> dict[str, Any]:
    """Build a reviewable sampled question set from template cases and captured payloads."""
    if sample_size < 1:
        raise ValueError("sample_size must be at least 1")
    raw = _load_json(questions_path)
    case_items = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(case_items, list):
        raise ValueError("questions file must contain a list of cases")

    payloads = _results_payload_map(results_path)
    bootstrapped_cases = []
    for case in case_items:
        if not isinstance(case, dict):
            continue
        case_dict = _as_dict(case)
        case_id = str(case_dict.get("id") or "")
        bootstrapped_cases.append(
            _sanitize_case_for_bootstrap(
                case_dict,
                payload=_as_dict(payloads.get(case_id)),
                sample_size=sample_size,
            )
        )

    description = ""
    if isinstance(raw, dict):
        description = str(raw.get("description") or "")
    description_suffix = "Bootstrapped sampled review set; confirm final labels before running scored evaluation."
    return {
        "version": int(raw.get("version") or 1) if isinstance(raw, dict) else 1,
        "description": f"{description} {description_suffix}".strip(),
        "bootstrap_metadata": {
            "status": "review_required",
            "questions_path": str(questions_path),
            "results_path": str(results_path),
            "sample_size": sample_size,
        },
        "cases": bootstrapped_cases,
    }


def benchmark_detection_recovery(*, benchmark_pack: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Measure whether a payload recovers actor and issue-family material from a benchmark pack."""
    actor_haystack = _structured_actor_haystack(payload)
    issue_haystack = _structured_issue_haystack(payload)
    seed_actors = [str(item) for item in _as_list(benchmark_pack.get("seed_actors")) if str(item).strip()]
    issue_families = [str(item) for item in _as_list(benchmark_pack.get("issue_families")) if str(item).strip()]
    recovered_actors = [actor for actor in seed_actors if _normalized_text(actor) and _normalized_text(actor) in actor_haystack]
    recovered_issues = [
        issue for issue in issue_families if _normalized_text(issue) and _normalized_text(issue) in issue_haystack
    ]
    return {
        "benchmark_id": str(benchmark_pack.get("benchmark_id") or ""),
        "usage_rule": str(benchmark_pack.get("usage_rule") or ""),
        "actor_recovery": {
            "total": len(seed_actors),
            "recovered": len(recovered_actors),
            "coverage": round((len(recovered_actors) / len(seed_actors)), 4) if seed_actors else 0.0,
            "recovered_items": recovered_actors,
        },
        "issue_family_recovery": {
            "total": len(issue_families),
            "recovered": len(recovered_issues),
            "coverage": round((len(recovered_issues) / len(issue_families)), 4) if issue_families else 0.0,
            "recovered_items": recovered_issues,
        },
        "chronology_anchor_recovery": _chronology_anchor_recovery(benchmark_pack=benchmark_pack, payload=payload),
        "manifest_link_recovery": _manifest_link_recovery(benchmark_pack=benchmark_pack, payload=payload),
        "mixed_source_report_completeness": _report_completeness(benchmark_pack=benchmark_pack, payload=payload),
    }
