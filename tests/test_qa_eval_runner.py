import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest


def test_default_live_report_path_uses_agent_report_convention():
    from src.qa_eval import default_live_report_path

    path = default_live_report_path(Path("docs/agent/qa_eval_questions.core.json"))

    assert path.name == "qa_eval_report.core.live.json"
    assert str(path).endswith("private/tests/results/qa_eval/qa_eval_report.core.live.json")


def test_default_live_report_path_uses_backend_specific_suffix():
    from src.qa_eval import default_live_report_path

    path = default_live_report_path(Path("docs/agent/qa_eval_questions.live_expanded.json"), backend="embedding")

    assert path.name == "qa_eval_report.live_expanded.embedding.live.json"
    assert str(path).endswith("private/tests/results/qa_eval/qa_eval_report.live_expanded.embedding.live.json")


def test_default_remediation_report_path_uses_agent_report_convention():
    from src.qa_eval import default_remediation_report_path

    path = default_remediation_report_path(Path("docs/agent/qa_eval_report.live_expanded.live.json"))

    assert path.name == "qa_eval_remediation.live_expanded.live.json"
    assert str(path).endswith("private/tests/results/qa_eval/qa_eval_remediation.live_expanded.live.json")


def test_query_terms_extracts_lowercase_natural_language_tokens():
    from src.qa_eval import _query_terms

    terms = _query_terms("Which email had attachments and discussed Configurator 2 Blueprints?")

    assert "which" not in terms
    assert "attachments" not in terms
    assert "configurator" in terms
    assert "blueprints" in terms


def test_query_terms_drop_mailbox_noise_but_keep_topic_words():
    from src.qa_eval import _query_terms

    terms = _query_terms("Which image-only message was titled Manual and who sent the HARICA certificate mail?")

    assert "message" not in terms
    assert "sent" not in terms
    assert "mail" not in terms
    assert "manual" in terms
    assert "harica" in terms


def test_run_qa_eval_live_defaults_to_persistent_report(monkeypatch, tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    expected_questions_path = questions_path
    output_path = tmp_path / "qa_eval_report.core.live.json"

    monkeypatch.setattr(runner, "ROOT", tmp_path)

    class _LiveDeps:
        live_backend = "sqlite_fallback"

    def fake_resolve_live_deps(*, preferred_backend="auto"):
        assert preferred_backend == "auto"
        return _LiveDeps()

    def fake_default_live_report_path(path: Path, *, backend=None) -> Path:
        assert path == questions_path
        assert backend is None
        return output_path

    def fake_run_evaluation_sync(*, questions_path, results_path=None, live_deps=None, limit=None, source_mode="auto"):
        assert questions_path == expected_questions_path
        assert live_deps is not None
        assert source_mode == "auto"
        return {"summary": {"total_cases": 0}, "results": []}

    monkeypatch.setattr("src.qa_eval.resolve_live_deps", fake_resolve_live_deps)
    monkeypatch.setattr("src.qa_eval.default_live_report_path", fake_default_live_report_path)
    monkeypatch.setattr("src.qa_eval.run_evaluation_sync", fake_run_evaluation_sync)

    exit_code = runner.main(["--questions", str(questions_path), "--live"])

    assert exit_code == 0
    assert output_path.exists()
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "live"
    assert status["status"] == "ok"
    assert status["live_backend"] == "sqlite_fallback"
    assert status["output"] == str(output_path)
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["summary"]["total_cases"] == 0
    assert persisted["results"] == []


def test_run_qa_eval_check_thresholds_returns_nonzero_on_threshold_failure(monkeypatch, tmp_path: Path):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.legal_support.captured.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")

    def fake_run_evaluation_sync(*, questions_path, results_path=None, live_deps=None, limit=None, source_mode="auto"):
        del results_path, live_deps, limit
        assert source_mode == "auto"
        return {
            "questions_path": str(questions_path),
            "results_path": None,
            "total_cases": 1,
            "cases": [],
            "results": [],
            "source_mode": "captured_only",
            "summary": {
                "total_cases": 1,
                "legal_support_product_completeness": {"scorable": 1, "passed": 0, "failed": 1},
            },
            "failure_taxonomy": {"total_flagged_cases": 1, "categories": {}, "ranked_categories": []},
            "source_counts": {"captured": 1},
        }

    monkeypatch.setattr("src.qa_eval.run_evaluation_sync", fake_run_evaluation_sync)

    exit_code = runner.main(
        ["--questions", str(questions_path), "--results", str(tmp_path / "results.json"), "--check-thresholds"]
    )

    assert exit_code == 2


def test_run_qa_eval_live_embedding_reexecs_into_project_venv(monkeypatch, tmp_path: Path):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(runner, "_interpreter_has_module", lambda name: False)
    monkeypatch.setattr(runner, "_project_venv_python", lambda: venv_python)

    seen: dict[str, object] = {}

    class _Completed:
        returncode = 0

    def fake_run(cmd, cwd):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return _Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    exit_code = runner.main(["--questions", str(questions_path), "--live", "--live-backend", "embedding"])

    assert exit_code == 0
    assert seen["cmd"] == [
        str(venv_python),
        str(runner.__file__),
        "--questions",
        str(questions_path),
        "--live",
        "--live-backend",
        "embedding",
    ]


def test_run_qa_eval_live_writes_blocked_report(monkeypatch, tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    output_path = tmp_path / "qa_eval_report.core.live.json"

    def fake_resolve_live_deps(*, preferred_backend="auto"):
        assert preferred_backend == "auto"
        raise ModuleNotFoundError("No module named 'chromadb'")

    def fake_default_live_report_path(path: Path, *, backend=None) -> Path:
        assert path == questions_path
        assert backend is None
        return output_path

    monkeypatch.setattr("src.qa_eval.resolve_live_deps", fake_resolve_live_deps)
    monkeypatch.setattr("src.qa_eval.default_live_report_path", fake_default_live_report_path)

    exit_code = runner.main(["--questions", str(questions_path), "--live"])

    assert exit_code == 1
    assert output_path.exists()
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "live"
    assert status["status"] == "blocked"
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["live_status"]["status"] == "blocked"
    assert persisted["live_status"]["error_type"] == "ModuleNotFoundError"
    assert "chromadb" in persisted["live_status"]["error"]
    assert persisted["threshold_verdict"]["status"] == "fail"


def test_run_qa_eval_remediation_writes_persistent_summary(monkeypatch, tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    report_path = tmp_path / "qa_eval_report.live_expanded.live.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total_cases": 3,
                    "bucket_counts": {"fact_lookup": 1, "thread_process": 2},
                    "top_1_correctness": {"scorable": 3, "passed": 1, "failed": 2},
                    "support_uid_hit_top_3": {"scorable": 3, "passed": 1, "failed": 2},
                    "confidence_calibration_match": {"scorable": 3, "passed": 1, "failed": 2},
                },
                "failure_taxonomy": {
                    "total_flagged_cases": 2,
                    "ranked_categories": [
                        {
                            "category": "retrieval_recall",
                            "flagged_cases": 2,
                            "failed_cases": 2,
                            "weak_cases": 0,
                            "case_ids": ["fact-1", "thread-1"],
                            "drivers": ["no_supported_hit"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "qa_eval_remediation.live_expanded.live.json"

    monkeypatch.setattr(runner, "ROOT", tmp_path)

    exit_code = runner.main(["--remediation-from", str(report_path), "--output", str(output_path)])

    assert exit_code == 0
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["total_cases"] == 3
    assert persisted["failure_taxonomy"]["ranked_categories"][0]["category"] == "retrieval_recall"
    assert json.loads(capsys.readouterr().out)["immediate_next_targets"][0]["category"] == "retrieval_recall"


def test_run_qa_eval_bootstrap_writes_reviewable_sampled_questions(tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.template.json"
    questions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "description": "Template set.",
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "status": "todo",
                        "question": "Who asked for the updated budget?",
                        "expected_answer": "TODO(human): fill after synthetic corpus review",
                        "expected_support_uids": [],
                        "expected_top_uid": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results_path = tmp_path / "qa_eval_results.captured.json"
    results_path.write_text(
        json.dumps(
            {
                "fact-001": {
                    "count": 1,
                    "candidates": [{"uid": "uid-1", "score": 0.91}],
                    "attachment_candidates": [],
                    "answer_quality": {"top_candidate_uid": "uid-1", "confidence_label": "high", "ambiguity_reason": None},
                }
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "qa_eval_questions.sampled.json"

    exit_code = runner.main(
        [
            "--questions",
            str(questions_path),
            "--results",
            str(results_path),
            "--bootstrap",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["cases"][0]["status"] == "sampled"
    assert persisted["cases"][0]["bootstrap_candidates"][0]["uid"] == "uid-1"
    assert "TODO(human)" not in output_path.read_text(encoding="utf-8")
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "bootstrap"
    assert status["status"] == "ok"


def test_run_qa_eval_requires_explicit_source_mode_when_results_and_live_are_combined(tmp_path: Path):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    results_path = tmp_path / "qa_eval_results.core.json"
    results_path.write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(SystemExit):
        runner.main(["--questions", str(questions_path), "--results", str(results_path), "--live"])


def test_run_evaluation_live_uses_real_answer_context_with_deterministic_deps(tmp_path: Path):
    from src.qa_eval import run_evaluation_sync

    questions_path = tmp_path / "qa_eval_questions.live.json"
    questions_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "live-001",
                        "bucket": "fact_lookup",
                        "question": "Which message mentioned the budget meeting?",
                        "status": "labeled",
                        "expected_support_uids": ["uid-live-1"],
                        "expected_top_uid": "uid-live-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _Retriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            assert query == "Which message mentioned the budget meeting?"
            assert top_k == 5
            assert kwargs == {}
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-live-1",
                        "subject": "Budget meeting",
                        "sender_email": "manager@example.org",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-12T10:00:00",
                        "conversation_id": "conv-live-1",
                    },
                    chunk_id="chunk-live-1",
                    text="Please prepare for the budget meeting tomorrow.",
                    score=0.93,
                )
            ]

    class _DB:
        conn = None

        def get_emails_full_batch(self, uids):
            assert uids == ["uid-live-1"]
            return {
                "uid-live-1": {
                    "uid": "uid-live-1",
                    "body_text": "Please prepare for the budget meeting tomorrow.",
                    "normalized_body_source": "body_text_html",
                    "conversation_id": "conv-live-1",
                    "to": ["alex@example.org"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "manager@example.org",
                    "reply_context_to_json": "[]",
                }
            }

        def get_thread_emails(self, conversation_id):
            assert conversation_id == "conv-live-1"
            return [
                {
                    "uid": "uid-live-1",
                    "sender_email": "manager@example.org",
                    "date": "2026-02-12T10:00:00",
                }
            ]

        def attachments_for_email(self, uid):
            assert uid == "uid-live-1"
            return []

    class _Deps:
        live_backend = "deterministic_fixture"
        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return _DB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        @staticmethod
        def sanitize(text: str) -> str:
            return text

        @staticmethod
        def tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def write_tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def idempotent_write_annotations(title: str):
            return {"title": title}

    report = run_evaluation_sync(questions_path=questions_path, live_deps=cast(Any, _Deps()))

    assert report["source_counts"] == {"live": 1}
    assert report["results"][0]["top_uid"] == "uid-live-1"
    assert report["results"][0]["support_uid_hit"] is True
