"""Compatibility imports for investigation-report helpers."""

from __future__ import annotations

from .investigation_report_assessment import overall_assessment_section as _overall_assessment_section
from .investigation_report_compact import compact_investigation_report
from .investigation_report_constants import INVESTIGATION_REPORT_VERSION, SECTION_ORDER
from .investigation_report_employment import (
    employment_issue_frameworks_section as _employment_issue_frameworks_section,
)
from .investigation_report_employment import (
    missing_information_section as _missing_information_section,
)
from .investigation_report_employment import (
    report_master_chronology_payload as _report_master_chronology_payload,
)
from .investigation_report_employment import (
    report_retaliation_timeline_payload as _report_retaliation_timeline_payload,
)
from .investigation_report_findings import (
    evidence_triage_section as _evidence_triage_section,
)
from .investigation_report_findings import (
    factual_summary_entry as _factual_summary_entry,
)
from .investigation_report_findings import (
    finding_entries as _finding_entries,
)
from .investigation_report_findings import (
    report_highlights as _report_highlights,
)
from .investigation_report_sections import (
    _as_dict,
    _as_list,
    _evidence_table_section,
    _language_section,
    _power_section,
    _section_with_entries,
    _timeline_section,
    _title,
)
from .investigation_report_sections_extra import (
    _actor_and_witness_map_section,
    _case_dashboard_section,
    _controlled_factual_drafting_section,
    _cross_output_consistency_section,
    _document_request_checklist_section,
    _lawyer_briefing_memo_section,
    _lawyer_issue_matrix_section,
    _matter_evidence_index_section,
    _promise_and_contradiction_analysis_section,
    _skeptical_employer_review_section,
    _witness_question_packs_section,
)

__all__ = [
    "INVESTIGATION_REPORT_VERSION",
    "SECTION_ORDER",
    "_actor_and_witness_map_section",
    "_as_dict",
    "_as_list",
    "_case_dashboard_section",
    "_controlled_factual_drafting_section",
    "_cross_output_consistency_section",
    "_document_request_checklist_section",
    "_employment_issue_frameworks_section",
    "_evidence_table_section",
    "_evidence_triage_section",
    "_factual_summary_entry",
    "_finding_entries",
    "_language_section",
    "_lawyer_briefing_memo_section",
    "_lawyer_issue_matrix_section",
    "_matter_evidence_index_section",
    "_missing_information_section",
    "_overall_assessment_section",
    "_power_section",
    "_promise_and_contradiction_analysis_section",
    "_report_highlights",
    "_report_master_chronology_payload",
    "_report_retaliation_timeline_payload",
    "_section_with_entries",
    "_skeptical_employer_review_section",
    "_timeline_section",
    "_title",
    "_witness_question_packs_section",
    "compact_investigation_report",
]
