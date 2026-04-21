# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405, RUF022
"""Compatibility facade for split multi-source case-bundle helpers."""

from __future__ import annotations

from . import multi_source_case_bundle_chronology as _multi_source_case_bundle_chronology
from . import multi_source_case_bundle_common as _multi_source_case_bundle_common
from . import multi_source_case_bundle_linking as _multi_source_case_bundle_linking
from . import multi_source_case_bundle_reliability as _multi_source_case_bundle_reliability
from . import multi_source_case_bundle_sources as _multi_source_case_bundle_sources
from .multi_source_case_bundle_chronology import *
from .multi_source_case_bundle_common import *
from .multi_source_case_bundle_linking import *
from .multi_source_case_bundle_reliability import *
from .multi_source_case_bundle_sources import *

_SPLIT_MODULES = (
    _multi_source_case_bundle_common,
    _multi_source_case_bundle_linking,
    _multi_source_case_bundle_reliability,
    _multi_source_case_bundle_chronology,
    _multi_source_case_bundle_sources,
)
_WRAPPED_EXPORTS: set[str] = set()


def _bind_split_namespace() -> None:
    namespace = {}
    for module in _SPLIT_MODULES:
        namespace.update({name: getattr(module, name) for name in getattr(module, "__all__", ())})
    for module in _SPLIT_MODULES:
        module.__dict__.update(namespace)
    globals().update({key: value for key, value in namespace.items() if key not in _WRAPPED_EXPORTS})


_bind_split_namespace()


__all__ = [
    "MULTI_SOURCE_CASE_BUNDLE_VERSION",
    "_DECLARED_SOURCE_TYPES",
    "_FORMAL_DOCUMENT_EXTENSIONS",
    "_FORMAL_DOCUMENT_MIME_MARKERS",
    "_NOTE_RECORD_KEYWORDS",
    "_TIME_RECORD_KEYWORDS",
    "_PARTICIPATION_RECORD_KEYWORDS",
    "_ISO_DATE_RE",
    "_DATE_RANGE_RE",
    "_EU_DATE_RE",
    "_DATE_RANGE_EU_RE",
    "_SHEET_NAME_RE",
    "_MONTH_LABEL_RE",
    "_ICAL_FIELD_RE",
    "_ICAL_DATETIME_RE",
    "_EMAIL_LINK_TOKEN_RE",
    "_TITLE_DATE_RE",
    "_EMAIL_LINK_STOPWORDS",
    "_INLINE_EMAIL_RE",
    "_DATE_ORIGIN_PRIORITY",
    "_normalized_text",
    "_normalized_subject",
    "_date_key",
    "_identity_tokens_for_source",
    "_issue_tokens",
    "_link_confidence",
    "_iso_date_from_eu_text",
    "_date_candidates_from_text",
    "resolve_manifest_email_links",
    "_attachment_source_type",
    "_attachment_document_kind",
    "_attachment_reliability_basis_prefix",
    "_source_review_recommendation",
    "_source_reliability_for_chat_log",
    "_is_formal_document",
    "_source_reliability_for_email",
    "_source_reliability_for_attachment",
    "_source_reliability_for_meeting",
    "_weighting_metadata",
    "_string_list",
    "_documentary_support_payload",
    "_spreadsheet_semantics",
    "_document_locator",
    "_chronology_text",
    "_date_range_from_text",
    "_event_date_from_text",
    "_ical_field_params",
    "_ical_to_iso",
    "_calendar_semantics",
    "_meeting_event_date",
    "_chronology_anchor_for_source",
    "_meeting_note_sources",
    "_chat_log_sources",
]
