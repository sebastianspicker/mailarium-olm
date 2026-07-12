"""End-to-end ingestion pipeline."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-positional-arguments,too-many-statements

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import zipfile
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from . import ingest_pipeline as pipeline_family
from . import ingest_reingest as reingest_family
from .chunker import chunk_attachment, chunk_email
from .config import (
    configure_logging,
    get_settings,
    resolve_runtime_summary,
    should_enable_image_embedding,
)
from .ingest_embed_pipeline import (
    _SENTINEL,
    _EmbedPipeline,
    _exchange_entities_from_email,
)
from .parse_olm import parse_olm
from .validation import positive_int as _shared_positive_int

_COMPATIBILITY_EXPORTS = (
    _EmbedPipeline,
    _SENTINEL,
    _exchange_entities_from_email,
)

logger = logging.getLogger(__name__)


def _resolve_entity_extractor(extract_entities: bool, dry_run: bool) -> Callable[[str, str], list[Any]] | None:
    """Return the appropriate entity extractor callable, or None if not needed.

    Tries spaCy (NLP + regex) first, downloading models if needed.
    Falls back to regex-only if spaCy is unavailable.
    Returns None when ``extract_entities`` is False or ``dry_run`` is True.
    """
    if not extract_entities or dry_run:
        return None
    try:
        from .nlp_entity_extractor import extract_nlp_entities, is_spacy_available

        if not is_spacy_available():
            if os.environ.get("SPACY_AUTO_DOWNLOAD_DURING_INGEST", "1") != "0":
                _auto_download_spacy_models()
                from .nlp_entity_extractor import reset_model_cache

                reset_model_cache()
            else:
                logger.info(
                    "Entity extraction: spaCy models unavailable; automatic download disabled via "
                    "SPACY_AUTO_DOWNLOAD_DURING_INGEST=0."
                )

        if is_spacy_available():
            logger.info("Entity extraction: spaCy NLP + regex (enhanced)")
            return extract_nlp_entities
        from .entity_extractor import extract_entities as _extract_entities

        logger.info("Entity extraction: regex-only (spaCy models not available)")
        return _extract_entities
    except ImportError:
        from .entity_extractor import extract_entities as _extract_entities

        logger.info("Entity extraction: regex-only")
        return _extract_entities


def _entity_extractor_provenance(entity_extractor_fn: Callable[[str, str], list[Any]] | None) -> tuple[str, str]:
    """Return stable provenance labels for the active entity extractor."""
    if entity_extractor_fn is None:
        return "", ""
    module_name = str(getattr(entity_extractor_fn, "__module__", "") or "")
    if module_name.endswith("nlp_entity_extractor"):
        return "spacy_regex", "1"
    if module_name.endswith("entity_extractor"):
        return "regex_only", "1"
    return "custom", "1"


def _hash_file_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file using streaming reads."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


_SPACY_MODELS = ["en_core_web_sm", "de_core_news_sm"]


def _auto_download_spacy_models() -> None:
    """Download spaCy language models if not already installed."""
    if os.environ.get("SPACY_AUTO_DOWNLOAD", "1") == "0":
        logger.debug("spaCy auto-download disabled via SPACY_AUTO_DOWNLOAD=0")
        return

    try:
        import spacy
    except ImportError:
        logger.debug("spaCy not installed, skipping model download")
        return

    import subprocess  # nosec B404
    import sys

    for model_name in _SPACY_MODELS:
        try:
            spacy.load(model_name)
            logger.debug("spaCy model already installed: %s", model_name)
        except OSError:
            logger.info("Downloading spaCy model: %s ...", model_name)
            try:
                subprocess.check_call(  # nosemgrep
                    [sys.executable, "-m", "spacy", "download", model_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("spaCy model installed: %s", model_name)
            except subprocess.CalledProcessError:
                logger.warning("Failed to download spaCy model: %s", model_name)


class _NoOpProgressBar:
    """Fallback when tqdm is not available."""

    def update(self, n: int = 1) -> None:
        pass

    def close(self) -> None:
        pass

    def set_postfix(self, **kwargs: Any) -> None:
        pass


def _make_progress_bar(total: int | None, desc: str = "", unit: str = "it") -> Any:
    """Create a tqdm progress bar if available, otherwise return a no-op."""
    try:
        from tqdm import tqdm

        return tqdm(total=total, desc=desc, unit=unit)
    except ImportError:
        return _NoOpProgressBar()


def ingest(
    olm_path: str,
    chromadb_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 500,
    max_emails: int | None = None,
    dry_run: bool = False,
    extract_attachments: bool = False,
    extract_entities: bool = False,
    incremental: bool = False,
    embed_images: bool = False,
    resume: bool = False,
    timing: bool = False,
) -> dict[str, Any]:
    """Run the end-to-end ingestion pipeline for Outlook .olm exports.

    Parses emails from the OLM archive, chunks them, generates embeddings,
    and stores results in ChromaDB and SQLite databases.

    Args:
        olm_path: Path to the Outlook .olm export file.
        chromadb_path: Custom path for ChromaDB storage. Defaults to None (uses default location).
        sqlite_path: Custom path for SQLite metadata database. Defaults to None (uses default location).
        batch_size: Number of chunks per write batch (default: 500).
        max_emails: Optional cap on the number of emails to parse.
        dry_run: If True, parse and chunk without writing to databases.
        extract_attachments: If True, extract and index text from attachments.
        extract_entities: If True, extract entities (orgs, URLs, phones) and store in SQLite.
        incremental: If True, skip emails already present in SQLite.
        embed_images: If True, embed image attachments using Visualized-BGE-M3.
        resume: If True, resume from the most recent checkpoint.
        timing: If True, show per-phase timing breakdown.

    Returns:
        Dictionary containing ingestion statistics (emails parsed, chunks created, etc.).
    """
    return pipeline_family.ingest_impl(
        olm_path=olm_path,
        chromadb_path=chromadb_path,
        sqlite_path=sqlite_path,
        batch_size=batch_size,
        max_emails=max_emails,
        dry_run=dry_run,
        extract_attachments=extract_attachments,
        extract_entities=extract_entities,
        incremental=incremental,
        embed_images=embed_images,
        resume=resume,
        timing=timing,
        get_settings=get_settings,
        resolve_runtime_summary=resolve_runtime_summary,
        should_enable_image_embedding=should_enable_image_embedding,
        parse_olm=parse_olm,
        chunk_email=chunk_email,
        chunk_attachment=chunk_attachment,
        hash_file_sha256=_hash_file_sha256,
        resolve_entity_extractor=_resolve_entity_extractor,
        resolve_entity_extractor_provenance=_entity_extractor_provenance,
        exchange_entities_from_email=_exchange_entities_from_email,
        embed_pipeline_cls=_EmbedPipeline,
        make_progress_bar=_make_progress_bar,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the ingestion pipeline.

    Args:
        argv: List of command-line arguments. Defaults to None (uses sys.argv).

    Returns:
        Parsed argparse.Namespace containing all configuration options.

    Raises:
        SystemExit: If required arguments are missing or invalid.
    """
    parser = argparse.ArgumentParser(description="Ingest Outlook .olm export into the email RAG database.")
    _add_ingest_arguments(parser)
    _add_reprocessing_arguments(parser)
    _add_common_arguments(parser)
    args = parser.parse_args(argv)
    if _olm_path_required(args) and not getattr(args, "olm_path", None):
        parser.error(
            "olm_path is required for ingest, --reingest-bodies, --reingest-metadata, and --reprocess-degraded-attachments."
        )
    return args


def _add_ingest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("olm_path", nargs="?", help="Path to the .olm file to ingest or re-parse when required.")
    parser.add_argument("--chromadb-path", default=None, help="Custom path for ChromaDB storage.")
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=500,
        help="Chunks per ingest write batch (default: 500).",
    )
    parser.add_argument(
        "--max-emails",
        type=_positive_int,
        default=None,
        help="Optional cap for number of emails to parse.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk emails without writing embeddings to ChromaDB.",
    )
    parser.add_argument(
        "--extract-attachments",
        action="store_true",
        help="Extract and index text content from attachments (PDF, DOCX, XLSX, text).",
    )
    parser.add_argument(
        "--embed-images",
        action="store_true",
        help="Embed image attachments (JPG, PNG, etc.) using Visualized-BGE-M3.",
    )
    parser.add_argument(
        "--extract-entities",
        action="store_true",
        help="Extract entities (organizations, URLs, phones) and store in SQLite.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help="Custom path for SQLite metadata database.",
    )


def _add_reprocessing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Skip emails already present in SQLite (saves embedding compute on re-runs).",
    )
    parser.add_argument(
        "--reset-index",
        action="store_true",
        help="Delete ChromaDB collection and SQLite DB, then exit.",
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
        help="Re-chunk and re-embed all emails from corrected SQLite body text into ChromaDB.",
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
        help="Resume ingest from the most recent checkpoint for the same OLM path.",
    )


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", action="store_true", help="Confirm destructive operations.")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Logging level override (DEBUG, INFO, WARNING, ERROR).",
    )


def _olm_path_required(args: argparse.Namespace) -> bool:
    """Check if olm_path argument is required based on other arguments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        True if olm_path is required, False if another operation mode is selected
        that doesn't need an OLM file (e.g., --reset-index, --reingest-analytics).
    """
    return not any(
        [
            getattr(args, "reset_index", False),
            getattr(args, "reingest_analytics", False),
            getattr(args, "reextract_entities", False),
            getattr(args, "reembed", False),
        ]
    )


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the ingestion pipeline.

    Orchestrates the ingestion process based on command-line arguments.
    Handles various operation modes: standard ingestion, re-ingestion variants,
    re-embedding, and index reset.

    Args:
        argv: List of command-line arguments. Defaults to None (uses sys.argv).

    Raises:
        SystemExit: On errors or when operations complete (with appropriate exit codes).
    """
    load_dotenv()
    args = parse_args(argv)
    configure_logging(args.log_level)
    if _run_maintenance_command(args):
        return
    stats = _run_ingest_command(args)
    print("\n" + "\n".join(format_ingestion_summary(stats)))


def _run_maintenance_command(args: argparse.Namespace) -> bool:
    if args.reset_index:
        _run_reset_index(args)

    if args.reingest_bodies:
        _print_command_completion(reingest_bodies(args.olm_path, sqlite_path=args.sqlite_path, force=args.force))

    if args.reingest_metadata:
        _print_command_completion(reingest_metadata(args.olm_path, sqlite_path=args.sqlite_path))

    if args.reingest_analytics:
        _print_command_completion(reingest_analytics(sqlite_path=args.sqlite_path))

    if args.reextract_entities:
        _print_command_completion(reextract_entities(sqlite_path=args.sqlite_path, force=args.force))

    if args.reprocess_degraded_attachments:
        _print_command_completion(
            reprocess_degraded_attachments(
                args.olm_path,
                chromadb_path=args.chromadb_path,
                sqlite_path=args.sqlite_path,
                batch_size=args.batch_size,
                force=args.force,
            )
        )

    if args.reembed:
        _print_command_completion(
            reembed(chromadb_path=args.chromadb_path, sqlite_path=args.sqlite_path, batch_size=args.batch_size)
        )
    return False


def _run_reset_index(args: argparse.Namespace) -> None:
    if not args.yes:
        print("Refusing to reset index without --yes.")
        raise SystemExit(2)
    _reset_index(args)
    print("Index has been reset.")
    raise SystemExit(0)


def _print_command_completion(result: dict[str, Any]) -> None:
    print(result["message"])
    raise SystemExit(0)


def _run_ingest_command(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return ingest(
            args.olm_path,
            chromadb_path=args.chromadb_path,
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


def reingest_bodies(
    olm_path: str,
    sqlite_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Re-parse OLM file to backfill body_text and body_html fields.

    Args:
        olm_path: Path to the Outlook .olm export file.
        sqlite_path: Custom path for SQLite metadata database. Defaults to None.
        force: If True, also updates subjects and sender names.

    Returns:
        Dictionary containing operation results and statistics.
    """
    return reingest_family.reingest_bodies_impl(
        olm_path,
        sqlite_path=sqlite_path,
        force=force,
        parse_olm_fn=parse_olm,
    )


def reingest_metadata(
    olm_path: str,
    sqlite_path: str | None = None,
) -> dict[str, Any]:
    """Re-parse OLM file to backfill v7 metadata fields.

    Backfills metadata including categories, thread_topic, calendar events,
    references, and attachment information.

    Args:
        olm_path: Path to the Outlook .olm export file.
        sqlite_path: Custom path for SQLite metadata database. Defaults to None.

    Returns:
        Dictionary containing operation results and statistics.
    """
    return reingest_family.reingest_metadata_impl(
        olm_path,
        sqlite_path=sqlite_path,
        exchange_entities_from_email=_exchange_entities_from_email,
        parse_olm_fn=parse_olm,
    )


def reingest_analytics(
    sqlite_path: str | None = None,
) -> dict[str, Any]:
    """Backfill language detection and sentiment analysis for emails.

    Processes emails missing analytics data in the SQLite database.

    Args:
        sqlite_path: Custom path for SQLite metadata database. Defaults to None.

    Returns:
        Dictionary containing operation results and statistics.
    """
    return reingest_family.reingest_analytics_impl(sqlite_path=sqlite_path)


def reextract_entities(
    sqlite_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Re-extract entities from stored email bodies.

    Re-processes email bodies to extract entities (organizations, URLs, phones, etc.)
    and persists extractor provenance metadata.

    Args:
        sqlite_path: Custom path for SQLite metadata database. Defaults to None.
        force: If True, re-extract entities even if already present.

    Returns:
        Dictionary containing operation results and statistics.
    """
    entity_extractor_fn = _resolve_entity_extractor(extract_entities=True, dry_run=False)
    extractor_key, extraction_version = _entity_extractor_provenance(entity_extractor_fn)
    return reingest_family.reextract_entities_impl(
        sqlite_path=sqlite_path,
        entity_extractor_fn=entity_extractor_fn,
        extractor_key=extractor_key,
        extraction_version=extraction_version,
        force=force,
    )


def reprocess_degraded_attachments(
    olm_path: str,
    chromadb_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
    force: bool = False,
) -> dict[str, Any]:
    """Re-process mailbox attachments for degraded/unsupported rows.

    Attempts OCR recovery for image attachments and re-extracts text from
    attachments that were previously marked as degraded or unsupported.

    Args:
        olm_path: Path to the Outlook .olm export file.
        chromadb_path: Custom path for ChromaDB storage. Defaults to None.
        sqlite_path: Custom path for SQLite metadata database. Defaults to None.
        batch_size: Number of items per batch (default: 100).
        force: If True, re-process all attachments regardless of current state.

    Returns:
        Dictionary containing operation results and statistics.
    """
    from .attachment_extractor import extract_attachment_text_ocr, extract_text

    return reingest_family.reprocess_degraded_attachments_impl(
        olm_path,
        chromadb_path=chromadb_path,
        sqlite_path=sqlite_path,
        batch_size=batch_size,
        force=force,
        parse_olm_fn=parse_olm,
        chunk_attachment_fn=chunk_attachment,
        attachment_text_extractor=extract_text,
        attachment_ocr_extractor=extract_attachment_text_ocr,
    )


def reembed(
    chromadb_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Re-chunk and re-embed all emails from SQLite body text into ChromaDB.

    Uses corrected body text from SQLite database to regenerate chunks and
    embeddings in ChromaDB.

    Args:
        chromadb_path: Custom path for ChromaDB storage. Defaults to None.
        sqlite_path: Custom path for SQLite metadata database. Defaults to None.
        batch_size: Number of chunks per batch (default: 100).

    Returns:
        Dictionary containing operation results and statistics.
    """
    return reingest_family.reembed_impl(
        chromadb_path=chromadb_path,
        sqlite_path=sqlite_path,
        batch_size=batch_size,
    )


def _reset_index(args: argparse.Namespace) -> None:
    """Delete ChromaDB collection and SQLite DB file."""
    reingest_family.reset_index_impl(args)


def _positive_int(raw: str) -> int:
    """Validate and convert a string to a positive integer.

    Args:
        raw: String to convert.

    Returns:
        The parsed positive integer.

    Raises:
        argparse.ArgumentTypeError: If the string cannot be parsed as a positive integer.
    """
    try:
        return _shared_positive_int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def format_ingestion_summary(stats: dict[str, Any]) -> list[str]:
    """Format ingestion statistics into a human-readable summary.

    Args:
        stats: Dictionary containing ingestion statistics (emails_parsed, chunks_created,
            chunks_added, chunks_skipped, batches_written, total_in_db, dry_run, etc.).

    Returns:
        List of formatted summary lines ready for display.
    """
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

    timing_info = stats.get("timing")
    if timing_info:
        parts = []
        if timing_info.get("embed_seconds"):
            parts.append(f"embed={timing_info['embed_seconds']}s")
        if timing_info.get("write_seconds"):
            parts.append(f"write={timing_info['write_seconds']}s")
        if parts:
            lines.append(f"Timing: {', '.join(parts)}")
        # Detailed sub-phase breakdown (when --timing flag is used)
        detail_keys = [
            ("parse_seconds", "parse"),
            ("queue_wait_seconds", "queue_wait"),
            ("sqlite_seconds", "sqlite"),
            ("entity_seconds", "entities"),
            ("analytics_seconds", "analytics"),
        ]
        detail_parts = []
        for key, label in detail_keys:
            if key in timing_info:
                detail_parts.append(f"{label}={timing_info[key]}s")
        if detail_parts:
            lines.append(f"  Breakdown: {', '.join(detail_parts)}")

    lines.append(f"Elapsed: {stats['elapsed_seconds']}s")
    return lines


if __name__ == "__main__":
    main()
