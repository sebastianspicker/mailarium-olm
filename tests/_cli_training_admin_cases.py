# ruff: noqa: I001
"""CLI training and administration command dispatch with prerequisite validation."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from mailarium.cli import (
    _cmd_admin,
    _cmd_training,
    _run_fine_tune,
    _run_generate_training_data,
)

# ── Fake SearchResult ────────────────────────────────────────────────

from .helpers.cli_fakes import _make_retriever


class TestCmdTraining:
    def test_training_generate_data(self):
        args = argparse.Namespace(
            training_action="generate-data",
            output_path="data.jsonl",
        )
        with patch("mailarium.cli_commands._run_generate_training_data") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_training(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("data.jsonl")

    def test_training_fine_tune(self):
        args = argparse.Namespace(
            training_action="fine-tune",
            data_path="train.jsonl",
            output_dir="models/custom",
            epochs=5,
        )
        with patch("mailarium.cli_commands._run_fine_tune") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_training(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with(
                "train.jsonl",
                output_dir="models/custom",
                epochs=5,
                mode="dense",
            )

    def test_training_fine_tune_defaults(self):
        args = argparse.Namespace(
            training_action="fine-tune",
            data_path="train.jsonl",
        )
        with patch("mailarium.cli_commands._run_fine_tune") as mock_fn:
            with pytest.raises(SystemExit):
                _cmd_training(args)
            call_kwargs = mock_fn.call_args
            assert call_kwargs[1]["output_dir"] == "models/fine-tuned"
            assert call_kwargs[1]["epochs"] == 3

    def test_training_no_action(self, capsys):
        args = argparse.Namespace(training_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_training(args)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


class TestCmdAdmin:
    def test_admin_reset_index_with_yes(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(admin_action="reset-index", yes=True)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_admin(args, retriever)
        assert exc_info.value.code == 0
        retriever.reset_index.assert_called_once()
        output = capsys.readouterr().out
        assert "Index has been reset" in output

    def test_admin_reset_index_without_yes(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(admin_action="reset-index", yes=False)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_admin(args, retriever)
        assert exc_info.value.code == 2
        retriever.reset_index.assert_not_called()
        output = capsys.readouterr().out
        assert "Refusing to reset" in output

    def test_admin_no_action(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(admin_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_admin(args, retriever)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


class TestRunGenerateTrainingData:
    def test_generate_training_data(self, capsys):
        mock_db = MagicMock()
        mock_gen = MagicMock()
        mock_gen.export_jsonl.return_value = {"triplet_count": 150}
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.training_data_generator.TrainingDataGenerator", return_value=mock_gen):
                _run_generate_training_data("train.jsonl")
        output = capsys.readouterr().out
        assert "train.jsonl" in output
        assert "150 triplets" in output


class TestRunFineTune:
    def test_fine_tune_success(self, capsys):
        mock_ft = MagicMock()
        mock_ft.fine_tune.return_value = {
            "status": "completed",
            "triplet_count": 100,
            "epochs": 3,
            "config_path": "models/config.json",
        }
        with patch("mailarium.fine_tuner.FineTuner", return_value=mock_ft):
            _run_fine_tune("train.jsonl", output_dir="models/ft", epochs=3)
        output = capsys.readouterr().out
        assert "completed" in output
        assert "100" in output
        assert "Config: models/config.json" in output

    def test_fine_tune_no_config_path(self, capsys):
        mock_ft = MagicMock()
        mock_ft.fine_tune.return_value = {
            "status": "completed",
            "triplet_count": 50,
            "epochs": 5,
            "config_path": None,
        }
        with patch("mailarium.fine_tuner.FineTuner", return_value=mock_ft):
            _run_fine_tune("train.jsonl", output_dir="models/ft", epochs=5)
        output = capsys.readouterr().out
        assert "Config:" not in output


class TestGetEmailDb:
    def test_get_email_db_missing_sqlite(self, capsys):
        from mailarium.cli import _get_email_db

        mock_settings = MagicMock()
        mock_settings.sqlite_path = "/nonexistent/path/db.sqlite"
        with patch("mailarium.cli_commands.get_settings", return_value=mock_settings):
            with pytest.raises(SystemExit) as exc_info:
                _get_email_db()
            assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "SQLite database not found" in output

    def test_get_email_db_no_path(self, capsys):
        from mailarium.cli import _get_email_db

        mock_settings = MagicMock()
        mock_settings.sqlite_path = None
        with patch("mailarium.cli_commands.get_settings", return_value=mock_settings):
            with pytest.raises(SystemExit) as exc_info:
                _get_email_db()
            assert exc_info.value.code == 1

    def test_get_email_db_success(self, tmp_path):
        from mailarium.cli import _get_email_db

        # Create a dummy sqlite file
        db_path = tmp_path / "test.sqlite"
        db_path.touch()
        mock_settings = MagicMock()
        mock_settings.sqlite_path = str(db_path)
        mock_db = MagicMock()
        with patch("mailarium.cli_commands.get_settings", return_value=mock_settings):
            with patch("mailarium.email_db.EmailDatabase", return_value=mock_db):
                result = _get_email_db()
                assert result is mock_db
