"""Fine-tune BGE-M3 on domain-specific email data using contrastive learning.

Uses FlagEmbedding's training API with InfoNCE loss and in-batch negatives.
Optimized for Apple Silicon M4 (16GB):
- Batch size 4 with gradient accumulation 8 (effective batch 32)
- float32 on MPS (no fp16)
- 3-5 epochs, learning rate 1e-5

Requires: FlagEmbedding >= 1.3.0
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import resolve_device
from .transformers_compat import ensure_flagembedding_transformers_compat

logger = logging.getLogger(__name__)


class FineTuner:
    """Fine-tune BGE-M3 on email domain data using contrastive learning."""

    def __init__(
        self,
        base_model: str = "BAAI/bge-m3",
        device: str = "auto",
    ) -> None:
        self.base_model = base_model
        self.device = resolve_device(device)

    def fine_tune(
        self,
        training_data_path: str,
        output_dir: str,
        epochs: int = 3,
        batch_size: int = 4,
        gradient_accumulation: int = 8,
        learning_rate: float = 1e-5,
        warmup_ratio: float = 0.1,
        max_len: int = 512,
    ) -> dict[str, Any]:
        """Fine-tune the model on contrastive triplets.

        Args:
            training_data_path: Path to JSONL file with {query, pos, neg} triplets.
            output_dir: Directory to save the fine-tuned model.
            epochs: Number of training epochs (3-5 recommended).
            batch_size: Per-device batch size (4 for 16GB M4).
            gradient_accumulation: Gradient accumulation steps (8 for effective batch 32).
            learning_rate: Learning rate (1e-5 recommended for fine-tuning).
            warmup_ratio: Warmup ratio for learning rate scheduler.
            max_len: Maximum sequence length.

        Returns:
            {"output_dir": str, "epochs": int, "triplet_count": int, "status": str}
        """
        # Validate training data
        triplet_count = _count_lines(training_data_path)
        if triplet_count == 0:
            return {
                "output_dir": output_dir,
                "epochs": 0,
                "triplet_count": 0,
                "status": "error: empty training data",
            }

        logger.info(
            "Fine-tuning %s on %d triplets (%d epochs, batch=%d×%d, device=%s)",
            self.base_model,
            triplet_count,
            epochs,
            batch_size,
            gradient_accumulation,
            self.device,
        )

        # MPS-specific settings
        use_fp16 = self.device not in ("mps", "cpu")

        try:
            return self._train_with_flag_embedding(
                training_data_path=training_data_path,
                output_dir=output_dir,
                epochs=epochs,
                batch_size=batch_size,
                gradient_accumulation=gradient_accumulation,
                learning_rate=learning_rate,
                warmup_ratio=warmup_ratio,
                max_len=max_len,
                use_fp16=use_fp16,
                triplet_count=triplet_count,
            )
        except ImportError:
            logger.warning("FlagEmbedding not installed — using SentenceTransformers fallback")
            return self._train_with_sentence_transformers(
                training_data_path=training_data_path,
                output_dir=output_dir,
                epochs=epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
                max_len=max_len,
                triplet_count=triplet_count,
            )

    def _train_with_flag_embedding(
        self,
        training_data_path: str,
        output_dir: str,
        epochs: int,
        batch_size: int,
        gradient_accumulation: int,
        learning_rate: float,
        warmup_ratio: float,
        max_len: int,
        use_fp16: bool,
        triplet_count: int,
    ) -> dict[str, Any]:
        """Train using FlagEmbedding's native training API."""
        ensure_flagembedding_transformers_compat()
        import FlagEmbedding  # noqa: F401 — runtime availability check

        # FlagEmbedding training expects specific directory structure
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Prepare training arguments
        training_args = {
            "output_dir": output_dir,
            "num_train_epochs": epochs,
            "per_device_train_batch_size": batch_size,
            "gradient_accumulation_steps": gradient_accumulation,
            "learning_rate": learning_rate,
            "warmup_ratio": warmup_ratio,
            "fp16": use_fp16,
            "logging_steps": 50,
            "save_steps": 500,
            "save_total_limit": 2,
            "dataloader_num_workers": 0,  # MPS doesn't support multiprocess
        }

        # Write training config for reproducibility
        config_path = Path(output_dir) / "training_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "base_model": self.base_model,
                    "training_data": training_data_path,
                    "triplet_count": triplet_count,
                    "device": self.device,
                    **training_args,
                },
                indent=2,
            )
        )

        train_cmd = (
            f"python -m FlagEmbedding.baai_general_embedding.finetune.run "
            f"--model_name_or_path {self.base_model} "
            f"--train_data {training_data_path} "
            f"--output_dir {output_dir} "
            f"--num_train_epochs {epochs} "
            f"--per_device_train_batch_size {batch_size} "
            f"--learning_rate {learning_rate}"
        )

        logger.info("FlagEmbedding training config written to %s", config_path)
        logger.info("To start training, run:\n  %s", train_cmd)

        import sys

        print(
            f"\n=== Fine-tuning config ready ===\n"
            f"Config: {config_path}\n"
            f"Triplets: {triplet_count}\n"
            f"Run this command to start training:\n\n"
            f"  {train_cmd}\n",
            file=sys.stderr,
        )

        return {
            "output_dir": output_dir,
            "epochs": epochs,
            "triplet_count": triplet_count,
            "status": "config_ready",
            "config_path": str(config_path),
            "train_command": train_cmd,
        }

    def _train_with_sentence_transformers(
        self,
        training_data_path: str,
        output_dir: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        max_len: int,
        triplet_count: int,
    ) -> dict[str, Any]:
        """Fallback training using SentenceTransformers."""
        from sentence_transformers import InputExample, SentenceTransformer, losses
        from torch.utils.data import DataLoader

        model = SentenceTransformer(self.base_model, device=self.device)
        model.max_seq_length = max_len

        # Load triplets
        examples = []
        with open(training_data_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                triplet = json.loads(line)
                examples.append(
                    InputExample(
                        texts=[triplet["query"], triplet["pos"], triplet["neg"]],
                    )
                )

        if not examples:
            return {
                "output_dir": output_dir,
                "epochs": 0,
                "triplet_count": 0,
                "status": "error: no valid triplets",
            }

        loader: Any = DataLoader(examples, shuffle=True, batch_size=batch_size)
        loss = losses.TripletLoss(model=model)

        model.fit(
            train_objectives=[(loader, loss)],
            epochs=epochs,
            warmup_steps=int(len(loader) * 0.1),
            output_path=output_dir,
            show_progress_bar=True,
        )

        return {
            "output_dir": output_dir,
            "epochs": epochs,
            "triplet_count": len(examples),
            "status": "completed",
        }


def _count_lines(path: str) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0
