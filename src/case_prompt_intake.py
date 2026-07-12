"""Bounded prompt-to-intake preflight for legal-support case workflows."""
# pylint: disable=too-many-locals

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class _PromptPreflightContext:
    prompt_text: str
    factual_text: str
    matter_factual_context: str
    allegation_focus: list[str]
    issue_tracks: list[str]
    dates: dict[str, Any]
    target_rows: list[dict[str, Any]]
    suspected_rows: list[dict[str, Any]]
    comparator_rows: list[dict[str, Any]]
    context_people: list[dict[str, Any]]
    institutional_actors: list[dict[str, Any]]
    candidate_structures: dict[str, Any]
    missing_required_inputs: list[dict[str, Any]]
    recommended_source_scope: str


def build_case_prompt_preflight(params: Any) -> dict[str, Any]:
    """Return a bounded prompt-to-intake preflight payload."""
    context = _prompt_preflight_context(params)
    draft_case_scope = _draft_case_scope(context)
    draft_case_analysis_input: dict[str, Any] = {
        "case_scope": draft_case_scope,
        "source_scope": context.recommended_source_scope,
        "review_mode": "retrieval_only",
    }
    if context.matter_factual_context:
        draft_case_analysis_input["matter_factual_context"] = context.matter_factual_context
    payload = _prompt_preflight_payload(params, context, draft_case_scope, draft_case_analysis_input)
    if context.matter_factual_context:
        payload["matter_factual_context"] = context.matter_factual_context
    return payload


def _prompt_preflight_context(params: Any) -> _PromptPreflightContext:
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
    return _PromptPreflightContext(
        prompt_text=prompt_text,
        factual_text=factual_text,
        matter_factual_context=matter_factual_context,
        allegation_focus=allegation_focus,
        issue_tracks=issue_tracks,
        dates=dates,
        target_rows=target_rows,
        suspected_rows=suspected_rows,
        comparator_rows=comparator_rows,
        context_people=context_people,
        institutional_actors=institutional_actors,
        candidate_structures=candidate_structures,
        missing_required_inputs=missing_required_inputs,
        recommended_source_scope=recommended_source_scope,
    )


def _draft_case_scope(context: _PromptPreflightContext) -> dict[str, Any]:
    return {
        "target_person": context.target_rows[0] if context.target_rows else None,
        "suspected_actors": context.suspected_rows,
        "comparator_actors": context.comparator_rows,
        "context_people": context.context_people,
        "institutional_actors": context.institutional_actors,
        "date_from": context.dates.get("date_from"),
        "date_to": context.dates.get("date_to"),
        "allegation_focus": context.allegation_focus,
        "analysis_goal": _analysis_goal(context.prompt_text),
        "context_notes": context.factual_text[:4000],
        "employment_issue_tracks": context.issue_tracks,
    }


def _recommended_next_inputs(context: _PromptPreflightContext) -> list[dict[str, str]]:
    recommended_next_inputs = [
        {
            "field": item["field"],
            "recommendation": item["reason"],
        }
        for item in context.missing_required_inputs
    ]
    if "retaliation" in context.allegation_focus:
        recommended_next_inputs.append(
            {
                "field": "case_scope.trigger_events",
                "recommendation": (
                    "Add dated trigger events and dated post-trigger actions before relying on retaliation framing."
                ),
            }
        )
    if {"unequal_treatment", "discrimination"} & set(context.allegation_focus):
        recommended_next_inputs.append(
            {
                "field": "case_scope.comparator_equivalence_notes",
                "recommendation": "Explain why the proposed comparators are meaningfully comparable.",
            }
        )
    return list(
        {
            (item["field"], item["recommendation"]): item
            for item in recommended_next_inputs
            if _compact(item.get("field")) and _compact(item.get("recommendation"))
        }.values()
    )


def _prompt_limits(context: _PromptPreflightContext) -> list[str]:
    prompt_limits = [
        "This preflight does not prove facts; it only drafts intake fields from the supplied prompt.",
        "Dedicated legal-support products still require exhaustive manifest-backed review.",
    ]
    if context.missing_required_inputs:
        prompt_limits.append("The current prompt is not yet complete enough for a full structured case run.")
    return prompt_limits


def _prompt_preflight_payload(
    params: Any,
    context: _PromptPreflightContext,
    draft_case_scope: dict[str, Any],
    draft_case_analysis_input: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": CASE_PROMPT_PREFLIGHT_VERSION,
        "workflow": "case_prompt_preflight",
        "output_language": str(getattr(params, "output_language", "en")),
        "analysis_goal": draft_case_scope["analysis_goal"],
        "recommended_source_scope": context.recommended_source_scope,
        "draft_case_scope": draft_case_scope,
        "draft_case_analysis_input": draft_case_analysis_input,
        "candidate_structures": context.candidate_structures,
        "extraction_summary": {
            "named_target_candidates": context.target_rows,
            "named_suspected_actor_candidates": context.suspected_rows,
            "named_comparator_candidates": context.comparator_rows,
            "named_context_people": context.context_people,
            "institutional_actors": context.institutional_actors,
            "issue_hints": context.allegation_focus,
            "issue_track_hints": context.issue_tracks,
            "date_candidates": context.dates["explicit_dates"],
            "used_today_for_open_ended_range": context.dates["used_today_for_open_ended_range"],
            "candidate_counts": dict(context.candidate_structures["summary"]),
        },
        "missing_required_inputs": context.missing_required_inputs,
        "recommended_next_inputs": _recommended_next_inputs(context),
        "ready_for_case_analysis": not context.missing_required_inputs,
        "supports_exhaustive_legal_support": False,
        "prompt_limits": _prompt_limits(context),
    }
