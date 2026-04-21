# Case Analysis Implementation Spec

Version: `1`

Status: `approved_for_implementation`

This document freezes the `P0` contract for implementing a serious workplace case-analysis workflow on top of the existing email RAG and behavioural-analysis surface.

It defines:

- the product boundary
- the operator-facing MCP and CLI contracts
- the required intake schema
- the required output contract
- downgrade and overclaiming rules
- implementation boundaries for `P1` and later milestones

It does not define internal code structure beyond what is necessary to keep the interface stable.

## 1. Product boundary

The target workflow is:

- evidence-based review of workplace communications
- focused on potentially hostile, exclusionary, retaliatory, discriminatory, manipulative, or mobbing-like patterns
- suitable for:
  - `internal_review`
  - `hr_review`
  - `lawyer_briefing`
  - `formal_complaint`
  - `neutral_chronology`

The workflow is not:

- a legal decision engine
- a motive inference engine
- a generic “summarize all communications” helper
- a replacement for manual HR or legal review

The system must remain conservative:

- facts must be separated from interpretation
- interpretation must be separated from speculation
- legal conclusions must not be asserted from this layer alone

## 1.1 Bounded final assessment categories

The dedicated workflow must classify the current record using one bounded review category as the primary assessment.

Allowed primary assessment values:

- `ordinary_workplace_conflict`
- `poor_communication_or_process_noise`
- `targeted_hostility_concern`
- `unequal_treatment_concern`
- `retaliation_concern`
- `discrimination_concern`
- `mobbing_like_pattern_concern`
- `insufficient_evidence`

Meaning:

- `ordinary_workplace_conflict`
  - interpersonal or professional conflict is present, but the current record does not support a stronger targeted-pattern reading
- `poor_communication_or_process_noise`
  - the record is better explained by disorganization, ambiguity, inconsistency, or weak process rather than targeted mistreatment
- `targeted_hostility_concern`
  - the record suggests repeated or focused hostile treatment toward one person, but not necessarily retaliation, discrimination, or mobbing-like conduct
- `unequal_treatment_concern`
  - the record suggests materially different treatment compared with relevant comparators, while remaining below a stronger discrimination conclusion
- `retaliation_concern`
  - the record suggests adverse treatment after a defined trigger event, subject to explicit before/after and confounder limits
- `discrimination_concern`
  - the record suggests unequal or hostile treatment plausibly linked to a protected-context allegation or explicit discriminatory content, but still does not amount to a legal finding
- `mobbing_like_pattern_concern`
  - the record suggests a repeated, multi-signal pattern of exclusion, undermining, pressure, or humiliation that is more consistent with a mobbing-like pattern than with isolated conflict
- `insufficient_evidence`
  - the available record does not support a reliable stronger interpretation

The workflow may also return secondary plausible interpretations, but it must not collapse multiple plausible categories into one confident unsupported label.

## 1.2 Hard product limits

The dedicated workflow must not:

- decide legal liability
- decide whether a legal standard is conclusively met
- infer motive from hostility alone
- infer discrimination from generic interpersonal conflict alone
- infer retaliation from chronology alone without a defined trigger event and measurable adverse shift
- infer mobbing-like pattern concern from a single message or weak isolated indicators

## 1.3 Minimum closing blocks

Every final case-analysis report must end with all of the following blocks in visible form:

- neutral factual summary
- strongest indicators of problematic conduct
- strongest counterarguments
- overall assessment
- missing evidence important for HR or legal review

## 2. Primary user problem

An operator wants to submit a structured case scope plus a set of relevant communications and receive:

- per-message analysis
- cross-message pattern analysis
- chronology
- language and behaviour findings
- power/context analysis
- evidence table with citations
- overall cautious assessment
- explicit missing-information and downgrade reasons

## 3. Dedicated surfaces

## 3.1 MCP tool

Add one dedicated MCP tool:

- `email_case_analysis`

Purpose:

- run a full case-scoped analysis in one call
- return one coherent case-analysis payload
- wrap the existing behavioural-analysis building blocks instead of requiring manual orchestration through generic search tools

The initial implementation may internally reuse:

- `email_answer_context`
- `build_case_bundle(...)`
- `build_multi_source_case_bundle(...)`
- `build_power_context(...)`
- `build_case_patterns(...)`
- `build_retaliation_analysis(...)`
- `build_comparative_treatment(...)`
- `build_behavioral_evidence_chains(...)`
- `apply_behavioral_strength(...)`
- `build_investigation_report(...)`

But the outward contract must be stable under the dedicated tool name.

## 3.2 CLI surface

Add one dedicated CLI family:

- `python -m src.cli case analyze`

Purpose:

- expose the same structured workflow outside MCP
- allow reproducible local analysis and export from Terminal

The CLI must support:

- passing a structured intake file
- choosing output format
- optionally writing the full report to disk

Recommended command shape:

```bash
python -m src.cli case analyze \
  --input case.json \
  --format json \
  --output case-analysis.json
```

Optional later CLI subcommands may include:

- `python -m src.cli case validate --input case.json`
- `python -m src.cli case template`

But `case analyze` is the required `P1` entrypoint.

## 4. Intake contract

## 4.1 Required fields

The dedicated workflow must require all of the following:

- `target_person`
- `allegation_focus`
- `analysis_goal`
- `date_from`
- `date_to`

Rationale:

- serious case analysis should not silently run across an undefined time period
- the target person and intended use materially affect interpretation and downgrade behavior

## 4.2 Strongly recommended fields

The workflow must accept these as optional input fields, but it must emit structured completeness warnings if they are missing:

- `suspected_actors`
- `comparator_actors`
- `trigger_events`
- `org_context`
- `context_notes`

The warnings must be machine-readable and visible in the final report.

## 4.3 Required source-set declaration

The dedicated workflow must require the operator to declare source intent.

Required field:

- `source_scope`

Allowed initial values:

- `emails_only`
- `emails_and_attachments`
- `mixed_case_file`

Meaning:

- `emails_only`
  - analyze only email bodies and email-derived metadata
- `emails_and_attachments`
  - include email bodies plus attachment and formal-document evidence
- `mixed_case_file`
  - reserved for later mixed-source ingestion, including chat logs and non-email materials

If the selected `source_scope` asks for source types not actually present, the system must disclose that gap explicitly.

## 4.4 Required case-intake schema

The dedicated tool should accept a top-level payload in this shape:

```json
{
  "case_scope": {
    "case_label": "optional short label",
    "target_person": {
      "name": "employee",
      "email": "employee@example.test",
      "role_hint": "employee"
    },
    "suspected_actors": [
      {
        "name": "manager",
        "email": "manager@example.test",
        "role_hint": "manager"
      }
    ],
    "comparator_actors": [
      {
        "name": "Alex Beispiel",
        "email": "alex@example.org",
        "role_hint": "peer"
      }
    ],
    "allegation_focus": [
      "retaliation",
      "exclusion",
      "unequal_treatment"
    ],
    "analysis_goal": "lawyer_briefing",
    "date_from": "2025-01-01",
    "date_to": "2025-06-30",
    "context_notes": "Short neutral background context.",
    "trigger_events": [
      {
        "trigger_type": "complaint",
        "date": "2025-03-14",
        "actor": {
          "name": "employee",
          "email": "employee@example.test",
          "role_hint": "employee"
        },
        "notes": "Formal complaint submitted to supervisor."
      }
    ],
    "org_context": {
      "role_facts": [],
      "reporting_lines": [],
      "dependency_relations": [],
      "vulnerability_contexts": []
    }
  },
  "source_scope": "emails_and_attachments",
  "include_message_appendix": true,
  "compact_case_evidence": false,
  "output_mode": "full_report"
}
```

## 4.5 Input validation rules

The dedicated workflow must enforce:

- `date_from <= date_to`
- `target_person` must not duplicate a comparator or suspected actor by email when email is present
- `allegation_focus` must be non-empty
- `analysis_goal` must be one of the supported review modes
- `source_scope` must be one of the declared values

The dedicated workflow must also emit warnings for:

- missing `suspected_actors`
- missing `trigger_events` when `allegation_focus` contains `retaliation`
- missing `comparator_actors` when `allegation_focus` contains `discrimination` or `unequal_treatment`
- missing `org_context` when `analysis_goal` is `hr_review`, `lawyer_briefing`, or `formal_complaint`

## 5. Output contract

## 5.1 Top-level output

The dedicated tool must return a top-level payload containing:

- `case_analysis_version`
- `workflow`
- `case_bundle`
- `case_scope_quality`
- `multi_source_case_bundle`
- `power_context`
- `case_patterns`
- `retaliation_analysis`
- `comparative_treatment`
- `finding_evidence_index`
- `evidence_table`
- `behavioral_strength_rubric`
- `investigation_report`
- `message_appendix`
- `analysis_limits`

Recommended top-level constants:

- `case_analysis_version = "1"`
- `workflow = "case_analysis"`

## 5.2 Mandatory report sections

The final report must include these sections in order:

1. `executive_summary`
2. `chronological_pattern_analysis`
3. `language_analysis`
4. `behaviour_analysis`
5. `power_context_analysis`
6. `evidence_table`
7. `overall_assessment`
8. `missing_information`

This stays aligned with the existing investigation report renderer.

## 5.3 Mandatory message appendix

The dedicated workflow must add a first-class `message_appendix`.

Purpose:

- satisfy the Level 1 requirement for individual message analysis
- make the output useful for HR and legal review
- avoid hiding important weak signals behind only aggregated findings

Each `message_appendix.rows[*]` entry must include:

- `uid`
- `date`
- `sender`
- `recipients_summary`
- `subject`
- `message_level_summary`
- `language_signals`
- `behavior_candidates`
- `evidence_strength`
- `counter_indicators`
- `alternative_explanations`
- `supporting_citation_ids`

Initial implementation rule:

- if `include_message_appendix = true`, the appendix is mandatory
- if `include_message_appendix = false`, the payload must still disclose that message-level rows were omitted on purpose

## 5.4 Assessment language

The overall assessment must:

- name one primary assessment from the bounded category list in `1.1`
- state any secondary plausible interpretations when the evidence is mixed
- state whether the material is more consistent with ordinary conflict, poor communication, targeted hostility, unequal treatment, retaliation concern, discrimination concern, mobbing-like pattern concern, or insufficient evidence
- explain why using evidence-backed language
- include the strongest counterarguments
- explicitly disclose when evidence is mixed

The overall assessment must not:

- assert legal liability
- assert motive without support
- collapse weak indicators into a definitive conclusion
- use `discrimination_concern` unless explicit discriminatory content, strong comparator asymmetry, or protected-context evidence materially supports it
- use `retaliation_concern` unless at least one trigger event and one before/after adverse-shift signal are present
- use `mobbing_like_pattern_concern` unless recurrence and multi-signal support are both present

## 6. Case-scope quality block

The dedicated workflow must return a machine-readable intake quality block:

```json
{
  "status": "complete | degraded | insufficient",
  "required_fields_present": [],
  "missing_required_fields": [],
  "recommended_fields_present": [],
  "missing_recommended_fields": [],
  "downgrade_reasons": [],
  "supports_retaliation_analysis": true,
  "supports_comparator_analysis": false,
  "supports_power_analysis": true
}
```

Purpose:

- prevent operators from overtrusting under-scoped runs
- provide stable downgrade hooks for the report and CLI exit summary

## 7. Evidence and citation rules

Every non-trivial finding must trace back to concrete evidence through:

- `finding_id`
- `citation_id`
- `uid`

Each message-level and case-level finding must carry:

- `evidence_strength`
- `counter_indicators`
- `alternative_explanations`

Where evidence is weak or contradictory:

- the report must downgrade interpretation level
- the message appendix must preserve that downgrade visibly

## 8. Overclaiming guardrails

The dedicated workflow must inherit the current interpretation policy and keep these hard rules:

- no legal conclusions
- no motive claims without specific support
- no direct assertion of coordination from pattern flags alone
- no direct assertion of discrimination from unequal-treatment heuristics alone
- no retaliation claim stronger than the available trigger-linked evidence supports
- no mobbing-like pattern concern from single-message evidence alone
- no protected-category inference unless the current record or structured intake supplies it
- no psychiatric, character, or diagnosis-style labels for actors

## 9. Initial non-goals

The first implementation does not need to deliver all future enhancements.

Specifically out of scope for `P1`:

- standalone legal qualification
- automatic discrimination-ground inference
- fully mature response-time pairing
- advanced comparator matching beyond the current conservative baseline
- production-grade chat ingestion
- multilingual ML classification

These remain later milestones.

## 10. Required implementation boundaries for P1

`P1` is done when all of the following are true:

- a dedicated MCP entrypoint exists
- a dedicated CLI entrypoint exists
- the required intake schema is enforced
- the output contains one coherent case-analysis payload
- the output contains the report and the message appendix
- missing critical inputs produce explicit validation failure or downgrade markers
- the workflow can be invoked end-to-end from one command or one MCP call

## 11. Verification expectations for P1

At minimum, `P1` verification should include:

- model validation tests for required and invalid intake payloads
- MCP tool tests for minimal valid case and rich case
- CLI tests for `case analyze`
- one end-to-end smoke probe using a representative case fixture

Required final reporting:

- distinguish introduced failures from pre-existing failures
- end with:
  - `VERDICT: PASS`
  - `VERDICT: FAIL`
  - `VERDICT: PARTIAL`

## 12. Implementation notes

- Prefer reusing the existing behavioural-analysis builders instead of inventing a parallel stack.
- Keep the dedicated surface thin and explicit.
- Favor deterministic output ordering for report sections and message appendix rows.
- Do not widen the contract during `P1`; new analytical ambitions belong to later milestones unless they are required to make the dedicated workflow coherent.
