"""Extended tests for image_embedder.py and tools/attachments.py — targets missing coverage."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.image_embedder import ImageEmbedder, is_image_file

# ── is_image_file edge cases ───────────────────────────────────


class TestIsImageFile:
    def test_tif_extension(self):
        assert is_image_file("scan.tif")

    def test_jpeg_extension(self):
        assert is_image_file("photo.JPEG")

    def test_no_dot(self):
        assert not is_image_file("noextension")

    def test_empty_string(self):
        assert not is_image_file("")

    def test_dot_only(self):
        assert not is_image_file(".")


# ── ImageEmbedder._resolve_weight_path ─────────────────────────


class TestResolveWeightPath:
    def test_explicit_path_exists(self):
        """Explicit weight path that exists is used (line 120)."""
        with tempfile.NamedTemporaryFile(suffix=".pth", delete=False) as f:
            f.write(b"fake weights")
            tmp_path = f.name

        try:
            with patch.object(ImageEmbedder, "_try_load"):
                embedder = ImageEmbedder(weight_path=tmp_path)
                assert embedder._weight_path == tmp_path
        finally:
            os.unlink(tmp_path)

    def test_explicit_path_not_exists(self):
        """Explicit weight path that doesn't exist returns None (line 121-122)."""
        embedder = ImageEmbedder(weight_path="/nonexistent/path/weights.pth")
        assert embedder._weight_path is None
        assert not embedder.is_available

    def test_default_search_path_found(self):
        """Weight file found in default search path (line 126-127)."""
        with tempfile.NamedTemporaryFile(suffix=".pth", delete=False) as f:
            f.write(b"fake weights")
            tmp_path = f.name

        fake_paths = [Path(tmp_path)]
        try:
            with patch("src.image_embedder._WEIGHT_SEARCH_PATHS", fake_paths), patch.object(ImageEmbedder, "_try_load"):
                embedder = ImageEmbedder()
                assert embedder._weight_path == tmp_path
        finally:
            os.unlink(tmp_path)

    def test_auto_download_disabled(self):
        """Auto-download disabled via env var (lines 130-136)."""
        with (
            patch.dict(os.environ, {"IMAGE_EMBED_AUTO_DOWNLOAD": "0"}),
            patch("src.image_embedder._WEIGHT_SEARCH_PATHS", [Path("/nonexistent/a.pth")]),
        ):
            embedder = ImageEmbedder()
            assert embedder._weight_path is None
            assert not embedder.is_available

    def test_auto_download_enabled_calls_download(self):
        """When auto-download is enabled and no file found, calls _auto_download (line 138)."""
        with (
            patch.dict(os.environ, {"IMAGE_EMBED_AUTO_DOWNLOAD": "1"}, clear=False),
            patch("src.image_embedder._WEIGHT_SEARCH_PATHS", [Path("/nonexistent/a.pth")]),
            patch.object(ImageEmbedder, "_auto_download", return_value=None) as m,
            patch.object(ImageEmbedder, "_try_load"),
        ):
            ImageEmbedder()
            m.assert_called_once()


# ── ImageEmbedder._auto_download ───────────────────────────────


class TestAutoDownload:
    def test_huggingface_hub_not_installed(self):
        """ImportError for huggingface_hub returns None (lines 149-156)."""
        embedder = ImageEmbedder.__new__(ImageEmbedder)

        with patch.dict("sys.modules", {"huggingface_hub": None}):
            with patch("builtins.__import__", side_effect=ImportError("no hf_hub")):
                result = embedder._auto_download()
                assert result is None

    def test_huggingface_hub_download_success(self):
        """Successful download returns path (lines 164-171)."""
        embedder = ImageEmbedder.__new__(ImageEmbedder)

        mock_hf_hub = MagicMock()
        mock_hf_hub.hf_hub_download.return_value = "/tmp/downloaded_weights.pth"

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf_hub}):
            result = embedder._auto_download()
            assert result == "/tmp/downloaded_weights.pth"
            mock_hf_hub.hf_hub_download.assert_called_once()

    def test_huggingface_hub_download_failure(self):
        """Download exception returns None (lines 172-180)."""
        embedder = ImageEmbedder.__new__(ImageEmbedder)

        mock_hf_hub = MagicMock()
        mock_hf_hub.hf_hub_download.side_effect = RuntimeError("network error")

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf_hub}):
            result = embedder._auto_download()
            assert result is None


# ── ImageEmbedder._try_load ────────────────────────────────────


class TestTryLoad:
    def test_successful_load(self):
        """Model loads successfully (lines 187-192)."""
        mock_model = MagicMock()
        mock_visualized_bge = MagicMock(return_value=mock_model)

        mock_visual_modeling = MagicMock()
        mock_visual_modeling.Visualized_BGE = mock_visualized_bge

        with patch.dict(
            "sys.modules",
            {
                "FlagEmbedding": MagicMock(),
                "FlagEmbedding.visual": MagicMock(),
                "FlagEmbedding.visual.modeling": mock_visual_modeling,
            },
        ):
            embedder = ImageEmbedder.__new__(ImageEmbedder)
            embedder._model = None
            embedder._available = False
            embedder._weight_path = "/fake/weights.pth"
            embedder._try_load("BAAI/bge-m3")
            assert embedder._available is True
            assert embedder._model is mock_model

    def test_import_error(self):
        """FlagEmbedding not installed (lines 193-197)."""
        embedder = ImageEmbedder.__new__(ImageEmbedder)
        embedder._model = None
        embedder._available = False
        embedder._weight_path = "/fake/weights.pth"

        # Ensure FlagEmbedding modules are not in sys.modules
        with patch.dict(
            "sys.modules",
            {
                "FlagEmbedding": MagicMock(),
                "FlagEmbedding.visual": MagicMock(),
                "FlagEmbedding.visual.modeling": None,
            },
        ):
            embedder._try_load("BAAI/bge-m3")
            assert embedder._available is False

    def test_generic_exception(self):
        """Generic error during model load (lines 198-199)."""
        mock_visual_modeling = MagicMock()
        mock_visual_modeling.Visualized_BGE.side_effect = RuntimeError("GPU error")

        with patch.dict(
            "sys.modules",
            {
                "FlagEmbedding": MagicMock(),
                "FlagEmbedding.visual": MagicMock(),
                "FlagEmbedding.visual.modeling": mock_visual_modeling,
            },
        ):
            embedder = ImageEmbedder.__new__(ImageEmbedder)
            embedder._model = None
            embedder._available = False
            embedder._weight_path = "/fake/weights.pth"
            embedder._try_load("BAAI/bge-m3")
            assert embedder._available is False
            assert embedder._model is None


# ── ImageEmbedder.encode_image when available ──────────────────


class TestEncodeImageAvailable:
    def _make_available_embedder(self):
        embedder = ImageEmbedder.__new__(ImageEmbedder)
        embedder._model = MagicMock()
        embedder._available = True
        embedder._weight_path = "/fake/weights.pth"
        return embedder

    def test_encode_with_tolist(self):
        """Model returns ndarray-like with tolist() (lines 92-93)."""
        embedder = self._make_available_embedder()
        mock_result = MagicMock()
        mock_result.tolist.return_value = [0.1, 0.2, 0.3]
        embedder._model.encode.return_value = mock_result

        result = embedder.encode_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        assert result == [0.1, 0.2, 0.3]

    def test_encode_without_tolist(self):
        """Model returns iterable without tolist() (line 94)."""
        embedder = self._make_available_embedder()
        # Tuple does not have tolist()
        embedder._model.encode.return_value = (0.4, 0.5, 0.6)

        result = embedder.encode_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        assert result == [0.4, 0.5, 0.6]

    def test_encode_empty_bytes_returns_none(self):
        """Empty image bytes returns None (line 77)."""
        embedder = self._make_available_embedder()
        assert embedder.encode_image(b"") is None

    def test_encode_exception_returns_none(self):
        """Exception during encoding returns None (lines 98-100)."""
        embedder = self._make_available_embedder()
        embedder._model.encode.side_effect = RuntimeError("encode failed")

        result = embedder.encode_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        assert result is None

    def test_encode_creates_temp_file_and_cleans_up(self):
        """Verify temp file creation and cleanup (lines 84-96)."""
        embedder = self._make_available_embedder()
        mock_result = MagicMock()
        mock_result.tolist.return_value = [1.0]

        captured_path = None

        def capture_encode(image=None):
            nonlocal captured_path
            captured_path = image
            assert os.path.exists(image)
            return mock_result

        embedder._model.encode = capture_encode

        result = embedder.encode_image(b"\x89PNG" + b"\x00" * 50)
        assert result == [1.0]
        # Temp file should be cleaned up
        assert captured_path is not None
        assert not os.path.exists(captured_path)

    def test_encode_batch(self):
        """Batch encoding delegates to encode_image (line 113)."""
        embedder = self._make_available_embedder()
        mock_result = MagicMock()
        mock_result.tolist.return_value = [0.1]
        embedder._model.encode.return_value = mock_result

        results = embedder.encode_image_batch([b"\x89PNG" + b"\x00" * 50, b""])
        assert len(results) == 2
        assert results[0] == [0.1]
        assert results[1] is None  # empty bytes


# ── tools/attachments.py ───────────────────────────────────────


class TestAttachmentsToolRegistration:
    """Test the tools/attachments.py MCP tool wrapper."""

    def test_register_adds_tool(self):
        """register() decorates email_attachments function."""
        from src.tools.attachments import register

        mock_mcp = MagicMock()
        mock_deps = MagicMock()
        mock_deps.tool_annotations.return_value = {"readOnlyHint": True}

        # register() should call mcp.tool() to register the function
        register(mock_mcp, mock_deps)
        mock_mcp.tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_attachments_list_mode(self):
        """List mode calls db.list_attachments."""
        from src.mcp_models import EmailAttachmentsInput
        from src.tools.attachments import register

        mock_mcp = MagicMock()
        captured_fn = None

        def mock_tool(**kwargs):
            def decorator(fn):
                nonlocal captured_fn
                captured_fn = fn
                return fn

            return decorator

        mock_mcp.tool = mock_tool

        mock_db = MagicMock()
        mock_db.list_attachments.return_value = [{"filename": "test.pdf"}]

        mock_deps = MagicMock()
        mock_deps.tool_annotations.return_value = {}
        mock_deps.get_email_db.return_value = mock_db
        mock_deps.offload = AsyncMock(side_effect=lambda fn: fn())

        register(mock_mcp, mock_deps)
        assert captured_fn is not None

        params = EmailAttachmentsInput(mode="list")
        result = await captured_fn(params)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_email_attachments_search_mode(self):
        """Search mode calls db.search_emails_by_attachment."""
        from src.mcp_models import EmailAttachmentsInput
        from src.tools.attachments import register

        mock_mcp = MagicMock()
        captured_fn = None

        def mock_tool(**kwargs):
            def decorator(fn):
                nonlocal captured_fn
                captured_fn = fn
                return fn

            return decorator

        mock_mcp.tool = mock_tool

        mock_db = MagicMock()
        mock_db.search_emails_by_attachment.return_value = [{"uid": 1}]

        mock_deps = MagicMock()
        mock_deps.tool_annotations.return_value = {}
        mock_deps.get_email_db.return_value = mock_db
        mock_deps.offload = AsyncMock(side_effect=lambda fn: fn())

        register(mock_mcp, mock_deps)

        params = EmailAttachmentsInput(mode="search")
        result = await captured_fn(params)
        parsed = json.loads(result)
        assert "emails" in parsed
        assert parsed["count"] == 1

    @pytest.mark.asyncio
    async def test_email_attachments_stats_mode(self):
        """Stats mode calls db.attachment_stats."""
        from src.mcp_models import EmailAttachmentsInput
        from src.tools.attachments import register

        mock_mcp = MagicMock()
        captured_fn = None

        def mock_tool(**kwargs):
            def decorator(fn):
                nonlocal captured_fn
                captured_fn = fn
                return fn

            return decorator

        mock_mcp.tool = mock_tool

        mock_db = MagicMock()
        mock_db.attachment_stats.return_value = {"total": 42}

        mock_deps = MagicMock()
        mock_deps.tool_annotations.return_value = {}
        mock_deps.get_email_db.return_value = mock_db
        mock_deps.offload = AsyncMock(side_effect=lambda fn: fn())

        register(mock_mcp, mock_deps)

        params = EmailAttachmentsInput(mode="stats")
        result = await captured_fn(params)
        parsed = json.loads(result)
        assert parsed["total"] == 42

    @pytest.mark.asyncio
    async def test_email_attachments_invalid_mode(self):
        """Invalid mode is rejected by Pydantic Literal validation."""
        from pydantic import ValidationError

        from src.mcp_models import EmailAttachmentsInput

        with pytest.raises(ValidationError, match="mode"):
            EmailAttachmentsInput(mode="invalid")

    @pytest.mark.asyncio
    async def test_email_attachments_db_unavailable(self):
        """When DB is None, returns DB_UNAVAILABLE."""
        from src.mcp_models import EmailAttachmentsInput
        from src.tools.attachments import register

        mock_mcp = MagicMock()
        captured_fn = None

        def mock_tool(**kwargs):
            def decorator(fn):
                nonlocal captured_fn
                captured_fn = fn
                return fn

            return decorator

        mock_mcp.tool = mock_tool

        mock_deps = MagicMock()
        mock_deps.tool_annotations.return_value = {}
        mock_deps.get_email_db.return_value = None
        mock_deps.DB_UNAVAILABLE = '{"error": "DB unavailable"}'
        mock_deps.offload = AsyncMock(side_effect=lambda fn: fn())

        register(mock_mcp, mock_deps)

        params = EmailAttachmentsInput(mode="list")
        result = await captured_fn(params)
        parsed = json.loads(result)
        assert "error" in parsed
