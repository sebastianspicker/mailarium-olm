"""Embedding-based query expansion for improved recall."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)
_ASCII_FALLBACK_MAP = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
    }
)

_LEGAL_SUPPORT_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "chronology",
        (
            "chronology",
            "chronologie",
            "timeline",
            "zeitlinie",
            "sequence",
            "ablauf",
            "before",
            "vor",
            "after",
            "nach",
            "date",
            "datum",
            "dated",
            "calendar",
            "kalender",
            "meeting",
            "besprechung",
            "attendance",
            "anwesenheit",
            "timesheet",
            "arbeitszeit",
            "time record",
            "zeitnachweis",
            "note",
            "protokoll",
            "gedächtnisprotokoll",
        ),
        ("timeline", "chronology", "zeitlinie", "meeting note", "besprechungsprotokoll", "calendar record"),
    ),
    (
        "comparator",
        (
            "comparator",
            "vergleichsperson",
            "vergleichspersonen",
            "compare",
            "comparison",
            "unequal treatment",
            "ungleichbehandlung",
            "similarly situated",
            "other employee",
            "peer",
            "kollege",
            "kollegin",
            "benachteiligung",
        ),
        ("comparator", "vergleichsgruppe", "peer treatment", "similarly situated", "unequal treatment"),
    ),
    (
        "participation",
        (
            "sbv",
            "personalrat",
            "betriebsrat",
            "mitbestimmung",
            "vertretung",
            "lpvg",
            "participation",
            "consultation",
            "consult",
            "bem",
            "schwerbehindertenvertretung",
            "sgb ix",
            "sgb9",
            "teilhabe",
            "dienstvereinbarung",
        ),
        (
            "sbv",
            "personalrat",
            "betriebsrat",
            "schwerbehindertenvertretung",
            "participation record",
            "consultation",
            "bem",
            "sgb ix",
        ),
    ),
    (
        "retaliation",
        (
            "maßregelung",
            "massregelung",
            "vergeltung",
            "reaktion auf beschwerde",
            "benachteiligung nach beschwerde",
        ),
        ("maßregelung", "massregelung", "beschwerde", "reaktion nach beschwerde"),
    ),
    (
        "contradiction",
        (
            "contradiction",
            "widerspruch",
            "contradict",
            "widersprüchlich",
            "discrepancy",
            "abweichung",
            "inconsistent",
            "mismatch",
            "promise",
            "zusage",
            "omission",
            "unterlassen",
            "summary",
            "zusammenfassung",
            "conflict",
        ),
        ("contradiction", "widerspruch", "inconsistent summary", "promise", "omission", "discrepancy"),
    ),
    (
        "document_request",
        (
            "missing proof",
            "fehlender nachweis",
            "missing exhibit",
            "fehlende unterlage",
            "missing record",
            "fehlendes dokument",
            "document request",
            "aktenanforderung",
            "preservation",
            "beweissicherung",
            "custodian",
        ),
        ("missing record", "fehlender nachweis", "document request", "preservation", "custodian"),
    ),
    (
        "classification",
        (
            "eg12",
            "e12",
            "eingruppierung",
            "stufenvorweggewährung",
            "stufenvorweggewaehrung",
            "tv-l",
            "tvl",
            "classification",
            "tarif",
            "entgelt",
            "payroll",
        ),
        ("EG12", "classification", "payroll", "tarif", "TV-L", "Arbeitsvorgang", "Stufenvorweggewährung"),
    ),
    (
        "anti_discrimination",
        (
            "agg",
            "allgemeines gleichbehandlungsgesetz",
            "diskriminierung",
            "benachteiligungsverbot",
            "equal treatment",
        ),
        (
            "AGG",
            "Gleichbehandlung",
            "Benachteiligungsverbot",
            "equal treatment",
            "discrimination",
        ),
    ),
    (
        "timekeeping",
        (
            "time system",
            "zeiterfassung",
            "attendance",
            "timesheet",
            "arbeitszeit",
            "umbuchung",
            "rebooking",
        ),
        ("time system", "attendance", "timesheet", "Arbeitszeit", "rebooking"),
    ),
    (
        "task_ownership",
        (
            "aufgabenentzug",
            "task withdrawal",
            "projektbrief",
            "project brief",
            "rollenverantwortung",
            "zuständigkeit",
            "role ownership",
            "role clarification",
        ),
        ("task withdrawal", "project brief", "ownership", "role clarification", "Aufgabenentzug"),
    ),
    (
        "mobile_work",
        (
            "mobiles arbeiten",
            "mobile work",
            "homeoffice",
            "home office",
            "dienstvereinbarung",
            "20 prozent",
        ),
        ("mobile work", "home office", "Dienstvereinbarung", "policy", "comparator"),
    ),
)


def _wave_shared_terms(query: str | None) -> list[str]:
    from .question_execution_waves import shared_wave_vocabulary

    text = " ".join(str(query or "").lower().split())
    if not text:
        return []
    matched: list[str] = []
    for term in shared_wave_vocabulary(limit=48):
        if _query_trigger_matches(text, term):
            matched.append(term)
    return matched[:8]


def _compound_variant_lanes(query: str) -> list[str]:
    normalized_query = " ".join(str(query or "").split()).strip()
    if not normalized_query:
        return []
    lowered = normalized_query.casefold()
    lanes: list[str] = []
    compound_map: dict[str, tuple[str, ...]] = {
        "stufenvorweggewährung": ("stufenvorweggewaehrung", "stufen vorweg gewaehrung"),
        "stufenvorweggewaehrung": ("stufenvorweggewährung", "stufen vorweg gewaehrung"),
        "wiedereingliederung": ("wieder eingliederung",),
        "leidensgerechter": ("leidens gerechter",),
        "schwerbehindertenvertretung": ("schwerbehinderten vertretung", "sbv"),
    }
    for trigger, variants in compound_map.items():
        if trigger not in lowered:
            continue
        for variant in variants:
            lanes.append(f"{normalized_query} {variant}".strip())
    return lanes


def _query_trigger_matches(text: str, trigger: str) -> bool:
    normalized_trigger = " ".join(str(trigger or "").lower().split()).strip()
    if not normalized_trigger:
        return False
    if " " in normalized_trigger:
        return normalized_trigger in text
    return bool(re.search(r"(?<!\w)" + re.escape(normalized_trigger) + r"(?!\w)", text))


def legal_support_query_profile(query: str | None) -> dict[str, Any]:
    """Return deterministic legal-support intent flags for one query."""
    text = " ".join(str(query or "").lower().split())
    intents: list[str] = []
    suggested_terms: list[str] = []
    intent_suggested_terms: dict[str, list[str]] = {}
    for intent_id, triggers, additions in _LEGAL_SUPPORT_RULES:
        if any(_query_trigger_matches(text, trigger) for trigger in triggers):
            intents.append(intent_id)
            intent_terms: list[str] = []
            for term in additions:
                if term not in suggested_terms and not re.search(r"\b" + re.escape(term) + r"\b", text):
                    suggested_terms.append(term)
                if not re.search(r"\b" + re.escape(term) + r"\b", text):
                    intent_terms.append(term)
            intent_suggested_terms[intent_id] = intent_terms
    shared_wave_terms = [term for term in _wave_shared_terms(query) if term not in suggested_terms]
    suggested_terms.extend(shared_wave_terms)
    return {
        "is_legal_support": bool(intents),
        "intents": intents,
        "suggested_terms": suggested_terms,
        "intent_suggested_terms": intent_suggested_terms,
        "shared_wave_terms": shared_wave_terms,
    }


class QueryExpander:
    """Expand queries with semantically related terms using the embedding model.

    Reuses the already-loaded SentenceTransformer model and keyword vocabulary
    from the keyword extractor to find related terms at near-zero cost.
    """

    def __init__(self, model: Any = None, vocabulary: list[str] | None = None):
        """Initialize query expander.

        Args:
            model: SentenceTransformer model instance (reuses existing).
            vocabulary: List of corpus keywords to match against.
        """
        self._model = model
        self._vocabulary = vocabulary or []
        self._vocab_embeddings = None

    def set_vocabulary(self, vocabulary: list[str]) -> None:
        """Set or update the keyword vocabulary.

        Args:
            vocabulary: List of keywords/phrases from the corpus.
        """
        self._vocabulary = vocabulary
        self._vocab_embeddings = None  # Reset cached embeddings

    def _compute_similarities(self, query: str):
        """Return ``(similarities, top_indices)`` for *query* against the vocabulary.

        Lazily computes and caches vocabulary embeddings.  Returns ``None`` if
        numpy/model are unavailable or if the vocabulary is empty.
        """
        import numpy as np

        if not self._vocabulary:
            return None

        if self._vocab_embeddings is None:
            self._vocab_embeddings = np.array(self._model.encode_dense(self._vocabulary))
        query_embedding = np.array(self._model.encode_dense([query]))
        similarities = np.dot(self._vocab_embeddings, query_embedding.T).flatten()
        return similarities, similarities.argsort()[::-1]

    def expand(self, query: str, n_terms: int = 3) -> str:
        """Expand a query with semantically related terms.

        Embeds the query and finds the closest keywords from the corpus
        vocabulary, appending them to the original query.

        Args:
            query: Original search query.
            n_terms: Number of related terms to add.

        Returns:
            Expanded query string.
        """
        if not query or not query.strip():
            return query

        if n_terms <= 0:
            return query

        if not self._vocabulary or not self._model:
            return query

        try:
            query_lower = query.lower()
            added: list[str] = []
            profile = legal_support_query_profile(query)
            for term in profile["suggested_terms"]:
                if len(added) >= n_terms:
                    break
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", query_lower):
                    continue
                added.append(term)

            sim_result = self._compute_similarities(query)
            if sim_result is None:
                return f"{query} {' '.join(added)}".strip() if added else query
            _similarities, top_indices = sim_result
            for idx in top_indices:
                if len(added) >= n_terms:
                    break
                term = self._vocabulary[idx]
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", query_lower):
                    continue
                if len(term) < 3:
                    continue
                if term in added:
                    continue
                added.append(term)

            if not added:
                return query

            expanded = f"{query} {' '.join(added)}"
            logger.debug("Query expanded: '%s' → '%s'", query, expanded)
            return expanded

        except Exception:
            logger.debug("Query expansion failed", exc_info=True)
            return query

    def expand_lanes(self, query: str, n_terms: int = 3, max_lanes: int = 4) -> list[str]:
        """Return retrieval lanes instead of collapsing expansion into one query."""
        base_query = " ".join(str(query or "").split()).strip()
        if not base_query:
            return []
        if max_lanes <= 1:
            return [base_query]

        lanes: list[str] = [base_query]
        ascii_lane = base_query.translate(_ASCII_FALLBACK_MAP)
        if ascii_lane != base_query:
            lanes.append(ascii_lane)

        profile = legal_support_query_profile(base_query)
        intent_suggested_terms = profile.get("intent_suggested_terms") or {}
        if isinstance(intent_suggested_terms, dict):
            for intent_id in profile.get("intents") or []:
                intent_terms = [str(term).strip() for term in intent_suggested_terms.get(intent_id, []) if str(term).strip()]
                if intent_terms:
                    lanes.append(f"{base_query} {' '.join(intent_terms[: min(n_terms, len(intent_terms))])}".strip())
        shared_wave_terms = [str(term).strip() for term in profile.get("shared_wave_terms") or [] if str(term).strip()]
        if shared_wave_terms:
            lanes.append(f"{base_query} {' '.join(shared_wave_terms[: min(n_terms, len(shared_wave_terms))])}".strip())
        lanes.extend(_compound_variant_lanes(base_query))

        try:
            if self._vocabulary and self._model:
                related_terms = [term for term, _score in self.get_related_terms(base_query, n_terms=max(1, n_terms * 2))]
                if related_terms:
                    lanes.append(f"{base_query} {' '.join(related_terms[:n_terms])}".strip())
        except Exception:
            logger.debug("Query lane expansion failed", exc_info=True)

        normalized: list[str] = []
        seen: set[str] = set()
        for lane in lanes:
            compact = " ".join(str(lane or "").split()).strip()
            lowered = compact.casefold()
            if not compact or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(compact)
            if len(normalized) >= max_lanes:
                break
        return normalized

    def get_related_terms(self, query: str, n_terms: int = 5) -> list[tuple[str, float]]:
        """Get related terms with their similarity scores.

        Args:
            query: Search query.
            n_terms: Number of terms to return.

        Returns:
            List of (term, similarity_score) tuples.
        """
        if not query or not self._vocabulary or not self._model or n_terms <= 0:
            return []

        try:
            sim_result = self._compute_similarities(query)
            if sim_result is None:
                return []
            similarities, top_indices = sim_result
            query_lower = query.lower()
            results: list[tuple[str, float]] = []
            for idx in top_indices:
                if len(results) >= n_terms:
                    break
                term = self._vocabulary[idx]
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", query_lower) or len(term) < 3:
                    continue
                results.append((term, round(float(similarities[idx]), 4)))

            return results

        except Exception:
            logger.debug("get_related_terms failed", exc_info=True)
            return []
