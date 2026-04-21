"""Actor identity resolution helpers for behavioural-analysis workflows."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_REPLY_CONTEXT_JSON_PREVIEW_LIMIT = 180
logger = logging.getLogger(__name__)


def _compact_text(value: str | None) -> str:
    """Return compact whitespace-normalized text."""
    return " ".join((value or "").split()).strip()


def _normalize_email(value: str | None) -> str:
    """Return normalized email identity or an empty string."""
    compacted = _compact_text(value).lower()
    if not compacted:
        return ""
    match = _EMAIL_RE.search(compacted)
    if match:
        return match.group(1).lower()
    return compacted if "@" in compacted else ""


def _normalize_name(value: str | None) -> str:
    """Return a stable lowercased name key or an empty string."""
    return _compact_text(value).casefold()


def _display_name(value: str | None) -> str:
    """Return the best-effort original-casing display name."""
    return _compact_text(value)


def _infer_role_hints(*, email: str, name: str, role_hint: str, source_tag: str) -> set[str]:
    hints: set[str] = set()
    compact_role = _compact_text(role_hint)
    if compact_role:
        hints.add(compact_role)
    haystack = " ".join([_normalize_email(email), _normalize_name(name), _normalize_name(source_tag)]).strip()
    if "case_scope.target_person" in source_tag:
        hints.add("target_person")
    if "case_scope.suspected_actors" in source_tag:
        hints.add("suspected_actor")
    if "case_scope.comparator_actors" in source_tag:
        hints.add("comparator")
    if any(token in haystack for token in ("personalrat", "betriebsrat", "sbv", "schwerbehindertenvertret", "vertret")):
        hints.add("representation")
    if any(token in haystack for token in ("personal", "hr", "human resources")):
        hints.add("hr")
    if any(token in haystack for token in ("leitung", "manager", "dekan", "direktor", "vorgesetz")):
        hints.add("management")
    return {hint for hint in hints if _compact_text(hint)}


def _recipient_identity(value: str) -> tuple[str, str]:
    """Parse one recipient string into display name and email."""
    compacted = _compact_text(value)
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
    entity_type = str(occurrence.get("entity_type") or "").strip().casefold()
    normalized = str(occurrence.get("normalized_form") or occurrence.get("entity_text") or "").strip().casefold()
    hints: set[str] = set()
    if entity_type in {"organization", "committee"} and any(
        token in normalized for token in ("sbv", "personalrat", "betriebsrat", "schwerbehindertenvertret")
    ):
        hints.add("representation")
    if entity_type in {"legal_reference", "statute"} and any(token in normalized for token in ("agg", "sgb", "tv-l")):
        hints.add("legal_reference")
    if entity_type in {"workplace_process", "process", "event"} and any(
        token in normalized for token in ("bem", "wiedereingliederung", "eingruppierung", "leidensgerechter")
    ):
        hints.add("workplace_process")
    return hints


def _parse_reply_context_to_list(raw_value: Any, *, uid: str) -> tuple[list[str], dict[str, Any] | None]:
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
        normalized_email = _normalize_email(email)
        display_name = _display_name(name)
        normalized_name = _normalize_name(display_name)
        actor_key = email_to_key.get(normalized_email, "") if normalized_email else ""

        if not actor_key and normalized_name:
            candidate_keys = name_to_keys.get(normalized_name, set())
            if len(candidate_keys) == 1:
                candidate_key = next(iter(candidate_keys))
                candidate_node = actor_nodes.get(candidate_key)
                if not normalized_email or (
                    candidate_node and (not candidate_node.emails or normalized_email in candidate_node.emails)
                ):
                    actor_key = candidate_key
            elif len(candidate_keys) > 1 and not normalized_email:
                unresolved_name_refs.append(
                    {
                        "name": display_name,
                        "source": source_tag,
                        "reason": "ambiguous_name_multiple_emails",
                    }
                )
                return None

        if not actor_key:
            actor_key = normalized_email or f"name:{normalized_name or source_tag}:{len(actor_nodes)}"
            actor_nodes.setdefault(actor_key, _ActorNode(primary_email=normalized_email))

        node = actor_nodes.setdefault(actor_key, _ActorNode(primary_email=normalized_email))
        if normalized_email:
            node.emails.add(normalized_email)
            if not node.primary_email:
                node.primary_email = normalized_email
            email_to_key[normalized_email] = actor_key
        if display_name:
            node.names.add(display_name)
            _register_name(display_name, actor_key)
        inferred_role_hints = _infer_role_hints(
            email=normalized_email,
            name=display_name,
            role_hint=role_hint if role_hint else "",
            source_tag=source_tag,
        )
        if inferred_role_hints:
            node.role_hints.update(inferred_role_hints)
        node.source_tags.add(source_tag)
        return actor_key

    def _register_case_person(person: Any, source_tag: str) -> str | None:
        return _ensure_node(
            email=getattr(person, "email", "") or "",
            name=getattr(person, "name", "") or "",
            role_hint=getattr(person, "role_hint", "") or "",
            source_tag=source_tag,
        )

    if case_scope is not None:
        _register_case_person(case_scope.target_person, "case_scope.target_person")
        for idx, actor in enumerate(case_scope.suspected_actors):
            _register_case_person(actor, f"case_scope.suspected_actors[{idx}]")
        for idx, actor in enumerate(case_scope.comparator_actors):
            _register_case_person(actor, f"case_scope.comparator_actors[{idx}]")

    full_map = full_map or {}
    for candidate in [*candidates, *attachment_candidates]:
        uid = str(candidate.get("uid") or "")
        full_email = full_map.get(uid) if isinstance(full_map, dict) else None
        _ensure_node(
            email=str(candidate.get("sender_email") or ""),
            name=str(candidate.get("sender_name") or ""),
            source_tag=f"candidate:{uid}:sender",
        )
        for field_name in ("to", "cc", "bcc"):
            if not full_email:
                continue
            for raw_recipient in full_email.get(field_name, []) or []:
                rec_name, rec_email = _recipient_identity(str(raw_recipient))
                _ensure_node(
                    email=rec_email,
                    name=rec_name,
                    source_tag=f"candidate:{uid}:{field_name}",
                )
        if full_email:
            _ensure_node(
                email=str(full_email.get("reply_context_from") or ""),
                source_tag=f"candidate:{uid}:reply_context_from",
            )
            reply_context_to_rows, reply_context_diag = _parse_reply_context_to_list(
                full_email.get("reply_context_to_json", "[]"),
                uid=uid,
            )
            if isinstance(reply_context_diag, dict):
                unresolved_name_refs.append(reply_context_diag)
            for idx, raw_reply_to in enumerate(reply_context_to_rows):
                _ensure_node(
                    email=str(raw_reply_to or ""),
                    source_tag=f"candidate:{uid}:reply_context_to[{idx}]",
                )
        speaker_attribution = candidate.get("speaker_attribution")
        if isinstance(speaker_attribution, dict):
            authored = speaker_attribution.get("authored_speaker")
            if isinstance(authored, dict):
                _ensure_node(
                    email=str(authored.get("email") or ""),
                    name=str(authored.get("name") or ""),
                    source_tag=f"candidate:{uid}:authored_speaker",
                )
            for idx, block in enumerate(speaker_attribution.get("quoted_blocks", []) or []):
                if not isinstance(block, dict):
                    continue
                email = str(block.get("speaker_email") or "")
                if email:
                    _ensure_node(
                        email=email,
                        source_tag=f"candidate:{uid}:quoted_block[{idx}]",
                    )

        entity_occurrences = candidate.get("entity_occurrences")
        if isinstance(entity_occurrences, list):
            for idx, occurrence in enumerate(entity_occurrences):
                if not isinstance(occurrence, dict):
                    continue
                entity_text = _display_name(str(occurrence.get("entity_text") or ""))
                entity_type = str(occurrence.get("entity_type") or "").strip().casefold()
                source_scope = str(occurrence.get("source_scope") or "")
                if entity_type in {"person", "person_title"} and entity_text:
                    _ensure_node(
                        name=entity_text,
                        source_tag=f"candidate:{uid}:entity_occurrence[{idx}]",
                    )
                role_hints = _role_hints_from_entity_occurrence(occurrence)
                if role_hints:
                    sender_email = str(candidate.get("sender_email") or "")
                    sender_name = str(candidate.get("sender_name") or "")
                    sender_key = _ensure_node(
                        email=sender_email,
                        name=sender_name,
                        source_tag=f"candidate:{uid}:entity_scope:{source_scope or 'unknown'}",
                    )
                    if sender_key:
                        actor_nodes[sender_key].role_hints.update(role_hints)

    actors: list[dict[str, Any]] = []
    ambiguous_name_keys: list[str] = []
    for normalized_name, keys in name_to_keys.items():
        if normalized_name and len(keys) > 1:
            ambiguous_name_keys.append(normalized_name)

    actor_key_to_id: dict[str, str] = {}
    for actor_key, node in actor_nodes.items():
        actor_id = _stable_actor_id(primary_email=node.primary_email, names=node.names)
        actor_key_to_id[actor_key] = actor_id
        actors.append(
            {
                "actor_id": actor_id,
                "primary_email": node.primary_email or None,
                "emails": sorted(node.emails),
                "display_names": sorted(node.names),
                "role_hints": sorted(node.role_hints),
                "source_tags": sorted(node.source_tags),
                "ambiguity": {
                    "ambiguous_name_match": any(_normalize_name(name) in ambiguous_name_keys for name in node.names),
                },
            }
        )

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


def resolve_actor_id(
    actor_graph: dict[str, Any],
    *,
    email: str = "",
    name: str = "",
) -> tuple[str | None, dict[str, Any]]:
    """Resolve one reference against the actor graph without over-merging."""
    normalized_email = _normalize_email(email)
    if normalized_email:
        actor_key = actor_graph.get("_email_to_key", {}).get(normalized_email)
        if actor_key:
            return actor_graph.get("_actor_key_to_id", {}).get(actor_key), {
                "resolved_by": "email",
                "ambiguous": False,
            }
        return None, {"resolved_by": "email", "ambiguous": False}

    normalized_name = _normalize_name(name)
    if not normalized_name:
        return None, {"resolved_by": "none", "ambiguous": False}
    keys = list(actor_graph.get("_name_to_keys", {}).get(normalized_name, set()))
    if len(keys) == 1:
        actor_key = keys[0]
        return actor_graph.get("_actor_key_to_id", {}).get(actor_key), {
            "resolved_by": "name",
            "ambiguous": False,
        }
    if len(keys) > 1:
        return None, {"resolved_by": "name", "ambiguous": True}
    return None, {"resolved_by": "name", "ambiguous": False}
