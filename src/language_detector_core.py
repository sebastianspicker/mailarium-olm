"""Core helpers for the lightweight language detector."""

from __future__ import annotations

from collections import Counter

from .language_detector_data import STOPWORDS, TOKEN_RE

_GERMAN_MARKERS = {
    "bitte",
    "danke",
    "grüßen",
    "grues",
    "rückmeldung",
    "rueckmeldung",
    "prävention",
    "praevention",
    "arbeitszeit",
    "zeiterfassung",
    "eingruppierung",
    "vereinbarung",
    "kündigung",
    "kuendigung",
    "mitteilung",
    "kollegin",
    "kollege",
    "abwesenheit",
    "genehmigung",
    "besprechung",
    "protokoll",
    "einladung",
}
_FORWARD_PREFIX_TOKENS = {"wg", "aw", "fw", "fwd", "re"}


def _marker_hits(tokens: list[str], *, language: str) -> int:
    if language != "de":
        return 0
    return sum(1 for token in tokens if token in _GERMAN_MARKERS)


def _special_character_bias(text: str) -> dict[str, float]:
    lowered = text.casefold()
    german_bias = 0.0
    if any(char in lowered for char in ("ä", "ö", "ü", "ß")):
        german_bias += 0.025
    if any(token in lowered for token in (" wg:", " aw:", " rück", " prä", " grü")):
        german_bias += 0.015
    return {"de": german_bias}


def tokenize_impl(text: str) -> list[str]:
    """Simple word tokenizer: lowercase, split on non-alpha."""
    tokens = TOKEN_RE.findall(text.lower())
    normalized: list[str] = []
    for token in tokens:
        compact = token.strip()
        if compact in _FORWARD_PREFIX_TOKENS:
            continue
        normalized.append(compact)
    return normalized


def score_languages_impl(tokens: list[str], *, original_text: str = "") -> dict[str, float]:
    """Return normalized stopword-overlap scores for each supported language."""
    token_counts = Counter(tokens)
    total_tokens = len(tokens)
    scores = {
        lang: (sum(token_counts[word] for word in stopwords if word in token_counts) / total_tokens if total_tokens else 0.0)
        for lang, stopwords in STOPWORDS.items()
    }
    marker_hits = {lang: _marker_hits(tokens, language=lang) for lang in STOPWORDS}
    biases = _special_character_bias(original_text)
    for lang, hits in marker_hits.items():
        if hits:
            scores[lang] = float(scores.get(lang, 0.0)) + min(0.06, hits * 0.015)
    for lang, bias in biases.items():
        scores[lang] = float(scores.get(lang, 0.0)) + float(bias)
    return scores


def language_hit_counts_impl(tokens: list[str]) -> dict[str, int]:
    """Return raw stopword hit counts for each supported language."""
    token_counts = Counter(tokens)
    return {lang: sum(token_counts[word] for word in stopwords if word in token_counts) for lang, stopwords in STOPWORDS.items()}


def detect_language_details_impl(text: str) -> dict[str, str | float | int]:
    """Return language plus lightweight confidence metadata."""
    tokens = tokenize_impl(text)
    token_count = len(tokens)
    if token_count == 0:
        return {"language": "unknown", "confidence": "none", "reason": "empty_text", "token_count": 0}

    scores = score_languages_impl(tokens, original_text=text)
    ranked_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_lang, best_score = ranked_scores[0] if ranked_scores else ("unknown", 0.0)
    second_score = ranked_scores[1][1] if len(ranked_scores) > 1 else 0.0
    german_marker_hits = _marker_hits(tokens, language="de")

    if token_count < 5:
        if german_marker_hits > 0:
            return {
                "language": "de",
                "confidence": "low",
                "reason": "short_text_german_marker",
                "token_count": token_count,
            }
        if best_score <= 0 or best_score == second_score:
            return {
                "language": "unknown",
                "confidence": "none",
                "reason": "short_text_insufficient_signal",
                "token_count": token_count,
            }
        return {
            "language": best_lang,
            "confidence": "low",
            "reason": "short_text_stopword_vote",
            "token_count": token_count,
        }

    best_score = float(best_score)
    if best_score < 0.02:
        if german_marker_hits > 0:
            return {
                "language": "de",
                "confidence": "low",
                "reason": "german_marker_bias",
                "token_count": token_count,
                "score": float(scores.get("de", 0.0)),
            }
        return {
            "language": "unknown",
            "confidence": "none",
            "reason": "score_below_threshold",
            "token_count": token_count,
        }

    confidence = "high" if best_score >= 0.08 else "medium"
    if best_lang == "de" and german_marker_hits > 0 and confidence == "medium":
        confidence = "high"
    return {
        "language": best_lang,
        "confidence": confidence,
        "reason": "stopword_overlap_with_markers" if german_marker_hits > 0 and best_lang == "de" else "stopword_overlap",
        "token_count": token_count,
        "score": best_score,
    }


def detect_language_impl(text: str) -> str:
    """Detect the language of the given text."""
    details = detect_language_details_impl(text)
    return str(details.get("language") or "unknown")
