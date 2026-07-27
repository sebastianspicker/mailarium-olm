# QA Evaluation Fixture Provenance

The retained fixtures in this directory are intentionally authored synthetic regression data.
No operator mailbox export, customer dataset, production message store, or
private runtime artifact was used to create them.

The four captured scenarios exercise distinct contracts:

- `core`: fact, thread, attachment, ambiguity, grounding, and negative-control
  behavior.
- `quote`: quoted-speaker attribution.
- `inferred_thread`: inferred-only thread grouping.
- `attachment_ocr`: OCR-positive and OCR-negative attachment handling.

Core message identifiers are deterministic truncated SHA-256 values derived
from the namespace `outlook-email-rag-alpha:<scenario-name>`. The exact
scenario-name-to-UID mapping is stored in `uid_seed_manifest` at the top of
`qa_eval_questions.core.json` and is verified by a repository contract test.
The other captured scenarios use visibly synthetic symbolic identifiers and
reserved example email domains. The template file contains generic, unlabeled
questions for local evaluation setup.

Captured reports are derived only from their paired question and result JSON
files. Refresh or verify them with:

```bash
python3.14 scripts/refresh_qa_eval_captured_reports.py
python3.14 scripts/refresh_qa_eval_captured_reports.py --check
```

Do not publish evaluation material adapted from operator data by merely
renaming, redacting, or relabeling it as synthetic. Add newly authored cases
instead.
