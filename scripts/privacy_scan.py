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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


def _term_union(terms: tuple[str, ...]) -> str:
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
    re.compile(r"(^|/)\.kilo/"),
    re.compile(r"(^|/)private/"),
    re.compile(r"(^|/)data/(chromadb|email_metadata\.db)"),
    re.compile(r"\.(olm|sqlite3|db|db-wal|db-shm)$", re.IGNORECASE),
)

UNTRACKED_FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.kilo/"),
    re.compile(r"(^|/)\.example/"),
    re.compile(r"(^|/)private/"),
    re.compile(r"(^|/)data/(chromadb|email_metadata\.db)"),
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
        r"\b(api[_-]?key|bearer\s+[A-Z0-9._-]+|meeting-id\s*[:=]|pwd=|zoom\.us|kenncode\s*[:=]|passcode\s*[:=])",
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
    "outlook_email_rag.egg-info/",
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
    category: str
    path: str


def _run_git(args: list[str], *, check: bool = True) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _run_git_bytes(args: list[str], *, check: bool = True) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        capture_output=True,
    )
    return completed.stdout


def _tracked_paths() -> list[str]:
    return _run_git(["ls-files"])


def _untracked_paths() -> list[str]:
    return _run_git(["ls-files", "--others", "--exclude-standard"])


def _history_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "log", "--all", "--name-only", "--pretty=format:"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted({line for line in completed.stdout.splitlines() if line})


def _history_blobs() -> list[tuple[str, str]]:
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
    return any(pattern.search(path) for pattern in patterns)


def _is_text_scan_path_candidate(path: str) -> bool:
    if path in TEXT_EXEMPT_PATHS:
        return False
    if path.startswith(TEXT_EXEMPT_PREFIXES):
        return False
    return not path.lower().endswith(TEXT_EXEMPT_SUFFIXES)


def _is_text_scan_candidate(path: str) -> bool:
    if not _is_text_scan_path_candidate(path):
        return False
    file_path = REPO_ROOT / path
    return file_path.is_file()


def _scan_text(paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if not _is_text_scan_candidate(path):
            continue
        try:
            text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for category, pattern in TEXT_PATTERNS.items():
            if pattern.search(text):
                findings.append(Finding(category, path))
    return findings


def _scan_history_text() -> list[Finding]:
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
    findings: list[Finding] = []
    tracked = _tracked_paths()
    for path in tracked:
        if _path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS):
            findings.append(Finding("tracked-forbidden-path", path))
    findings.extend(_scan_text(tracked))

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
