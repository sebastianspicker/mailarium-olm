from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_write_and_load_active_results_manifest_uses_relative_paths(tmp_path: Path) -> None:
    from src.investigation_results_workspace import load_active_results_manifest, write_active_results_manifest

    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "run.md"
    report = results_root / "03_exhaustive_run" / "report.json"
    register = results_root / "11_memo_draft_dashboard" / "question_register.md"
    open_tasks = results_root / "11_memo_draft_dashboard" / "open_tasks_companion.md"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    register.parent.mkdir(parents=True, exist_ok=True)
    open_tasks.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("stub", encoding="utf-8")
    report.write_text("stub", encoding="utf-8")
    register.write_text("question register for P32 investigation_2026-04-16_P32", encoding="utf-8")
    open_tasks.write_text("open tasks for P32 investigation_2026-04-16_P32", encoding="utf-8")

    written = write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:abc123",
        run_id="investigation_2026-04-16_P32",
        phase_id="P32",
        active_checkpoint=checkpoint,
        active_result_paths=[report],
        question_register_path=register,
        open_tasks_companion_path=open_tasks,
    )

    loaded = load_active_results_manifest(results_root)

    assert written["status"] == "active"
    assert loaded["matter_id"] == "matter:abc123"
    assert loaded["active_checkpoint"] == "_checkpoints/run.md"
    assert loaded["active_result_paths"] == ["03_exhaustive_run/report.json"]
    assert loaded["question_register_path"] == "11_memo_draft_dashboard/question_register.md"
    assert loaded["open_tasks_companion_path"] == "11_memo_draft_dashboard/open_tasks_companion.md"
    assert loaded["curation"]["status"] == "curated_current"
    assert loaded["curation"]["current_ledgers"] == [
        "11_memo_draft_dashboard/question_register.md",
        "11_memo_draft_dashboard/open_tasks_companion.md",
    ]


def test_archive_results_paths_moves_files_under_archive_subdir(tmp_path: Path) -> None:
    from src.investigation_results_workspace import archive_results_paths

    results_root = tmp_path / "results"
    report = results_root / "03_exhaustive_run" / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("{}", encoding="utf-8")

    archived = archive_results_paths(
        results_root=results_root,
        relative_paths=["03_exhaustive_run/report.json"],
        archive_label="superseded_run",
    )

    assert archived == ["_archive/superseded_run/03_exhaustive_run/report.json"]
    assert not report.exists()
    assert (results_root / archived[0]).read_text(encoding="utf-8") == "{}"


def test_write_active_results_manifest_rejects_absolute_path_outside_results_root(tmp_path: Path) -> None:
    from src.investigation_results_workspace import write_active_results_manifest

    results_root = tmp_path / "results"
    outside_checkpoint = tmp_path / "outside.md"
    outside_checkpoint.write_text("stub", encoding="utf-8")

    with pytest.raises(ValueError, match="results path must stay within"):
        write_active_results_manifest(
            results_root=results_root,
            matter_id="matter:abc123",
            run_id="investigation_2026-04-16_P32",
            phase_id="P32",
            active_checkpoint=outside_checkpoint,
            active_result_paths=[],
        )


def test_write_active_results_manifest_rejects_relative_traversal(tmp_path: Path) -> None:
    from src.investigation_results_workspace import write_active_results_manifest

    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "run.md"
    outside_report = tmp_path / "outside.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("stub", encoding="utf-8")
    outside_report.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="results path must stay within"):
        write_active_results_manifest(
            results_root=results_root,
            matter_id="matter:abc123",
            run_id="investigation_2026-04-16_P32",
            phase_id="P32",
            active_checkpoint=checkpoint,
            active_result_paths=["../outside.json"],
        )


def test_archive_results_paths_rejects_escape_before_any_rename(tmp_path: Path) -> None:
    from src.investigation_results_workspace import archive_results_paths

    results_root = tmp_path / "results"
    report = results_root / "03_exhaustive_run" / "report.json"
    outside = tmp_path / "outside.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("{}", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="results path must stay within"):
        archive_results_paths(
            results_root=results_root,
            relative_paths=["03_exhaustive_run/report.json", "../outside.json"],
            archive_label="superseded_run",
        )

    assert report.exists()
    assert report.read_text(encoding="utf-8") == "{}"
    assert outside.exists()
    assert not (results_root / "_archive" / "superseded_run" / "03_exhaustive_run" / "report.json").exists()


def test_archive_results_paths_rejects_absolute_source_outside_results_root(tmp_path: Path) -> None:
    from src.investigation_results_workspace import archive_results_paths

    results_root = tmp_path / "results"
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="results path must stay within"):
        archive_results_paths(
            results_root=results_root,
            relative_paths=[str(outside.resolve())],
            archive_label="superseded_run",
        )


def test_active_results_manifest_is_machine_readable_json(tmp_path: Path) -> None:
    from src.investigation_results_workspace import write_active_results_manifest

    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "run.md"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("stub", encoding="utf-8")

    write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:abc123",
        run_id="investigation_2026-04-16_P32",
        phase_id="P32",
        active_checkpoint=checkpoint,
        active_result_paths=[],
    )

    manifest = json.loads((results_root / "active_run.json").read_text(encoding="utf-8"))

    assert manifest["version"] == 2
    assert manifest["archive_dir"] == "_archive"
    assert manifest["curation"]["status"] == "raw_results_pending_curation"


def test_write_active_results_manifest_handles_repo_relative_inputs(tmp_path: Path, monkeypatch) -> None:
    from src.investigation_results_workspace import write_active_results_manifest

    monkeypatch.chdir(tmp_path)
    results_root = Path("results")
    checkpoint = results_root / "_checkpoints" / "run.md"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("stub", encoding="utf-8")

    manifest = write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:abc123",
        run_id="investigation_2026-04-16_P32",
        phase_id="P32",
        active_checkpoint=Path("results/_checkpoints/run.md"),
        active_result_paths=[Path("results/_checkpoints/run.md")],
    )

    assert manifest["active_checkpoint"] == "_checkpoints/run.md"
    assert manifest["active_result_paths"] == ["_checkpoints/run.md"]
    assert manifest["curation"]["status"] == "raw_results_pending_curation"


def test_write_active_results_manifest_marks_stale_ledgers_when_phase_references_lag(tmp_path: Path) -> None:
    from src.investigation_results_workspace import write_active_results_manifest

    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "run.md"
    report = results_root / "03_exhaustive_run" / "report.json"
    register = results_root / "11_memo_draft_dashboard" / "question_register.md"
    open_tasks = results_root / "11_memo_draft_dashboard" / "open_tasks_companion.md"
    for path, body in (
        (checkpoint, "stub"),
        (report, "{}"),
        (register, "still documents P40"),
        (open_tasks, "still documents investigation_2026-04-16_P40"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    manifest = write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:abc123",
        run_id="investigation_2026-04-16_P50",
        phase_id="P50",
        active_checkpoint=checkpoint,
        active_result_paths=[report],
        question_register_path=register,
        open_tasks_companion_path=open_tasks,
    )

    assert manifest["curation"]["status"] == "stale_curated_ledgers"
    assert manifest["curation"]["stale_ledgers"] == [
        "11_memo_draft_dashboard/question_register.md",
        "11_memo_draft_dashboard/open_tasks_companion.md",
    ]
    assert manifest["curation"]["required_action"] == "refresh_or_invalidate_stale_ledgers"


def test_write_active_results_manifest_requires_both_run_and_phase_for_current_ledgers(tmp_path: Path) -> None:
    from src.investigation_results_workspace import write_active_results_manifest

    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "run.md"
    register = results_root / "11_memo_draft_dashboard" / "question_register.md"
    open_tasks = results_root / "11_memo_draft_dashboard" / "open_tasks_companion.md"
    for path, body in (
        (checkpoint, "stub"),
        (register, "question register for P70 only"),
        (open_tasks, "open tasks for investigation_2026-04-16_P70 only"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    manifest = write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:abc123",
        run_id="run-70",
        phase_id="P70",
        active_checkpoint=checkpoint,
        active_result_paths=[],
        question_register_path=register,
        open_tasks_companion_path=open_tasks,
    )

    assert manifest["curation"]["status"] == "stale_curated_ledgers"
    assert manifest["curation"]["current_ledgers"] == []
