# QA Evaluation Plan

This document defines the first end-to-end evaluation phase for `email_answer_context`.

## Goal

Measure whether the current Outlook email MCP can answer real mailbox questions with:

- relevant top candidates
- correct supporting evidence
- honest ambiguity handling
- usable attachment/thread behavior

This phase is intentionally evaluation-first. It should decide the next implementation priority from evidence instead of adding more answer features blindly.

## Scope

Use the current `email_answer_context` contract as-is.

Do not change retrieval or parser behavior inside this phase.

Evaluate four question buckets:

1. `fact_lookup`
   - direct factual lookup from message body or metadata
2. `thread_process`
   - chronology, replies, thread evolution, and conversation stitching
3. `attachment_lookup`
   - questions whose answer may live in attachment-derived evidence
4. `ambiguity_stress`
   - close subjects, forwarded chains, quoted replies, image-only/source-shell cases, and weak-evidence scenarios

## Evaluation assets

1. Question set
   - `docs/agent/qa_eval_questions.template.json`
   - starts as a labeled template with `25` cases
   - expected answers/supporting UIDs remain operator-filled until a live corpus pass is done

2. Runner
   - `scripts/run_qa_eval.py`
   - supports:
     - `--results` for scoring captured `email_answer_context` payloads offline
     - `--live` for calling the current answer-context path through the repo's `ToolDeps`

3. Scoring helper
   - `src/qa_eval.py`
   - loads cases
   - scores support-UID hits, top-UID match, and ambiguity handling
   - emits a compact machine-readable report

## Case labeling contract

Each question case should eventually capture:

- `id`
- `bucket`
- `question`
- `status`
- `evidence_mode`
- optional `filters`
- `expected_answer`
- `expected_support_uids`
- `expected_top_uid`
- `expected_ambiguity`
- `notes`

Until the live corpus is reviewed, template cases stay in `status = "todo"`.

## First-pass success criteria

The first useful live run should report at least:

- top supporting UID present in top `3` for most fully labeled fact cases
- ambiguity surfaced on known ambiguous cases
- no false-confident handling on known weak/insufficient-evidence cases
- attachment questions marked weak or ambiguous when extraction is unavailable

This is not a publish gate yet. It is a prioritization tool.

## Recommended workflow

1. Fill the template with real expected UIDs and ambiguity expectations.
2. Run a captured/offline scoring pass first if live retrieval is not ready.
3. Run a live pass once the local DB/vector index is populated.
4. Review failures bucket-by-bucket:
   - fact failures -> retrieval or ranking
   - thread failures -> thread stitching / quoted attribution
   - attachment failures -> extraction / indexing / attachment ranking
   - ambiguity failures -> confidence policy / answer-quality calibration

## Commands

Offline scoring of captured payloads:

```bash
python scripts/run_qa_eval.py \
  --questions docs/agent/qa_eval_questions.template.json \
  --results path/to/captured_answer_context_payloads.json
```

Live scoring against the local repo state:

```bash
python scripts/run_qa_eval.py \
  --questions docs/agent/qa_eval_questions.template.json \
  --live
```

Write a report artifact:

```bash
python scripts/run_qa_eval.py \
  --questions docs/agent/qa_eval_questions.template.json \
  --results path/to/captured_answer_context_payloads.json \
  --output docs/agent/qa_eval_report.json
```

## Known limits

- A useful live run still depends on a populated local SQLite/vector state.
- `--live` evaluates the current answer-context path, but it does not solve missing local model/index state.
- The first version scores structural answer quality only:
  - support UID hit
  - top UID match
  - ambiguity handling

It does not yet grade free-form final answer wording.
