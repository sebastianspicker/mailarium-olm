"""Extended tests for src/fine_tuner.py — targets lines missed by existing tests."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.fine_tuner import FineTuner, _count_lines

# ── _train_with_flag_embedding ───────────────────────────────────


class TestTrainWithFlagEmbedding:
    def _make_training_data(self, tmpdir: Path, n: int = 5) -> str:
        """Create a JSONL file with n triplets."""
        data_path = tmpdir / "data.jsonl"
        with open(data_path, "w") as f:
            for i in range(n):
                f.write(
                    json.dumps(
                        {
                            "query": f"query {i}",
                            "pos": f"positive {i}",
                            "neg": f"negative {i}",
                        }
                    )
                    + "\n"
                )
        return str(data_path)

    def test_flag_embedding_writes_config(self, tmp_path):
        """_train_with_flag_embedding writes config and returns config_ready."""
        # Inject a fake FlagEmbedding module so the import succeeds
        flag_mod = types.ModuleType("FlagEmbedding")
        flag_bge = types.ModuleType("FlagEmbedding.baai_general_embedding")
        flag_ft = types.ModuleType("FlagEmbedding.baai_general_embedding.finetune")
        flag_run = types.ModuleType("FlagEmbedding.baai_general_embedding.finetune.run")
        with patch.dict(
            sys.modules,
            {
                "FlagEmbedding": flag_mod,
                "FlagEmbedding.baai_general_embedding": flag_bge,
                "FlagEmbedding.baai_general_embedding.finetune": flag_ft,
                "FlagEmbedding.baai_general_embedding.finetune.run": flag_run,
            },
        ):
            data_path = self._make_training_data(tmp_path, n=3)
            output_dir = str(tmp_path / "output")

            ft = FineTuner(device="cpu")
            result = ft._train_with_flag_embedding(
                training_data_path=data_path,
                output_dir=output_dir,
                epochs=2,
                batch_size=4,
                gradient_accumulation=8,
                learning_rate=1e-5,
                warmup_ratio=0.1,
                max_len=512,
                use_fp16=False,
                triplet_count=3,
            )

            assert result["status"] == "config_ready"
            assert result["triplet_count"] == 3
            assert result["epochs"] == 2
            assert "config_path" in result
            assert "train_command" in result

            # Verify config file was written
            config_path = Path(result["config_path"])
            assert config_path.exists()
            config_data = json.loads(config_path.read_text())
            assert config_data["base_model"] == "BAAI/bge-m3"
            assert config_data["num_train_epochs"] == 2
            assert config_data["per_device_train_batch_size"] == 4

    def test_flag_embedding_creates_output_dir(self, tmp_path):
        """_train_with_flag_embedding creates the output directory."""
        flag_mod = types.ModuleType("FlagEmbedding")
        with patch.dict(sys.modules, {"FlagEmbedding": flag_mod}):
            data_path = self._make_training_data(tmp_path, n=2)
            output_dir = str(tmp_path / "nested" / "output")

            ft = FineTuner(device="cpu")
            result = ft._train_with_flag_embedding(
                training_data_path=data_path,
                output_dir=output_dir,
                epochs=1,
                batch_size=2,
                gradient_accumulation=4,
                learning_rate=1e-5,
                warmup_ratio=0.1,
                max_len=256,
                use_fp16=False,
                triplet_count=2,
            )

            assert Path(output_dir).is_dir()
            assert result["output_dir"] == output_dir

    def test_flag_embedding_fp16_flag(self, tmp_path):
        """_train_with_flag_embedding respects use_fp16 in config."""
        flag_mod = types.ModuleType("FlagEmbedding")
        with patch.dict(sys.modules, {"FlagEmbedding": flag_mod}):
            data_path = self._make_training_data(tmp_path, n=1)
            output_dir = str(tmp_path / "output")

            ft = FineTuner(device="cuda")
            result = ft._train_with_flag_embedding(
                training_data_path=data_path,
                output_dir=output_dir,
                epochs=1,
                batch_size=4,
                gradient_accumulation=8,
                learning_rate=1e-5,
                warmup_ratio=0.1,
                max_len=512,
                use_fp16=True,
                triplet_count=1,
            )

            config_data = json.loads(Path(result["config_path"]).read_text())
            assert config_data["fp16"] is True


# ── _train_with_sentence_transformers ─────────────────────────────


class TestTrainWithSentenceTransformers:
    def _make_training_data(self, tmpdir: Path, n: int = 5) -> str:
        """Create a JSONL file with n triplets."""
        data_path = tmpdir / "data.jsonl"
        with open(data_path, "w") as f:
            for i in range(n):
                f.write(
                    json.dumps(
                        {
                            "query": f"query {i}",
                            "pos": f"positive {i}",
                            "neg": f"negative {i}",
                        }
                    )
                    + "\n"
                )
        return str(data_path)

    def test_sentence_transformers_training(self, tmp_path):
        """_train_with_sentence_transformers loads data and trains."""
        # Build stub modules for sentence_transformers with full API
        st_mod = types.ModuleType("sentence_transformers")

        class MockModel:
            def __init__(self, name, device=None):
                self.max_seq_length = 512

            def fit(self, train_objectives, epochs, warmup_steps, output_path, show_progress_bar):
                Path(output_path).mkdir(parents=True, exist_ok=True)

        class MockInputExample:
            def __init__(self, texts):
                self.texts = texts

        class MockLosses:
            @staticmethod
            def TripletLoss(model):
                return MagicMock()

        st_mod.SentenceTransformer = MockModel
        st_mod.InputExample = MockInputExample

        losses_mod = types.ModuleType("sentence_transformers.losses")
        losses_mod.TripletLoss = MockLosses.TripletLoss  # type: ignore[attr-defined]

        # Also need torch.utils.data.DataLoader
        torch_mod = sys.modules.get("torch", types.ModuleType("torch"))
        torch_utils = types.ModuleType("torch.utils")
        torch_data = types.ModuleType("torch.utils.data")
        torch_data.DataLoader = lambda examples, shuffle, batch_size: examples  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {
                "sentence_transformers": st_mod,
                "sentence_transformers.losses": losses_mod,
                "torch": torch_mod,
                "torch.utils": torch_utils,
                "torch.utils.data": torch_data,
            },
        ):
            data_path = self._make_training_data(tmp_path, n=3)
            output_dir = str(tmp_path / "st_output")

            ft = FineTuner(device="cpu")
            result = ft._train_with_sentence_transformers(
                training_data_path=data_path,
                output_dir=output_dir,
                epochs=1,
                batch_size=2,
                learning_rate=1e-5,
                max_len=256,
                triplet_count=3,
            )

            assert result["status"] == "completed"
            assert result["triplet_count"] == 3
            assert result["epochs"] == 1

    def test_sentence_transformers_empty_data(self, tmp_path):
        """_train_with_sentence_transformers returns error on empty data."""
        st_mod = types.ModuleType("sentence_transformers")

        class MockModel:
            def __init__(self, name, device=None):
                self.max_seq_length = 512

        class MockInputExample:
            def __init__(self, texts):
                self.texts = texts

        st_mod.SentenceTransformer = MockModel
        st_mod.InputExample = MockInputExample

        losses_mod = types.ModuleType("sentence_transformers.losses")
        losses_mod.TripletLoss = MagicMock  # type: ignore[attr-defined]

        torch_mod = sys.modules.get("torch", types.ModuleType("torch"))
        torch_utils = types.ModuleType("torch.utils")
        torch_data = types.ModuleType("torch.utils.data")
        torch_data.DataLoader = MagicMock  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {
                "sentence_transformers": st_mod,
                "sentence_transformers.losses": losses_mod,
                "torch": torch_mod,
                "torch.utils": torch_utils,
                "torch.utils.data": torch_data,
            },
        ):
            # Create a file with only empty lines
            data_path = tmp_path / "empty.jsonl"
            data_path.write_text("\n\n\n")

            ft = FineTuner(device="cpu")
            result = ft._train_with_sentence_transformers(
                training_data_path=str(data_path),
                output_dir=str(tmp_path / "output"),
                epochs=1,
                batch_size=2,
                learning_rate=1e-5,
                max_len=256,
                triplet_count=0,
            )

            assert result["status"] == "error: no valid triplets"
            assert result["triplet_count"] == 0

    def test_sentence_transformers_skips_blank_lines(self, tmp_path):
        """Blank lines in the JSONL file are skipped during loading."""
        st_mod = types.ModuleType("sentence_transformers")

        class MockModel:
            def __init__(self, name, device=None):
                self.max_seq_length = 512

            def fit(self, **kwargs):
                pass

        class MockInputExample:
            def __init__(self, texts):
                self.texts = texts

        st_mod.SentenceTransformer = MockModel
        st_mod.InputExample = MockInputExample

        losses_mod = types.ModuleType("sentence_transformers.losses")
        losses_mod.TripletLoss = lambda model: MagicMock()  # type: ignore[attr-defined]

        torch_mod = sys.modules.get("torch", types.ModuleType("torch"))
        torch_utils = types.ModuleType("torch.utils")
        torch_data = types.ModuleType("torch.utils.data")
        torch_data.DataLoader = lambda examples, shuffle, batch_size: examples  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {
                "sentence_transformers": st_mod,
                "sentence_transformers.losses": losses_mod,
                "torch": torch_mod,
                "torch.utils": torch_utils,
                "torch.utils.data": torch_data,
            },
        ):
            data_path = tmp_path / "with_blanks.jsonl"
            lines = [
                json.dumps({"query": "q1", "pos": "p1", "neg": "n1"}),
                "",
                json.dumps({"query": "q2", "pos": "p2", "neg": "n2"}),
                "",
            ]
            data_path.write_text("\n".join(lines))

            ft = FineTuner(device="cpu")
            result = ft._train_with_sentence_transformers(
                training_data_path=str(data_path),
                output_dir=str(tmp_path / "output"),
                epochs=1,
                batch_size=2,
                learning_rate=1e-5,
                max_len=256,
                triplet_count=2,
            )

            assert result["triplet_count"] == 2
            assert result["status"] == "completed"


# ── fine_tune (integration: fallback to sentence_transformers) ────


class TestFineTuneFallback:
    def test_fine_tune_falls_back_to_sentence_transformers(self, tmp_path):
        """When FlagEmbedding import fails, fine_tune falls back to ST."""
        data_path = tmp_path / "data.jsonl"
        with open(data_path, "w") as f:
            for i in range(3):
                f.write(
                    json.dumps(
                        {
                            "query": f"query {i}",
                            "pos": f"positive {i}",
                            "neg": f"negative {i}",
                        }
                    )
                    + "\n"
                )

        output_dir = str(tmp_path / "output")
        ft = FineTuner(device="cpu")

        # Mock _train_with_flag_embedding to raise ImportError
        # and _train_with_sentence_transformers to return success
        with patch.object(ft, "_train_with_flag_embedding", side_effect=ImportError("no FlagEmbedding")):
            with patch.object(
                ft,
                "_train_with_sentence_transformers",
                return_value={
                    "output_dir": output_dir,
                    "epochs": 1,
                    "triplet_count": 3,
                    "status": "completed",
                },
            ) as mock_st:
                result = ft.fine_tune(
                    training_data_path=str(data_path),
                    output_dir=output_dir,
                    epochs=1,
                )

                assert result["status"] == "completed"
                mock_st.assert_called_once()

    def test_fine_tune_uses_fp16_on_cuda(self, tmp_path):
        """fine_tune sets use_fp16=True when device is not mps/cpu."""
        data_path = tmp_path / "data.jsonl"
        data_path.write_text(json.dumps({"query": "q", "pos": "p", "neg": "n"}) + "\n")

        ft = FineTuner(device="cuda")
        with patch.object(
            ft,
            "_train_with_flag_embedding",
            return_value={
                "status": "config_ready",
                "triplet_count": 1,
                "epochs": 1,
            },
        ) as mock_flag:
            ft.fine_tune(
                training_data_path=str(data_path),
                output_dir=str(tmp_path / "output"),
            )
            call_kwargs = mock_flag.call_args[1]
            assert call_kwargs["use_fp16"] is True

    def test_fine_tune_no_fp16_on_mps(self, tmp_path):
        """fine_tune sets use_fp16=False when device is mps."""
        data_path = tmp_path / "data.jsonl"
        data_path.write_text(json.dumps({"query": "q", "pos": "p", "neg": "n"}) + "\n")

        ft = FineTuner(device="mps")
        with patch.object(
            ft,
            "_train_with_flag_embedding",
            return_value={
                "status": "config_ready",
                "triplet_count": 1,
                "epochs": 1,
            },
        ) as mock_flag:
            ft.fine_tune(
                training_data_path=str(data_path),
                output_dir=str(tmp_path / "output"),
            )
            call_kwargs = mock_flag.call_args[1]
            assert call_kwargs["use_fp16"] is False

    def test_fine_tune_no_fp16_on_cpu(self, tmp_path):
        """fine_tune sets use_fp16=False when device is cpu."""
        data_path = tmp_path / "data.jsonl"
        data_path.write_text(json.dumps({"query": "q", "pos": "p", "neg": "n"}) + "\n")

        ft = FineTuner(device="cpu")
        with patch.object(
            ft,
            "_train_with_flag_embedding",
            return_value={
                "status": "config_ready",
                "triplet_count": 1,
                "epochs": 1,
            },
        ) as mock_flag:
            ft.fine_tune(
                training_data_path=str(data_path),
                output_dir=str(tmp_path / "output"),
            )
            call_kwargs = mock_flag.call_args[1]
            assert call_kwargs["use_fp16"] is False


# ── _count_lines (extra coverage) ────────────────────────────────


class TestCountLinesExtended:
    def test_count_lines_with_whitespace_only_lines(self, tmp_path):
        """Lines that are only whitespace are not counted."""
        path = tmp_path / "ws.jsonl"
        path.write_text("line1\n   \nline2\n\t\n")
        assert _count_lines(str(path)) == 2

    def test_count_lines_no_trailing_newline(self, tmp_path):
        """File without trailing newline still counts the last line."""
        path = tmp_path / "no_nl.jsonl"
        path.write_text("line1\nline2")
        assert _count_lines(str(path)) == 2
