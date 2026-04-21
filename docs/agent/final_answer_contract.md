# Final Answer Contract

Outward response contract for MCP-client mailbox answers built from `email_answer_context`.

This is the AQ10 contract. It sits on top of the AQ7 internal `answer_policy`.

## Goal

Keep user-facing answers consistent, citable, and honest under three states:

- `answer`
- `ambiguous`
- `insufficient_evidence`

## Scope boundary for case analysis

This contract governs short mailbox answers built from `email_answer_context`.

It does not govern the dedicated `email_case_analysis` workflow. That workflow must use the case-analysis report contract instead of compressing serious workplace-review output into the AQ10 single-paragraph answer shapes.

For avoidance of doubt:

- `email_case_analysis` must not present high-stakes workplace review as a generic direct-answer paragraph
- bounded case-review classifications belong to the investigation-style case-analysis report, not to AQ10
- AQ10 remains valid for ordinary mailbox question answering only

## Answer format

### `answer`

- shape: `single_paragraph`
- begin with the confidence wording from `answer_policy.confidence_phrase`
- answer the question directly
- cite at sentence end
- cite at most `1` UID unless a future contract explicitly widens that

Example shape:

`The evidence strongly indicates that Alice approved the rollout on 2025-06-05. [uid:abc123]`

### `ambiguous`

- shape: `two_short_paragraphs`
- first paragraph:
  - state the ambiguity clearly
  - avoid collapsing to one unsupported claim
- second paragraph:
  - name the strongest competing interpretations
  - cite up to `2` UIDs

Example shape:

`The available evidence is ambiguous. Two nearby messages plausibly answer the question. [uid:abc123] [uid:def456]`

### `insufficient_evidence`

- shape: `single_paragraph`
- state the fallback wording clearly
- do not state message content confidently
- cite at most `1` UID if one likely message can still be identified

Example shape:

`I can identify the likely message, but the available evidence is too weak to state the content confidently. [uid:abc123]`

## Citation format

- style: `inline_uid_brackets`
- required pattern: `[uid:<EMAIL_UID>]`
- sentence placement:
  - put citations at the end of the sentence they support
- attribution rule:
  - only cite UIDs from `final_answer_contract.required_citation_uids`

## Confidence wording

Use the wording already derived in `answer_policy`.

- high-confidence answer:
  - `The evidence strongly indicates`
- medium-confidence answer:
  - `The available evidence suggests`
- insufficient-evidence case:
  - `The available evidence is limited`

## Ambiguity wording

Use:

- `The available evidence is ambiguous`

Do not soften this into a confident claim.

## Fallback wording

Use:

- `I can identify the likely message, but the available evidence is too weak to state the content confidently.`

This is the default weak-evidence fallback for:

- `image_only`
- `source_shell_only`
- `metadata_only_reply`
- `true_blank`
- weak attachment references without extracted text

## Refusal to overclaim

Always honor:

- `final_answer_contract.refuse_to_overclaim = true`

If the evidence is ambiguous or insufficient, the outward answer must stay ambiguous or insufficient.

## Scope boundary

This contract defines:

- outward answer shape
- outward citation syntax
- outward confidence / ambiguity / fallback wording

This contract does not define:

- natural-language style beyond the required structure
- multi-turn conversation strategy
- UI rendering
