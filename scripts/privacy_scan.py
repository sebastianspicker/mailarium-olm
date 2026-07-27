#!/usr/bin/env python3
"""Scan the repository for publication-risk private artifacts.

The scanner intentionally reports categories and paths only. It never prints
matching source text, because the scanner itself is used while cleaning private
research copies.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_GIT_PATH = shutil.which("git") or "git"


def _term(*parts: str) -> str:
    """Assemble sensitive marker literals from fragments so the scanner does not self-match them."""
    return "".join(parts)


def _term_union(terms: tuple[str, ...]) -> str:
    """Escape marker literals and combine them into a safe regular-expression alternation."""
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

QA_EVAL_FIXTURE_PREFIX = "tests/fixtures/qa_eval/"
QA_EVAL_PROVENANCE_PATTERN = re.compile(
    r"\b(?:"
    r"live(?:\s+eval)?\s+(?:corpus|mailbox|message|conversation|thread|fixture|run)"
    r"|real\s+(?:archive|attachment|conversation|corpus|email|fixture|forwarded|image|mail|message|scan|source-shell|thread)"
    r")\b",
    re.IGNORECASE,
)


TRACKED_FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.(agents|codacy|codegraph|codex|kilo|serena)/"),
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
    "tests/test_repo_contracts.py",
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
    """Immutable publication-risk category and path pair safe for user-visible output."""

    category: str
    path: str


def _run_git(args: list[str], *, check: bool = True) -> list[str]:
    """Run a text-mode Git query at the repository root and discard blank output lines."""
    completed = subprocess.run(  # nosemgrep
        [_GIT_PATH, *args],
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _run_git_bytes(args: list[str], *, check: bool = True) -> bytes:
    """Run a binary-safe Git query for index or historical blob contents."""
    completed = subprocess.run(  # nosemgrep
        [_GIT_PATH, *args],
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
    )
    return completed.stdout


def _tracked_paths() -> list[str]:
    """Enumerate paths represented in Git's current index."""
    return _run_git(["ls-files"])


def _untracked_paths() -> list[str]:
    """Enumerate unignored worktree paths absent from Git's index."""
    return _run_git(["ls-files", "--others", "--exclude-standard"])


def _history_paths() -> list[str]:
    """Enumerate every non-empty path recorded across all Git refs."""
    completed = subprocess.run(  # nosemgrep
        [_GIT_PATH, "log", "--all", "--name-only", "--pretty=format:"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted({line for line in completed.stdout.splitlines() if line})


def _history_blobs() -> list[tuple[str, str]]:
    """Map unique historical blob hashes to each path that referenced their contents."""
    blob_paths: dict[tuple[str, str], None] = {}
    for commit in _run_git(["rev-list", "--all"]):
        for record in _run_git_bytes(["ls-tree", "-rz", commit]).split(b"\0"):
            line = record.decode("utf-8", errors="ignore")
            if not line:
                continue
            try:
                meta, path = line.split("\t", 1)
                _mode, kind, blob_hash = meta.split(" ", 2)
            except ValueError:
                continue
            if kind != "blob":
                continue
            blob_paths[(blob_hash, path)] = None
    return sorted(blob_paths)


def _path_matches(path: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """Apply the configured path-risk patterns to one repository-relative path."""
    return any(pattern.search(path) for pattern in patterns)


def _is_text_scan_path_candidate(path: str) -> bool:
    """Exclude scanner sources, tool caches, and binary suffixes from content matching."""
    if path in TEXT_EXEMPT_PATHS:
        return False
    if path.startswith(TEXT_EXEMPT_PREFIXES):
        return False
    return not path.lower().endswith(TEXT_EXEMPT_SUFFIXES)


def _scan_text(paths: list[str], *, index_fallback: bool = False) -> list[Finding]:
    """Scan eligible files or index fallbacks for publication risks without returning matched content."""
    findings: list[Finding] = []
    for path in paths:
        if not _is_text_scan_path_candidate(path):
            continue
        try:
            text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            if not index_fallback:
                continue
            text = _run_git_bytes(["show", f":{path}"], check=False).decode("utf-8", errors="ignore")
        except OSError:
            # Publication scanning is fail-closed: an unreadable candidate file
            # has unknown contents and therefore cannot be treated as clean.
            findings.append(Finding("unreadable-candidate-file", path))
            continue
        for category, pattern in TEXT_PATTERNS.items():
            if pattern.search(text):
                findings.append(Finding(category, path))
        if path.startswith(QA_EVAL_FIXTURE_PREFIX) and QA_EVAL_PROVENANCE_PATTERN.search(text):
            findings.append(Finding("non-synthetic-qa-provenance", path))
    return findings


def _scan_history_text() -> list[Finding]:
    """Scan each historical blob once and associate risk categories with every path that referenced it."""
    findings: list[Finding] = []
    scanned_blob_hashes: set[str] = set()
    blob_matches: dict[str, set[str]] = {}
    for blob_hash, path in _history_blobs():
        if not _is_text_scan_path_candidate(path):
            continue
        if blob_hash not in scanned_blob_hashes:
            scanned_blob_hashes.add(blob_hash)
            blob_bytes = _run_git_bytes(["cat-file", "-p", blob_hash], check=False)
            text = blob_bytes.decode("utf-8", errors="ignore")
            blob_matches[blob_hash] = {category for category, pattern in TEXT_PATTERNS.items() if pattern.search(text)}
        for category in blob_matches.get(blob_hash, set()):
            findings.append(Finding(f"history-{category}", path))
    return findings


def scan(*, include_untracked: bool = True, include_history: bool = False) -> list[Finding]:
    """Combine tracked, untracked, and optional history findings into a stable deduplicated risk list."""
    findings: list[Finding] = []
    tracked = _tracked_paths()
    for path in tracked:
        if _path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS):
            findings.append(Finding("tracked-forbidden-path", path))
    findings.extend(_scan_text(tracked, index_fallback=True))

    if include_untracked:
        untracked = _untracked_paths()
        for path in untracked:
            if _path_matches(path, UNTRACKED_FORBIDDEN_PATH_PATTERNS):
                findings.append(Finding("untracked-private-artifact", path))
        findings.extend(Finding(f"untracked-{finding.category}", finding.path) for finding in _scan_text(untracked))

    if include_history:
        for path in _history_paths():
            if _path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS):
                findings.append(Finding("history-risk-path", path))
        findings.extend(_scan_history_text())

    return sorted(set(findings), key=lambda item: (item.category, item.path))


def main(argv: list[str] | None = None) -> int:
    """Select scan scope, emit category-and-path findings as text or JSON, and fail when risks remain."""
    parser = argparse.ArgumentParser(description="Scan for publication-risk private artifacts without printing secrets.")
    parser.add_argument("--tracked-only", action="store_true", help="Only scan tracked files.")
    parser.add_argument("--include-history", action="store_true", help="Also report risky paths seen in git history.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    findings = scan(include_untracked=not args.tracked_only, include_history=args.include_history)
    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(f"{finding.category}\t{finding.path}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
