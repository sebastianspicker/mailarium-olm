"""SigLIP2 loading and safety tests without model downloads."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from mailarium.image_embedder import ImageEmbedder, _normalized_vector

_MODEL_REVISION = "a" * 40


def test_local_only_loader_passes_safe_transformers_options():
    embedder = ImageEmbedder(device="cpu", load_mode="local_only", model_revision=_MODEL_REVISION)
    processor, model = MagicMock(), MagicMock()
    model.to.return_value = model
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoProcessor = MagicMock()
    fake_transformers.AutoModel = MagicMock()
    fake_transformers.AutoProcessor.from_pretrained.return_value = processor
    fake_transformers.AutoModel.from_pretrained.return_value = model
    with patch.dict(sys.modules, {"transformers": fake_transformers}):
        embedder._ensure_loaded()
    load_processor = fake_transformers.AutoProcessor.from_pretrained
    load_model = fake_transformers.AutoModel.from_pretrained
    assert load_processor.call_args.kwargs == {
        "trust_remote_code": False,
        "revision": _MODEL_REVISION,
        "local_files_only": True,
    }
    assert load_model.call_args.kwargs == {
        "trust_remote_code": False,
        "revision": _MODEL_REVISION,
        "local_files_only": True,
        "use_safetensors": True,
    }
    model.eval.assert_called_once()


@pytest.mark.parametrize("revision", ["", "main", "v1.0.0", "abc123", "g" * 40])
def test_loader_rejects_mutable_or_invalid_model_revisions(revision):
    with pytest.raises(ValueError, match="full 40-character hexadecimal commit hash"):
        ImageEmbedder(device="cpu", model_revision=revision)


def test_availability_records_load_error():
    embedder = ImageEmbedder(device="cpu")
    with patch.object(embedder, "_ensure_loaded", side_effect=OSError("unavailable")):
        assert embedder.is_available is False
    assert "unavailable" in embedder.runtime_summary()["load_error"]


def test_normalized_vector_rejects_zero_vector():
    try:
        _normalized_vector(np.zeros((1, 2)))
    except ValueError as exc:
        assert "zero norm" in str(exc)
    else:
        raise AssertionError("zero vector must be rejected")
