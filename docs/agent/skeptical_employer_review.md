# Skeptical Employer-Side Review

## Goal

Stress-test the claimant-side case from an employer-side review angle, then pair each weakness with conservative repair guidance.

## Output

`skeptical_employer_review`

Fields:

- `version`
- `summary`
  - `weakness_count`
  - `weakness_categories`
- `weaknesses`

Each weakness contains:

- `weakness_id`
- `category`
- `critique`
- `why_it_matters`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`
- `repair_guidance`
  - `how_to_fix`
  - `evidence_that_would_repair`
  - `cautious_rewrite`

## Covered weakness classes

- chronology problems
- overstated comparisons
- alternative explanations
- missing documentation
- factual leaps
- unsupported motive claims
- weak legal-to-evidence linkage
- internal inconsistency
- ordinary management explanations

## Rules

- This is a disciplined weaknesses memo, not a defense holding.
- Every criticism must be paired with a repair path.
- `cautious_rewrite` must reduce overstatement directly.
- The output stays evidence-bound and should never invent employer-side facts.
