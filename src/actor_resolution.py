"""Actor identity resolution helpers for behavioural-analysis workflows."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src._utils import compact

_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_REPLY_CONTEXT_JSON_PREVIEW_LIMIT = 180
logger = logging.getLogger(__name__)


def _normalize_email(value: str | None) -> str:
    """Return normalized email identity or an empty string."""
    compacted = compact(value).lower()
    if not compacted:
        return ""
    match = _EMAIL_RE.search(compacted)
    if match:
        return match.group(1).lower()
    return compacted if "@" in compacted else ""


def _normalize_name(value: str | None) -> str:
    """Return a stable lowercased name key or an empty string."""
    return compact(value).casefold()


def _display_name(value: str | None) -> str:
    """Return the best-effort original-casing display name."""
    return compact(value)


def _infer_role_hints(*, email: str, name: str, role_hint: str, source_tag: str) -> set[str]:
    """Infer role hints from email, name, role hint, and source tag.

    Args:
        email: The email address of the actor.
        name: The name of the actor.
        role_hint: Explicit role hint from the source.
        source_tag: The source tag indicating where this data came from.

    Returns:
        A set of inferred role hints based on the input data.
    """
    hints: set[str] = set()
    compact_role = compact(role_hint)
    if compact_role:
        hints.add(compact_role)
    haystack = " ".join([_normalize_email(email), _normalize_name(name), _normalize_name(source_tag)]).strip()
    source_roles = {
        "case_scope.target_person": "target_person",
        "case_scope.suspected_actors": "suspected_actor",
        "case_scope.comparator_actors": "comparator",
    }
    hints.update(role for marker, role in source_roles.items() if marker in source_tag)
    token_roles = {
        "representation": ("personalrat", "betriebsrat", "sbv", "schwerbehindertenvertret", "vertret"),
        "hr": ("personal", "hr", "human resources"),
        "management": ("leitung", "manager", "dekan", "direktor", "vorgesetz"),
    }
    hints.update(role for role, tokens in token_roles.items() if any(token in haystack for token in tokens))
    return {hint for hint in hints if compact(hint)}


def _recipient_identity(value: str) -> tuple[str, str]:
    """Parse one recipient string into display name and email."""
    compacted = compact(value)
    if not compacted:
        return "", ""
    email = _normalize_email(compacted)
    if not email:
        return compacted, ""
    angle = re.match(r"^(.*?)\s*<[^>]+>$", compacted)
    if angle:
        return _display_name(angle.group(1)), email
    name = compacted.replace(email, "").strip(" <>\"'")
    return _display_name(name), email


def _role_hints_from_entity_occurrence(occurrence: dict[str, Any]) -> set[str]:
    """Extract role hints from an entity occurrence dictionary.

    Args:
        occurrence: A dictionary containing entity occurrence data with keys
            like entity_type, normalized_form, entity_text.

    Returns:
        A set of role hints inferred from the entity occurrence.
    """
    entity_type = str(occurrence.get("entity_type") or "").strip().casefold()
    normalized = str(occurrence.get("normalized_form") or occurrence.get("entity_text") or "").strip().casefold()
    role_rules = (
        ({"organization", "committee"}, ("sbv", "personalrat", "betriebsrat", "schwerbehindertenvertret"), "representation"),
        ({"legal_reference", "statute"}, ("agg", "sgb", "tv-l"), "legal_reference"),
        (
            {"workplace_process", "process", "event"},
            ("bem", "wiedereingliederung", "eingruppierung", "leidensgerechter"),
            "workplace_process",
        ),
    )
    return {
        role
        for entity_types, tokens, role in role_rules
        if entity_type in entity_types and any(token in normalized for token in tokens)
    }


def _parse_reply_context_to_list(raw_value: Any, *, uid: str) -> tuple[list[str], dict[str, Any] | None]:
    """Parse reply context field into a list of email addresses.

    Args:
        raw_value: The raw value of the reply_context_to field, either a list or
            a JSON string.
        uid: The unique identifier of the email for logging purposes.

    Returns:
        A tuple of (list_of_emails, diagnostic_info) where diagnostic_info is None
        if parsing succeeded, or a dict with error details if parsing failed.
    """
    if isinstance(raw_value, list):
        return [str(item or "") for item in raw_value], None
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return [], None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        preview = raw_text[:_REPLY_CONTEXT_JSON_PREVIEW_LIMIT]
        logger.warning("Malformed reply_context_to_json for uid=%s; ignoring value", uid)
        return [], {
            "source": f"candidate:{uid}:reply_context_to_json",
            "reason": "malformed_reply_context_to_json",
            "value_preview": preview,
        }
    if not isinstance(parsed, list):
        logger.warning("Non-list reply_context_to_json for uid=%s; ignoring value", uid)
        return [], {
            "source": f"candidate:{uid}:reply_context_to_json",
            "reason": "reply_context_to_json_not_list",
            "value_preview": str(type(parsed).__name__),
        }
    return [str(item or "") for item in parsed], None


@dataclass
class _ActorNode:
    """Mutable actor node while building the identity graph."""

    primary_email: str = ""
    names: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    role_hints: set[str] = field(default_factory=set)
    source_tags: set[str] = field(default_factory=set)


def _stable_actor_id(*, primary_email: str, names: set[str]) -> str:
    """Build a deterministic actor id from stable identity material."""
    key = primary_email or "|".join(sorted(names))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"actor-{digest}"


def resolve_actor_graph(
    *,
    case_scope: Any | None,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    full_map: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a stable actor identity graph from case scope and answer evidence."""
    actor_nodes: dict[str, _ActorNode] = {}
    email_to_key: dict[str, str] = {}
    name_to_keys: dict[str, set[str]] = {}
    unresolved_name_refs: list[dict[str, Any]] = []

    def _register_name(name: str, actor_key: str) -> None:
        normalized_name = _normalize_name(name)
        if normalized_name:
            name_to_keys.setdefault(normalized_name, set()).add(actor_key)

    def _ensure_node(
        *,
        email: str = "",
        name: str = "",
        role_hint: str = "",
        source_tag: str,
    ) -> str | None:
        return _ensure_actor_node(
            actor_nodes=actor_nodes,
            email_to_key=email_to_key,
            name_to_keys=name_to_keys,
            unresolved=unresolved_name_refs,
            register_name=_register_name,
            email=email,
            name=name,
            role_hint=role_hint,
            source_tag=source_tag,
        )

    def _register_case_person(person: Any, source_tag: str) -> str | None:
        return _ensure_node(
            email=getattr(person, "email", "") or "",
            name=getattr(person, "name", "") or "",
            role_hint=getattr(person, "role_hint", "") or "",
            source_tag=source_tag,
        )

    _register_case_scope(case_scope, _register_case_person)

    full_map = full_map or {}
    for candidate in [*candidates, *attachment_candidates]:
        _register_candidate_actors(candidate, full_map, _ensure_node, unresolved_name_refs, actor_nodes)

    ambiguous_name_keys = [name for name, keys in name_to_keys.items() if name and len(keys) > 1]
    actors, actor_key_to_id = _actor_rows(actor_nodes, ambiguous_name_keys)

    return {
        "actors": sorted(actors, key=lambda actor: str(actor.get("actor_id") or "")),
        "unresolved_references": unresolved_name_refs,
        "stats": {
            "actor_count": len(actors),
            "ambiguous_name_count": len(ambiguous_name_keys),
            "unresolved_reference_count": len(unresolved_name_refs),
        },
        "_actor_key_to_id": actor_key_to_id,
        "_email_to_key": email_to_key,
        "_name_to_keys": name_to_keys,
    }


def _ensure_actor_node(*, actor_nodes, email_to_key, name_to_keys, unresolved, register_name, email, name, role_hint, source_tag):
    normalized_email = _normalize_email(email)
    display_name = _display_name(name)
    normalized_name = _normalize_name(display_name)
    actor_key = email_to_key.get(normalized_email, "") if normalized_email else ""
    actor_key, ambiguous = _name_matched_actor_key(actor_key, normalized_name, normalized_email, name_to_keys, actor_nodes)
    if ambiguous:
        unresolved.append({"name": display_name, "source": source_tag, "reason": "ambiguous_name_multiple_emails"})
        return None
    if not actor_key:
        actor_key = normalized_email or f"name:{normalized_name or source_tag}:{len(actor_nodes)}"
    node = actor_nodes.setdefault(actor_key, _ActorNode(primary_email=normalized_email))
    _update_actor_node(node, actor_key, normalized_email, display_name, email_to_key, register_name)
    node.role_hints.update(
        _infer_role_hints(email=normalized_email, name=display_name, role_hint=role_hint or "", source_tag=source_tag)
    )
    node.source_tags.add(source_tag)
    return actor_key


def _name_matched_actor_key(actor_key, normalized_name, normalized_email, name_to_keys, actor_nodes):
    if actor_key or not normalized_name:
        return actor_key, False
    candidate_keys = name_to_keys.get(normalized_name, set())
    if len(candidate_keys) > 1 and not normalized_email:
        return "", True
    if len(candidate_keys) != 1:
        return "", False
    candidate_key = next(iter(candidate_keys))
    node = actor_nodes.get(candidate_key)
    compatible = not normalized_email or (node and (not node.emails or normalized_email in node.emails))
    return (candidate_key if compatible else ""), False


def _update_actor_node(node, actor_key, email, name, email_to_key, register_name):
    if email:
        node.emails.add(email)
        node.primary_email = node.primary_email or email
        email_to_key[email] = actor_key
    if name:
        node.names.add(name)
        register_name(name, actor_key)


def _register_case_scope(case_scope, register_person):
    if case_scope is None:
        return
    register_person(case_scope.target_person, "case_scope.target_person")
    for actor_field in ("suspected_actors", "comparator_actors"):
        for idx, actor in enumerate(getattr(case_scope, actor_field)):
            register_person(actor, f"case_scope.{actor_field}[{idx}]")


def _actor_rows(actor_nodes, ambiguous_names):
    actors = []
    key_to_id = {}
    for actor_key, node in actor_nodes.items():
        actor_id = _stable_actor_id(primary_email=node.primary_email, names=node.names)
        key_to_id[actor_key] = actor_id
        actors.append(
            {
                "actor_id": actor_id,
                "primary_email": node.primary_email or None,
                "emails": sorted(node.emails),
                "display_names": sorted(node.names),
                "role_hints": sorted(node.role_hints),
                "source_tags": sorted(node.source_tags),
                "ambiguity": {"ambiguous_name_match": any(_normalize_name(name) in ambiguous_names for name in node.names)},
            }
        )
    return actors, key_to_id


def resolve_actor_id(
    actor_graph: dict[str, Any],
    *,
    email: str = "",
    name: str = "",
) -> tuple[str | None, dict[str, Any]]:
    """Resolve one reference against the actor graph without over-merging."""
    # Extract lookup tables once for readability.
    email_to_key = actor_graph.get("_email_to_key", {})
    actor_key_to_id = actor_graph.get("_actor_key_to_id", {})
    name_to_keys = actor_graph.get("_name_to_keys", {})

    normalized_email = _normalize_email(email)
    if normalized_email:
        actor_key = email_to_key.get(normalized_email)
        if actor_key:
            return actor_key_to_id.get(actor_key), {
                "resolved_by": "email",
                "ambiguous": False,
            }
        return None, {"resolved_by": "email", "ambiguous": False}

    normalized_name = _normalize_name(name)
    if not normalized_name:
        return None, {"resolved_by": "none", "ambiguous": False}
    keys = list(name_to_keys.get(normalized_name, set()))
    if len(keys) == 1:
        actor_key = keys[0]
        return actor_key_to_id.get(actor_key), {
            "resolved_by": "name",
            "ambiguous": False,
        }
    if len(keys) > 1:
        return None, {"resolved_by": "name", "ambiguous": True}
    return None, {"resolved_by": "name", "ambiguous": False}


def _register_candidate_actors(candidate, full_map, ensure_node, unresolved, actor_nodes) -> None:
    uid = str(candidate.get("uid") or "")
    full_email = full_map.get(uid) if isinstance(full_map, dict) else None
    ensure_node(
        email=str(candidate.get("sender_email") or ""),
        name=str(candidate.get("sender_name") or ""),
        source_tag=f"candidate:{uid}:sender",
    )
    _register_recipients(uid, full_email, ensure_node)
    if full_email:
        _register_reply_context(uid, full_email, ensure_node, unresolved)
    _register_speakers(uid, candidate.get("speaker_attribution"), ensure_node)
    _register_entity_occurrences(uid, candidate, ensure_node, actor_nodes)


def _register_recipients(uid, full_email, ensure_node):
    if not full_email:
        return
    for field_name in ("to", "cc", "bcc"):
        for raw_recipient in full_email.get(field_name, []) or []:
            name, email = _recipient_identity(str(raw_recipient))
            ensure_node(email=email, name=name, source_tag=f"candidate:{uid}:{field_name}")


def _register_reply_context(uid, full_email, ensure_node, unresolved):
    ensure_node(email=str(full_email.get("reply_context_from") or ""), source_tag=f"candidate:{uid}:reply_context_from")
    rows, diagnostic = _parse_reply_context_to_list(full_email.get("reply_context_to_json", "[]"), uid=uid)
    if isinstance(diagnostic, dict):
        unresolved.append(diagnostic)
    for idx, raw_email in enumerate(rows):
        ensure_node(email=str(raw_email or ""), source_tag=f"candidate:{uid}:reply_context_to[{idx}]")


def _register_speakers(uid, attribution, ensure_node):
    if not isinstance(attribution, dict):
        return
    authored = attribution.get("authored_speaker")
    if isinstance(authored, dict):
        ensure_node(
            email=str(authored.get("email") or ""),
            name=str(authored.get("name") or ""),
            source_tag=f"candidate:{uid}:authored_speaker",
        )
    for idx, block in enumerate(attribution.get("quoted_blocks", []) or []):
        if isinstance(block, dict) and (email := str(block.get("speaker_email") or "")):
            ensure_node(email=email, source_tag=f"candidate:{uid}:quoted_block[{idx}]")


def _register_entity_occurrences(uid, candidate, ensure_node, actor_nodes):
    occurrences = candidate.get("entity_occurrences")
    if not isinstance(occurrences, list):
        return
    for idx, occurrence in enumerate(occurrences):
        if not isinstance(occurrence, dict):
            continue
        _register_entity_occurrence(uid, idx, occurrence, candidate, ensure_node, actor_nodes)


def _register_entity_occurrence(uid, idx, occurrence, candidate, ensure_node, actor_nodes):
    entity_text = _display_name(str(occurrence.get("entity_text") or ""))
    entity_type = str(occurrence.get("entity_type") or "").strip().casefold()
    if entity_type in {"person", "person_title"} and entity_text:
        ensure_node(name=entity_text, source_tag=f"candidate:{uid}:entity_occurrence[{idx}]")
    role_hints = _role_hints_from_entity_occurrence(occurrence)
    if not role_hints:
        return
    source_scope = str(occurrence.get("source_scope") or "")
    sender_key = ensure_node(
        email=str(candidate.get("sender_email") or ""),
        name=str(candidate.get("sender_name") or ""),
        source_tag=f"candidate:{uid}:entity_scope:{source_scope or 'unknown'}",
    )
    if sender_key:
        actor_nodes[sender_key].role_hints.update(role_hints)
