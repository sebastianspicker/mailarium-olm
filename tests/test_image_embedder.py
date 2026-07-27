"""Deterministic SigLIP2 image-embedding contracts."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np

from mailarium.image_embedder import ImageEmbedder, is_image_file


def test_supported_image_extensions():
    assert is_image_file("photo.jpg")
    assert is_image_file("photo.PNG")
    assert not is_image_file("document.pdf")
    assert not is_image_file("")


def test_invalid_image_input_does_not_load_model():
    embedder = ImageEmbedder(device="cpu")
    assert embedder.encode_image(b"", filename="photo.jpg") is None
    assert embedder.encode_image(b"bytes", filename="document.txt") is None


def test_image_features_are_normalized_without_disk_io():
    embedder = ImageEmbedder(device="cpu")
    model = type("Model", (), {"get_image_features": lambda _self, **_kwargs: np.array([[3.0, 4.0]])})()
    embedder._model = model
    embedder._processor = lambda **_kwargs: {"pixel_values": _DeviceValue()}
    with patch("mailarium.image_embedder._validated_image", return_value=object()):
        assert embedder.encode_image(b"image", filename="photo.png") == [0.6000000238418579, 0.800000011920929]


class _DeviceValue:
    def to(self, _device):
        return self
