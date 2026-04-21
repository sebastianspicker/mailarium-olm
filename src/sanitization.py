"""Shared text sanitization helpers for untrusted output."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
OSC_ESCAPE_RE = re.compile(r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:(?:\+|00)\d[\d\s()./-]{6,}\d|\b\d{3,}[\d\s()./-]{4,}\d\b)")
# Unicode bidirectional override/embedding codepoints.  Malicious emails
# use these to visually reorder text (e.g. making "evil.exe" appear as
# "exe.live"), which could mislead both human readers and LLM consumers.
DISALLOWED_BIDI_CODEPOINTS = {
    0x061C,  # Arabic Letter Mark
    0x200E,  # Left-to-Right Mark
    0x200F,  # Right-to-Left Mark
    0x202A,  # Left-to-Right Embedding
    0x202B,  # Right-to-Left Embedding
    0x202C,  # Pop Directional Formatting
    0x202D,  # Left-to-Right Override
    0x202E,  # Right-to-Left Override
    0x2066,  # Left-to-Right Isolate
    0x2067,  # Right-to-Left Isolate
    0x2068,  # First Strong Isolate
    0x2069,  # Pop Directional Isolate
}
PRIVACY_MODE_RULES: dict[str, dict[str, Any]] = {
    "full_access": {
        "audience": "internal_case_team",
        "description": "Full internal review mode with no privacy redaction beyond terminal sanitization.",
        "redact_contact": False,
        "redact_privileged": False,
        "redact_medical": False,
        "redact_structured_identity": False,
    },
    "external_counsel_export": {
        "audience": "external_counsel",
        "description": "Least-exposure export for counsel handoff while preserving factual and medical context.",
        "redact_contact": True,
        "redact_privileged": False,
        "redact_medical": False,
        "redact_structured_identity": False,
    },
    "internal_complaint_use": {
        "audience": "internal_complaint_channel",
        "description": "Redacted complaint-facing mode that suppresses privileged and medical-detail exposure.",
        "redact_contact": True,
        "redact_privileged": True,
        "redact_medical": True,
        "redact_structured_identity": False,
    },
    "witness_sharing": {
        "audience": "limited_circulation_witness",
        "description": "High-redaction mode for limited witness circulation and least-exposure review.",
        "redact_contact": True,
        "redact_privileged": True,
        "redact_medical": True,
        "redact_structured_identity": True,
    },
}
STRUCTURED_IDENTITY_KEYS = frozenset(
    {
        "name",
        "display_name",
        "display_names",
        "sender_or_author",
        "recipients",
        "participants",
        "primary_email",
        "email",
        "sender_email",
    }
)
PRIVILEGED_TERMS = (
    "privileged",
    "attorney-client",
    "counsel",
    "legal strategy",
    "litigation strategy",
    "counsel memo",
    "work product",
)
MEDICAL_TERMS = (
    "medical",
    "diagnosis",
    "doctor",
    "physician",
    "therap",
    "krank",
    "disability",
    "behinderung",
    "schwerbehind",
    "betriebsarzt",
    "medical recommendation",
)


def sanitize_untrusted_text(value: str) -> str:
    """Strip ANSI/OSC escapes and unsafe control chars from untrusted text."""
    no_osc = OSC_ESCAPE_RE.sub("", value)
    no_ansi = ANSI_ESCAPE_RE.sub("", no_osc)
    no_esc = no_ansi.replace("\x1b", "")
    return "".join(
        ch
        for ch in no_esc
        if (ch in "\n\t" or (0x20 <= ord(ch) <= 0x7E) or ord(ch) >= 0xA0) and ord(ch) not in DISALLOWED_BIDI_CODEPOINTS
    )


def resolve_privacy_mode(mode: str | None) -> str:
    """Return a supported privacy mode, defaulting to full access."""
    normalized = str(mode or "full_access").strip().lower()
    if normalized not in PRIVACY_MODE_RULES:
        raise ValueError("Unsupported privacy mode. Use one of: " + ", ".join(sorted(PRIVACY_MODE_RULES)))
    return normalized


def privacy_mode_policy(mode: str | None) -> dict[str, Any]:
    """Return structured privacy policy metadata for one output mode."""
    normalized = resolve_privacy_mode(mode)
    rules = PRIVACY_MODE_RULES[normalized]
    return {
        "privacy_mode": normalized,
        "audience": str(rules["audience"]),
        "description": str(rules["description"]),
        "least_exposure_rules": [
            rule
            for rule in (
                "Redact direct contact data in outward redacted modes." if rules["redact_contact"] else "",
                "Suppress privileged/legal-strategy text in this mode." if rules["redact_privileged"] else "",
                "Suppress sensitive medical detail in this mode." if rules["redact_medical"] else "",
                "Suppress structured participant identity fields in this mode." if rules["redact_structured_identity"] else "",
            )
            if rule
        ],
    }


def _path_has_identity_key(path: tuple[Any, ...]) -> bool:
    return any(isinstance(item, str) and item in STRUCTURED_IDENTITY_KEYS for item in path)


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _redact_string(
    value: str,
    *,
    mode: str,
    path: tuple[Any, ...],
    counters: Counter[str],
) -> str:
    """Redact one string according to the configured privacy mode."""
    clean = sanitize_untrusted_text(value)
    rules = PRIVACY_MODE_RULES[mode]
    if not clean:
        return clean

    if rules["redact_structured_identity"] and _path_has_identity_key(path):
        counters["structured_identity"] += 1
        return "[REDACTED: participant_identity]"

    if rules["redact_privileged"] and _contains_any_term(clean, PRIVILEGED_TERMS):
        counters["privileged"] += 1
        return "[REDACTED: privileged_content]"

    if rules["redact_medical"] and _contains_any_term(clean, MEDICAL_TERMS):
        counters["medical"] += 1
        return "[REDACTED: sensitive_medical_content]"

    redacted = clean
    if rules["redact_contact"]:
        updated = EMAIL_RE.sub("[REDACTED: email]", redacted)
        if updated != redacted:
            counters["contact"] += 1
        redacted = updated
        updated = PHONE_RE.sub("[REDACTED: phone]", redacted)
        if updated != redacted:
            counters["contact"] += 1
        redacted = updated
    return redacted


def _redact_value(value: Any, *, mode: str, path: tuple[Any, ...], counters: Counter[str]) -> Any:
    if isinstance(value, str):
        return _redact_string(value, mode=mode, path=path, counters=counters)
    if isinstance(value, list):
        return [_redact_value(item, mode=mode, path=(*path, index), counters=counters) for index, item in enumerate(value)]
    if isinstance(value, dict):
        return {key: _redact_value(item, mode=mode, path=(*path, key), counters=counters) for key, item in value.items()}
    return value


def apply_privacy_guardrails(payload: Any, *, privacy_mode: str | None) -> tuple[Any, dict[str, Any]]:
    """Return a privacy-processed payload plus structured guardrail metadata."""
    mode = resolve_privacy_mode(privacy_mode)
    counters: Counter[str] = Counter()
    redacted_payload = _redact_value(payload, mode=mode, path=(), counters=counters)
    policy = privacy_mode_policy(mode)
    guardrails = {
        "privacy_mode": mode,
        "audience": policy["audience"],
        "description": policy["description"],
        "least_exposure_rules": policy["least_exposure_rules"],
        "redaction_summary": {
            "redaction_applied": mode != "full_access" and bool(counters),
            "category_counts": {
                "contact": int(counters.get("contact", 0)),
                "medical": int(counters.get("medical", 0)),
                "privileged": int(counters.get("privileged", 0)),
                "structured_identity": int(counters.get("structured_identity", 0)),
            },
        },
    }
    return redacted_payload, guardrails
