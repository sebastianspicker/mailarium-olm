"""Export/report command-family implementations for the CLI."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def run_generate_report_impl(db: ArchiveDatabase, output_path: str) -> None:
    """Generate a comprehensive report from the email database.

    Args:
        db: The runtime-owned ArchiveDatabase instance.
        output_path: Path where the report will be saved.
    """
    from mailarium.investigation.report_generator import ReportGenerationError, ReportGenerator

    generator = ReportGenerator(db)
    try:
        generator.generate(output_path=output_path)
    except ReportGenerationError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    warnings = getattr(generator, "last_warnings", [])
    if isinstance(warnings, list) and warnings:
        print(f"Report generated with warnings: {output_path}")
        for warning in warnings:
            print(f"  Warning: {warning}")
        return

    print(f"Report generated: {output_path}")


def run_export_thread_impl(
    db: ArchiveDatabase,
    conversation_id: str,
    fmt: str,
    output_path: str | None,
) -> None:
    """Export a conversation thread to the specified format.

    Args:
        db: The runtime-owned ArchiveDatabase instance.
        conversation_id: The conversation/thread identifier to export.
        fmt: Output format (e.g., 'json', 'html', 'text').
        output_path: Optional path for the output file. If None, a default path is generated.
    """
    from mailarium.investigation.email_exporter import EmailExporter

    exporter = EmailExporter(db)
    if output_path:
        result = exporter.export_thread_file(
            conversation_id,
            output_path,
            fmt=fmt,
        )
    else:
        safe_id = conversation_id[:20].replace("/", "_")
        default_path = f"private/exports/thread_{safe_id}.{fmt}"
        result = exporter.export_thread_file(
            conversation_id,
            default_path,
            fmt=fmt,
        )

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Thread exported: {result['output_path']} ({result['email_count']} emails)")
    if "note" in result:
        print(f"  Note: {result['note']}")


def run_export_email_impl(
    db: ArchiveDatabase,
    uid: str,
    fmt: str,
    output_path: str | None,
) -> None:
    """Export a single email to the specified format.

    Args:
        db: The runtime-owned ArchiveDatabase instance.
        uid: The unique identifier of the email to export.
        fmt: Output format (e.g., 'json', 'html', 'text').
        output_path: Optional path for the output file. If None, a default path is generated.
    """
    from mailarium.investigation.email_exporter import EmailExporter

    exporter = EmailExporter(db)
    if not output_path:
        output_path = f"private/exports/email_{uid[:12]}.{fmt}"
    result = exporter.export_single_file(uid, output_path, fmt=fmt)
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Email exported: {result['output_path']}")
    if "note" in result:
        print(f"  Note: {result['note']}")


def run_export_network_impl(db: ArchiveDatabase, output_path: str) -> None:
    """Export the communication network as a GraphML file.

    Args:
        db: The runtime-owned ArchiveDatabase instance.
        output_path: Path where the GraphML file will be saved.
    """
    from mailarium.investigation.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    result = net.export_graphml(output_path)
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Network exported: {output_path}")
    print(f"  Nodes: {result['total_nodes']}, Edges: {result['total_edges']}")
