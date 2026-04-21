"""NLP-based entity extraction using spaCy with regex fallback."""

from __future__ import annotations

import collections
import logging
from typing import TYPE_CHECKING

from .entity_extractor import ExtractedEntity, extract_entities

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# spaCy entity types we care about, mapped to our schema
_SPACY_TYPE_MAP = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "location",
    "LOC": "location",
    "MONEY": "money",
    "EVENT": "event",
}

# Types we skip (too noisy or not useful)
_SPACY_SKIP_TYPES = frozenset({"DATE", "TIME", "CARDINAL", "ORDINAL", "QUANTITY", "PERCENT", "LANGUAGE"})

_nlp_models: dict[str, object] = {}
_nlp_load_attempted = False
_LANG_CACHE_MAX = 256
# OrderedDict gives LRU semantics: move_to_end on hit, popitem(last=False) to evict.
_sender_lang_cache: collections.OrderedDict[str, str | None] = collections.OrderedDict()

# Models to try loading, in order. First match becomes the default.
_SPACY_MODELS = {
    "en": "en_core_web_sm",
    "de": "de_core_news_sm",
}


def _load_models() -> None:
    """Lazy-load all available spaCy models."""
    global _nlp_load_attempted
    if _nlp_load_attempted:
        return
    _nlp_load_attempted = True
    try:
        import spacy
    except ImportError:
        logger.debug("spaCy not installed, will use regex-only extraction")
        return

    for lang, model_name in _SPACY_MODELS.items():
        try:
            _nlp_models[lang] = spacy.load(model_name, disable=["parser", "lemmatizer"])
            logger.info("spaCy model loaded: %s", model_name)
        except OSError:
            logger.debug("spaCy model %s not installed, skipping", model_name)

    if _nlp_models:
        logger.info("spaCy languages available: %s", ", ".join(sorted(_nlp_models)))
    else:
        logger.debug("No spaCy models found, will use regex-only extraction")


def _get_nlp(lang: str | None = None):
    """Get spaCy model for a language. Falls back to English, then any available model."""
    _load_models()
    if not _nlp_models:
        return None
    if lang and lang in _nlp_models:
        return _nlp_models[lang]
    # Fallback: English first, then first available
    return _nlp_models.get("en") or next(iter(_nlp_models.values()))


def is_spacy_available() -> bool:
    """Check if any spaCy model is available."""
    _load_models()
    return bool(_nlp_models)


def preload() -> None:
    """Force-load spaCy models now (instead of on first extraction call)."""
    _load_models()


def _normalize_person(text: str) -> str:
    """Normalize a person name for dedup."""
    # Strip titles/prefixes
    parts = text.strip().split()
    # Remove common titles
    titles = {"mr", "mrs", "ms", "dr", "prof", "sir", "dame", "herr", "frau", "hr", "fr"}
    cleaned = [p for p in parts if p.lower().rstrip(".") not in titles]
    return " ".join(cleaned).lower().strip() if cleaned else text.lower().strip()


def _normalize_entity(text: str, entity_type: str) -> str:
    """Normalize an entity for dedup based on type."""
    if entity_type == "person":
        return _normalize_person(text)
    return text.lower().strip()


def extract_spacy_entities(text: str, lang: str | None = None) -> list[ExtractedEntity]:
    """Extract entities using spaCy NER.

    Args:
        text: Text to extract entities from.
        lang: ISO 639-1 language code (e.g., "en", "de"). Auto-detects if None.

    Returns empty list if spaCy is not available.
    """
    nlp = _get_nlp(lang)
    if nlp is None:
        return []

    if not text or len(text.strip()) < 3:
        return []

    # Truncate very long texts to avoid memory issues
    max_chars = 100_000
    if len(text) > max_chars:
        text = text[:max_chars]

    doc = nlp(text)
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    for ent in doc.ents:
        spacy_label = ent.label_
        if spacy_label in _SPACY_SKIP_TYPES:
            continue
        our_type = _SPACY_TYPE_MAP.get(spacy_label)
        if our_type is None:
            continue

        ent_text = ent.text.strip()
        if not ent_text or len(ent_text) < 2:
            continue

        # Skip single-character or purely numeric entities
        if ent_text.isdigit():
            continue

        normalized = _normalize_entity(ent_text, our_type)
        key = (normalized, our_type)
        if key in seen:
            continue
        seen.add(key)

        entities.append(
            ExtractedEntity(
                text=ent_text,
                entity_type=our_type,
                normalized_form=normalized,
            )
        )

    return entities


def extract_nlp_entities(text: str, sender_email: str | None = None, lang: str | None = None) -> list[ExtractedEntity]:
    """Extract entities using spaCy NER + regex, with deduplication.

    Attempts spaCy first for PERSON, ORG, GPE, MONEY, EVENT entities.
    Always runs regex for URLs, phones, mentions, email addresses.
    Falls back to regex-only if spaCy is not available.

    Args:
        text: Email body text to extract entities from.
        sender_email: Sender email for organization-from-domain extraction.
        lang: ISO 639-1 language code (e.g., "en", "de"). Auto-detected if None.

    Returns:
        Deduplicated list of ExtractedEntity objects.
    """
    if not text:
        return []

    # Auto-detect language if not provided, with per-email text LRU cache.
    # Using a content-based cache key (hash of first 500 chars) instead of
    # sender_email avoids misclassification when a sender writes in multiple
    # languages across different emails.
    if lang is None and is_spacy_available():
        import hashlib as _hashlib

        text_prefix = text[:500] if text else ""
        cache_key = _hashlib.md5(text_prefix.encode(), usedforsecurity=False).hexdigest()
        if cache_key in _sender_lang_cache:
            _sender_lang_cache.move_to_end(cache_key)  # LRU: mark as recently used
            lang = _sender_lang_cache[cache_key]
        else:
            from .language_detector import detect_language

            lang = detect_language(text)
            if lang == "unknown":
                lang = None
            _sender_lang_cache[cache_key] = lang
            if len(_sender_lang_cache) > _LANG_CACHE_MAX:
                _sender_lang_cache.popitem(last=False)  # evict LRU entry

    # Always get regex entities (URLs, phones, mentions, emails, org-from-domain)
    regex_entities = extract_entities(text, sender_email)

    # Try spaCy for NLP entities
    spacy_entities = extract_spacy_entities(text, lang=lang)

    if not spacy_entities:
        return regex_entities

    # Merge: spaCy entities first, then regex entities, dedup by (normalized, type)
    merged: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    # spaCy entities take priority for overlapping types (e.g., organization)
    for entity in spacy_entities:
        key = (entity.normalized_form, entity.entity_type)
        if key not in seen:
            seen.add(key)
            merged.append(entity)

    # Regex entities fill in types spaCy doesn't cover (url, phone, mention, email)
    for entity in regex_entities:
        key = (entity.normalized_form, entity.entity_type)
        if key not in seen:
            seen.add(key)
            merged.append(entity)

    return merged


def reset_model_cache() -> None:
    """Reset the model cache (useful for testing)."""
    global _nlp_load_attempted
    _nlp_models.clear()
    _nlp_load_attempted = False
    _sender_lang_cache.clear()
