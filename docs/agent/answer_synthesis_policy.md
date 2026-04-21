# Answer Synthesis Policy

Internal policy for answering mailbox questions from `email_answer_context`.

This is the AQ7 contract. It is answer-policy guidance, not a full natural-language answer generator.

## Goals

- Keep answer phrasing consistent.
- Verify exact wording against stronger evidence before quoting or overclaiming.
- Limit citations to the strongest necessary evidence.
- Degrade explicitly on ambiguous or weak-evidence cases.

## Decision states

### `answer`

Use when:

- `answer_quality.confidence_label` is not `low`
- the bundle is not marked ambiguous
- the bundle is not dominated by weak-message evidence

Default phrasing:

- high confidence: `The evidence strongly indicates`
- medium confidence: `The available evidence suggests`

### `ambiguous`

Use when:

- `answer_quality.confidence_label == "ambiguous"`
- or the top candidates are too close to support one confident answer

Required behavior:

- do not collapse to one unsupported claim
- cite up to the top `2` candidates
- state the ambiguity explicitly

Default phrasing:

- `The available evidence is ambiguous`

### `insufficient_evidence`

Use when:

- `answer_quality.confidence_label == "low"`
- the ambiguity reason is `no_evidence`, `weak_top_score`, or `weak_scan_body`
- or the bundle is marked as weak evidence:
  - `image_only`
  - `source_shell_only`
  - `metadata_only_reply`
  - `true_blank`
  - weak attachment reference without extracted text

Required behavior:

- identify the likely message only when that is still supportable
- do not state message content confidently
- cite at most one candidate

Default phrasing:

- `I can identify the likely message, but the available evidence is too weak to state the content confidently.`

## Verification mode rules

### `already_forensic`

Use when:

- the requested `evidence_mode` is already `forensic`

### `verify_forensic`

Use when:

- the question appears to ask for exact wording
- the bundle is ambiguous
- the bundle is weak enough that retrieval-only evidence is not sufficient

Exact-wording triggers include:

- `exactly`
- `exact wording`
- `what did`
- `quote`
- `quoted`
- `verbatim`

### `retrieval_ok`

Use when:

- the question is not exact-wording sensitive
- the bundle is not weak
- and the confidence state is strong enough to answer from the retrieval bundle

## Citation policy

- `answer`: cite the top `1` candidate
- `ambiguous`: cite up to the top `2` candidates
- `insufficient_evidence`: cite the top `1` candidate at most

The cited UID list comes from:

1. `answer_quality.top_candidate_uid`
2. `answer_quality.alternative_candidates`

## Overclaim policy

Always set:

- `refuse_to_overclaim = true`

This is intentional. The answer layer should be conservative by default, even when confidence is high.

## Scope boundary

This policy defines:

- decision state
- verification mode
- citation count
- core phrasing hooks

This policy does not define:

- the final external response format
- full citation rendering syntax
- long-form answer composition

Those stay in AQ10.
