from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/prepare_case_inputs.py"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prepare_case_inputs_builds_clean_case_json_and_overrides(tmp_path: Path) -> None:
    preflight_path = tmp_path / "preflight.json"
    case_json_path = tmp_path / "case.json"
    overrides_path = tmp_path / "full_pack_overrides.json"
    preflight_path.write_text(
        json.dumps(
            {
                "draft_case_scope": {
                    "target_person": {
                        "name": "employee",
                        "email": "employee@example.test",
                    },
                    "suspected_actors": [
                        {
                            "name": "manager",
                            "email": "manager@example.test",
                            "role_hint": "manager",
                        }
                    ],
                    "context_people": [
                        {
                            "name": "Lara Langer",
                            "email": "lara.langer@example.test",
                        }
                    ],
                    "institutional_actors": [
                        {
                            "label": "HR mailbox",
                            "actor_type": "shared_mailbox",
                            "email": "hr-mailbox@example.test",
                            "function": "HR gatekeeper and notice route",
                        }
                    ],
                },
                "recommended_source_scope": "mixed_case_file",
                "matter_factual_context": "## Explicit Address Directory\n\n- hr-mailbox@example.test",
                "draft_case_analysis_input": {
                    "case_scope": {
                        "target_person": {
                            "name": "employee",
                            "email": "employee@example.test",
                            "extraction_basis": "direct_prompt_text",
                        },
                        "suspected_actors": [
                            {
                                "name": "manager",
                                "email": None,
                                "role_hint": "manager",
                                "extraction_basis": "named_person",
                            }
                        ],
                        "trigger_events": [
                            {
                                "trigger_type": "complaint",
                                "date": "2025-03-01",
                                "date_confidence": "exact",
                                "actor": {
                                    "name": "employee",
                                    "extraction_basis": "named_person",
                                },
                            }
                        ],
                        "allegation_focus": ["retaliation"],
                        "analysis_goal": "hr_review",
                        "date_from": "2025-01-01",
                        "date_to": "2025-06-30",
                    },
                    "matter_factual_context": "## Old Context\n\n- should be replaced",
                    "source_scope": "emails_only",
                    "review_mode": "retrieval_only",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--preflight",
            str(preflight_path),
            "--case-json-out",
            str(case_json_path),
            "--overrides-out",
            str(overrides_path),
        ],
        check=True,
        cwd=REPO_ROOT,
    )

    case_json = _read_json(case_json_path)
    overrides = _read_json(overrides_path)

    assert case_json["review_mode"] == "retrieval_only"
    assert case_json["source_scope"] == "mixed_case_file"
    assert case_json["matter_factual_context"] == "## Explicit Address Directory\n\n- hr-mailbox@example.test"
    assert case_json["case_scope"]["target_person"] == {
        "name": "employee",
        "email": "employee@example.test",
    }
    assert case_json["case_scope"]["suspected_actors"] == [
        {
            "name": "manager",
            "email": "manager@example.test",
            "role_hint": "manager",
        }
    ]
    assert case_json["case_scope"]["context_people"] == [
        {
            "name": "Lara Langer",
            "email": "lara.langer@example.test",
        }
    ]
    assert case_json["case_scope"]["institutional_actors"] == [
        {
            "label": "HR mailbox",
            "actor_type": "shared_mailbox",
            "email": "hr-mailbox@example.test",
            "function": "HR gatekeeper and notice route",
        }
    ]
    trigger_event = case_json["case_scope"]["trigger_events"][0]
    assert trigger_event == {
        "trigger_type": "complaint",
        "date": "2025-03-01",
        "actor": {"name": "employee"},
    }

    assert "review_mode" not in overrides
    assert overrides["source_scope"] == "mixed_case_file"
    assert overrides["matter_factual_context"] == case_json["matter_factual_context"]
    assert overrides["case_scope"]["context_people"] == case_json["case_scope"]["context_people"]
    assert overrides["case_scope"]["institutional_actors"] == case_json["case_scope"]["institutional_actors"]
    assert overrides["case_scope"]["target_person"] == {
        "name": "employee",
        "email": "employee@example.test",
    }
    assert overrides["case_scope"]["trigger_events"][0] == trigger_event


def test_prepare_case_inputs_builds_full_pack_overrides_from_curated_case_json(tmp_path: Path) -> None:
    case_json_path = tmp_path / "case.json"
    overrides_path = tmp_path / "full_pack_overrides.json"
    case_json_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {
                        "name": "employee",
                        "email": "employee@example.test",
                    },
                    "trigger_events": [
                        {
                            "trigger_type": "complaint",
                            "date": "2025-03-01",
                        }
                    ],
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                },
                "source_scope": "mixed_case_file",
                "chat_exports": [
                    {
                        "source_path": "/tmp/chat-export.html",
                        "platform": "Teams",
                    }
                ],
                "review_mode": "retrieval_only",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--case-json",
            str(case_json_path),
            "--overrides-out",
            str(overrides_path),
        ],
        check=True,
        cwd=REPO_ROOT,
    )

    overrides = _read_json(overrides_path)
    assert "review_mode" not in overrides
    assert overrides["source_scope"] == "mixed_case_file"
    assert overrides["chat_exports"] == [
        {
            "source_path": "/tmp/chat-export.html",
            "platform": "Teams",
        }
    ]
    assert overrides["case_scope"]["trigger_events"] == [
        {
            "trigger_type": "complaint",
            "date": "2025-03-01",
        }
    ]


def test_prepare_case_inputs_rejects_output_to_tracked_repo_file(tmp_path: Path) -> None:
    case_json_path = tmp_path / "case.json"
    case_json_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "employee"},
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                },
                "source_scope": "emails_only",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--case-json",
            str(case_json_path),
            "--overrides-out",
            "README.md",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "case input output" in result.stderr


def test_prepare_case_inputs_rejects_input_outside_allowed_read_roots(tmp_path: Path) -> None:
    output_path = tmp_path / "case.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--case-json",
            "/etc/hosts",
            "--case-json-out",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "allowed local read roots" in result.stderr
