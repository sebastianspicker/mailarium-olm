"""Deterministic query-adaptive retrieval policy helpers.

This module only chooses explainable retrieval parameters.  It does not train a
model or infer a user's domain from their query text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_SCOPE_LENGTH = 64
GENERAL_SCOPE = "general"

# Horizontal/line whitespace is normalized below; other control characters are
# rejected because they cannot safely represent a scope label.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")
_QUOTED_PHRASE = re.compile(r"(?:\"[^\"\n]+\"|'[^'\n]+')")
_EMAIL_TOKEN = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_FILENAME = re.compile(r"\b[^\s/\\]+\.(?:pdf|docx?|xlsx?|pptx?|csv|txt|eml|msg|zip)\b", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"\b\d{6,}\b")
_LONG_IDENTIFIER = re.compile(r"\b(?=[A-Za-z0-9_-]{8,}\b)(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]+\b")
_QUESTION_START = re.compile(r"^\s*(?:who|what|when|where|why|how|which|can|could|does|do|is|are|was|were)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """Resolved, immutable retrieval settings with concise diagnostics."""

    scope: str
    semantic_weight: float
    keyword_weight: float
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize the resolved scope, blend weights, and decision reasons for diagnostics."""
        return {
            "scope": self.scope,
            "semantic_weight": self.semantic_weight,
            "keyword_weight": self.keyword_weight,
            "reason_codes": list(self.reason_codes),
        }


def normalize_scope(scope: str | None = None) -> str:
    """Normalize an optional user-declared scope without silently accepting invalid input."""
    if scope is None:
        return GENERAL_SCOPE
    if not isinstance(scope, str):
        raise TypeError("scope must be a string or None")
    if _CONTROL_CHARACTERS.search(scope):
        raise ValueError("scope must not contain control characters")

    normalized = _WHITESPACE.sub(" ", scope).strip().lower()
    if not normalized:
        raise ValueError("scope must not be empty")
    if len(normalized) > MAX_SCOPE_LENGTH:
        raise ValueError(f"scope must be at most {MAX_SCOPE_LENGTH} characters")
    return normalized


def resolve_retrieval_policy(query: str, scope: str | None = None) -> RetrievalPolicy:
    """Select deterministic semantic and lexical weights from query cues and explicit scope."""
    if not isinstance(query, str):
        raise TypeError("query must be a string")

    resolved_scope = normalize_scope(scope)
    reason_codes: list[str] = ["scope_general" if resolved_scope == GENERAL_SCOPE else "scope_explicit"]
    lexical_reasons = _lexical_reason_codes(query)
    if lexical_reasons:
        semantic_weight, keyword_weight = 0.30, 0.70
        reason_codes.extend(lexical_reasons)
    elif _is_semantic_query(query):
        semantic_weight, keyword_weight = 0.70, 0.30
        reason_codes.append("semantic_query_shape")
    else:
        semantic_weight, keyword_weight = 0.60, 0.40
        reason_codes.append("balanced_default")

    return RetrievalPolicy(
        scope=resolved_scope,
        semantic_weight=semantic_weight,
        keyword_weight=keyword_weight,
        reason_codes=tuple(reason_codes),
    )


def apply_scope_context(query: str, scope: str | None = None) -> str:
    """Append an explicit non-general scope marker so downstream retrieval honors it."""
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    resolved_scope = normalize_scope(scope)
    if resolved_scope == GENERAL_SCOPE:
        return query
    return f"{query}\nRetrieval scope: {resolved_scope}"


def _lexical_reason_codes(query: str) -> list[str]:
    reasons: list[str] = []
    if _QUOTED_PHRASE.search(query):
        reasons.append("quoted_phrase")
    if _EMAIL_TOKEN.search(query):
        reasons.append("email_token")
    if _FILENAME.search(query):
        reasons.append("filename_token")
    if _LONG_NUMBER.search(query) or _LONG_IDENTIFIER.search(query):
        reasons.append("long_identifier")
    return reasons


def _is_semantic_query(query: str) -> bool:
    words = query.split()
    return "?" in query or bool(_QUESTION_START.search(query)) or len(words) >= 8
