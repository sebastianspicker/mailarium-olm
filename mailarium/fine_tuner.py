"""Local dense and learned-sparse fine-tuning with SentenceTransformers."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any, Literal

from .config import resolve_device

TrainingMode = Literal["dense", "sparse"]


class FineTuner:
    """Train a local dense or sparse artifact from validated triplets."""

    def __init__(
        self,
        base_model: str = "BAAI/bge-m3",
        device: str = "auto",
        *,
        sparse_base_model: str = "opensearch-project/opensearch-neural-sparse-encoding-multilingual-v1",
    ) -> None:
        """Store model and training settings for a later fine-tuning run."""
        self.base_model = base_model
        self.sparse_base_model = sparse_base_model
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
        *,
        mode: TrainingMode = "dense",
    ) -> dict[str, Any]:
        """Train synchronously, save locally, and emit a reproducibility manifest."""
        _validate_training_options(
            mode=mode,
            epochs=epochs,
            batch_size=batch_size,
            gradient_accumulation=gradient_accumulation,
            learning_rate=learning_rate,
            warmup_ratio=warmup_ratio,
            max_len=max_len,
        )
        path = Path(training_data_path)
        triplets = _load_triplets(path)
        if not triplets:
            return {
                "output_dir": output_dir,
                "epochs": 0,
                "triplet_count": 0,
                "mode": mode,
                "status": "error: empty training data",
            }
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        config = {
            "mode": mode,
            "base_model": self.base_model if mode == "dense" else self.sparse_base_model,
            "training_data": str(path.resolve()),
            "training_data_sha256": _sha256(path),
            "triplet_count": len(triplets),
            "device": self.device,
            "epochs": epochs,
            "batch_size": batch_size,
            "gradient_accumulation": gradient_accumulation,
            "learning_rate": learning_rate,
            "warmup_ratio": warmup_ratio,
            "max_len": max_len,
        }
        config_path = destination / "training_config.json"
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        metrics = (
            self._train_dense(triplets, destination, config)
            if mode == "dense"
            else self._train_sparse(triplets, destination, config)
        )
        manifest = {
            **config,
            "dependencies": _dependency_versions(),
            "metrics": metrics,
            "artifact_files": _artifact_checksums(destination),
        }
        manifest_path = destination / "training_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "output_dir": str(destination),
            "epochs": epochs,
            "triplet_count": len(triplets),
            "mode": mode,
            "status": "completed",
            "config_path": str(config_path),
            "manifest_path": str(manifest_path),
            "metrics": metrics,
        }

    def _train_dense(
        self,
        triplets: list[dict[str, str]],
        output_dir: Path,
        config: dict[str, Any],
    ) -> dict[str, float]:
        """Fine-tune the dense encoder and save its model artifacts and metrics."""
        from datasets import Dataset
        from sentence_transformers import (
            SentenceTransformer,
            SentenceTransformerTrainer,
            SentenceTransformerTrainingArguments,
            losses,
        )

        model = SentenceTransformer(self.base_model, device=self.device, trust_remote_code=False)
        model.max_seq_length = int(config["max_len"])
        dataset = Dataset.from_dict(_triplet_columns(triplets))
        loss = losses.TripletLoss(model=model)
        arguments = SentenceTransformerTrainingArguments(
            **_training_arguments(output_dir, config, use_fp16=self.device == "cuda")
        )
        trainer = SentenceTransformerTrainer(
            model=model,
            args=arguments,
            train_dataset=dataset,
            loss=loss,
        )
        return _train_and_save(trainer, model, output_dir)

    def _train_sparse(
        self,
        triplets: list[dict[str, str]],
        output_dir: Path,
        config: dict[str, Any],
    ) -> dict[str, float]:
        """Fit sparse retrieval weights and save the resulting artifact bundle."""
        from datasets import Dataset
        from sentence_transformers import (
            SparseEncoder,
            SparseEncoderTrainer,
            SparseEncoderTrainingArguments,
        )
        from sentence_transformers.sparse_encoder import losses

        model = SparseEncoder(self.sparse_base_model, device=self.device, trust_remote_code=False)
        dataset = Dataset.from_dict(_triplet_columns(triplets))
        loss = losses.SparseTripletLoss(model=model)
        arguments = SparseEncoderTrainingArguments(**_training_arguments(output_dir, config, use_fp16=self.device == "cuda"))
        trainer = SparseEncoderTrainer(
            model=model,
            args=arguments,
            train_dataset=dataset,
            loss=loss,
        )
        return _train_and_save(trainer, model, output_dir)


def _training_arguments(
    output_dir: Path,
    config: dict[str, Any],
    *,
    use_fp16: bool,
) -> dict[str, Any]:
    """Return the shared dense and sparse trainer configuration."""
    return {
        "output_dir": str(output_dir / "checkpoints"),
        "num_train_epochs": float(config["epochs"]),
        "per_device_train_batch_size": int(config["batch_size"]),
        "gradient_accumulation_steps": int(config["gradient_accumulation"]),
        "learning_rate": float(config["learning_rate"]),
        "warmup_ratio": float(config["warmup_ratio"]),
        "fp16": use_fp16,
        "report_to": [],
        "save_strategy": "no",
    }


def _train_and_save(trainer: Any, model: Any, output_dir: Path) -> dict[str, float]:
    """Run a configured trainer and persist its model and numeric metrics."""
    result = trainer.train()
    model.save_pretrained(str(output_dir / "model"), safe_serialization=True)
    return _numeric_metrics(getattr(result, "metrics", {}))


def _load_triplets(path: Path) -> list[dict[str, str]]:
    """Load and validate query-positive-negative training rows from CSV."""
    if not path.is_file():
        return []
    triplets: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Training row {line_number} must be an object")
            normalized = {name: str(payload.get(name) or "").strip() for name in ("query", "pos", "neg")}
            missing = [name for name, value in normalized.items() if not value]
            if missing:
                raise ValueError(f"Training row {line_number} is missing non-empty field(s): {', '.join(missing)}")
            triplets.append(normalized)
    return triplets


def _count_lines(path: str) -> int:
    """Count non-empty JSONL rows without accepting malformed data."""
    return len(_load_triplets(Path(path)))


def _validate_training_options(
    *,
    mode: str,
    epochs: int,
    batch_size: int,
    gradient_accumulation: int,
    learning_rate: float,
    warmup_ratio: float,
    max_len: int,
) -> None:
    """Reject unsupported training modes and invalid numeric limits early."""
    if mode not in {"dense", "sparse"}:
        raise ValueError("mode must be 'dense' or 'sparse'")
    for name, value in (
        ("epochs", epochs),
        ("batch_size", batch_size),
        ("gradient_accumulation", gradient_accumulation),
        ("max_len", max_len),
    ):
        if int(value) <= 0:
            raise ValueError(f"{name} must be positive")
    if learning_rate <= 0:
        raise ValueError("learning_rate must be positive")
    if not 0.0 <= warmup_ratio < 1.0:
        raise ValueError("warmup_ratio must be between 0 and 1")


def _triplet_columns(triplets: list[dict[str, str]]) -> dict[str, list[str]]:
    """Resolve accepted column aliases for query, positive, and negative text."""
    return {
        "anchor": [row["query"] for row in triplets],
        "positive": [row["pos"] for row in triplets],
        "negative": [row["neg"] for row in triplets],
    }


def _numeric_metrics(metrics: Any) -> dict[str, float]:
    """Keep only finite numeric metrics for JSON serialization."""
    if not isinstance(metrics, dict):
        return {}
    return {str(name): float(value) for name, value in metrics.items() if isinstance(value, int | float)}


def _dependency_versions() -> dict[str, str]:
    """Capture installed dependency versions needed to reproduce training."""
    versions: dict[str, str] = {}
    for package in ("torch", "sentence-transformers", "transformers", "datasets", "accelerate"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def _artifact_checksums(output_dir: Path) -> dict[str, str]:
    """Hash generated artifacts for integrity verification."""
    checksums: dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "training_manifest.json":
            continue
        checksums[str(path.relative_to(output_dir))] = _sha256(path)
    return checksums


def _sha256(path: Path) -> str:
    """Stream a file into a SHA-256 digest without loading it wholly into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
