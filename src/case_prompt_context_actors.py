"""Actor and mailbox extraction helpers for preserved matter context."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_EMAIL_RE = re.compile(r"(?i)\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b")
_NATURAL_PERSONS_RE = re.compile(r"(?im)^\s*[-*]\s*natural persons:\s*(.+)$")
_FUNCTIONAL_ACTORS_RE = re.compile(r"(?im)^\s*[-*]\s*functional actors and surfaces:\s*(.+)$")
_INSTITUTIONAL_ACTORS_SECTION_RE = re.compile(
    r"(?ims)^\s{0,3}#{1,6}\s+Institutional Actors and Mailbox Surfaces\s*$\n(?P<body>.*?)(?=^\s{0,3}#{1,6}\s+|\Z)"
)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _identifier_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^a-z0-9]+", _ascii_fold(value).lower()) if token)


def best_matching_email(name: str, emails: list[str]) -> str | None:
    """Return the best explicit email match for one name, or ``None`` when ambiguous."""
    name_tokens = _identifier_tokens(name)
    if not name_tokens:
        return None
    best_email: str | None = None
    best_score = 0
    tied = False
    name_token_set = set(name_tokens)
    for email in emails:
        local_tokens = _identifier_tokens(str(email).split("@", 1)[0])
        if not local_tokens:
            continue
        local_token_set = set(local_tokens)
        score = 0
        if tuple(local_tokens) == tuple(name_tokens):
            score = 100
        elif name_token_set and name_token_set.issubset(local_token_set):
            score = 90
        else:
            overlap = len(name_token_set & local_token_set)
            if overlap == 0:
                continue
            if name_tokens[-1] in local_token_set:
                score += 40
            if name_tokens[0] in local_token_set:
                score += 30
            score += overlap * 10
        if score > best_score:
            best_email = email
            best_score = score
            tied = False
        elif score == best_score and score > 0:
            tied = True
    if tied or best_score < 50:
        return None
    return best_email


def _normalized_name_key(name: str) -> str:
    return " ".join(_identifier_tokens(name))


def _clean_markdown_atom(value: str) -> str:
    return _compact(str(value or "").replace("`", "").strip().strip("|"))


def _split_inline_items(value: str) -> list[str]:
    return [
        _compact(item.replace("`", "").strip().strip("-.:;"))
        for item in re.split(r",|;", str(value or ""))
        if _compact(item.replace("`", "").strip().strip("-.:;"))
    ]


def _natural_person_names_from_context(context_text: str) -> list[str]:
    names: list[str] = []
    for match in _NATURAL_PERSONS_RE.finditer(context_text):
        names.extend(_split_inline_items(match.group(1)))
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = _normalized_name_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped


def _functional_actor_labels_from_context(context_text: str) -> list[str]:
    labels: list[str] = []
    for match in _FUNCTIONAL_ACTORS_RE.finditer(context_text):
        labels.extend(_split_inline_items(match.group(1)))
    deduped: list[str] = []
    seen: set[str] = set()
    for label in labels:
        key = _normalized_name_key(label)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(label)
    return deduped


def _context_email_directory(context_text: str, *, candidate_names: list[str]) -> dict[str, str]:
    emails = list(dict.fromkeys(match.group(1).lower() for match in _EMAIL_RE.finditer(context_text)))
    directory: dict[str, str] = {}
    used_emails: set[str] = set()
    for name in candidate_names:
        email = best_matching_email(name, [item for item in emails if item not in used_emails])
        if not email:
            continue
        used_emails.add(email)
        directory[_normalized_name_key(name)] = email
    return directory


def merge_people_with_context_emails(rows: list[dict[str, Any]], email_directory: dict[str, str]) -> list[dict[str, Any]]:
    """Fill missing role-row emails from an explicit matter-context email directory."""
    merged: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        name = _compact(updated.get("name"))
        if not updated.get("email") and name:
            email = email_directory.get(_normalized_name_key(name))
            if email:
                updated["email"] = email
        merged.append(updated)
    return merged


def _context_people_from_names(
    names: list[str],
    *,
    email_directory: dict[str, str],
    exclude_people: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    excluded_name_keys = {
        _normalized_name_key(_compact(item.get("name"))) for item in exclude_people if _compact(item.get("name"))
    }
    excluded_emails = {_compact(item.get("email")).lower() for item in exclude_people if _compact(item.get("email"))}
    rows: list[dict[str, Any]] = []
    for name in names:
        name_key = _normalized_name_key(name)
        email = email_directory.get(name_key)
        if not name_key or name_key in excluded_name_keys:
            continue
        if email and email.lower() in excluded_emails:
            continue
        row: dict[str, Any] = {"name": name}
        if email:
            row["email"] = email
        rows.append(row)
    return rows


def _actor_type_from_hint(type_hint: str, label: str) -> str:
    hint = _ascii_fold(type_hint).lower()
    label_hint = _ascii_fold(label).lower()
    if "distribution list" in hint or "verteiler" in label_hint or label_hint.startswith("kw pr"):
        return "distribution_list"
    if "workflow surface" in hint or any(token in label_hint for token in ("route", "workflow", "queue")):
        return "workflow_surface"
    if "system" in hint or any(token in label_hint for token in ("time system", "ticket system")):
        return "system_surface"
    if "external body" in hint or any(token in label_hint for token in ("integrationsamt", "inklusionsamt")):
        return "external_body"
    if "mailbox" in hint:
        return "shared_mailbox"
    if "body" in hint:
        return "institutional_body"
    return "other"


def _institutional_label_and_email(cell_text: str) -> tuple[str, str | None]:
    pieces = [_clean_markdown_atom(piece) for piece in str(cell_text).split("/")]
    label_parts = [piece for piece in pieces if piece and not _EMAIL_RE.fullmatch(piece)]
    raw_email = next((piece for piece in pieces if _EMAIL_RE.fullmatch(piece)), None)
    email = raw_email.lower() if raw_email else None
    label = " / ".join(label_parts) if label_parts else (raw_email.split("@", 1)[0] if raw_email else "")
    return label, email


def _dedupe_institutional_actor_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = _compact(row.get("label"))
        email = _compact(row.get("email")).lower()
        key = email or _normalized_name_key(label)
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = row
            continue
        existing_score = sum(bool(_compact(existing.get(field))) for field in ("email", "function", "notes"))
        candidate_score = sum(bool(_compact(row.get(field))) for field in ("email", "function", "notes"))
        if candidate_score >= existing_score:
            deduped[key] = row
    return list(deduped.values())


def institutional_actors_from_matter(context_text: str) -> list[dict[str, Any]]:
    """Return structured institutional actors, mailboxes, and workflow surfaces from preserved matter text."""
    rows: list[dict[str, Any]] = []
    functional_labels = _functional_actor_labels_from_context(context_text)
    functional_email_directory = _context_email_directory(context_text, candidate_names=functional_labels)
    section_match = _INSTITUTIONAL_ACTORS_SECTION_RE.search(str(context_text or ""))
    section_body = section_match.group("body") if section_match else ""
    for raw_line in section_body.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 4 or all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if cells[0].strip().lower() == "label" and cells[1].strip().lower() == "type":
            continue
        label, email = _institutional_label_and_email(cells[0])
        if not label:
            continue
        rows.append(
            {
                "label": label,
                "actor_type": _actor_type_from_hint(cells[1], label),
                "email": email,
                "function": _clean_markdown_atom(cells[2]) or None,
                "notes": _clean_markdown_atom(cells[3]) or None,
            }
        )
    for label in functional_labels:
        rows.append(
            {
                "label": label,
                "actor_type": _actor_type_from_hint("", label),
                "email": functional_email_directory.get(_normalized_name_key(label)),
                "function": None,
                "notes": None,
            }
        )
    return _dedupe_institutional_actor_rows(rows)


def context_people_from_matter(context_text: str, *, exclude_people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return additional explicitly named natural persons from preserved matter text."""
    names = _natural_person_names_from_context(context_text)
    email_directory = _context_email_directory(context_text, candidate_names=names)
    return _context_people_from_names(names, email_directory=email_directory, exclude_people=exclude_people)


def person_email_directory_from_matter(context_text: str) -> dict[str, str]:
    """Return explicit natural-person email matches keyed by normalized person name."""
    return _context_email_directory(context_text, candidate_names=_natural_person_names_from_context(context_text))
