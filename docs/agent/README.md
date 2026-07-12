# Advanced Agent Documentation

This subtree contains advanced legal-support product docs, operator runbooks, synthetic fixtures, evaluation goldens, and archive/history material. It is not the default public reading path; start with [`../README.md`](../README.md) for product and operations documentation.

All checked-in examples in this subtree must remain synthetic. Do not add personal records, private actor names, institution-specific references, real mailbox excerpts, screenshots from live data, or local machine paths.

## Product And Contract Docs

- [`case_full_pack.md`](case_full_pack.md)
- [`review_governance.md`](review_governance.md)
- [`matter_evidence_index.md`](matter_evidence_index.md)
- [`master_chronology.md`](master_chronology.md)
- [`lawyer_issue_matrix.md`](lawyer_issue_matrix.md)
- [`lawyer_briefing_memo.md`](lawyer_briefing_memo.md)
- [`case_dashboard.md`](case_dashboard.md)

## Operator Runbooks

- [`Plan.md`](Plan.md)
- [`email_matter_analysis_single_source_of_truth.md`](email_matter_analysis_single_source_of_truth.md)
- [`runtime_path_remediation_plan.md`](runtime_path_remediation_plan.md)
- [`question_execution_companion.md`](question_execution_companion.md)
- [`question_execution_prompt_pack.md`](question_execution_prompt_pack.md)
- [`question_execution_query_packs.md`](question_execution_query_packs.md)
- [`post_harvest_evidence_refinement_manual.md`](post_harvest_evidence_refinement_manual.md)
- [`question_register_template.md`](question_register_template.md)
- [`open_tasks_companion_template.md`](open_tasks_companion_template.md)
- [`email_matter_investigation_checkpoint_template.md`](email_matter_investigation_checkpoint_template.md)
- [`mcp_client_config_snippet.md`](mcp_client_config_snippet.md)

## Synthetic Fixtures And Eval Assets

- `prompt_fixture.*.md`
- `legal_support_full_pack_golden.*.json`
- `qa_eval_*.json`

The historical `.live.json` suffix identifies frozen regression scenarios; it
does not mean the files contain a live mailbox or private matter data. All
tracked eval assets remain synthetic. Actual live QA output belongs under the
ignored `private/tests/results/qa_eval/` workspace.

## Archive Material

- [`../archive/2026-05-16-remediation-closure/agent-deprecated/deprecated/`](../archive/2026-05-16-remediation-closure/agent-deprecated/deprecated/)
  preserves audit-era docs and path shims as historical context.
- `archive/`, `implementation_log/`, `plan_history/`, and `matter_analysis/`
  are ignored local work areas unless explicitly promoted. Keep local status,
  ledger, Codacy, and remediation snapshots there when they include local paths
  or dirty-checkout evidence.

Local verification logs and audit/remediation ledgers belong in the ignored
work areas above, not in this tracked public subtree.
