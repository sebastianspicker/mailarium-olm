# Lawyer Issue Matrix

## Goal

Provide a first-class German employment lawyer issue matrix that maps the current record to legal relevance without giving final legal advice.

## Output

`lawyer_issue_matrix`

Fields:

- `version`
- `row_count`
- `rows`

Each row contains:

- `issue_id`
- `title`
- `legal_relevance_status`
- `relevant_facts`
- `strongest_documents`
- `likely_opposing_argument`
- `missing_proof`
- `urgency_or_deadline_relevance`
- `source_conflict_status`
- `unresolved_source_conflicts`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`
- `supporting_source_ids`
- `not_legal_advice`

## Covered issues

- `eingruppierung_tarifliche_bewertung`
- `agg_disadvantage`
- `burden_shifting_indicators`
- `retaliation_massregelungsverbot`
- `sgb_ix_164`
- `sgb_ix_167_bem`
- `sgb_ix_178_sbv`
- `pr_lpvg_participation`
- `fuersorgepflicht`

## Rules

- The matrix is a legal-relevance mapping layer only.
- It must reuse existing issue frameworks, findings, comparator signals, and exhibit-register rows.
- It must surface missing proof and a likely opposing argument for every row.
- `strongest_documents` prefers explicit evidence linkage first:
  - matching `supporting_finding_ids`
  - matching `supporting_citation_ids`
  - matching `supporting_uids`
  - matching issue-tag linkage
- keyword-only document matches remain allowed as a fallback, but each strongest-document entry must mark its `selection_basis`.
- strongest-document entries must carry at least:
  - `exhibit_id`
  - `source_id`
  - `selection_basis`
  - `supporting_finding_ids`
  - `supporting_citation_ids`
- It must not state that a claim is won, proven, or legally established.
- `not_legal_advice` stays `true` on every row.
