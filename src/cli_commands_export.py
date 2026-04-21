"""Export/report command-family implementations for the CLI."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email_db import EmailDatabase


def run_generate_report_impl(get_email_db: Callable[[], EmailDatabase], output_path: str) -> None:
    db = get_email_db()
    from .report_generator import ReportGenerator

    generator = ReportGenerator(db)
    generator.generate(output_path=output_path)
    print(f"Report generated: {output_path}")


def run_export_thread_impl(
    get_email_db: Callable[[], EmailDatabase],
    conversation_id: str,
    fmt: str,
    output_path: str | None,
) -> None:
    db = get_email_db()
    from .email_exporter import EmailExporter

    exporter = EmailExporter(db)
    if output_path:
        result = exporter.export_thread_file(conversation_id, output_path, fmt=fmt)
    else:
        safe_id = conversation_id[:20].replace("/", "_")
        default_path = f"thread_{safe_id}.{fmt}"
        result = exporter.export_thread_file(conversation_id, default_path, fmt=fmt)

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Thread exported: {result['output_path']} ({result['email_count']} emails)")
    if "note" in result:
        print(f"  Note: {result['note']}")


def run_export_email_impl(
    get_email_db: Callable[[], EmailDatabase],
    uid: str,
    fmt: str,
    output_path: str | None,
) -> None:
    db = get_email_db()
    from .email_exporter import EmailExporter

    exporter = EmailExporter(db)
    if not output_path:
        output_path = f"email_{uid[:12]}.{fmt}"
    result = exporter.export_single_file(uid, output_path, fmt=fmt)
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Email exported: {result['output_path']}")
    if "note" in result:
        print(f"  Note: {result['note']}")


def run_export_network_impl(get_email_db: Callable[[], EmailDatabase], output_path: str) -> None:
    db = get_email_db()
    from .network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    result = net.export_graphml(output_path)
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    print(f"Network exported: {output_path}")
    print(f"  Nodes: {result['total_nodes']}, Edges: {result['total_edges']}")
