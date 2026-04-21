# Investigation Report Format

## Version

- `1`

## Goal

Render a structured investigation-style report from the existing case-scoped behavioural-analysis payload without inventing new evidence beyond BA1 to BA15.

## Top-level contract

`investigation_report` is emitted only for case-scoped `email_answer_context` responses.

Fields:

- `version`
- `report_format`
  - `investigation_briefing`
- `section_order`
- `summary`
  - `section_count`
  - `supported_section_count`
  - `insufficient_section_count`
- `report_highlights`
  - `strongest_indicators`
  - `strongest_counterarguments`
- `deadline_warnings`
- `sections`

`deadline_warnings` is the shared operational timing-risk payload.

When present it contains:

- `version`
- `as_of_date`
- `overall_status`
  - `no_material_timing_warning`
  - `timing_review_recommended`
- `summary`
  - `warning_count`
  - `high_severity_count`
  - `categories`
- `warnings`

## Section order

1. `executive_summary`
2. `evidence_triage`
3. `chronological_pattern_analysis`
4. `language_analysis`
5. `behaviour_analysis`
6. `power_context_analysis`
7. `evidence_table`
8. `matter_evidence_index`
9. `employment_issue_frameworks`
10. `lawyer_issue_matrix`
11. `actor_and_witness_map`
12. `witness_question_packs`
13. `promise_and_contradiction_analysis`
14. `lawyer_briefing_memo`
15. `controlled_factual_drafting`
16. `case_dashboard`
17. `cross_output_consistency`
18. `skeptical_employer_review`
19. `document_request_checklist`
20. `overall_assessment`
21. `missing_information`

## Section contract

Each section contains:

- `section_id`
- `title`
- `status`
  - `supported`
  - `insufficient_evidence`
- `entries`
- `insufficiency_reason`

Each `entries[*]` object contains:

- `entry_id`
- `statement`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`

Rule:

- every supported section must carry at least one entry
- every entry must either point to supporting evidence through `finding_id`, `citation_id`, or `uid`
- insufficient sections must state an explicit `insufficiency_reason`

## Power and context section contract

`sections.power_context_analysis` may now also expose `comparator_matrix`.

When present, `comparator_matrix` contains:

- `row_count`
- `rows`

Rules:

- the report-facing comparator matrix is derived from `comparative_treatment.comparator_summaries[*].comparator_matrix`
- rows remain evidence-bound comparison points rather than final unequal-treatment conclusions
- weak or non-comparable rows must remain visible as weak or not comparable instead of being silently dropped

## Chronological pattern section contract

`sections.chronological_pattern_analysis` remains the narrative chronology section and may now also embed `master_chronology`.

When present, embedded `master_chronology` contains:

- `version`
- `entry_count`
- `summary`
- `entries`
- `views`

`sections.chronological_pattern_analysis` may also embed `retaliation_timeline_assessment`.

When present, embedded `retaliation_timeline_assessment` contains:

- `version`
- `protected_activity_timeline`
- `adverse_action_timeline`
- `temporal_correlation_analysis`
- `strongest_retaliation_indicators`
- `strongest_non_retaliatory_explanations`
- `overall_evidentiary_rating`

Rules:

- chronology prose remains the reviewer-facing narrative summary
- embedded `master_chronology` is the machine-readable chronology registry for later reuse
- chronology entries must keep `date_precision` and source linkage instead of flattening dates into narrative-only text
- chronology summary may also expose ranked `date_gaps_and_unexplained_sequences` for later dossier prioritization
- embedded `views` may expose:
  - `short_neutral_chronology`
  - `claimant_favorable_chronology`
  - `defense_favorable_chronology`
  - `balanced_timeline_assessment`
- embedded `retaliation_timeline_assessment` is the structured timing-review product for retaliation workflows and must keep confounders visible
- claimant-favorable and defense-favorable chronology views must keep visible uncertainty or counterargument content instead of reading as unqualified advocacy

## Evidence triage section contract

`sections.evidence_triage` is the counsel-facing split between what the current record directly shows, what it more cautiously supports by inference, what remains unresolved, and what proof is still missing.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `summary`
  - `direct_evidence_count`
  - `reasonable_inference_count`
  - `unresolved_point_count`
  - `missing_proof_count`
- `direct_evidence`
- `reasonable_inference`
- `unresolved_points`
- `missing_proof`

Rules:

- `direct_evidence` is for points that stay within observed-fact wording and remain anchored to direct cited material
- `reasonable_inference` is for bounded concern or interpretation statements that go beyond direct quotation but remain defensible from the cited record
- `unresolved_points` is for points that are not yet proven because ambiguity, weak support, low confidence, or live alternative explanations still matter
- `missing_proof` is for explicit evidence gaps that a reviewer would need to close before stronger conclusions
- every triage item must stay anchored to citation ids, finding ids, or message/document ids when such support exists
- `missing_proof` items may be source-gap markers without supporting findings, but must stay machine-readable and visible

## Employment issue frameworks section contract

`sections.employment_issue_frameworks` is the neutral issue-spotting layer for selected German employment-matter tracks.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `issue_tracks`

Each `issue_tracks[*]` object contains:

- `issue_track`
- `title`
- `neutral_question`
- `status`
  - `supported_by_current_record`
  - `alleged_but_not_yet_evidenced`
- `support_reason`
- `required_proof_elements`
- `normal_alternative_explanations`
- `missing_document_checklist`
- `minimum_source_quality_expectations`
- `why_not_yet_supported`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`

This section also contains:

- `issue_tag_summary`
  - `operator_supplied`
  - `direct_document_content`
  - `bounded_inference`

Rules:

- this section is an issue-spotting and evidence-organization layer, not a legal holding layer
- `supported_by_current_record` means the present record supports continued review of the issue track, not that liability or statutory satisfaction is established
- `alleged_but_not_yet_evidenced` means the track is explicitly in scope but the current record is still too thin or too incomplete for stronger support
- the section must stay neutral and preserve alternative explanations and missing-document needs for each track
- `issue_tag_summary` is the machine-readable tag summary that distinguishes directly supported tags from operator-supplied or inferred tags

## Lawyer issue matrix timing fields

`sections.lawyer_issue_matrix.lawyer_issue_matrix.rows[*]` may now also contain:

- `urgency_or_deadline_relevance`
- `timing_warning_ids`

Rules:

- these fields are operational timing warnings only
- they must stay explicitly non-final and non-statute-conclusive
- `timing_warning_ids` must point back to the shared `deadline_warnings.warnings[*].warning_id` payload when timing warnings exist

## Matter evidence index section contract

`sections.matter_evidence_index` is the report-facing summary surface for the reusable exhibit register.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `matter_evidence_index`

The embedded `matter_evidence_index` payload is the reusable exhibit register and contains:

- `version`
- `row_count`
- `summary`
- `rows`

For bilingual matters, exhibit rows may also expose:

- `source_language`
- `quoted_evidence`

Rule:

- `quoted_evidence.original_text` remains the original-language record and must not be silently replaced by an output-language summary

## Actor and witness map section contract

`sections.actor_and_witness_map` is the counsel-facing people registry for decision-makers, witnesses, gatekeepers, and coordination points.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `actor_map`
- `witness_map`

## Witness question packs section contract

`sections.witness_question_packs` is the practical interview-prep layer derived from the shared witness map, chronology, evidence index, and missing-proof checklist.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `witness_question_packs`

The embedded `witness_question_packs` payload contains:

- `version`
- `pack_count`
- `summary`
  - `decision_maker_pack_count`
  - `independent_witness_pack_count`
  - `record_holder_pack_count`
- `packs`

Each `packs[*]` object contains:

- `pack_id`
- `actor_id`
- `actor_name`
- `actor_email`
- `pack_type`
  - `decision_maker`
  - `independent_witness`
  - `record_holder`
- `likely_knowledge_areas`
- `key_tied_events`
- `documents_to_show_or_confirm`
- `factual_gaps_to_probe`
- `caution_notes`
- `suggested_questions`
- `non_leading_style`

Rules:

- packs must stay evidence-bound and tied to the shared actor/witness registry
- suggested questions should remain practical and non-leading rather than advocacy scripts
- record-holder packs may focus more on provenance, retention, and metadata than on motive or recollection

## Cross-output consistency section contract

`sections.cross_output_consistency` is the machine-detectable parity layer across the shared chronology, issue, memo, dashboard, skeptical-review, and drafting outputs.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `cross_output_consistency`

The embedded `cross_output_consistency` payload contains:

- `version`
- `overall_status`
  - `consistent`
  - `review_required`
- `machine_review_required`
- `summary`
  - `check_count`
  - `pass_count`
  - `mismatch_count`
- `affected_outputs`
- `checks`

Each `checks[*]` object contains:

- `check_id`
- `title`
- `status`
  - `pass`
  - `mismatch`
- `summary`
- `affected_outputs`
- `details`
- `linked_ids`

Rules:

- consistency checks must compare downstream outputs against the shared registries rather than against free-form text alone
- parity failures must stay machine-reviewable instead of being buried in prose
- current checks cover chronology ids, issue ids, exhibit ids and ranking/strength carry-through, actor-role parity, skeptical-review carry-through, and drafting-ceiling alignment
- `review_required` means one or more parity mismatches exist and counsel or a human reviewer should inspect the affected outputs before relying on them together

Rules:

- the section must be derived from the shared actor-identity, chronology, communication-graph, mixed-source, and matter-workspace registries rather than a report-only reconstruction
- actor entries must keep role/status classification explicit instead of leaving people significance narrative-only
- coordination points must remain graph-backed and uncertainty-preserving rather than framed as final motive findings

## Promise and contradiction analysis section contract

`sections.promise_and_contradiction_analysis` is the mixed-source review layer for promise-versus-action rows, later-summary omissions, and contradiction review.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `promise_contradiction_analysis`

Rules:

- the section must be derived from the shared mixed-source bundle and chronology registry rather than from report-only free text
- rows must keep `original_source_id` and later-source linkage explicit
- omission rows must remain lower-confidence than direct contradiction rows unless later source material clearly narrows the omission
- chronology-linked source-date contradictions may appear in the contradiction table alongside promise-versus-action contradictions

## Lawyer briefing memo section contract

`sections.lawyer_briefing_memo` is the compact onboarding memo derived from the stable matter model, evidence index, chronology, issue matrix, and next-step layers.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `lawyer_briefing_memo`

Rules:

- the memo must remain compact, non-repetitive, and evidence-bound
- it must not hide weaknesses, risks, urgent next steps, or open questions behind a strength-only summary
- it is an onboarding product for counsel and not a final legal holding or final legal advice
- the embedded payload may now include `bilingual_rendering`; when present, original-language quotations must remain separate from memo summary text

## Controlled factual drafting section contract

`sections.controlled_factual_drafting` is the disciplined drafting layer derived from the stable evidence, chronology, issue, weakness, and contradiction products.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `controlled_factual_drafting`

Rules:

- the section must surface a `framing_preflight` before or alongside the draft
- the allegation ceiling must remain explicit and must constrain the draft mechanically
- the draft must separate `established_facts`, `concerns`, `requests_for_clarification`, and `formal_demands`
- the draft must not convert concern-level support into motive attribution, liability claims, or unsupported legal conclusions
- the embedded payload may now include `bilingual_rendering`; if output text is English-facing, original-language evidence still remains anchored in the shared exhibit register

## Case dashboard section contract

`sections.case_dashboard` is the compact refreshable dashboard derived from shared matter entities and downstream stable registries.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `case_dashboard`

The embedded dashboard may now also expose:

- `summary.timing_warning_count`
- `cards.timing_warnings`

Rules:

- timing-warning cards are short operational prompts, not legal deadline conclusions
- the dashboard timing-warning card must be derived from the shared `deadline_warnings` payload rather than from independent wording logic

Rules:

- the dashboard must stay card-like rather than long-form
- its cards must be traceable to stable shared products such as the matter workspace, evidence index, chronology, issue matrix, actor map, and weakness/request layers
- it must refresh from entity and registry changes instead of depending on handwritten memo prose
- the embedded payload may now include `bilingual_rendering`; strongest-exhibit cards may carry `quoted_evidence` so original-language passages remain visible
- `top_15_exhibits`
- `top_10_missing_exhibits`

Rules:

- this section is the durable exhibit register surface for later dossier, chronology, and export work
- exhibit rows must stay anchored to source provenance, citation ids, finding ids, or stable source ids
- the report section may summarize only the first few rows, but the embedded `matter_evidence_index` payload remains the source of truth
- exhibit rows now carry structured `exhibit_reliability` data so counsel-facing review can distinguish `strength`, `reason`, and `next_step_logic.readiness` without re-deriving them from narrative prose
- the embedded payload now also carries the first dossier-priority layer through `top_15_exhibits` and concrete `top_10_missing_exhibits`
- when mixed-source records were appended after answer-context retrieval, the final report must still rebuild this section from the final mixed-source bundle instead of reusing an earlier email-only snapshot
- document-email links carried into this section must keep visible `confidence` and `match_basis` rather than opaque inferred linkage

## Lawyer issue matrix section contract

`sections.lawyer_issue_matrix` is the lawyer-facing legal-relevance matrix for German employment-matter review.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `lawyer_issue_matrix`

The embedded `lawyer_issue_matrix` payload contains:

- `version`
- `row_count`
- `rows`

The embedded payload may also contain:

- `bilingual_rendering`

Each `rows[*]` object contains:

- `issue_id`
- `title`
- `legal_relevance_status`
  - `supported_relevance`
  - `potentially_relevant`
  - `currently_under_supported`
- `relevant_facts`
- `strongest_documents`
- `likely_opposing_argument`
- `missing_proof`
- `urgency_or_deadline_relevance`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`
- `not_legal_advice`

Rules:

- this section maps facts to possible legal relevance for counsel review; it does not give final legal advice or assert statutory satisfaction
- rows must stay anchored to the neutral `employment_issue_frameworks` layer, the exhibit register, and existing finding or comparator support
- the outward section status must remain `insufficient_evidence` when every matrix row is still `currently_under_supported`; the embedded matrix may still be present for downstream review
- `likely_opposing_argument` must remain visible instead of collapsing the matrix into one-sided advocacy
- `strongest_documents` must point to actual exhibit-register rows, not inferred or hypothetical documents
- `not_legal_advice` must always be `true`
- if bilingual rendering is active, `strongest_documents[*].quoted_evidence.original_text` remains the original-language evidence anchor

## Skeptical employer-side review section contract

`sections.skeptical_employer_review` is the disciplined weaknesses memo that stress-tests the claimant-side record from an employer-side review stance.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `skeptical_employer_review`

The embedded `skeptical_employer_review` payload contains:

- `version`
- `summary`
  - `weakness_count`
  - `weakness_categories`
- `weaknesses`

Each `weaknesses[*]` object contains:

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

Rules:

- this section is a stress-test layer, not a defense merits holding
- each criticism must be paired with concrete repair guidance
- `cautious_rewrite` must reduce overstatement instead of merely warning about it
- the section may draw on chronology gaps, comparator weakness, alternative explanations, missing documents, internal inconsistency, and weak legal-to-evidence linkage

## Document-request checklist section contract

`sections.document_request_checklist` is the concrete records-request and preservation workflow derived from missing-proof analysis.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `document_request_checklist`

The embedded `document_request_checklist` payload contains:

- `version`
- `group_count`
- `groups`

Each `groups[*]` object contains:

- `group_id`
- `title`
- `item_count`
- `items`

Each `items[*]` object contains:

- `item_id`
- `request`
- `why_it_matters`
- `likely_custodian`
- `would_prove_or_disprove`
- `urgency`
- `risk_of_loss`
- `preservation_action`
- `linked_date_gap_ids`

Rules:

- checklist items must stay document-oriented, not generic advice-only bullets
- each item must identify a likely custodian
- urgency and loss risk must stay visible for preservation-sensitive items
- the section may be derived from missing exhibits, skeptical-review repair needs, and missing-information markers

## Overall assessment section contract

`sections.overall_assessment` is the stable outward report boundary for the high-stakes classification summary.

It must contain:

- `section_id`
- `title`
- `status`
- `entries`
- `insufficiency_reason`
- `primary_assessment`
- `secondary_plausible_interpretations`
- `assessment_strength`
- `downgrade_reasons`

Allowed `primary_assessment` values:

- `ordinary_workplace_conflict`
- `poor_communication_or_process_noise`
- `targeted_hostility_concern`
- `unequal_treatment_concern`
- `retaliation_concern`
- `discrimination_concern`
- `mobbing_like_pattern_concern`
- `insufficient_evidence`

Rules:

- `primary_assessment` must always be present, including insufficient cases
- `assessment_strength` must always be present and use the current evidence-strength labels when supported
- `secondary_plausible_interpretations` may be empty, but must be present
- `downgrade_reasons` may be empty, but must be present
- if `status == insufficient_evidence`, `primary_assessment` must be `insufficient_evidence`
- the overall assessment section must still include visible entries when it is supported; metadata fields do not replace the narrative entries
- weak-only records must default to `insufficient_evidence` as the primary assessment, while keeping stronger bounded interpretations only as secondary plausible interpretations when appropriate
- when material support and material counterarguments coexist, the narrative entries must say that the record is mixed rather than presenting a one-sided classification summary

## Budget behavior

Under tight JSON budgets the report is compacted, not dropped.

Compact mode keeps:

- `version`
- `report_format`
- `section_order`
- `summary`
- `report_highlights`
- per-section:
  - `title`
  - `status`
  - `entry_count`
  - first representative entry
  - `insufficiency_reason`
  - for `evidence_triage` only:
    - `summary`
    - first representative item from:
      - `direct_evidence`
      - `reasonable_inference`
      - `unresolved_points`
      - `missing_proof`
  - for `matter_evidence_index` only:
    - embedded `matter_evidence_index`
  - for `chronological_pattern_analysis` only:
    - compact chronology summary retains `date_gap_count`
    - compact chronology summary retains `largest_gap_days`
    - compact chronology may omit the multi-view chronology payload when JSON budget pressure requires it
    - compact chronology retains `retaliation_timeline_assessment.overall_evidentiary_rating`
  - for `employment_issue_frameworks` only:
    - first representative `issue_tracks` items
  - for `lawyer_issue_matrix` only:
    - embedded `lawyer_issue_matrix`
  - for `skeptical_employer_review` only:
    - embedded `skeptical_employer_review`
  - for `document_request_checklist` only:
    - embedded `document_request_checklist`
  - for `overall_assessment` only:
    - `primary_assessment`
    - `secondary_plausible_interpretations`
    - `assessment_strength`
    - `downgrade_reasons`

## Interpretation boundary

BA16 is a renderer only.

It does not:

- change evidence strength
- change quote ambiguity policy
- add new behavioural findings
- introduce legal or motive conclusions

Those concerns remain with earlier evidence/scoring milestones and the later BA17 policy milestone.
