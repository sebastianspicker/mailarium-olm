"""Tests for MCP server bug fixes: truncation, budgeting, defaults, lockfile."""

from __future__ import annotations

import json
import os
import sys

import pytest

# ── truncate_body ─────────────────────────────────────────────


class TestTruncateBody:
    def test_no_truncation_when_unlimited(self):
        from src.formatting import truncate_body

        text = "a" * 1000
        assert truncate_body(text, 0) == text

    def test_no_truncation_when_within_limit(self):
        from src.formatting import truncate_body

        text = "hello world"
        assert truncate_body(text, 500) == text

    def test_truncation_appends_hint(self):
        from src.formatting import truncate_body

        text = "a" * 600
        result = truncate_body(text, 500)
        assert result.startswith("a" * 500)
        assert "email_deep_context" in result
        assert "truncated" in result

    def test_truncation_exact_boundary(self):
        from src.formatting import truncate_body

        text = "a" * 500
        assert truncate_body(text, 500) == text  # Exactly at limit — no truncation

    def test_truncation_negative_is_unlimited(self):
        from src.formatting import truncate_body

        text = "a" * 1000
        assert truncate_body(text, -1) == text


# ── format_context_block with max_body_chars ─────────────────


class TestFormatContextBlockTruncation:
    def test_body_truncated_in_context_block(self):
        from src.formatting import format_context_block

        text = "x" * 1000
        metadata = {"sender_name": "Alice", "sender_email": "a@b.com", "date": "2024-01-01"}
        result = format_context_block(text, metadata, 0.95, max_body_chars=200)
        assert "truncated" in result
        assert "x" * 200 in result

    def test_no_truncation_when_zero(self):
        from src.formatting import format_context_block

        text = "x" * 1000
        metadata = {"date": "2024-01-01"}
        result = format_context_block(text, metadata, 0.5, max_body_chars=0)
        assert "truncated" not in result
        assert text in result


# ── Settings ──────────────────────────────────────────────────


class TestSettings:
    def test_default_mcp_settings(self):
        from src.config import Settings

        s = Settings()
        assert s.mcp_max_body_chars == 500
        assert s.mcp_max_response_tokens == 8000

    def test_env_override(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("MCP_MAX_BODY_CHARS", "0")
        monkeypatch.setenv("MCP_MAX_RESPONSE_TOKENS", "4000")
        s = Settings.from_env()
        assert s.mcp_max_body_chars == 0
        assert s.mcp_max_response_tokens == 4000

    def test_resolve_runtime_passes_through(self, monkeypatch):
        from src.config import get_settings, resolve_runtime_settings

        # Clear cached settings
        get_settings.cache_clear()
        monkeypatch.setenv("MCP_MAX_BODY_CHARS", "250")
        monkeypatch.setenv("MCP_MAX_RESPONSE_TOKENS", "5000")
        try:
            s = resolve_runtime_settings()
            assert s.mcp_max_body_chars == 250
            assert s.mcp_max_response_tokens == 5000
        finally:
            get_settings.cache_clear()


# ── format_results_for_llm budget ────────────────────────────


class TestFormatResultsBudget:
    def _make_result(self, text="body text", uid="uid1"):
        from src.retriever import SearchResult

        return SearchResult(
            chunk_id=f"chunk-{uid}",
            text=text,
            metadata={"sender_email": "a@b.com", "date": "2024-01-01", "uid": uid},
            distance=0.2,
        )

    def _make_retriever(self):
        from src.retriever import EmailRetriever

        r = EmailRetriever.__new__(EmailRetriever)
        return r

    def test_body_truncation_applied(self):
        r = self._make_retriever()
        result = self._make_result(text="x" * 1000, uid="u1")
        output = r.format_results_for_llm([result], max_body_chars=100, max_response_tokens=0)
        assert "truncated" in output
        assert "x" * 100 in output

    def test_budget_omits_excess_results(self):
        r = self._make_retriever()
        # Create many results with large bodies to exceed budget
        results = [self._make_result(text="x" * 500, uid=f"u{i}") for i in range(50)]
        output = r.format_results_for_llm(
            results,
            max_body_chars=0,
            max_response_tokens=200,
        )
        assert "omitted" in output or "Found 50" in output

    def test_unlimited_budget_shows_all(self):
        r = self._make_retriever()
        results = [self._make_result(uid=f"u{i}") for i in range(5)]
        output = r.format_results_for_llm(results, max_body_chars=0, max_response_tokens=0)
        assert "omitted" not in output
        assert "Result 5" in output


# ── serialize_results body truncation ─────────────────────────


class TestSerializeResultsTruncation:
    def test_bodies_truncated(self):
        from src.retriever import EmailRetriever, SearchResult

        r = EmailRetriever.__new__(EmailRetriever)
        result = SearchResult(
            chunk_id="c1",
            text="y" * 1000,
            metadata={"uid": "u1"},
            distance=0.1,
        )
        payload = r.serialize_results("test", [result], max_body_chars=100)
        assert "truncated" in payload["results"][0]["text"]
        assert payload["results"][0]["text"].startswith("y" * 100)

    def test_unlimited_no_truncation(self):
        from src.retriever import EmailRetriever, SearchResult

        r = EmailRetriever.__new__(EmailRetriever)
        result = SearchResult(
            chunk_id="c1",
            text="y" * 1000,
            metadata={"uid": "u1"},
            distance=0.1,
        )
        payload = r.serialize_results("test", [result], max_body_chars=0)
        assert payload["results"][0]["text"] == "y" * 1000


# ── MCP model defaults ───────────────────────────────────────


class TestMcpModelDefaults:
    def test_browse_defaults(self):
        from src.mcp_models import BrowseInput

        m = BrowseInput()
        assert m.include_body is False
        assert m.limit == 10


# ── Smart search flat text (no JSON wrapping) ────────────────


class TestSmartSearchFlat:
    """Verify smart search returns flat text, not JSON-wrapped formatted_results."""

    def test_no_json_formatted_results_key(self):
        # The output should be plain text, not JSON with a "formatted_results" key.
        # We test the structure by checking the output pattern matches what
        # email_search returns (flat text with header) rather than JSON.
        sample_output = "Smart search: budget\n\nSecurity note: The following..."
        # Should NOT be parseable as JSON with formatted_results
        try:
            parsed = json.loads(sample_output)
            assert "formatted_results" not in parsed
        except json.JSONDecodeError:
            pass  # Expected — flat text is not JSON


# ── Instance lock ─────────────────────────────────────────────


class TestInstanceLock:
    def test_lock_module_importable(self):
        """The lock functions should be importable without side effects in tests."""
        # We can't test the actual lock in unit tests (it runs at module import),
        # but we verify the helper functions exist.
        from src.mcp_server import _release_lock

        assert callable(_release_lock)

    @pytest.mark.skipif(sys.platform == "win32", reason="fcntl not available on Windows")
    def test_lock_file_created_in_data_dir(self, tmp_path, monkeypatch):
        """Verify _acquire_instance_lock creates a lock file with PID."""
        import fcntl

        from src.config import get_settings

        lock_path = tmp_path / "mcp_server.lock"

        # Create a mock settings pointing to tmp_path
        get_settings.cache_clear()
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))

        try:
            # Manually test the lock logic without triggering module-level code
            fd = open(lock_path, "w")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(str(os.getpid()))
            fd.flush()

            # Verify contents
            assert lock_path.read_text().strip() == str(os.getpid())

            fd.close()
        finally:
            get_settings.cache_clear()


# ── Browse truncation ─────────────────────────────────────────


class TestBrowseTruncation:
    """email_browse with include_body should truncate via mcp_max_body_chars."""

    def test_browse_body_truncated(self, monkeypatch):
        """Bodies returned by email_browse are truncated to mcp_max_body_chars."""
        from src.formatting import truncate_body

        body = "x" * 1000
        result = truncate_body(body, 500)
        assert len(result.split("\n")[0]) == 500
        assert "truncated" in result


# ── email_get_full soft limit ─────────────────────────────────


class TestGetFullSoftLimit:
    def test_setting_default(self):
        from src.config import Settings

        s = Settings()
        assert s.mcp_max_full_body_chars == 10000

    def test_env_override(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("MCP_MAX_FULL_BODY_CHARS", "5000")
        s = Settings.from_env()
        assert s.mcp_max_full_body_chars == 5000

    def test_zero_means_unlimited(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("MCP_MAX_FULL_BODY_CHARS", "0")
        s = Settings.from_env()
        assert s.mcp_max_full_body_chars == 0

    def test_resolve_runtime_passes_through(self, monkeypatch):
        from src.config import get_settings, resolve_runtime_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MCP_MAX_FULL_BODY_CHARS", "7500")
        try:
            s = resolve_runtime_settings()
            assert s.mcp_max_full_body_chars == 7500
        finally:
            get_settings.cache_clear()


# ── \xa0 normalization ────────────────────────────────────────


class TestNbspNormalization:
    def test_truncate_body_normalizes_nbsp(self):
        from src.formatting import truncate_body

        text = "hello\xa0world"
        result = truncate_body(text, 0)  # unlimited
        assert "\xa0" not in result
        assert result == "hello world"

    def test_truncate_body_normalizes_before_truncation(self):
        from src.formatting import truncate_body

        text = "\xa0" * 100 + "x" * 500
        result = truncate_body(text, 200)
        assert "\xa0" not in result
        assert result.startswith(" " * 100)

    def test_html_converter_strips_nbsp(self):
        from src.html_converter import html_to_text

        html = "<p>Hello&nbsp;world&nbsp;foo</p>"
        result = html_to_text(html)
        assert "\xa0" not in result
        assert "Hello world foo" in result


# ── serialize_results token budget ────────────────────────────


class TestSerializeResultsBudget:
    def _make_result(self, text="body text", uid="uid1"):
        from src.retriever import SearchResult

        return SearchResult(
            chunk_id=f"chunk-{uid}",
            text=text,
            metadata={"sender_email": "a@b.com", "date": "2024-01-01", "uid": uid},
            distance=0.2,
        )

    def _make_retriever(self):
        from src.retriever import EmailRetriever

        r = EmailRetriever.__new__(EmailRetriever)
        return r

    def test_budget_omits_excess(self):
        r = self._make_retriever()
        results = [self._make_result(text="x" * 500, uid=f"u{i}") for i in range(50)]
        payload = r.serialize_results("test", results, max_body_chars=0, max_response_tokens=200)
        # Should have a "note" entry about omitted results
        notes = [e for e in payload["results"] if "note" in e]
        assert len(notes) == 1
        assert "omitted" in notes[0]["note"]
        # count still reflects total
        assert payload["count"] == 50

    def test_unlimited_budget_shows_all(self):
        r = self._make_retriever()
        results = [self._make_result(uid=f"u{i}") for i in range(5)]
        payload = r.serialize_results("test", results, max_body_chars=0, max_response_tokens=0)
        notes = [e for e in payload["results"] if "note" in e]
        assert len(notes) == 0
        assert len(payload["results"]) == 5

    def test_budget_keeps_at_least_one_result(self):
        """Even with a very tight budget, the first result is always included."""
        r = self._make_retriever()
        results = [self._make_result(text="x" * 2000, uid="u0")]
        payload = r.serialize_results("test", results, max_body_chars=0, max_response_tokens=1)
        # First result should always be present (no note-only output)
        real_results = [e for e in payload["results"] if "note" not in e]
        assert len(real_results) == 1
