# Answer Grounding and Citations

`email_answer_context` builds a bounded evidence bundle and a deterministic
answer contract. It does not treat a retrieval score as proof, and it does not
train on mailbox content or queries.

## Decision states

The response uses one of three states:

| State | Meaning | Citation limit |
| --- | --- | --- |
| `answer` | The strongest evidence is sufficiently clear. | One reference |
| `ambiguous` | Multiple candidates remain plausible. | Up to two references |
| `insufficient_evidence` | The available body, attachment text, or score is too weak for a supported claim. | At most one likely reference |

The payload exposes the same decision through `answer_policy`,
`final_answer_contract`, and `final_answer`. Downstream clients should
preserve the decision instead of rewriting an ambiguous or weak result as a
confident answer.

## Verification modes

- `retrieval_ok` means the current retrieval bundle is adequate for the
  requested answer.
- `verify_forensic` means the client should request stronger source context
  before relying on exact wording.
- `already_forensic` means the request already used forensic evidence mode.

Exact-wording requests, medium-confidence results, ambiguous candidates, and
weak-message cases require forensic verification unless that mode is already
active.

## Citations

Rendered answers cite an evidence handle when one is available:

```text
[ref:<EVIDENCE_HANDLE>]
```

When no evidence handle exists, the fallback is the email UID:

```text
[uid:<EMAIL_UID>]
```

Only references listed by `final_answer_contract.required_citation_handles` or
`required_citation_uids` may be cited.

## Quoted-message attribution

Authored text and quoted history remain separate. Quote ownership can be:

- `explicit_header`
- `corroborated_reply_context`
- `inferred_single_candidate`
- `participant_exclusion`
- `unresolved`

The last three states are inferential or unresolved and lower the strength of
quote-driven findings. Quoted text is not automatically weak, but ownership
must be explicit or corroborated before a client presents it as certain.

## Review boundary

Always verify important conclusions against the original message or
attachment. OCR, truncated bodies, attachment-only messages, reconstructed
threads, and inferred quote ownership can all reduce confidence.
