"""Golden outputs for MCP tools over one synthetic archive.

The snapshot was recorded from the pre-reconstruction implementation (with the
runtime-cast and template-path fixes applied) and pins the observable output
of every MCP tool that runs offline: archive browsing, contacts, threads,
network, temporal, quality, attachments, diagnostics, evidence and custody
workflows, and HTML/CSV exports. Volatile values (temporary paths, current
timestamps, timing, and time-dependent dossier hashes) are normalized.
Regenerate deliberately with ``MAILARIUM_UPDATE_SNAPSHOTS=1``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from mailarium.archive import open_archive_database
from mailarium.ingestion.records import ParsedMessage
from mailarium.interfaces.mcp.runtime_state import McpRuntimeState
from mailarium.interfaces.mcp.server import create_mcp_server
from mailarium.platform.settings import clear_settings_cache

SNAPSHOT = Path(__file__).parent / "snapshots" / "mcp_tool_outputs.json"
PEOPLE = ["alice@example.test", "bob@example.test", "carol@example.test", "dave@example.test"]


def _message(
    index: int,
    sender: str,
    to: list[str],
    cc: list[str],
    subject: str,
    body: str,
    date: str,
    *,
    reply_to: int | None = None,
    attachment: bool = False,
    folder: str = "Inbox",
) -> ParsedMessage:
    return ParsedMessage(
        message_id=f"<m{index}@example.test>",
        subject=subject,
        sender_name=sender.split("@", maxsplit=1)[0].title(),
        sender_email=sender,
        to=to,
        cc=cc,
        bcc=[],
        date=date,
        body_text=body,
        body_html="",
        folder=folder,
        in_reply_to=f"<m{reply_to}@example.test>" if reply_to else "",
        references=[f"<m{reply_to}@example.test>"] if reply_to else [],
        conversation_id="conv-launch" if subject.lower().endswith("launch plan") else "conv-budget",
        has_attachments=attachment,
        attachment_names=["timeline.txt"] if attachment else [],
        attachments=[
            {
                "name": "timeline.txt",
                "mime_type": "text/plain",
                "size": 32,
                "extracted_text": "Launch timeline: review on Friday, ship Monday.",
                "extraction_state": "text_extracted",
            }
        ]
        if attachment
        else [],
    )


MESSAGES = [
    _message(
        1,
        PEOPLE[0],
        [PEOPLE[1]],
        [PEOPLE[2]],
        "Launch plan",
        "Hi Bob,\n\nWe will ship the release on Monday after the Friday review. Please confirm the budget.\n\nAlice",
        "2025-03-03T09:00:00",
        attachment=True,
    ),
    _message(
        2,
        PEOPLE[1],
        [PEOPLE[0]],
        [PEOPLE[2]],
        "RE: Launch plan",
        "Confirmed. I decided to approve the budget of 5000 EUR.\n\nOn Mon, Alice wrote:\n> We will ship the release on Monday",
        "2025-03-03T11:30:00",
        reply_to=1,
    ),
    _message(
        3,
        PEOPLE[2],
        [PEOPLE[0], PEOPLE[1]],
        [],
        "RE: Launch plan",
        "Action item: Carol will update the timeline by Thursday.",
        "2025-03-04T08:15:00",
        reply_to=2,
    ),
    _message(
        4,
        PEOPLE[3],
        [PEOPLE[0]],
        [PEOPLE[1]],
        "Budget review",
        "The quarterly budget review is scheduled for April. Berlin office attends.",
        "2025-03-10T14:00:00",
        folder="Projects",
    ),
    _message(
        5,
        PEOPLE[0],
        [PEOPLE[3]],
        [],
        "RE: Budget review",
        "Thanks Dave, I will join the budget review in Berlin.",
        "2025-03-11T10:00:00",
        reply_to=4,
        folder="Projects",
    ),
    _message(
        6,
        PEOPLE[1],
        [PEOPLE[3]],
        [PEOPLE[0]],
        "FW: Budget review",
        "Forwarding for visibility. No decision yet.",
        "2025-04-01T16:45:00",
        reply_to=4,
        folder="Projects",
    ),
]


def _calls(uids: list[str], exports: Path) -> list[tuple[str, dict[str, Any] | None]]:
    calls: list[tuple[str, dict[str, Any] | None]] = [
        ("email_stats", None),
        ("email_list_folders", None),
        ("email_list_senders", {"limit": 10}),
        ("email_browse", {"limit": 10}),
        ("email_browse", {"folder": "Projects", "include_body": True}),
        ("email_browse", {"list_categories": True}),
        ("email_contacts", {"email_address": PEOPLE[0]}),
        ("email_contacts", {"email_address": PEOPLE[0], "compare_with": PEOPLE[1]}),
        ("email_thread_lookup", {"conversation_id": "conv-launch"}),
        ("email_thread_lookup", {"thread_topic": "Budget review"}),
        ("email_thread_summary", {"conversation_id": "conv-launch"}),
        ("email_thread_lookup", {"conversation_id": "conv-budget"}),
        ("email_thread_summary", {"conversation_id": "conv-budget"}),
        ("email_action_items", {}),
        ("email_action_items", {"conversation_id": "conv-launch"}),
        ("email_action_items", {"conversation_id": "conv-budget"}),
        ("email_decisions", {}),
        ("email_decisions", {"conversation_id": "conv-launch"}),
        ("email_decisions", {"conversation_id": "conv-budget"}),
        ("email_network_analysis", {"top_n": 5}),
        ("relationship_paths", {"source": PEOPLE[2], "target": PEOPLE[3]}),
        ("shared_recipients", {"email_addresses": [PEOPLE[0], PEOPLE[1]]}),
        ("coordinated_timing", {"email_addresses": [PEOPLE[0], PEOPLE[1]]}),
        ("relationship_summary", {"email_address": PEOPLE[1]}),
        ("email_list_entities", {"limit": 20}),
        ("email_search_by_entity", {"entity": "Berlin"}),
        ("email_entity_network", {"entity": "Berlin"}),
        ("email_entity_timeline", {"entity": "Berlin"}),
        ("email_clusters", {}),
        ("email_topics", {}),
        ("email_provenance", {"email_uid": uids[0]}),
        ("email_deep_context", {"uid": uids[1], "include_thread": True, "include_sender_stats": True}),
        ("email_mailbox_proposal_status", {}),
        ("email_mailbox_status", {"account_id": "missing"}),
    ]
    calls += [("email_temporal", {"analysis": value}) for value in ("volume", "activity", "response_times")]
    calls += [("email_quality", {"check": value}) for value in ("duplicates", "languages", "sentiment")]
    calls += [("email_attachments", {"mode": value}) for value in ("list", "search", "stats")]
    calls += [("email_discovery", {"mode": value}) for value in ("keywords", "suggestions")]
    calls += [
        ("email_admin", {"action": "diagnostics"}),
        (
            "evidence_add",
            {
                "email_uid": uids[1],
                "category": "decision",
                "key_quote": "I decided to approve the budget",
                "summary": "Budget approved",
                "relevance": 5,
            },
        ),
        (
            "evidence_add",
            {
                "email_uid": uids[0],
                "category": "timeline",
                "key_quote": "We will ship the release on Monday",
                "summary": "Ship date",
                "relevance": 3,
            },
        ),
        (
            "evidence_add",
            {
                "email_uid": uids[0],
                "category": "bogus",
                "key_quote": "not in the email at all",
                "summary": "Bad quote",
                "relevance": 2,
            },
        ),
        ("evidence_query", {}),
        ("evidence_query", {"query": "budget", "include_quotes": True}),
        ("evidence_get", {"evidence_id": 1}),
        ("evidence_update", {"evidence_id": 2, "notes": "checked"}),
        ("evidence_overview", {}),
        ("evidence_provenance", {"evidence_id": 1}),
        ("evidence_verify", None),
        ("custody_chain", {"limit": 50}),
        ("evidence_remove", {"evidence_id": 2}),
        (
            "evidence_add_batch",
            {
                "items": [
                    {
                        "email_uid": uids[3],
                        "category": "meeting",
                        "key_quote": "budget review is scheduled for April",
                        "summary": "Review date",
                        "relevance": 4,
                    }
                ]
            },
        ),
        ("evidence_export", {"format": "html", "output_path": str(exports / "evidence.html")}),
        ("evidence_export", {"format": "csv", "output_path": str(exports / "evidence.csv")}),
        ("email_export", {"conversation_id": "conv-launch", "format": "html", "output_path": str(exports / "thread.html")}),
        ("email_export", {"uid": uids[3], "format": "html", "output_path": str(exports / "email.html")}),
        ("email_report", {"type": "archive", "output_path": str(exports / "report.html")}),
        ("email_report", {"type": "network", "output_path": str(exports / "network.html")}),
        ("email_report", {"type": "writing", "output_path": str(exports / "writing.html")}),
        ("email_dossier", {"output_path": str(exports / "dossier.html")}),
        ("email_admin", {"action": "reingest_analytics"}),
        ("email_quality", {"check": "languages"}),
    ]
    return calls


def _normalize(text: str, root: Path) -> str:
    try:
        text = json.dumps(json.loads(text), indent=1, sort_keys=True, ensure_ascii=False)
    except ValueError:
        pass
    text = text.replace(str(root), "<tmp>")
    for pattern in _TIMESTAMP_PATTERNS:
        text = pattern.sub(_timestamp, text)
    text = re.sub(r"(dossier_hash\W+)[0-9a-f]{64}", r"\1<hash>", text)
    text = re.sub(r"\"(elapsed|duration)[a-z_]*\": [0-9.]+", r'"\1": <t>', text)
    return re.sub(_HOST_HARDWARE_PATTERN, r'"\1": "<host>"', text)


# Diagnostics report the machine's device, memory, and derived batch size.
_HOST_HARDWARE_PATTERN = re.compile(
    r"\"(embedder_batch_size|embedder_device|memory_gb|resolved_batch_size|resolved_device)\": (?:\"[^\"]*\"|[0-9.]+)"
)

_TIMESTAMP_PATTERNS = (
    re.compile(r"(?P<year>\d{4})-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(\+00:00|Z| UTC)?"),
    re.compile(r"[A-Z][a-z]+ \d{1,2}, (?P<year>\d{4}), \d{1,2}:\d{2} [AP]M"),
)


def _timestamp(match: re.Match[str]) -> str:
    # Synthetic correspondence is dated 2025; any other timestamp is generation time.
    return match.group(0) if match.group("year") == "2025" else "<now>"


def _configuration_keys() -> set[str]:
    repository = Path(__file__).resolve().parents[2]
    documented = re.findall(r"^#? ?([A-Z][A-Z0-9_]+)=", (repository / ".env.example").read_text(encoding="utf-8"), re.MULTILINE)
    settings_source = (repository / "mailarium" / "platform" / "settings.py").read_text(encoding="utf-8")
    return set(documented) | set(re.findall(r"\"([A-Z][A-Z0-9_]{2,})\"", settings_source))


def _render(result: Any) -> str:
    if isinstance(result, tuple):
        result = result[0]
    items = result if isinstance(result, list) else [result]
    return "\n".join(getattr(item, "text", repr(item)) for item in items)


def test_mcp_tool_outputs_match_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    exports = root / "exports"
    exports.mkdir()
    (root / "data").mkdir()
    # Configuration in the developer's environment must not leak into the
    # golden outputs.
    for key in _configuration_keys():
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "MAILARIUM_RUNTIME_HOME": str(root),
        "MAILARIUM_ALLOWED_OUTPUT_ROOTS": str(exports),
        "RUNTIME_PROFILE": "offline-test",
        "EMBEDDING_LOAD_MODE": "local_only",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "SPACY_AUTO_DOWNLOAD_DURING_INGEST": "0",
        "TZ": "UTC",
        "ANALYTICS_TIMEZONE": "UTC",
    }.items():
        monkeypatch.setenv(key, value)

    sqlite_path = root / "data" / "archive.db"
    database = open_archive_database(str(sqlite_path))
    try:
        for message in MESSAGES:
            database.messages.insert_email(message)
    finally:
        database.close()
    uids = [message.uid for message in MESSAGES]

    clear_settings_cache()
    state = McpRuntimeState(vector_index_path=str(root / "data" / "vectors"), sqlite_path=str(sqlite_path))
    try:
        server = create_mcp_server(state)
        outputs: dict[str, str] = {}
        for index, (name, params) in enumerate(_calls(uids, exports)):
            arguments = {} if params is None else {"params": params}
            outputs[f"{index:03d} {name}"] = _normalize(_render(asyncio.run(server.call_tool(name, arguments))), root)
    finally:
        state.close()
        clear_settings_cache()
    for produced in sorted(exports.iterdir()):
        outputs[f"file {produced.name}"] = _normalize(produced.read_text(encoding="utf-8"), root)

    if os.environ.get("MAILARIUM_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(outputs, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(outputs) == sorted(expected)
    for key, value in expected.items():
        assert outputs[key] == value, key
