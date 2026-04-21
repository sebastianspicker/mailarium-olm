"""Bounded prompt-to-intake preflight for legal-support case workflows."""

from __future__ import annotations

from typing import Any

from .case_prompt_context_actors import (
    context_people_from_matter,
    institutional_actors_from_matter,
    merge_people_with_context_emails,
    person_email_directory_from_matter,
)
from .case_prompt_intake_helpers import (
    CASE_PROMPT_PREFLIGHT_VERSION,
    _analysis_goal,
    _candidate_structures,
    _compact,
    _extract_dates,
    _issue_hints,
    _missing_inputs,
    _named_people,
    _source_scope,
    matter_text,
    preserved_matter_factual_context,
)


def build_case_prompt_preflight(params: Any) -> dict[str, Any]:
    """Return a bounded prompt-to-intake preflight payload."""
    raw_prompt_text = str(getattr(params, "prompt_text", "") or "")
    prompt_text = _compact(raw_prompt_text)
    factual_text = matter_text(prompt_text)
    matter_factual_context = preserved_matter_factual_context(raw_prompt_text)
    allegation_focus, issue_tracks = _issue_hints(factual_text)
    dates = _extract_dates(
        factual_text,
        today=str(getattr(params, "today", "")),
        assume_date_to_today=bool(getattr(params, "assume_date_to_today", True)),
    )
    people = _named_people(factual_text)
    person_email_directory = person_email_directory_from_matter(matter_factual_context)
    target_rows = merge_people_with_context_emails(people["target_person"], person_email_directory)
    suspected_rows = merge_people_with_context_emails(people["suspected_actors"], person_email_directory)
    comparator_rows = merge_people_with_context_emails(people["comparator_actors"], person_email_directory)
    context_people = context_people_from_matter(
        matter_factual_context,
        exclude_people=[*target_rows, *suspected_rows, *comparator_rows],
    )
    institutional_actors = institutional_actors_from_matter(matter_factual_context)
    candidate_structures = _candidate_structures(factual_text, comparator_rows)
    missing_required_inputs = _missing_inputs(
        target_rows=target_rows,
        dates=dates,
        allegation_focus=allegation_focus,
        issue_tracks=issue_tracks,
        comparators=comparator_rows,
        prompt_text=factual_text,
    )
    recommended_source_scope = _source_scope(prompt_text, str(getattr(params, "default_source_scope", "emails_and_attachments")))
    draft_case_scope: dict[str, Any] = {
        "target_person": target_rows[0] if target_rows else None,
        "suspected_actors": suspected_rows,
        "comparator_actors": comparator_rows,
        "context_people": context_people,
        "institutional_actors": institutional_actors,
        "date_from": dates.get("date_from"),
        "date_to": dates.get("date_to"),
        "allegation_focus": allegation_focus,
        "analysis_goal": _analysis_goal(prompt_text),
        "context_notes": factual_text[:4000],
        "employment_issue_tracks": issue_tracks,
    }
    recommended_next_inputs = [
        {
            "field": item["field"],
            "recommendation": item["reason"],
        }
        for item in missing_required_inputs
    ]
    if "retaliation" in allegation_focus:
        recommended_next_inputs.append(
            {
                "field": "case_scope.trigger_events",
                "recommendation": (
                    "Add dated trigger events and dated post-trigger actions before relying on retaliation framing."
                ),
            }
        )
    if {"unequal_treatment", "discrimination"} & set(allegation_focus):
        recommended_next_inputs.append(
            {
                "field": "case_scope.comparator_equivalence_notes",
                "recommendation": "Explain why the proposed comparators are meaningfully comparable.",
            }
        )
    recommended_next_inputs = list(
        {
            (item["field"], item["recommendation"]): item
            for item in recommended_next_inputs
            if _compact(item.get("field")) and _compact(item.get("recommendation"))
        }.values()
    )
    prompt_limits = [
        "This preflight does not prove facts; it only drafts intake fields from the supplied prompt.",
        "Dedicated legal-support products still require exhaustive manifest-backed review.",
    ]
    if missing_required_inputs:
        prompt_limits.append("The current prompt is not yet complete enough for a full structured case run.")

    draft_case_analysis_input: dict[str, Any] = {
        "case_scope": draft_case_scope,
        "source_scope": recommended_source_scope,
        "review_mode": "retrieval_only",
    }
    if matter_factual_context:
        draft_case_analysis_input["matter_factual_context"] = matter_factual_context

    payload = {
        "version": CASE_PROMPT_PREFLIGHT_VERSION,
        "workflow": "case_prompt_preflight",
        "output_language": str(getattr(params, "output_language", "en")),
        "analysis_goal": draft_case_scope["analysis_goal"],
        "recommended_source_scope": recommended_source_scope,
        "draft_case_scope": draft_case_scope,
        "draft_case_analysis_input": draft_case_analysis_input,
        "candidate_structures": candidate_structures,
        "extraction_summary": {
            "named_target_candidates": target_rows,
            "named_suspected_actor_candidates": suspected_rows,
            "named_comparator_candidates": comparator_rows,
            "named_context_people": context_people,
            "institutional_actors": institutional_actors,
            "issue_hints": allegation_focus,
            "issue_track_hints": issue_tracks,
            "date_candidates": dates["explicit_dates"],
            "used_today_for_open_ended_range": dates["used_today_for_open_ended_range"],
            "candidate_counts": dict(candidate_structures["summary"]),
        },
        "missing_required_inputs": missing_required_inputs,
        "recommended_next_inputs": recommended_next_inputs,
        "ready_for_case_analysis": not missing_required_inputs,
        "supports_exhaustive_legal_support": False,
        "prompt_limits": prompt_limits,
    }
    if matter_factual_context:
        payload["matter_factual_context"] = matter_factual_context
    return payload
