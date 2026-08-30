"""Command-line adapter for local Outlook archive ingestion and maintenance."""

from __future__ import annotations

import argparse
import zipfile
from typing import Any

from dotenv import load_dotenv

from mailarium.config import configure_logging
from mailarium.ingestion import (
    ingest_archive,
    reembed,
    reextract_entities_archive,
    reingest_analytics,
    reingest_bodies,
    reingest_metadata_archive,
    reprocess_degraded_attachments_archive,
    reset_index,
)
from mailarium.platform.validation import positive_int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse public ingestion command-line arguments."""
    parser = argparse.ArgumentParser(description="Ingest Outlook .olm export into the Mailarium database.")
    _add_ingest_arguments(parser)
    _add_reprocessing_arguments(parser)
    _add_common_arguments(parser)
    args = parser.parse_args(argv)
    if _olm_path_required(args) and not args.olm_path:
        parser.error(
            "olm_path is required for ingest, --reingest-bodies, --reingest-metadata, and --reprocess-degraded-attachments."
        )
    return args


def main(argv: list[str] | None = None) -> None:
    """Run the public ingestion command against the feature-level library API."""
    load_dotenv()
    args = parse_args(argv)
    configure_logging(args.log_level)
    if _run_maintenance_command(args):
        return
    stats = _run_ingest_command(args)
    print("\n" + "\n".join(format_ingestion_summary(stats)))


def _add_ingest_arguments(parser: argparse.ArgumentParser) -> None:
    """Register source, index, batching, and extraction controls."""
    parser.add_argument("olm_path", nargs="?", help="Path to the .olm file to ingest or re-parse when required.")
    parser.add_argument("--vector-index-path", default=None, help="Custom path for USearch vector index storage.")
    parser.add_argument("--batch-size", type=_positive_int, default=500, help="Chunks per ingest write batch (default: 500).")
    parser.add_argument("--max-emails", type=_positive_int, default=None, help="Optional cap for number of emails to parse.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk emails without writing embeddings to USearch vector index.",
    )
    parser.add_argument(
        "--extract-attachments",
        action="store_true",
        help="Extract and index text content from attachments (PDF, DOCX, XLSX, text).",
    )
    parser.add_argument(
        "--embed-images",
        action="store_true",
        help="Embed image attachments (JPG, PNG, etc.) using the optional SigLIP2 image model.",
    )
    parser.add_argument(
        "--extract-entities",
        action="store_true",
        help="Extract entities (organizations, URLs, phones) and store in SQLite.",
    )
    parser.add_argument("--sqlite-path", default=None, help="Custom path for SQLite metadata database.")


def _add_reprocessing_arguments(parser: argparse.ArgumentParser) -> None:
    """Register maintenance operation selectors and their controls."""
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Skip emails already present in SQLite (saves embedding compute on re-runs).",
    )
    parser.add_argument(
        "--reset-index",
        action="store_true",
        help="Clear dense/sparse vector state and derived index files, preserving SQLite email metadata.",
    )
    parser.add_argument(
        "--reingest-bodies",
        action="store_true",
        help="Re-parse OLM to backfill body_text/body_html. With --force, also updates subjects and sender names.",
    )
    parser.add_argument(
        "--reingest-metadata",
        action="store_true",
        help="Re-parse OLM to backfill v7 metadata (categories, thread_topic, calendar, references, attachments).",
    )
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Re-chunk and re-embed all emails from corrected SQLite body text into USearch vector index.",
    )
    parser.add_argument(
        "--reingest-analytics",
        action="store_true",
        help="Backfill language detection and sentiment analysis for emails missing analytics data.",
    )
    parser.add_argument(
        "--reextract-entities",
        action="store_true",
        help="Re-extract entities from stored email bodies and persist extractor provenance metadata.",
    )
    parser.add_argument(
        "--reprocess-degraded-attachments",
        action="store_true",
        help="Re-parse mailbox attachments for degraded/unsupported rows and attempt OCR recovery for images.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-parse all emails (use with --reingest-bodies to overwrite existing body text and headers).",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Show per-phase timing breakdown (parse, embed, sqlite, entities, analytics).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume supported ingest work; with --reembed, skip matching committed body vectors.",
    )


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Register shared confirmation and logging controls."""
    parser.add_argument("--yes", action="store_true", help="Confirm destructive operations.")
    parser.add_argument("--log-level", default=None, help="Logging level override (DEBUG, INFO, WARNING, ERROR).")


def _positive_int(raw: str) -> int:
    """Translate shared validation failures into argparse errors."""
    try:
        return positive_int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _olm_path_required(args: argparse.Namespace) -> bool:
    """Return whether the selected operation reads an OLM archive."""
    return not any((args.reset_index, args.reingest_analytics, args.reextract_entities, args.reembed))


def _run_maintenance_command(args: argparse.Namespace) -> bool:
    """Dispatch one selected maintenance command and terminate after its result."""
    if args.reset_index:
        if not args.yes:
            print("Refusing to reset index without --yes.")
            raise SystemExit(2)
        reset_index(args)
        print("Index has been reset.")
        raise SystemExit(0)
    if args.reingest_bodies:
        _print_completion(reingest_bodies(args.olm_path, sqlite_path=args.sqlite_path, force=args.force))
    if args.reingest_metadata:
        _print_completion(reingest_metadata_archive(args.olm_path, sqlite_path=args.sqlite_path))
    if args.reingest_analytics:
        _print_completion(reingest_analytics(sqlite_path=args.sqlite_path))
    if args.reextract_entities:
        _print_completion(reextract_entities_archive(sqlite_path=args.sqlite_path, force=args.force))
    if args.reprocess_degraded_attachments:
        _print_completion(
            reprocess_degraded_attachments_archive(
                args.olm_path,
                vector_index_path=args.vector_index_path,
                sqlite_path=args.sqlite_path,
                batch_size=args.batch_size,
                force=args.force,
            )
        )
    if args.reembed:
        _print_completion(
            reembed(
                vector_index_path=args.vector_index_path,
                sqlite_path=args.sqlite_path,
                batch_size=args.batch_size,
                resume=args.resume,
            )
        )
    return False


def _print_completion(result: dict[str, Any]) -> None:
    """Print a maintenance outcome and terminate successfully."""
    print(result["message"])
    raise SystemExit(0)


def _run_ingest_command(args: argparse.Namespace) -> dict[str, Any]:
    """Translate parsed CLI options into the production ingestion facade."""
    try:
        return ingest_archive(
            olm_path=args.olm_path,
            vector_index_path=args.vector_index_path,
            sqlite_path=args.sqlite_path,
            batch_size=args.batch_size,
            max_emails=args.max_emails,
            dry_run=args.dry_run,
            extract_attachments=args.extract_attachments,
            extract_entities=args.extract_entities,
            incremental=args.incremental,
            embed_images=args.embed_images,
            resume=args.resume,
            timing=args.timing,
        )
    except FileNotFoundError as exc:
        print(str(exc))
        raise SystemExit(2) from exc
    except zipfile.BadZipFile as exc:
        print(f"Invalid OLM archive: {args.olm_path} ({exc})")
        raise SystemExit(2) from exc
    except OSError as exc:
        print(f"Could not read OLM archive: {args.olm_path} ({exc})")
        raise SystemExit(2) from exc
    except RuntimeError as exc:
        print(str(exc))
        raise SystemExit(2) from exc
    except KeyboardInterrupt as exc:
        print("Ingestion interrupted.")
        raise SystemExit(130) from exc


def format_ingestion_summary(stats: dict[str, Any]) -> list[str]:
    """Format the stable public completion summary for one ingest operation."""
    lines = [
        "=== Ingestion Summary ===",
        f"Emails parsed: {stats['emails_parsed']}",
        f"Chunks created: {stats['chunks_created']}",
    ]
    if stats["dry_run"]:
        lines.append("Database write disabled (dry-run).")
    else:
        lines.extend(
            [
                f"Chunks added: {stats['chunks_added']}",
                f"Chunks skipped: {stats['chunks_skipped']}",
                f"Write batches: {stats['batches_written']}",
                f"Total in DB: {stats['total_in_db']}",
            ]
        )
        if "sqlite_inserted" in stats:
            lines.append(f"SQLite rows inserted: {stats['sqlite_inserted']}")
        if stats.get("skipped_incremental", 0) > 0:
            lines.append(f"Skipped (incremental): {stats['skipped_incremental']}")
    _append_timing_summary(lines, stats.get("timing"))
    lines.append(f"Elapsed: {stats['elapsed_seconds']}s")
    return lines


def _append_timing_summary(lines: list[str], timing_info: Any) -> None:
    """Append the optional timing summary and phase breakdown."""
    if not timing_info:
        return
    timing_parts = [
        f"{label}={timing_info[key]}s"
        for key, label in (("embed_seconds", "embed"), ("write_seconds", "write"))
        if timing_info.get(key)
    ]
    if timing_parts:
        lines.append(f"Timing: {', '.join(timing_parts)}")
    detail_parts = [
        f"{label}={timing_info[key]}s"
        for key, label in (
            ("parse_seconds", "parse"),
            ("queue_wait_seconds", "queue_wait"),
            ("sqlite_seconds", "sqlite"),
            ("entity_seconds", "entities"),
            ("analytics_seconds", "analytics"),
        )
        if key in timing_info
    ]
    if detail_parts:
        lines.append(f"  Breakdown: {', '.join(detail_parts)}")
