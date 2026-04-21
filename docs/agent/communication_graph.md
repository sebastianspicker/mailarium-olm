# BA10 Communication Graph

Version: `1`

This BA10 layer adds graph-based communication evidence on top of earlier text and behavior analysis. It is still conservative and should not be treated as a final hostile-pattern conclusion on its own.

## Output sections

- `nodes`
  - sender and recipient graph nodes
- `edges`
  - sender-to-recipient communication edges with channel counts and UID traces
- `graph_findings`
  - graph-based finding objects kept separate from rhetoric and behaviour layers

## Graph-based finding types

### `repeated_exclusion`

- same sender repeatedly appears in messages where the target is absent from visible recipients
- evidence basis:
  - `graph_plus_behavior`

### `visibility_asymmetry`

- same sender sometimes includes the target and sometimes excludes them
- evidence basis:
  - `graph_only`

### `selective_escalation`

- same sender uses multi-recipient escalation or correction patterns in target-related messages
- evidence basis:
  - `graph_plus_behavior`

### `forked_side_channel`

- same sender shows both included and excluded target communication inside the same thread group
- evidence basis:
  - `graph_only`

## Boundaries

- BA10 separates graph findings from language and behaviour findings.
- Graph findings are still conditional and can have neutral operational explanations.
- Later BA phases still need stronger evidence scoring, multi-source corroboration, and report-level interpretation policy.
