"""CLI search and browse subcommand tests split from RF17."""

from __future__ import annotations

import contextlib
import io

import pytest

from src.cli import main, parse_args


class TestSearchSubcommand:
    def test_root_help_uses_subcommand_parser(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), pytest.raises(SystemExit) as exc:
            main(["--help"])

        assert exc.value.code == 0
        output = buffer.getvalue()
        assert "search" in output
        assert "analytics" in output
        assert "Legacy flat-flag syntax is still supported but deprecated" in output

    def test_search_with_positional_query(self) -> None:
        args = parse_args(["search", "budget review"])
        assert args.subcommand == "search"
        assert args.query == "budget review"

    def test_search_with_query_flag(self) -> None:
        args = parse_args(["search", "--query", "budget review"])
        assert args.subcommand == "search"
        assert args.query == "budget review"

    def test_search_with_filters(self) -> None:
        args = parse_args(
            [
                "search",
                "--query",
                "budget",
                "--sender",
                "john",
                "--date-from",
                "2024-01-01",
                "--rerank",
                "--top-k",
                "5",
            ]
        )
        assert args.subcommand == "search"
        assert args.query == "budget"
        assert args.sender == "john"
        assert args.date_from == "2024-01-01"
        assert args.rerank is True
        assert args.top_k == 5

    def test_search_with_format_json(self) -> None:
        args = parse_args(["search", "--query", "test", "--format", "json"])
        assert args.subcommand == "search"
        assert args.format == "json"

    def test_search_with_all_metadata_filters(self) -> None:
        args = parse_args(
            [
                "search",
                "--query",
                "test",
                "--subject",
                "approval",
                "--folder",
                "inbox",
                "--cc",
                "team",
                "--to",
                "boss",
                "--bcc",
                "hr",
                "--has-attachments",
                "--priority",
                "3",
                "--email-type",
                "reply",
                "--min-score",
                "0.7",
                "--hybrid",
                "--topic",
                "2",
                "--cluster-id",
                "4",
                "--expand-query",
            ]
        )
        assert args.subcommand == "search"
        assert args.subject == "approval"
        assert args.folder == "inbox"
        assert args.cc == "team"
        assert args.to == "boss"
        assert args.bcc == "hr"
        assert args.has_attachments is True
        assert args.priority == 3
        assert args.email_type == "reply"
        assert args.min_score == 0.7
        assert args.hybrid is True
        assert args.topic == 2
        assert args.cluster_id == 4
        assert args.expand_query is True

    def test_search_accepts_root_flags_before_subcommand(self) -> None:
        args = parse_args(["--log-level", "INFO", "search", "budget review"])
        assert args.subcommand == "search"
        assert args.log_level == "INFO"
        assert args.query == "budget review"


class TestBrowseSubcommand:
    def test_browse_defaults(self) -> None:
        args = parse_args(["browse"])
        assert args.subcommand == "browse"
        assert args.page == 1
        assert args.page_size == 20

    def test_browse_with_page_and_size(self) -> None:
        args = parse_args(["browse", "--page", "3", "--page-size", "30"])
        assert args.page == 3
        assert args.page_size == 30

    def test_browse_rejects_page_size_above_documented_max(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["browse", "--page-size", "51"])

    def test_browse_with_filters(self) -> None:
        args = parse_args(["browse", "--folder", "inbox", "--sender", "alice"])
        assert args.folder == "inbox"
        assert args.sender == "alice"
