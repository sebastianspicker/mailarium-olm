"""Synchronous SentenceTransformers trainer orchestration tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mailarium.fine_tuner import FineTuner


def _triplets(path: Path) -> None:
    path.write_text(json.dumps({"query": "q", "pos": "p", "neg": "n"}) + "\n", encoding="utf-8")


def test_dense_training_writes_config_manifest_and_completed_status(tmp_path):
    data, output = tmp_path / "triplets.jsonl", tmp_path / "model"
    _triplets(data)
    trainer = FineTuner(device="cpu")
    with patch.object(trainer, "_train_dense", return_value={"loss": 0.25}) as train:
        result = trainer.fine_tune(str(data), str(output), epochs=2)
    assert result["status"] == "completed"
    assert result["mode"] == "dense"
    assert train.call_count == 1
    manifest = json.loads((output / "training_manifest.json").read_text(encoding="utf-8"))
    assert manifest["metrics"] == {"loss": 0.25}
    assert manifest["training_data_sha256"]


def test_sparse_mode_selects_sparse_trainer(tmp_path):
    data, output = tmp_path / "triplets.jsonl", tmp_path / "model"
    _triplets(data)
    trainer = FineTuner(device="cpu")
    with patch.object(trainer, "_train_sparse", return_value={"loss": 0.5}) as train:
        result = trainer.fine_tune(str(data), str(output), mode="sparse")
    assert result["mode"] == "sparse"
    train.assert_called_once()


@pytest.mark.parametrize("mode", ["invalid", "", None])
def test_invalid_training_mode_is_rejected(tmp_path, mode):
    with pytest.raises(ValueError):
        FineTuner(device="cpu").fine_tune(str(tmp_path / "missing"), str(tmp_path / "out"), mode=mode)
