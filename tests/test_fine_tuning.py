"""Training-data and synchronous trainer public contracts."""

from __future__ import annotations

import json

from mailarium.fine_tuner import FineTuner, _count_lines
from mailarium.training_data_generator import TrainingDataGenerator, _truncate


def test_truncate_bounds_text():
    assert _truncate("abcdefgh", 4) == "abcd"


def test_training_generator_empty_database_produces_no_triplets():
    from mailarium.email_db import EmailDatabase

    generator = TrainingDataGenerator(EmailDatabase(":memory:"))
    assert generator.generate_triplets() == []


def test_empty_training_data_returns_stable_error_without_loading_models(tmp_path):
    result = FineTuner(device="cpu").fine_tune(str(tmp_path / "empty.jsonl"), str(tmp_path / "output"))
    assert result == {
        "output_dir": str(tmp_path / "output"),
        "epochs": 0,
        "triplet_count": 0,
        "mode": "dense",
        "status": "error: empty training data",
    }


def test_count_lines_ignores_blank_rows(tmp_path):
    data = tmp_path / "triplets.jsonl"
    data.write_text(json.dumps({"query": "q", "pos": "p", "neg": "n"}) + "\n\n", encoding="utf-8")
    assert _count_lines(str(data)) == 1
