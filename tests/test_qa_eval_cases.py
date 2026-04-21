import json
from pathlib import Path


def test_load_question_cases_reads_template_object(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "question": "Who asked for the updated budget?",
                        "expected_support_uids": ["uid-1"],
                        "triage_tags": ["retrieval_recall"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert len(cases) == 1
    assert cases[0].id == "fact-001"
    assert cases[0].expected_support_uids == ["uid-1"]
    assert cases[0].triage_tags == ["retrieval_recall"]


def test_load_question_cases_reads_case_scope_and_bundle_expectations(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "investigation-001",
                        "bucket": "investigation_case",
                        "question": "Analyze the rapid review conversation.",
                        "case_scope": {
                            "target_person": {"name": "Alex Example"},
                            "suspected_actors": [{"name": "Morgan Manager", "email": "manager@example.com"}],
                            "allegation_focus": ["hostility", "exclusion"],
                            "analysis_goal": "internal_review",
                        },
                        "expected_case_bundle_uids": ["uid-1", "uid-2"],
                        "expected_source_types": ["email"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert len(cases) == 1
    assert cases[0].case_scope is not None
    assert cases[0].case_scope.analysis_goal == "internal_review"
    assert cases[0].expected_case_bundle_uids == ["uid-1", "uid-2"]
    assert cases[0].expected_source_types == ["email"]


def test_load_question_cases_reads_behavioral_analysis_expectations(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "behavior-001",
                        "bucket": "explicit_hostility",
                        "question": "Assess the conduct in this message.",
                        "expected_timeline_uids": ["uid-1"],
                        "expected_behavior_ids": ["escalation", "public_correction"],
                        "expected_counter_indicator_markers": ["process friction"],
                        "expected_max_claim_level": "observed_fact",
                        "expected_report_sections": ["executive_summary", "overall_assessment"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert cases[0].expected_timeline_uids == ["uid-1"]
    assert cases[0].expected_behavior_ids == ["escalation", "public_correction"]
    assert cases[0].expected_counter_indicator_markers == ["process friction"]
    assert cases[0].expected_max_claim_level == "observed_fact"
    assert cases[0].expected_report_sections == ["executive_summary", "overall_assessment"]


def test_load_question_cases_reads_grounding_and_forbidden_expectations(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "legal-support-001",
                        "bucket": "legal_support_workspace",
                        "question": "Check grounded legal-support outputs.",
                        "expected_answer_terms": ["policy", "meeting"],
                        "expected_support_source_ids": ["email:uid-1"],
                        "expected_case_bundle_source_ids": ["email:uid-1"],
                        "expected_timeline_source_ids": ["email:uid-1"],
                        "expected_legal_support_products": ["lawyer_issue_matrix"],
                        "expected_legal_support_source_ids": ["email:uid-1"],
                        "forbidden_support_source_ids": ["email:uid-forbidden"],
                        "forbidden_issue_ids": ["forbidden_issue"],
                        "forbidden_actor_ids": ["actor-forbidden"],
                        "forbidden_dashboard_cards": ["forbidden_card"],
                        "forbidden_checklist_group_ids": ["forbidden_group"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert cases[0].expected_answer_terms == ["policy", "meeting"]
    assert cases[0].expected_support_source_ids == ["email:uid-1"]
    assert cases[0].expected_case_bundle_source_ids == ["email:uid-1"]
    assert cases[0].expected_timeline_source_ids == ["email:uid-1"]
    assert cases[0].expected_legal_support_source_ids == ["email:uid-1"]
    assert cases[0].forbidden_support_source_ids == ["email:uid-forbidden"]
    assert cases[0].forbidden_issue_ids == ["forbidden_issue"]
    assert cases[0].forbidden_actor_ids == ["actor-forbidden"]
    assert cases[0].forbidden_dashboard_cards == ["forbidden_card"]
    assert cases[0].forbidden_checklist_group_ids == ["forbidden_group"]


def test_bootstrap_question_set_produces_reviewable_sampled_artifact(tmp_path: Path):
    from src.qa_eval import bootstrap_question_set, load_question_cases

    questions_path = tmp_path / "questions.template.json"
    questions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "description": "Template question set.",
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "status": "todo",
                        "question": "Who asked for the updated budget?",
                        "expected_answer": "TODO(human): fill after synthetic corpus review",
                        "expected_support_uids": [],
                        "expected_top_uid": None,
                        "notes": "Simple sender lookup from message body.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "fact-001": {
                    "count": 1,
                    "candidates": [
                        {
                            "uid": "uid-1",
                            "score": 0.91,
                            "subject": "Budget update",
                        }
                    ],
                    "attachment_candidates": [],
                    "answer_quality": {
                        "top_candidate_uid": "uid-1",
                        "confidence_label": "high",
                        "ambiguity_reason": None,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    bootstrapped = bootstrap_question_set(questions_path=questions_path, results_path=results_path)
    output_path = tmp_path / "questions.sampled.json"
    output_path.write_text(json.dumps(bootstrapped), encoding="utf-8")

    cases = load_question_cases(output_path)

    assert len(cases) == 1
    assert cases[0].status == "sampled"
    assert cases[0].expected_answer == ""
    assert cases[0].expected_support_uids == []
    assert cases[0].expected_top_uid is None
    assert bootstrapped["bootstrap_metadata"]["status"] == "review_required"
    assert bootstrapped["cases"][0]["bootstrap_candidates"][0]["uid"] == "uid-1"
    assert "TODO(human)" not in json.dumps(bootstrapped)


def test_template_question_set_is_machine_readable_without_manual_todo_markers() -> None:
    payload = json.loads(Path("docs/agent/qa_eval_questions.template.json").read_text(encoding="utf-8"))

    assert "bootstrap" in payload["description"]
    assert all(case["expected_answer"] == "" for case in payload["cases"])
    assert "TODO(human)" not in json.dumps(payload)


def test_detection_benchmark_pack_and_recovery_are_evaluation_only(tmp_path: Path) -> None:
    from src.case_operator_intake import build_detection_benchmark_pack
    from src.qa_eval_bootstrap import benchmark_detection_recovery

    dossier = tmp_path / "dossier.md"
    dossier.write_text("manager Schwellenbach\nmobiles Arbeiten\n", encoding="utf-8")

    pack = build_detection_benchmark_pack(
        source_paths=[str(dossier)],
        seed_actors=["manager Schwellenbach", "Anabel Derlam"],
        issue_families=["mobiles Arbeiten", "BEM"],
        chronology_anchor_markers=[
            {"date": "2026-03-06", "title_terms": ["vergeltungsgespraech"]},
        ],
        manifest_link_targets=[
            {"document_source_id": "manifest:doc:1", "email_source_id": "email:uid-1"},
        ],
        required_report_sections=["matter_evidence_index", "overall_assessment"],
    )

    recovery = benchmark_detection_recovery(
        benchmark_pack=pack,
        payload={
            "archive_harvest": {
                "evidence_bank": [
                    {
                        "subject": "mobiles Arbeiten",
                        "sender_name": "manager Schwellenbach",
                        "snippet": "BEM und mobiles Arbeiten",
                    }
                ]
            },
            "master_chronology": {
                "entries": [
                    {
                        "chronology_id": "CHR-1",
                        "date": "2026-03-06",
                        "title": "Vergeltungsgespraech",
                        "description": "Documented meeting.",
                    }
                ]
            },
            "multi_source_case_bundle": {
                "sources": [
                    {"source_id": "manifest:doc:1", "title": "Dossier note"},
                    {"source_id": "email:uid-1", "title": "Status mail"},
                ],
                "source_links": [
                    {
                        "from_source_id": "manifest:doc:1",
                        "to_source_id": "email:uid-1",
                        "link_type": "declared_related_record",
                        "confidence": "high",
                    }
                ],
            },
            "investigation_report": {
                "sections": {
                    "matter_evidence_index": {"status": "supported"},
                    "overall_assessment": {"status": "supported"},
                }
            },
        },
    )

    assert pack["usage_rule"] == "evaluation_only_not_search_filter"
    assert recovery["actor_recovery"]["recovered"] == 1
    assert recovery["issue_family_recovery"]["recovered"] == 2
    assert recovery["chronology_anchor_recovery"]["recovered"] == 1
    assert recovery["manifest_link_recovery"]["recovered"] == 1
    assert recovery["mixed_source_report_completeness"]["recovered"] == 2
