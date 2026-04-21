"""CLI argument handling, legacy compatibility, and detection tests split from RF17."""

from __future__ import annotations

import warnings

import pytest

from src.cli import parse_args


def _parse_legacy_args(argv: list[str]):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        args = parse_args(argv)
    assert any(issubclass(item.category, DeprecationWarning) for item in caught)
    return args


def _assert_legacy_parse_error(argv: list[str]) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(SystemExit):
            parse_args(argv)
    assert any(issubclass(item.category, DeprecationWarning) for item in caught)


class TestArgumentValidation:
    def test_search_rejects_both_positional_and_flag_query(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["search", "positional query", "--query", "flag query"])

    def test_search_requires_query(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["search"])


class TestSharedFlags:
    def test_chromadb_path_on_search(self) -> None:
        args = parse_args(["search", "--query", "test", "--chromadb-path", "/tmp/db"])
        assert args.chromadb_path == "/tmp/db"
        assert args.subcommand == "search"

    def test_sqlite_path_on_search(self) -> None:
        args = parse_args(["search", "--query", "test", "--sqlite-path", "/tmp/email.db"])
        assert args.sqlite_path == "/tmp/email.db"
        assert args.subcommand == "search"

    def test_log_level_on_browse(self) -> None:
        args = parse_args(["browse", "--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"
        assert args.subcommand == "browse"

    def test_chromadb_path_on_analytics(self) -> None:
        args = parse_args(["analytics", "--chromadb-path", "/tmp/db", "stats"])
        assert args.chromadb_path == "/tmp/db"

    def test_chromadb_path_on_legacy(self) -> None:
        args = _parse_legacy_args(["--chromadb-path", "/tmp/db", "--stats"])
        assert args.chromadb_path == "/tmp/db"

    def test_sqlite_path_on_legacy(self) -> None:
        args = _parse_legacy_args(["--sqlite-path", "/tmp/email.db", "--stats"])
        assert args.sqlite_path == "/tmp/email.db"


class TestLegacyBackwardCompat:
    def test_legacy_query_flag_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--query", "budget"])
            assert args.subcommand == "search"
            assert args.query == "budget"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_legacy_stats_flag_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--stats"])
            assert args.subcommand == "analytics"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_legacy_browse_flag_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--browse"])
            assert args.subcommand == "browse"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_legacy_export_thread_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--export-thread", "conv-123"])
            assert args.subcommand == "export"
            assert args.export_thread == "conv-123"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_legacy_evidence_list_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--evidence-list"])
            assert args.subcommand == "evidence"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_legacy_reset_index_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--reset-index"])
            assert args.subcommand == "admin"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_legacy_fine_tune_still_works(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            args = parse_args(["--generate-training-data", "out.jsonl"])
            assert args.subcommand == "training"
            assert any(issubclass(item.category, DeprecationWarning) for item in caught)

    def test_no_subcommand_no_flags_returns_none(self) -> None:
        args = parse_args([])
        assert args.subcommand is None

    def test_legacy_validation_still_applies(self) -> None:
        _assert_legacy_parse_error(["--stats", "--suggest"])


class TestSubcommandDetection:
    def test_has_subcommand_with_search(self) -> None:
        from src.cli import _has_subcommand

        assert _has_subcommand(["search", "--query", "test"]) is True

    def test_has_subcommand_with_legacy_flags(self) -> None:
        from src.cli import _has_subcommand

        assert _has_subcommand(["--query", "test"]) is False

    def test_has_subcommand_empty(self) -> None:
        from src.cli import _has_subcommand

        assert _has_subcommand([]) is False

    def test_has_subcommand_with_global_flags_before(self) -> None:
        from src.cli import _has_subcommand

        assert _has_subcommand(["--log-level", "DEBUG", "browse"]) is True
        assert _has_subcommand(["--chromadb-path", "/tmp/db", "analytics"]) is True
        assert _has_subcommand(["--sqlite-path", "/tmp/email.db", "analytics"]) is True

    def test_has_subcommand_all_valid_names(self) -> None:
        from src.cli import _has_subcommand

        for name in ["search", "browse", "export", "evidence", "analytics", "training", "admin"]:
            assert _has_subcommand([name]) is True, f"{name} not detected"

    def test_has_subcommand_ignores_flag_values(self) -> None:
        from src.cli import _has_subcommand

        assert _has_subcommand(["--db-path", "analytics"]) is False
        assert _has_subcommand(["--chromadb-path", "/tmp/admin"]) is False
        assert _has_subcommand(["--log-level", "search"]) is False

    def test_has_subcommand_with_equals_style_root_flag(self) -> None:
        from src.cli import _has_subcommand

        assert _has_subcommand(["--log-level=INFO", "search"]) is True


class TestLegacyDispatchActions:
    """Verify _infer_subcommand sets action attributes for legacy flags."""

    def test_stats_sets_analytics_action(self) -> None:
        args = _parse_legacy_args(["--stats"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "stats"

    def test_list_senders_sets_analytics_action(self) -> None:
        args = _parse_legacy_args(["--list-senders", "20"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "senders"

    def test_suggest_sets_analytics_action(self) -> None:
        args = _parse_legacy_args(["--suggest"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "suggest"

    def test_volume_sets_analytics_action(self) -> None:
        args = _parse_legacy_args(["--volume", "month"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "volume"

    def test_heatmap_sets_analytics_action(self) -> None:
        args = _parse_legacy_args(["--heatmap"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "heatmap"

    def test_response_times_sets_analytics_action(self) -> None:
        args = _parse_legacy_args(["--response-times"])
        assert args.subcommand == "analytics"
        assert args.analytics_action == "response-times"

    def test_evidence_list_sets_evidence_action(self) -> None:
        args = _parse_legacy_args(["--evidence-list"])
        assert args.subcommand == "evidence"
        assert args.evidence_action == "list"

    def test_evidence_stats_sets_evidence_action(self) -> None:
        args = _parse_legacy_args(["--evidence-stats"])
        assert args.subcommand == "evidence"
        assert args.evidence_action == "stats"

    def test_evidence_verify_sets_evidence_action(self) -> None:
        args = _parse_legacy_args(["--evidence-verify"])
        assert args.subcommand == "evidence"
        assert args.evidence_action == "verify"

    def test_reset_index_sets_admin_action(self) -> None:
        args = _parse_legacy_args(["--reset-index"])
        assert args.subcommand == "admin"
        assert args.admin_action == "reset-index"

    def test_generate_training_data_sets_training_action(self) -> None:
        args = _parse_legacy_args(["--generate-training-data", "out.jsonl"])
        assert args.subcommand == "training"
        assert args.training_action == "generate-data"
