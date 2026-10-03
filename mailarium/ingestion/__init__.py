"""Explicit orchestration API for local mailbox ingestion.

The package boundary owns source adaptation, parsed attachment surfaces,
message projection, and the durable/archive plus vector write lifecycle.
Imports remain lazy so parser-only consumers do not initialise retrieval or
database runtime dependencies.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .records import ParsedMessage

__all__ = [
    "ParsedMessage",
    "ProductionIngestDependencies",
    "build_ingest_runtime_resources",
    "ingest",
    "ingest_archive",
    "production_ingest_dependencies",
    "reembed",
    "reextract_entities",
    "reextract_entities_archive",
    "reingest_analytics",
    "reingest_bodies",
    "reingest_metadata",
    "reingest_metadata_archive",
    "reprocess_degraded_attachments",
    "reset_index",
]

# Public name -> defining module. Every target is the plain-named function or
# class itself; ``*_archive`` names bind production services where the core
# operation accepts an explicit extractor or dependency bundle.
_PUBLIC_OPERATIONS = {
    "ParsedMessage": ".records",
    "build_ingest_runtime_resources": ".runtime",
    "ingest": ".orchestration",
    "ingest_archive": ".api",
    "ProductionIngestDependencies": ".context",
    "production_ingest_dependencies": ".api",
    "reingest_bodies": ".maintenance",
    "reingest_metadata": ".maintenance",
    "reingest_metadata_archive": ".api",
    "reingest_analytics": ".maintenance",
    "reextract_entities": ".maintenance",
    "reextract_entities_archive": ".api",
    "reprocess_degraded_attachments": ".attachments.reprocessing",
    "reembed": ".reembedding",
    "reset_index": ".reset",
}


def __getattr__(name: str) -> Any:
    """Load parser records and runtime operations only when callers request them."""
    if module_name := _PUBLIC_OPERATIONS.get(name):
        return getattr(import_module(module_name, __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
