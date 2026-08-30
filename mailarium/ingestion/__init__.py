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
    "reprocess_degraded_attachments_archive",
    "reset_index",
]

_PUBLIC_OPERATIONS = {
    "build_ingest_runtime_resources": (".runtime", "build_ingest_runtime_resources"),
    "ingest": (".orchestration", "ingest_impl"),
    "ingest_archive": (".api", "ingest_archive"),
    "ProductionIngestDependencies": (".api", "ProductionIngestDependencies"),
    "production_ingest_dependencies": (".api", "production_ingest_dependencies"),
    "reingest_bodies": (".maintenance", "reingest_bodies_impl"),
    "reingest_metadata": (".maintenance", "reingest_metadata_impl"),
    "reingest_metadata_archive": (".api", "reingest_metadata_archive"),
    "reingest_analytics": (".maintenance", "reingest_analytics_impl"),
    "reextract_entities": (".maintenance", "reextract_entities_impl"),
    "reextract_entities_archive": (".api", "reextract_entities_archive"),
    "reprocess_degraded_attachments": (".attachment_reprocessing", "reprocess_degraded_attachments_impl"),
    "reprocess_degraded_attachments_archive": (".api", "reprocess_degraded_attachments_archive"),
    "reembed": (".reembedding", "reembed_impl"),
    "reset_index": (".reset", "reset_index_impl"),
}


def __getattr__(name: str) -> Any:
    """Load parser records and runtime operations only when callers request them."""
    if name == "ParsedMessage":
        from .records import ParsedMessage

        return ParsedMessage
    if operation := _PUBLIC_OPERATIONS.get(name):
        module_name, attribute = operation
        return getattr(import_module(module_name, __name__), attribute)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
