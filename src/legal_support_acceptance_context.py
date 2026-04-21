"""Deterministic answer-context builders for realistic legal-support fixtures."""

from __future__ import annotations

from typing import Any

from .legal_support_acceptance_cases import acceptance_case


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _message_candidates(case_id: str) -> list[dict[str, Any]]:
    if case_id == "retaliation_rights_assertion":
        return [
            {
                "uid": "ret-1",
                "date": "2025-03-01T09:00:00",
                "sender_name": "employee",
                "sender_email": "employee@example.test",
                "subject": "Complaint to HR",
                "snippet": "I request SBV participation and review of the accommodation denial.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "rights_assertion", "label": "Rights assertion"}],
                        "counter_indicators": [],
                        "tone_summary": "Formal assertion of rights.",
                        "relevant_wording": [{"text": "I request SBV participation.", "source_scope": "authored_text"}],
                        "omissions_or_process_signals": [],
                    }
                },
            },
            {
                "uid": "ret-2",
                "date": "2025-03-05T15:10:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Project reassignment",
                "snippet": "Effective immediately, the claimant is removed from the TD-heavy project and reporting will tighten.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "control_shift", "label": "Control shift"}],
                        "counter_indicators": ["Management cites restructuring."],
                        "tone_summary": "Directive and restrictive.",
                        "relevant_wording": [
                            {"text": "effective immediately", "source_scope": "authored_text"},
                            {"text": "reporting will tighten", "source_scope": "authored_text"},
                        ],
                        "omissions_or_process_signals": [
                            {"signal": "sbv_not_cced", "summary": "SBV not included despite protected-context complaint."}
                        ],
                    }
                },
            },
        ]
    if case_id == "comparator_unequal_treatment":
        return [
            {
                "uid": "cmp-1",
                "date": "2025-02-10T08:30:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Mobile work request",
                "snippet": "Claimant must submit extra documentation before mobile work is reconsidered.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "selective_formality", "label": "Selective formality"}],
                        "counter_indicators": ["Manager cites consistency."],
                        "tone_summary": "Controlling and procedural.",
                        "relevant_wording": [{"text": "extra documentation", "source_scope": "authored_text"}],
                        "omissions_or_process_signals": [],
                    }
                },
            },
            {
                "uid": "cmp-2",
                "date": "2025-02-11T11:15:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Pat mobile work approved",
                "snippet": "Pat Vergleich may continue mobile work without further paperwork.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "comparator_flexibility", "label": "Comparator flexibility"}],
                        "counter_indicators": [],
                        "tone_summary": "Routine and permissive.",
                        "relevant_wording": [{"text": "without further paperwork", "source_scope": "authored_text"}],
                        "omissions_or_process_signals": [],
                    }
                },
            },
        ]
    if case_id == "eingruppierung_task_withdrawal":
        return [
            {
                "uid": "ing-1",
                "date": "2025-04-02T09:00:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Task redistribution",
                "snippet": (
                    "The claimant will no longer perform the TD-heavy coordination tasks listed in the Tätigkeitsdarstellung."
                ),
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "task_withdrawal", "label": "Task withdrawal"}],
                        "counter_indicators": ["Management cites project reprioritization."],
                        "tone_summary": "Directive and explanatory.",
                        "relevant_wording": [{"text": "will no longer perform", "source_scope": "authored_text"}],
                        "omissions_or_process_signals": [],
                    }
                },
            }
        ]
    if case_id == "chronology_contradiction":
        return [
            {
                "uid": "chr-1",
                "date": "2025-03-14T14:00:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Meeting follow-up",
                "snippet": "We will circulate the written summary and include SBV before any decision is implemented.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "promise", "label": "Promise"}],
                        "counter_indicators": [],
                        "tone_summary": "Reassuring.",
                        "relevant_wording": [{"text": "include SBV", "source_scope": "authored_text"}],
                        "omissions_or_process_signals": [],
                    }
                },
            },
            {
                "uid": "chr-2",
                "date": "2025-03-18T16:00:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Implementation without summary",
                "snippet": "The process will proceed now; a written summary is not necessary.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [{"behavior_id": "contradiction", "label": "Contradiction"}],
                        "counter_indicators": ["Manager cites urgency."],
                        "tone_summary": "Defensive and compressed.",
                        "relevant_wording": [{"text": "not necessary", "source_scope": "authored_text"}],
                        "omissions_or_process_signals": [
                            {
                                "signal": "summary_missing",
                                "summary": "Promised written summary omitted.",
                            }
                        ],
                    }
                },
            },
        ]
    return [
        {
            "uid": "dis-1",
            "date": "2025-02-03T10:00:00",
            "sender_name": "manager",
            "sender_email": "manager@example.test",
            "subject": "Return-to-office and process",
            "snippet": "Mobile work remains denied despite the attached medical recommendation; SBV can be involved later.",
            "message_findings": {
                "authored_text": {
                    "behavior_candidates": [
                        {
                            "behavior_id": "medical_recommendation_ignored",
                            "label": "Medical recommendation ignored",
                        }
                    ],
                    "counter_indicators": ["Manager cites team policy."],
                    "tone_summary": "Defensive and restrictive.",
                    "relevant_wording": [{"text": "SBV can be involved later", "source_scope": "authored_text"}],
                    "omissions_or_process_signals": [
                        {"signal": "sbv_delayed", "summary": "SBV participation deferred despite accommodation dispute."}
                    ],
                }
            },
        }
    ]


def _findings(case_id: str) -> list[dict[str, Any]]:
    if case_id == "retaliation_rights_assertion":
        return [
            {
                "finding_id": "finding-retaliation-timing",
                "finding_label": "Temporal escalation after complaint",
                "evidence_strength": {"label": "strong_indicator"},
                "alternative_explanations": ["Reported restructuring may partly explain the timing."],
                "counter_indicators": ["A restructuring context appears in the record."],
                "supporting_evidence": [{"message_or_document_id": "ret-2", "citation_id": "ret:1"}],
            }
        ]
    if case_id == "comparator_unequal_treatment":
        return [
            {
                "finding_id": "finding-comparator-delta",
                "finding_label": "Comparator paperwork asymmetry",
                "evidence_strength": {"label": "strong_indicator"},
                "alternative_explanations": ["Comparator role differences should still be tested."],
                "counter_indicators": ["Exact workflow parity is not fully documented."],
                "supporting_evidence": [{"message_or_document_id": "cmp-1", "citation_id": "cmp:1"}],
            }
        ]
    if case_id == "eingruppierung_task_withdrawal":
        return [
            {
                "finding_id": "finding-eingruppierung",
                "finding_label": "Task profile changed against TD baseline",
                "evidence_strength": {"label": "moderate_indicator"},
                "alternative_explanations": ["Ordinary reprioritization remains possible."],
                "counter_indicators": ["No final job-evaluation decision is in the email corpus."],
                "supporting_evidence": [{"message_or_document_id": "ing-1", "citation_id": "ing:1"}],
            }
        ]
    if case_id == "chronology_contradiction":
        return [
            {
                "finding_id": "finding-contradiction",
                "finding_label": "Promise later contradicted",
                "evidence_strength": {"label": "strong_indicator"},
                "alternative_explanations": ["Urgency could explain summary compression."],
                "counter_indicators": ["No written summary was later recovered."],
                "supporting_evidence": [{"message_or_document_id": "chr-2", "citation_id": "chr:1"}],
            }
        ]
    return [
        {
            "finding_id": "finding-participation-gap",
            "finding_label": "Participation delayed despite accommodation issue",
            "evidence_strength": {"label": "moderate_indicator"},
            "alternative_explanations": ["Manager may have misunderstood the process order."],
            "counter_indicators": ["No explicit refusal of SBV involvement is recorded in the email itself."],
            "supporting_evidence": [{"message_or_document_id": "dis-1", "citation_id": "dis:1"}],
        }
    ]


def _retaliation_analysis(case_id: str) -> dict[str, Any]:
    if case_id != "retaliation_rights_assertion":
        return {
            "trigger_event_count": 0,
            "retaliation_timeline_assessment": {
                "version": "1",
                "protected_activity_timeline": [],
                "adverse_action_timeline": [],
                "temporal_correlation_analysis": [],
                "strongest_retaliation_indicators": [],
                "strongest_non_retaliatory_explanations": [],
                "overall_evidentiary_rating": {"rating": "insufficient_timing_record"},
            },
        }
    return {
        "trigger_event_count": 1,
        "retaliation_point_count": 1,
        "retaliation_points": [
            {
                "retaliation_point_id": "retaliation-point-1",
                "trigger_type": "complaint",
                "trigger_date": "2025-03-01",
                "assessment_status": "timing_supportive",
                "analysis_quality": "medium",
                "support_strength": "moderate_indicator",
                "strongest_metric_changes": ["task_withdrawal_within_4_days", "control_intensity_increase"],
                "confounder_signals": ["organizational_restructuring_context_after_trigger"],
                "confounder_summary": {"confounder_count": 1, "confounder_weight": "medium"},
                "supporting_uids": ["ret-2"],
                "point_summary": "Task withdrawal and tighter control followed within days of the protected complaint.",
                "counterargument": "Management also referenced restructuring in the same period.",
            }
        ],
        "retaliation_timeline_assessment": {
            "version": "1",
            "protected_activity_timeline": [
                {"date": "2025-03-01", "event": "Complaint to HR requesting SBV involvement", "source_document": "email:ret-1"}
            ],
            "adverse_action_timeline": [
                {"date": "2025-03-05", "event": "Project withdrawal and tighter controls", "source_document": "email:ret-2"}
            ],
            "temporal_correlation_analysis": [
                {
                    "trigger_date": "2025-03-01",
                    "adverse_date": "2025-03-05",
                    "assessment_status": "timing_supportive",
                    "analysis_quality": "medium",
                    "supporting_uids": ["ret-2"],
                }
            ],
            "strongest_retaliation_indicators": ["Project withdrawal followed within four days of the complaint."],
            "strongest_non_retaliatory_explanations": ["Management cites restructuring."],
            "overall_evidentiary_rating": {"rating": "moderate_indicator"},
            "confounder_summary": {"confounder_count": 1, "confounder_weight": "medium"},
        },
    }


def _comparative_treatment(case_id: str) -> dict[str, Any]:
    if case_id != "comparator_unequal_treatment":
        return {"summary": {"available_comparator_count": 0}, "comparator_points": []}
    return {
        "summary": {"available_comparator_count": 1},
        "matrix_rows": [
            {
                "issue_id": "mobile_work",
                "claimant_treatment": "Extra documentation required before approval.",
                "colleague_treatment": "Pat Vergleich approved without extra paperwork.",
                "comparison_strength": "moderate",
            }
        ],
        "comparator_points": [
            {
                "comparator_point_id": "comparator-point-mobile-work",
                "issue_id": "mobile_work",
                "issue_label": "Mobile work / home office",
                "comparison_strength": "moderate",
                "comparison_quality": "high_quality_comparator",
                "point_summary": "Claimant faced extra formal requirements that were not applied to Pat Vergleich.",
                "counterargument": "Role differences remain a live alternative explanation.",
                "missing_proof": ["Final role-equivalence confirmation"],
                "evidence_uids": ["cmp-1", "cmp-2"],
                "supported_signal_ids": ["selective_formality"],
                "claimant_treatment": "Extra documentation required.",
                "colleague_treatment": "No additional paperwork required.",
            }
        ],
    }


def _actor_graph(case_id: str) -> dict[str, Any]:
    actors = [
        {
            "actor_id": "actor-claimant",
            "primary_email": "employee@example.test",
            "display_names": ["employee"],
            "role_hints": ["employee"],
        },
        {
            "actor_id": "actor-manager",
            "primary_email": "manager@example.test",
            "display_names": ["manager"],
            "role_hints": ["manager"],
        },
    ]
    if case_id in {"retaliation_rights_assertion", "comparator_unequal_treatment", "disability_participation_failures"}:
        actors.append(
            {
                "actor_id": "actor-hr",
                "primary_email": "hr@example.org",
                "display_names": ["Hanna HR"],
                "role_hints": ["hr"],
            }
        )
    if case_id == "comparator_unequal_treatment":
        actors.append(
            {
                "actor_id": "actor-comparator",
                "primary_email": "pat@example.org",
                "display_names": ["Pat Vergleich"],
                "role_hints": ["peer"],
            }
        )
    return {"actors": actors}


def _issue_framework_rows(case_id: str) -> list[dict[str, Any]]:
    if case_id == "retaliation_rights_assertion":
        return [
            {
                "issue_track": "retaliation_after_protected_event",
                "status": "supported_by_current_record",
                "support_reason": "Protected complaint was followed by project withdrawal and tighter controls within days.",
                "why_not_yet_supported": [],
                "normal_alternative_explanations": ["Restructuring context still appears in the same period."],
                "missing_document_checklist": ["Formal restructuring records"],
                "supporting_finding_ids": ["finding-retaliation-timing"],
                "supporting_citation_ids": ["ret:1"],
                "supporting_uids": ["ret-2"],
            }
        ]
    if case_id == "comparator_unequal_treatment":
        return [
            {
                "issue_track": "disability_disadvantage",
                "status": "supported_by_current_record",
                "support_reason": (
                    "Comparator messages show stricter mobile-work formality for the claimant than for Pat Vergleich."
                ),
                "why_not_yet_supported": [],
                "normal_alternative_explanations": ["Role equivalence should still be confirmed."],
                "missing_document_checklist": ["Comparator role description"],
                "supporting_finding_ids": ["finding-comparator-delta"],
                "supporting_citation_ids": ["cmp:1"],
                "supporting_uids": ["cmp-1", "cmp-2"],
            },
            {
                "issue_track": "participation_duty_gap",
                "status": "partially_supported",
                "support_reason": "Process notes suggest different participation formality around the claimant's request.",
                "why_not_yet_supported": ["Full PR/SBV mailing lists are not yet in the record."],
                "normal_alternative_explanations": ["Routine process variation remains possible."],
                "missing_document_checklist": ["Full PR/SBV email trail"],
                "supporting_finding_ids": ["finding-comparator-delta"],
                "supporting_citation_ids": ["cmp:1"],
                "supporting_uids": ["cmp-1"],
            },
        ]
    if case_id == "eingruppierung_task_withdrawal":
        return [
            {
                "issue_track": "eingruppierung_dispute",
                "status": "supported_by_current_record",
                "support_reason": (
                    "Task-withdrawal emails and notes indicate a gap between actual work and the recorded TD baseline."
                ),
                "why_not_yet_supported": [],
                "normal_alternative_explanations": ["Ordinary reprioritization is still possible."],
                "missing_document_checklist": ["Signed updated job evaluation"],
                "supporting_finding_ids": ["finding-eingruppierung"],
                "supporting_citation_ids": ["ing:1"],
                "supporting_uids": ["ing-1"],
            }
        ]
    if case_id == "chronology_contradiction":
        return [
            {
                "issue_track": "participation_duty_gap",
                "status": "partially_supported",
                "support_reason": "Meeting and follow-up records diverge on promised SBV inclusion before implementation.",
                "why_not_yet_supported": ["No later written summary confirming SBV inclusion was recovered."],
                "normal_alternative_explanations": ["Urgency may explain the missing written summary."],
                "missing_document_checklist": ["Written meeting summary", "SBV invitation record"],
                "supporting_finding_ids": ["finding-contradiction"],
                "supporting_citation_ids": ["chr:1"],
                "supporting_uids": ["chr-1", "chr-2"],
            }
        ]
    return [
        {
            "issue_track": "disability_disadvantage",
            "status": "partially_supported",
            "support_reason": (
                "Accommodation-dispute emails and attendance records show medical recommendations were not clearly integrated."
            ),
            "why_not_yet_supported": ["Formal accommodation decision memo is still missing."],
            "normal_alternative_explanations": ["Manager may have applied a broad office-presence policy."],
            "missing_document_checklist": ["Accommodation decision memo"],
            "supporting_finding_ids": ["finding-participation-gap"],
            "supporting_citation_ids": ["dis:1"],
            "supporting_uids": ["dis-1"],
        },
        {
            "issue_track": "participation_duty_gap",
            "status": "partially_supported",
            "support_reason": "SBV involvement appears discussed but delayed in the initial process sequence.",
            "why_not_yet_supported": ["Full SBV calendar and email records are not yet complete."],
            "normal_alternative_explanations": ["The manager may have viewed SBV timing as not yet triggered."],
            "missing_document_checklist": ["SBV calendar invite", "PR / SBV email chain"],
            "supporting_finding_ids": ["finding-participation-gap"],
            "supporting_citation_ids": ["dis:1"],
            "supporting_uids": ["dis-1"],
        },
        {
            "issue_track": "prevention_duty_gap",
            "status": "partially_supported",
            "support_reason": "Follow-up materials mention prevention/BEM without showing timely initiation.",
            "why_not_yet_supported": ["No complete prevention/BEM record is attached."],
            "normal_alternative_explanations": ["Process may have still been in an early stage."],
            "missing_document_checklist": ["BEM / prevention record"],
            "supporting_finding_ids": ["finding-participation-gap"],
            "supporting_citation_ids": ["dis:1"],
            "supporting_uids": ["dis-1"],
        },
    ]


def build_fixture_answer_context(case_id: str) -> dict[str, Any]:
    """Return a deterministic rich answer-context payload for one realistic fixture case."""
    case = acceptance_case(case_id)
    overrides = case.intake_overrides["case_scope"]
    candidates = _message_candidates(case_id)
    findings = _findings(case_id)
    timeline_events = [
        {
            "uid": candidate["uid"],
            "date": candidate["date"],
            "subject": candidate["subject"],
            "conversation_id": f"{case_id}-conv",
        }
        for candidate in candidates
    ]
    bundle_sources = [
        {
            "source_id": f"email:{candidate['uid']}",
            "source_type": "email",
            "document_kind": "email_body",
            "uid": candidate["uid"],
            "actor_id": "actor-manager" if candidate["sender_email"] != "employee@example.test" else "actor-claimant",
            "title": candidate["subject"],
            "date": candidate["date"],
            "snippet": candidate["snippet"],
            "source_reliability": {"level": "high", "basis": "authored_email_body"},
            "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
            "chronology_anchor": {"date": str(candidate["date"]).split("T", 1)[0]},
            "provenance": {"evidence_handle": f"email:{candidate['uid']}"},
        }
        for candidate in candidates
    ]
    return {
        "search": {
            "top_k": 8,
            "date_from": overrides["date_from"],
            "date_to": overrides["date_to"],
            "hybrid": False,
            "rerank": False,
        },
        "case_bundle": {
            "bundle_id": f"fixture:{case_id}",
            "scope": {
                "employment_issue_tracks": list(_as_list(overrides.get("employment_issue_tracks"))),
                "allegation_focus": list(_as_list(overrides.get("allegation_focus"))),
                "analysis_goal": str(overrides.get("analysis_goal") or ""),
                "context_notes": case.prompt_text,
            },
            "target_person": overrides.get("target_person"),
        },
        "multi_source_case_bundle": {
            "summary": {"missing_source_types": [], "source_type_counts": {"email": len(bundle_sources)}},
            "chronology_anchors": [
                {
                    "source_id": source["source_id"],
                    "source_type": source["source_type"],
                    "document_kind": source["document_kind"],
                    "date": source["date"],
                    "title": source["title"],
                    "reliability_level": "high",
                }
                for source in bundle_sources
            ],
            "sources": bundle_sources,
            "source_links": [],
            "source_type_profiles": [],
        },
        "timeline": {"events": timeline_events},
        "power_context": {"missing_org_context": False},
        "case_patterns": {"summary": {"behavior_cluster_count": max(1, len(candidates))}},
        "retaliation_analysis": _retaliation_analysis(case_id),
        "comparative_treatment": _comparative_treatment(case_id),
        "actor_identity_graph": _actor_graph(case_id),
        "communication_graph": {"graph_findings": []},
        "finding_evidence_index": {"findings": findings},
        "evidence_table": {"row_count": len(findings)},
        "behavioral_strength_rubric": {"version": "1"},
        "investigation_report": {
            "summary": {
                "section_count": 3,
                "supported_section_count": 3,
                "insufficient_section_count": 0,
            },
            "sections": {
                "missing_information": {
                    "section_id": "missing_information",
                    "title": "Missing Information / Further Evidence Needed",
                    "status": "supported",
                    "entries": [{"text": "Comparator-role parity and complete calendar records remain useful."}],
                },
                "employment_issue_frameworks": {
                    "section_id": "employment_issue_frameworks",
                    "title": "Employment Issue Frameworks",
                    "status": "supported",
                    "issue_tracks": _issue_framework_rows(case_id),
                },
                "overall_assessment": {
                    "section_id": "overall_assessment",
                    "title": "Overall Assessment",
                    "status": "supported",
                    "entries": [{"text": "The current record shows mixed but reviewable case signals."}],
                },
            },
        },
        "candidates": candidates,
    }
