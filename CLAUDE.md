# Email RAG — Instructions for Claude

You have access to a local email archive via 46 MCP tools under the `email_search` server. The archive contains the user's Outlook emails indexed with BGE-M3 embeddings, stored in ChromaDB (vectors) and SQLite (metadata). Everything runs locally — no data leaves the machine.

For the full tool reference, see `docs/CLAUDE-TOOLS.md`.

## Workflow

**Triage mode** — scan the archive broadly (answering "what's relevant?"):
1. Issue 3-5 `email_triage` calls in one message with different queries (50-100 results each, ultra-compact ~80 tokens/result). FastMCP executes them concurrently.
2. `email_deep_context` on emails of interest — returns full body + thread summary + existing evidence + sender stats in one call.
3. `evidence_add` with exact quotes from the full body text.

**Investigation mode** — deep analysis, building a case:
1. `email_search_structured` with filters (sender, date, folder, attachment, category).
2. `email_thread_summary`, `email_action_items`, `email_decisions` for thread analysis.
3. `relationship_paths`, `coordinated_timing`, `email_entity_timeline` for connections.
4. `evidence_add` / `evidence_add_batch` to collect evidence. `email_dossier` to export.

**Progressive investigation** — multi-pass with dedup (recommended for thorough scans):
1. Pick a `scan_id` (e.g., `"harassment_case"`). Pass it to all triage/search calls.
2. **Phase 1 (Scan):** 3-5 `email_triage(scan_id=...)` calls — server auto-deduplicates across calls.
3. **Phase 2 (Refine):** `email_search_structured(scan_id=...)` + `email_find_similar(scan_id=...)` — only unseen results appear.
4. `email_scan(action='flag', uids=[...], label='bossing', phase=1)` to mark candidates.
5. **Phase 3 (Deep):** `email_scan(action='candidates')` → `email_deep_context` on each → `evidence_add_batch`.
6. `email_scan(action='status')` for session overview at any time.

**Quick lookup** — known email or person:
`email_deep_context` for a known UID. `email_find_similar` to surface patterns from one email.

## Response Truncation

Bodies are truncated to ~500 chars in search/browse results. Use `email_deep_context` to read complete text (soft-limited to 10K chars). Total responses are capped at ~8K tokens — narrow your search if results are omitted. All limits are configurable via env vars (`MCP_MAX_BODY_CHARS`, `MCP_MAX_RESPONSE_TOKENS`, `MCP_MAX_FULL_BODY_CHARS`). Set `MCP_MODEL_PROFILE` to `haiku`, `sonnet`, or `opus` to auto-tune all budget knobs for the calling model's context size (default: `auto` = sonnet). Per-variable env overrides always take precedence over profiles.

## Evidence Categories

Use these canonical categories with `evidence_add`:

- `bossing` — intimidation, power abuse, unreasonable demands
- `harassment` — hostile behavior, bullying, unwanted conduct
- `discrimination` — unequal treatment based on protected characteristics
- `retaliation` — punishment for reporting or complaining
- `hostile_environment` — toxic workplace patterns
- `micromanagement` — excessive control, undermining autonomy
- `exclusion` — deliberate isolation from meetings, decisions, information
- `gaslighting` — denying facts, rewriting history, questioning competence
- `workload` — unreasonable assignments, impossible deadlines
- `general` — other relevant evidence

## Relevance Scores

- **5** — direct proof, strongest evidence
- **4** — strong evidence, clear pattern
- **3** — supporting evidence, adds context
- **2** — background information, minor relevance
- **1** — tangential, worth preserving

## Tips

- Always cite the email UID, sender, date, and subject when presenting results.
- Use `email_find_similar` after finding one relevant email — it surfaces patterns.
- Use `relationship_paths` and `coordinated_timing` to show connections between people.
- Use `email_entity_timeline` to show trends over time.
- When the user asks to collect evidence, search first, then offer to mark relevant results.
- When building a dossier, collect evidence items first — the dossier generator pulls from the evidence collection automatically.
- The evidence system tracks who added each item and when; each quote is verified against the source email body.
