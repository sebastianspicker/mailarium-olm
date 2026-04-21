# Matter Workspace

Version: `1`

Status: `approved_for_implementation`

`matter_workspace` is the shared matter-level workspace core for MCP-backed legal-support flows.

It exists to give downstream surfaces one source of truth for:

- matter identity
- stable party entities
- issue-track and issue-tag entities
- evidence and chronology registry references

## Top-level shape

`matter_workspace` contains:

- `version`
- `workspace_id`
- `matter`
- `parties`
- `issue_registry`
- `evidence_registry`
- `chronology_registry`
- `registry_refs`

## Matter contract

`matter` contains:

- `matter_id`
- `bundle_id`
- `case_label`
- `analysis_goal`
- `date_range`
  - `date_from`
  - `date_to`
- `target_person_entity_id`

## Party entities

Each `parties[*]` entry contains:

- `entity_id`
- `name`
- `email`
- `role_hint`
- `roles_in_matter`
- `source_paths`

Current `roles_in_matter` values include:

- `target_person`
- `suspected_actor`
- `comparator_actor`
- `trigger_actor`
- `org_context_person`
- `vulnerability_context_person`

## Issue registry

`issue_registry` contains:

- `employment_issue_tracks`
- `employment_issue_tags`

Track entities keep:

- `entity_id`
- `issue_track`
- `title`
- `neutral_question`

Tag entities keep:

- `entity_id`
- `tag_id`
- `label`
- `assignment_basis`

## Registry references

`evidence_registry` contains:

- `source_count`
- `source_type_counts`
- `exhibit_ids`
- `source_ids`

`chronology_registry` contains:

- `entry_ids`
- `entry_count`
- `date_range`
- `date_precision_counts`

`registry_refs` contains:

- `case_bundle_ref`
- `matter_evidence_index_version`
- `master_chronology_version`

## Current boundary

Version `1` is the in-process workspace core only:

- it does not yet persist matters into an external MCP store
- it does not replace the existing `case_bundle`, `matter_evidence_index`, or `master_chronology`
- it gives downstream legal-support layers stable matter entities and registry references instead of forcing each layer to rebuild them
