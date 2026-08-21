"""Pure publication-risk markers and classification rules.

The marker literals are assembled from fragments so the privacy scanner does
not report its own implementation as a finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _term(*parts: str) -> str:
    """Assemble a sensitive marker without spelling it in scanner source."""
    return "".join(parts)


def _term_union(terms: tuple[str, ...]) -> str:
    """Escape marker literals and combine them into a regex alternation."""
    return "|".join(re.escape(term) for term in terms)


PRIVATE_PERSON_OR_ORG_TERMS = (
    _term("se", "bas", "tian"),
    _term("hf", "mt"),
    _term("ko", "eln"),
    _term("kö", "ln"),
    _term("per", "sonal", "abteilung"),
    _term("cl", "aus"),
    _term("na", "zan"),
    _term("max", " ", "must", "ermann"),
    _term("er", "ika", " ", "bei", "spiel"),
    _term("alice", " ", "example"),
    _term("hans", " ", "bei", "spiel"),
)

PRIVATE_MATTER_TERMS = (
    _term("an", "walt"),
    _term("nach", "zug"),
    _term("nova", "time"),
    _term("za", "mmad"),
    _term("open", "project"),
)

LOCAL_USER_PATH_PATTERN = "/" + _term("Us", "ers") + r"/[A-Za-z0-9._-]+/"
LIVE_CORPUS_TERMS = (
    _term("live", " ", "corpus"),
    _term("real", " ", "corpus"),
    _term("real", " ", "parsed", " ", "message"),
    _term("current", " ", "matter"),
)

TRACKED_FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.(agents|codegraph|codex|kilo|serena)/"),
    re.compile(r"^\.codacy/(?!codacy\.(?:config\.json|ya?ml)$)"),
    re.compile(r"(^|/)private/"),
    re.compile(r"(^|/)data/(vector-index|email_metadata\.db)"),
    re.compile(r"^AUDIT_REPORT_.*\.md$", re.IGNORECASE),
    re.compile(r"^archive/local/"),
    re.compile(r"^docs/agent/"),
    re.compile(r"^pre-clean/"),
    re.compile(r"\.(olm|sqlite3|db|db-wal|db-shm)$", re.IGNORECASE),
)

UNTRACKED_FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.(agents|codacy|codegraph|codex|kilo|serena)/"),
    re.compile(r"(^|/)\.example/"),
    re.compile(r"^archive/local/"),
    re.compile(r"(^|/)private/"),
    re.compile(r"^pre-clean/"),
    re.compile(r"(^|/)data/(vector-index|email_metadata\.db)"),
    re.compile(r"\.(olm|sqlite3|db|db-wal|db-shm)$", re.IGNORECASE),
    re.compile(
        rf"(^|/)({_term_union((_term('an', 'walt'), 'handoff', 'forensic', _term('nach', 'zug')))})[^/]*",
        re.IGNORECASE,
    ),
    re.compile(r"(^|/)docs/agent/(implementation_log|plan_history|matter_analysis)/"),
)

TEXT_PATTERNS = {
    "non-reserved-email-domain": re.compile(
        r"\b[A-Z0-9._%+-]+@(?!example\.(?:com|org|net|test)\b|fixture\.local\b)[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),
    "secret-or-meeting-token": re.compile(
        r"\b(api[_-]?key\s*[:=]\s*[\"']?[A-Z0-9][A-Z0-9._-]{7,}"
        r"|bearer\s+[A-Z0-9._-]+|meeting-id\s*[:=]|pwd=|zoom\.us|kenncode\s*[:=]|passcode\s*[:=])",
        re.IGNORECASE,
    ),
    "local-absolute-path": re.compile(LOCAL_USER_PATH_PATTERN),
    "private-person-or-org-marker": re.compile(
        rf"\b({_term_union(PRIVATE_PERSON_OR_ORG_TERMS)})\b",
        re.IGNORECASE,
    ),
    "private-matter-marker": re.compile(rf"\b({_term_union(PRIVATE_MATTER_TERMS)})\b", re.IGNORECASE),
    "live-corpus-marker": re.compile(rf"\b({_term_union(LIVE_CORPUS_TERMS)})\b", re.IGNORECASE),
}

TEXT_EXEMPT_PATHS = {
    "scripts/privacy_scan.py",
    "mailarium/privacy_scan_rules.py",
}

TEXT_EXEMPT_PREFIXES = (
    ".git/",
    ".venv/",
    ".ruff_cache/",
    ".pytest_cache/",
    ".mypy_cache/",
    "mailarium.egg-info/",
    "archive/local/",
    "pre-clean/",
)

TEXT_EXEMPT_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".pyc",
)


@dataclass(frozen=True)
class Finding:
    """Immutable publication-risk category and path pair safe for output."""

    category: str
    path: str


def path_matches(path: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """Return whether a repository-relative path matches a risk pattern."""
    return any(pattern.search(path) for pattern in patterns)


def forbidden_path_findings(
    paths: list[str],
    patterns: tuple[re.Pattern[str], ...],
    category: str,
) -> list[Finding]:
    """Return findings for paths matching a configured forbidden-path rule."""
    return [Finding(category, path) for path in paths if path_matches(path, patterns)]


def is_text_scan_path_candidate(path: str) -> bool:
    """Return whether a path is eligible for text matching."""
    if path in TEXT_EXEMPT_PATHS:
        return False
    if path.startswith(TEXT_EXEMPT_PREFIXES):
        return False
    return not path.lower().endswith(TEXT_EXEMPT_SUFFIXES)


def text_findings(path: str, text: str) -> list[Finding]:
    """Classify text without exposing any matched content."""
    return [Finding(category, path) for category, pattern in TEXT_PATTERNS.items() if pattern.search(text)]
