"""Training command-family implementations for the CLI."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email_db import EmailDatabase


def run_generate_training_data_impl(get_email_db: Callable[[], EmailDatabase], output_path: str) -> None:
    """Generate contrastive training triplets from email data.

    Args:
        get_email_db: Factory function to get the email database instance.
        output_path: Path to save the generated training data JSONL file.
    """
    db = get_email_db()
    from .training_data_generator import TrainingDataGenerator

    gen = TrainingDataGenerator(db)
    result = gen.export_jsonl(output_path)
    print(f"Training data generated: {output_path} ({result['triplet_count']} triplets)")


def run_fine_tune_impl(data_path: str, output_dir: str, epochs: int) -> None:
    """Fine-tune the embedding model on training data.

    Args:
        data_path: Path to the training data JSONL file.
        output_dir: Directory to save the fine-tuned model.
        epochs: Number of training epochs.
    """
    from .fine_tuner import FineTuner

    ft = FineTuner()
    result = ft.fine_tune(
        training_data_path=data_path,
        output_dir=output_dir,
        epochs=epochs,
    )
    print(f"Fine-tuning result: {result['status']}")
    print(f"  Triplets: {result['triplet_count']}, Epochs: {result['epochs']}")
    if result.get("config_path"):
        print(f"  Config: {result['config_path']}")
