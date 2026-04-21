# ruff: noqa: F403
from ._investigation_report_assessment_cases import *
from ._investigation_report_issue_compact_cases import *
from ._investigation_report_rendering_cases import *


def test_build_investigation_report_threads_requested_language_contract() -> None:
    from src.investigation_report import build_investigation_report

    report = build_investigation_report(
        case_bundle={
            "scope": {
                "trigger_events": [],
                "employment_issue_tracks": ["participation_duty_gap"],
                "context_notes": "SBV participation appears missing.",
            }
        },
        candidates=[],
        timeline={"events": []},
        power_context={"missing_org_context": True, "supplied_role_facts": []},
        case_patterns={"behavior_patterns": [], "corpus_behavioral_review": {}},
        retaliation_analysis=None,
        comparative_treatment={"summary": {}, "comparator_summaries": []},
        communication_graph={"graph_findings": []},
        finding_evidence_index={"findings": []},
        evidence_table={"rows": []},
        actor_identity_graph={"actors": []},
        multi_source_case_bundle={"summary": {"source_type_counts": {"email": 1}}, "sources": []},
        output_language="de",
        translation_mode="source_only",
    )

    assert report is not None
    assert report["bilingual_workflow"]["output_language"] == "de"
    assert report["bilingual_workflow"]["translation_mode"] == "source_only"
