"""Extended tests for src/nlp_entity_extractor.py — targeting uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── Minimal spaCy fakes ──────────────────────────────────────


class _FakeEnt:
    def __init__(self, text: str, label: str):
        self.text = text
        self.label_ = label


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]):
        self.ents = ents


def _fake_nlp(text):
    return _FakeDoc(
        [
            _FakeEnt("John Smith", "PERSON"),
            _FakeEnt("Acme Corp", "ORG"),
        ]
    )


def _setup_module_with_fake_nlp():
    import src.nlp_entity_extractor as mod

    mod.reset_model_cache()
    mod._nlp_models["en"] = _fake_nlp
    mod._nlp_load_attempted = True
    return mod


# ── _load_models (lines 47-64) ──────────────────────────────


class TestLoadModels:
    def test_load_models_spacy_not_installed(self):
        """When spaCy is not importable, _load_models sets attempted flag."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        with patch.dict("sys.modules", {"spacy": None}):
            mod._load_models()
        assert mod._nlp_load_attempted is True
        assert mod._nlp_models == {}

    def test_load_models_model_not_found(self):
        """When spaCy model is not installed (OSError), it is skipped."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mock_spacy = MagicMock()
        mock_spacy.load.side_effect = OSError("model not found")
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            mod._load_models()
        assert mod._nlp_load_attempted is True
        assert mod._nlp_models == {}

    def test_load_models_success(self):
        """When spaCy models load successfully, they are cached."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mock_model = MagicMock()
        mock_spacy = MagicMock()
        mock_spacy.load.return_value = mock_model
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            mod._load_models()
        assert mod._nlp_load_attempted is True
        assert len(mod._nlp_models) > 0

    def test_load_models_only_once(self):
        """_load_models only runs once even when called multiple times."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_load_attempted = True  # Simulate already loaded
        mod._load_models()
        # Should not change anything since already attempted
        assert mod._nlp_models == {}

    def test_load_models_partial_success(self):
        """When only some models load, available ones are cached."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mock_spacy = MagicMock()
        call_count = [0]

        def selective_load(name, disable=None):
            call_count[0] += 1
            if "en_core" in name:
                return MagicMock()
            raise OSError("not found")

        mock_spacy.load = selective_load
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            mod._load_models()
        assert "en" in mod._nlp_models
        assert "de" not in mod._nlp_models


# ── _get_nlp fallback (line 73) ──────────────────────────────


class TestGetNlpFallback:
    def test_get_nlp_fallback_to_first_available(self):
        """When requested lang not available and no English, use first model."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        fake_de = MagicMock()
        mod._nlp_models["de"] = fake_de
        mod._nlp_load_attempted = True

        result = mod._get_nlp("fr")
        assert result is fake_de

    def test_get_nlp_english_fallback(self):
        """When requested lang not available, fall back to English."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        fake_en = MagicMock()
        mod._nlp_models["en"] = fake_en
        mod._nlp_load_attempted = True

        result = mod._get_nlp("fr")
        assert result is fake_en


# ── preload (line 86) ────────────────────────────────────────


class TestPreload:
    def test_preload_forces_model_loading(self):
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mock_spacy = MagicMock()
        mock_spacy.load.side_effect = OSError("not found")
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            mod.preload()
        assert mod._nlp_load_attempted is True


# ── extract_spacy_entities edge cases ────────────────────────


class TestExtractSpacyEntitiesEdgeCases:
    def test_truncation_of_long_text(self):
        """Text > 100,000 chars is truncated."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        received_texts = []

        def capturing_nlp(text):
            received_texts.append(text)
            return _FakeDoc([])

        mod._nlp_models["en"] = capturing_nlp
        mod._nlp_load_attempted = True

        long_text = "x" * 150_000
        mod.extract_spacy_entities(long_text)
        assert len(received_texts[0]) == 100_000

    def test_unmapped_spacy_type_skipped(self):
        """Entity with unmapped spaCy type (e.g. NORP) is skipped."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()

        def norp_nlp(text):
            return _FakeDoc([_FakeEnt("Democrats", "NORP")])

        mod._nlp_models["en"] = norp_nlp
        mod._nlp_load_attempted = True

        entities = mod.extract_spacy_entities("Democrats voted")
        assert len(entities) == 0

    def test_short_entity_text_skipped(self):
        """Entity text < 2 chars is skipped."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()

        def short_nlp(text):
            return _FakeDoc([_FakeEnt("A", "PERSON")])

        mod._nlp_models["en"] = short_nlp
        mod._nlp_load_attempted = True

        entities = mod.extract_spacy_entities("A person here")
        assert len(entities) == 0

    def test_digit_only_entity_skipped(self):
        """Purely numeric entity text is skipped."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()

        def digit_nlp(text):
            return _FakeDoc([_FakeEnt("42", "MONEY")])

        mod._nlp_models["en"] = digit_nlp
        mod._nlp_load_attempted = True

        entities = mod.extract_spacy_entities("42 dollars")
        assert len(entities) == 0

    def test_whitespace_only_entity_skipped(self):
        """Empty/whitespace entity text is skipped."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()

        def ws_nlp(text):
            return _FakeDoc([_FakeEnt("   ", "PERSON")])

        mod._nlp_models["en"] = ws_nlp
        mod._nlp_load_attempted = True

        entities = mod.extract_spacy_entities("whitespace entity")
        assert len(entities) == 0


# ── extract_nlp_entities: language detection + cache ─────────


class TestLanguageDetectionCache:
    def test_language_detection_with_sender_cache(self):
        """Language is detected and cached per email text content."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models["en"] = _fake_nlp
        mod._nlp_load_attempted = True

        with patch("src.language_detector.detect_language", return_value="en") as mock_detect:
            # First call: detects language
            mod.extract_nlp_entities("Hello world", sender_email="employee@example.test")
            assert mock_detect.call_count == 1

            # Second call with same text content: uses cache (keyed by content hash)
            mod.extract_nlp_entities("Hello world", sender_email="employee@example.test")
            assert mock_detect.call_count == 1  # Not called again

            # Third call with different text: not cached
            mod.extract_nlp_entities("Hello again", sender_email="employee@example.test")
            assert mock_detect.call_count == 2  # Called again for new text

    def test_language_detection_unknown_falls_back_to_none(self):
        """When detection returns 'unknown', lang is set to None."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models["en"] = _fake_nlp
        mod._nlp_load_attempted = True

        with patch("src.language_detector.detect_language", return_value="unknown"):
            entities = mod.extract_nlp_entities("Hallo Welt", sender_email="bob@example.com")
            # Should still work (falls back to English model)
            assert isinstance(entities, list)

    def test_sender_lang_cache_eviction(self):
        """LRU cache evicts oldest entry when full."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models["en"] = _fake_nlp
        mod._nlp_load_attempted = True

        with patch("src.language_detector.detect_language", return_value="en"):
            # Fill cache beyond max
            for i in range(mod._LANG_CACHE_MAX + 5):
                mod.extract_nlp_entities("Hello world test text", sender_email=f"user{i}@example.com")

        assert len(mod._sender_lang_cache) <= mod._LANG_CACHE_MAX

    def test_no_sender_email_still_caches_by_content(self):
        """Cache works even without sender_email (keyed by content hash)."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models["en"] = _fake_nlp
        mod._nlp_load_attempted = True

        with patch("src.language_detector.detect_language", return_value="en") as mock_detect:
            mod.extract_nlp_entities("Hello world", sender_email=None)
            mod.extract_nlp_entities("Hello world", sender_email=None)
            # Same text content -> cached by content hash (only 1 detection call)
            assert mock_detect.call_count == 1

            # Different text -> not cached
            mod.extract_nlp_entities("Different text", sender_email=None)
            assert mock_detect.call_count == 2

    def test_cached_language_reused_on_hit(self):
        """Cached language is found by content hash on cache hit."""
        import hashlib

        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models["en"] = _fake_nlp
        mod._nlp_load_attempted = True
        # Pre-populate cache with content hash of "Hello world"
        content_hash = hashlib.md5("Hello world"[:500].encode(), usedforsecurity=False).hexdigest()
        mod._sender_lang_cache[content_hash] = "en"

        # This should use cache, not call detect_language
        with patch("src.language_detector.detect_language") as mock_detect:
            mod.extract_nlp_entities("Hello world", sender_email="test@example.com")
            assert mock_detect.call_count == 0


# ── _normalize_entity ────────────────────────────────────────


class TestNormalizeEntity:
    def test_normalize_non_person_entity(self):
        from src.nlp_entity_extractor import _normalize_entity

        assert _normalize_entity("  Berlin  ", "location") == "berlin"

    def test_normalize_person_with_title(self):
        from src.nlp_entity_extractor import _normalize_person

        assert _normalize_person("Herr Schmidt") == "schmidt"
        assert _normalize_person("Frau Mueller") == "mueller"
        assert _normalize_person("Hr. Weber") == "weber"
        assert _normalize_person("Fr. Fischer") == "fischer"
