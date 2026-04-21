"""CLI evidence and report/export subcommand tests split from RF17."""

from __future__ import annotations

from src.cli import parse_args


class TestExportSubcommand:
    def test_export_thread(self) -> None:
        args = parse_args(["export", "thread", "conv-123"])
        assert args.subcommand == "export"
        assert args.export_action == "thread"
        assert args.conversation_id == "conv-123"

    def test_export_thread_with_format_and_output(self) -> None:
        args = parse_args(
            [
                "export",
                "thread",
                "conv-123",
                "--format",
                "pdf",
                "-o",
                "out.pdf",
            ]
        )
        assert args.format == "pdf"
        assert args.output == "out.pdf"

    def test_export_email(self) -> None:
        args = parse_args(["export", "email", "uid-abc"])
        assert args.subcommand == "export"
        assert args.export_action == "email"
        assert args.uid == "uid-abc"

    def test_export_report(self) -> None:
        args = parse_args(["export", "report"])
        assert args.subcommand == "export"
        assert args.export_action == "report"
        assert args.output == "private/exports/report.html"

    def test_export_report_custom_output(self) -> None:
        args = parse_args(["export", "report", "--output", "custom.html"])
        assert args.output == "custom.html"

    def test_export_network(self) -> None:
        args = parse_args(["export", "network"])
        assert args.subcommand == "export"
        assert args.export_action == "network"
        assert args.output == "private/exports/network.graphml"


class TestEvidenceSubcommand:
    def test_evidence_list(self) -> None:
        args = parse_args(["evidence", "list"])
        assert args.subcommand == "evidence"
        assert args.evidence_action == "list"

    def test_evidence_list_with_filters(self) -> None:
        args = parse_args(
            [
                "evidence",
                "list",
                "--category",
                "discrimination",
                "--min-relevance",
                "3",
            ]
        )
        assert args.category == "discrimination"
        assert args.min_relevance == 3

    def test_evidence_export(self) -> None:
        args = parse_args(["evidence", "export", "report.html"])
        assert args.evidence_action == "export"
        assert args.output_path == "report.html"

    def test_evidence_export_csv(self) -> None:
        args = parse_args(["evidence", "export", "data.csv", "--format", "csv"])
        assert args.format == "csv"

    def test_evidence_stats(self) -> None:
        args = parse_args(["evidence", "stats"])
        assert args.evidence_action == "stats"

    def test_evidence_verify(self) -> None:
        args = parse_args(["evidence", "verify"])
        assert args.evidence_action == "verify"

    def test_evidence_dossier(self) -> None:
        args = parse_args(["evidence", "dossier", "output.html"])
        assert args.evidence_action == "dossier"
        assert args.output_path == "output.html"

    def test_evidence_dossier_pdf(self) -> None:
        args = parse_args(["evidence", "dossier", "out.pdf", "--format", "pdf"])
        assert args.format == "pdf"

    def test_evidence_custody(self) -> None:
        args = parse_args(["evidence", "custody"])
        assert args.evidence_action == "custody"

    def test_evidence_provenance(self) -> None:
        args = parse_args(["evidence", "provenance", "uid-xyz"])
        assert args.evidence_action == "provenance"
        assert args.uid == "uid-xyz"
