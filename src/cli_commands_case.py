"""Dedicated case-analysis CLI helpers."""
# pylint: disable=too-many-locals

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from .case_analysis import build_case_analysis
from .case_campaign_workflow import (
    build_execution_authority,
    execute_all_waves_payload,
    execute_wave_payload,
    gather_evidence_payload,
)
from .case_full_pack import execute_case_full_pack
from .case_operator_intake import build_manifest_from_materials_dir, matter_manifest_has_mixed_artifacts
from .case_prompt_intake import build_case_prompt_preflight
from .investigation_results_workspace import (
    active_results_manifest_path,
    archive_results_paths,
    write_active_results_manifest,
)
from .legal_support_exporter import LegalSupportExporter
from .mcp_models import (
    EmailCaseAnalysisInput,
    EmailCaseFullPackInput,
    EmailCasePromptPreflightInput,
    EmailLegalSupportExportInput,
)
from .mcp_models_base import _resolve_local_path
from .mcp_models_case_analysis_manifest import CaseGatherEvidenceLimitsInput
from .repo_paths import validate_local_read_path, validate_new_output_path


def _cli_execution_authority(case_action: str) -> dict[str, str]:
    """Build an execution authority dict for CLI case actions.

    Creates an authority dictionary with surface and case action information,
    adding the command family marker.

    Args:
        case_action: The specific case action being performed.

    Returns:
        A dict with execution authority information including surface,
        case_action, and command_family.
    """
    authority = build_execution_authority(surface="repository_cli", case_action=case_action)
    authority["command_family"] = "case"
    return authority


def _stamp_cli_payload(payload: dict[str, Any], *, case_action: str) -> dict[str, Any]:
    """Stamp a payload dict with CLI execution authority.

    Adds execution authority information to a payload dictionary.

    Args:
        payload: The payload dict to stamp.
        case_action: The case action for the authority.

    Returns:
        A new dict with the execution authority added.
    """
    stamped = dict(payload)
    stamped["execution_authority"] = _cli_execution_authority(case_action)
    return stamped


def _render_cli_json(payload: Any, *, case_action: str, indent: int | None = None) -> str:
    """Render a payload as JSON with CLI execution authority stamping.

    If the payload is a string, attempts to parse it as JSON first.
    If the payload is a dict, stamps it with execution authority before
    serializing to JSON.

    Args:
        payload: The data to render as JSON.
        case_action: The case action for authority stamping.
        indent: Optional indentation level for pretty printing.

    Returns:
        A JSON string representation of the payload.
    """
    if isinstance(payload, str):
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError:
            return payload
    else:
        loaded = payload

    if isinstance(loaded, dict):
        loaded = _stamp_cli_payload(loaded, case_action=case_action)
        return json.dumps(loaded, ensure_ascii=False, indent=indent)
    return json.dumps(loaded, ensure_ascii=False, indent=indent)


def _resolve_results_path(results_root: Path, path: Path | str) -> Path:
    """Resolve a path relative to the results root directory.

    Expands user paths, makes relative paths absolute relative to results_root,
    and validates that the resolved path stays within the results root.

    Args:
        results_root: The root directory for results.
        path: The path to resolve (string or Path).

    Returns:
        The resolved absolute Path.

    Raises:
        ValueError: If the resolved path escapes the results root.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = results_root / candidate
    resolved = candidate.resolve()
    resolved_root = results_root.resolve()
    if resolved_root not in (resolved, *resolved.parents):
        raise ValueError(f"results path must stay within {results_root}: {path}")
    return resolved


def _require_existing_results_path(results_root: Path, path: Path | str, *, label: str) -> Path:
    """Require that a path exists within the results root directory.

    Resolves the path and checks that it exists.

    Args:
        results_root: The root directory for results.
        path: The path to check (string or Path).
        label: A label describing the path for error messages.

    Returns:
        The resolved existing Path.

    Raises:
        ValueError: If the path does not exist or escapes the results root.
    """
    resolved = _resolve_results_path(results_root, path)
    if not resolved.exists():
        raise ValueError(f"{label} does not exist: {path}")
    return resolved


class _SyncToolDeps:
    """Minimal ToolDeps-compatible adapter for CLI execution."""

    def __init__(self, retriever: Any, email_db: Any):
        """Initialize the adapter with retriever and database instances.

        Args:
            retriever: An EmailRetriever instance for searching.
            email_db: An EmailDatabase instance for database operations.
        """
        self._retriever = retriever
        self._email_db = email_db

    def get_retriever(self) -> Any:
        """Get the retriever instance.

        Returns:
            The EmailRetriever instance.
        """
        return self._retriever

    def get_email_db(self) -> Any:
        """Get the email database instance.

        Returns:
            The EmailDatabase instance.
        """
        return self._email_db

    async def offload(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function synchronously (no actual offloading in CLI context).

        Args:
            fn: The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function call.
        """
        if args or kwargs:
            return fn(*args, **kwargs)
        return fn()

    def tool_annotations(self, title: str) -> Any:
        """Get tool annotations for a title.

        Args:
            title: The title string.

        Returns:
            The title string (identity function for compatibility).
        """
        return title

    def write_tool_annotations(self, title: str) -> Any:
        """Get write tool annotations for a title.

        Args:
            title: The title string.

        Returns:
            The title string (identity function for compatibility).
        """
        return title

    def idempotent_write_annotations(self, title: str) -> Any:
        """Get idempotent write annotations for a title.

        Args:
            title: The title string.

        Returns:
            The title string (identity function for compatibility).
        """
        return title

    DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available. Run ingestion first."})

    def sanitize(self, text: str) -> str:
        """Sanitize text (identity function for compatibility).

        Args:
            text: The text to sanitize.

        Returns:
            The original text (no sanitization performed in CLI context).
        """
        return text


def _cli_exit(message: str, *, code: int) -> NoReturn:
    """Exit the CLI with a message and exit code.

    Args:
        message: The error or status message to print.
        code: The exit code to use.

    Raises:
        SystemExit: Always raised with the given code.
    """
    print(message)
    raise SystemExit(code)


def _read_text_or_exit(path: str, *, label: str) -> str:
    """Read text from a file path, exiting on error.

    Validates the path and reads its content as UTF-8 text.

    Args:
        path: The file path to read.
        label: A label describing the file for error messages.

    Returns:
        The file content as a string.

    Raises:
        SystemExit: If the file cannot be read.
    """
    try:
        input_path = validate_local_read_path(path, field_name=label)
        return input_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        _cli_exit(f"{label} read error: {exc}", code=2)


def _load_json_object_or_exit(path: str, *, label: str) -> Any:
    """Load and parse a JSON file, exiting on error.

    Reads the file and parses its content as JSON.

    Args:
        path: The JSON file path to load.
        label: A label describing the file for error messages.

    Returns:
        The parsed JSON data (dict, list, etc.).

    Raises:
        SystemExit: If the file cannot be read or parsed as JSON.
    """
    raw_input = _read_text_or_exit(path, label=label)
    try:
        return json.loads(raw_input)
    except json.JSONDecodeError as exc:
        _cli_exit(f"{label} json error: {exc.msg}", code=3)


def _write_text_or_exit(path: str, content: str, *, label: str) -> None:
    """Write text to a file path, exiting on error.

    Validates the output path, creates parent directories as needed,
    and writes the content as UTF-8 text.

    Args:
        path: The file path to write to.
        content: The text content to write.
        label: A label describing the file for error messages.

    Raises:
        SystemExit: If the file cannot be written.
    """
    try:
        output_path = validate_new_output_path(path, field_name=label)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as exc:
        _cli_exit(f"{label} write error: {exc}", code=4)


def _validate_case_analysis_input_or_exit(raw_input: Any, *, label: str) -> EmailCaseAnalysisInput:
    """Validate raw input as an EmailCaseAnalysisInput, exiting on error.

    Args:
        raw_input: The raw input data to validate.
        label: A label describing the input for error messages.

    Returns:
        A validated EmailCaseAnalysisInput instance.

    Raises:
        SystemExit: If validation fails.
    """
    try:
        return EmailCaseAnalysisInput.model_validate(raw_input)
    except ValidationError as exc:
        _cli_exit(f"{label} validation error: {exc.errors()[0]['msg']}", code=3)


def _validate_full_pack_input_or_exit(payload: dict[str, Any], *, label: str) -> EmailCaseFullPackInput:
    """Validate a payload as an EmailCaseFullPackInput, exiting on error.

    Args:
        payload: The payload dict to validate.
        label: A label describing the payload for error messages.

    Returns:
        A validated EmailCaseFullPackInput instance.

    Raises:
        SystemExit: If validation fails.
    """
    try:
        return EmailCaseFullPackInput.model_validate(payload)
    except ValidationError as exc:
        _cli_exit(f"{label} validation error: {exc.errors()[0]['msg']}", code=3)


def _validate_counsel_export_input_or_exit(payload: dict[str, Any], *, label: str) -> EmailLegalSupportExportInput:
    """Validate a payload as an EmailLegalSupportExportInput, exiting on error.

    Args:
        payload: The payload dict to validate.
        label: A label describing the payload for error messages.

    Returns:
        A validated EmailLegalSupportExportInput instance.

    Raises:
        SystemExit: If validation fails.
    """
    try:
        return EmailLegalSupportExportInput.model_validate(payload)
    except ValidationError as exc:
        _cli_exit(f"{label} validation error: {exc.errors()[0]['msg']}", code=3)


def run_case_analyze_impl(retriever: Any, get_email_db: Callable[[], Any], args: Any) -> None:
    """Run the exploratory/raw-input case-analysis workflow from the CLI."""
    params = _load_case_analysis_input(args.input)
    deps = _SyncToolDeps(retriever, get_email_db())
    rendered = asyncio.run(build_case_analysis(deps, params))
    rendered = _render_cli_json(rendered, case_action="analyze")
    if getattr(args, "output", None):
        _write_text_or_exit(args.output, rendered, label="case output")
    else:
        print(rendered)


def _load_case_analysis_input(path: str) -> EmailCaseAnalysisInput:
    """Load and validate a case analysis input file.

    Args:
        path: Path to the JSON input file.

    Returns:
        A validated EmailCaseAnalysisInput instance.

    Raises:
        SystemExit: If the file cannot be read or validated.
    """
    return _validate_case_analysis_input_or_exit(_load_json_object_or_exit(path, label="case input"), label="case input")


def _validated_gather_evidence_limits(args: Any) -> tuple[int, int]:
    """Extract and validate gather evidence limits from args.

    Args:
        args: Argument namespace containing harvest_limit_per_wave and
            promote_limit_per_wave attributes.

    Returns:
        A tuple of (harvest_limit_per_wave, promote_limit_per_wave).
    """
    validated = CaseGatherEvidenceLimitsInput.model_validate(
        {
            "harvest_limit_per_wave": int(getattr(args, "harvest_limit_per_wave", 12)),
            "promote_limit_per_wave": int(getattr(args, "promote_limit_per_wave", 4)),
        }
    )
    return validated.harvest_limit_per_wave, validated.promote_limit_per_wave


def run_case_execute_wave_impl(retriever: Any, get_email_db: Callable[[], Any], args: Any) -> None:
    """Execute one documented question wave from a structured case-analysis input."""
    params = _load_case_analysis_input(args.input)
    deps = _SyncToolDeps(retriever, get_email_db())
    payload = asyncio.run(
        execute_wave_payload(
            deps,
            params,
            wave_id=args.wave,
            scan_id_prefix=getattr(args, "scan_id_prefix", None),
        )
    )
    rendered = _render_cli_json(payload, case_action="execute-wave", indent=2)
    if getattr(args, "output", None):
        _write_text_or_exit(args.output, rendered, label="case output")
    else:
        print(rendered)


def run_case_execute_all_waves_impl(retriever: Any, get_email_db: Callable[[], Any], args: Any) -> None:
    """Execute all documented question waves in sequence from one structured case-analysis input."""
    params = _load_case_analysis_input(args.input)
    deps = _SyncToolDeps(retriever, get_email_db())
    result = asyncio.run(
        execute_all_waves_payload(
            deps,
            params,
            scan_id_prefix=getattr(args, "scan_id_prefix", None),
            include_payloads=bool(getattr(args, "include_payloads", False)),
        )
    )
    rendered = _render_cli_json(result, case_action="execute-all-waves", indent=2)
    if getattr(args, "output", None):
        _write_text_or_exit(args.output, rendered, label="case output")
    else:
        print(rendered)


def run_case_gather_evidence_impl(retriever: Any, get_email_db: Callable[[], Any], args: Any) -> None:
    """Execute all waves and persist harvested evidence candidates."""
    params = _load_case_analysis_input(args.input)
    deps = _SyncToolDeps(retriever, get_email_db())
    harvest_limit_per_wave, promote_limit_per_wave = _validated_gather_evidence_limits(args)
    result = asyncio.run(
        gather_evidence_payload(
            deps,
            params,
            run_id=args.run_id,
            phase_id=args.phase_id,
            scan_id_prefix=getattr(args, "scan_id_prefix", None),
            harvest_limit_per_wave=harvest_limit_per_wave,
            promote_limit_per_wave=promote_limit_per_wave,
            include_payloads=bool(getattr(args, "include_payloads", False)),
        )
    )
    rendered = _render_cli_json(result, case_action="gather-evidence", indent=2)
    if getattr(args, "output", None):
        _write_text_or_exit(args.output, rendered, label="case output")
    else:
        print(rendered)


def run_case_prompt_preflight_impl(args: Any) -> None:
    """Build a bounded draft case intake from a natural-language matter prompt file."""
    prompt_text = _read_text_or_exit(args.input, label="prompt input")
    params = EmailCasePromptPreflightInput.model_validate(
        {
            "prompt_text": prompt_text,
            "output_language": getattr(args, "output_language", "de"),
        }
    )
    rendered = _render_cli_json(build_case_prompt_preflight(params), case_action="prompt-preflight", indent=2)
    if getattr(args, "output", None):
        _write_text_or_exit(args.output, rendered, label="case output")
    else:
        print(rendered)


def run_case_refresh_active_run_impl(args: Any) -> None:
    """Refresh the canonical active-run manifest for the local investigation workspace."""
    results_root = Path(args.results_root).expanduser()
    _require_existing_results_path(results_root, args.active_checkpoint, label="active_checkpoint")
    for result_path in getattr(args, "active_result_paths", []):
        _require_existing_results_path(results_root, result_path, label="active_result_path")
    if getattr(args, "question_register_path", None):
        _require_existing_results_path(results_root, args.question_register_path, label="question_register_path")
    if getattr(args, "open_tasks_companion_path", None):
        _require_existing_results_path(results_root, args.open_tasks_companion_path, label="open_tasks_companion_path")

    manifest = write_active_results_manifest(
        results_root=results_root,
        matter_id=args.matter_id,
        run_id=args.run_id,
        phase_id=args.phase_id,
        active_checkpoint=args.active_checkpoint,
        active_result_paths=list(getattr(args, "active_result_paths", [])),
        question_register_path=getattr(args, "question_register_path", None),
        open_tasks_companion_path=getattr(args, "open_tasks_companion_path", None),
    )
    print(
        json.dumps(
            {
                "workflow": "case_refresh_active_run",
                "status": "completed",
                "manifest_path": str(active_results_manifest_path(results_root)),
                "manifest": manifest,
            },
            ensure_ascii=False,
        )
    )


def run_case_archive_results_impl(args: Any) -> None:
    """Archive superseded local investigation result files."""
    results_root = Path(args.results_root).expanduser()
    for relative_path in getattr(args, "relative_paths", []):
        _require_existing_results_path(results_root, relative_path, label="relative_path")
    archived_paths = archive_results_paths(
        results_root=results_root,
        relative_paths=list(getattr(args, "relative_paths", [])),
        archive_label=args.archive_label,
    )
    print(
        json.dumps(
            {
                "workflow": "case_archive_results",
                "status": "completed",
                "results_root": str(results_root),
                "archive_label": args.archive_label,
                "archived_paths": archived_paths,
            },
            ensure_ascii=False,
        )
    )


def _require_email_db(get_email_db: Callable[[], Any]) -> Any:
    """Require and return an EmailDatabase instance.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.

    Returns:
        The EmailDatabase instance.

    Raises:
        ValueError: If the database is not available.
    """
    db = get_email_db()
    if db is None:
        raise ValueError("SQLite database not available. Run ingestion first.")
    return db


def _load_optional_json(path: str | None, *, default: Any) -> Any:
    """Load an optional JSON file, returning a default if not provided.

    Args:
        path: Optional path to a JSON file.
        default: Default value to return if path is None.

    Returns:
        The parsed JSON data, or the default value.
    """
    if not path:
        return default
    return _load_json_object_or_exit(path, label="optional json input")


def run_case_counsel_pack_impl(retriever: Any, get_email_db: Callable[[], Any], args: Any) -> int:
    """Build a manifest-backed counsel pack from a case scope file plus materials directory."""
    case_scope = _load_json_object_or_exit(args.case_scope, label="case scope input")
    materials_dir = _resolve_local_path(args.materials_dir, field_name="materials_dir")
    if materials_dir is None:
        _cli_exit("case input validation error: materials_dir is required", code=3)
    assert materials_dir is not None
    if not materials_dir.exists() or not materials_dir.is_dir():
        raise ValueError(f"materials_dir must be an existing directory: {materials_dir}")
    manifest = build_manifest_from_materials_dir(args.materials_dir)
    source_scope = "mixed_case_file" if matter_manifest_has_mixed_artifacts(manifest) else "emails_and_attachments"
    params = _validate_counsel_export_input_or_exit(
        {
            "case_scope": case_scope,
            "source_scope": source_scope,
            "review_mode": "exhaustive_matter_review",
            "matter_manifest": manifest,
            "delivery_target": args.delivery_target,
            "delivery_format": args.delivery_format,
            "output_path": args.output,
            "privacy_mode": args.privacy_mode,
            "output_language": args.output_language,
            "translation_mode": args.translation_mode,
        },
        label="case counsel-pack input",
    )
    deps = _SyncToolDeps(retriever, get_email_db())
    payload = asyncio.run(build_case_analysis(deps, params))
    rendered_payload = json.loads(payload)
    exporter = LegalSupportExporter()
    blocked = _blocked_counsel_export(exporter, rendered_payload, params)
    if blocked is not None:
        print(_render_cli_json(blocked, case_action="counsel-pack"))
        return 0 if bool(getattr(args, "allow_blocked_exit_zero", False)) else 1
    result = exporter.export_file(
        payload=rendered_payload,
        output_path=params.output_path,
        delivery_target=params.delivery_target,
        delivery_format=params.delivery_format,
    )
    rendered_result = {"workflow": "case_counsel_pack", **result}
    print(_render_cli_json(rendered_result, case_action="counsel-pack"))
    return 0


def _blocked_counsel_export(exporter: Any, payload: dict[str, Any], params: Any) -> dict[str, Any] | None:
    target = str(params.delivery_target or "").strip()
    status_fn = getattr(exporter, "counsel_export_status", None)
    if target not in {"counsel_handoff", "counsel_handoff_bundle"} or not callable(status_fn):
        return None
    status = status_fn(payload=payload)
    if not isinstance(status, dict) or bool(status.get("ready")):
        return None
    metadata = status.get("export_metadata")
    readiness = metadata.get("counsel_export_readiness", {}) if isinstance(metadata, dict) else {}
    blockers = [str(item) for item in status.get("blockers", []) if item]
    return {
        "workflow": "case_counsel_pack",
        "status": "blocked",
        "delivery_target": params.delivery_target,
        "delivery_format": params.delivery_format,
        "output_path": params.output_path,
        "analysis_query": str(payload.get("analysis_query") or ""),
        "next_step": readiness.get("next_step"),
        "blockers": [_counsel_blocker(item) for item in blockers],
        "export_metadata": metadata,
    }


def _counsel_blocker(field: str) -> dict[str, str]:
    return {
        "field": field,
        "severity": "blocking",
        "reason": "Counsel-facing export remains blocked until the recorded readiness issue is resolved.",
    }


def run_case_review_status_impl(get_email_db: Callable[[], Any], args: Any) -> None:
    """Inspect current review-governance state for one persisted matter workspace."""
    db = _require_email_db(get_email_db)
    latest_snapshot = db.latest_matter_snapshot(workspace_id=args.workspace_id)
    payload = {
        "workflow": "case_review_status",
        "workspace_id": args.workspace_id,
        "latest_snapshot": latest_snapshot,
        "snapshots": db.list_matter_snapshots(workspace_id=args.workspace_id),
        "review_status": db.matter_review_status_summary(workspace_id=args.workspace_id),
        "overrides": db.list_matter_review_overrides(workspace_id=args.workspace_id),
    }
    print(json.dumps(payload, ensure_ascii=False))


def run_case_review_override_impl(get_email_db: Callable[[], Any], args: Any) -> None:
    """Persist one bounded human review override for a matter workspace item."""
    db = _require_email_db(get_email_db)
    override_payload = _load_optional_json(args.override_json, default={})
    machine_payload = _load_optional_json(args.machine_json, default={})
    source_evidence = _load_optional_json(args.source_evidence_json, default=[])
    result = db.upsert_matter_review_override(
        workspace_id=args.workspace_id,
        target_type=args.target_type,
        target_id=args.target_id,
        review_state=args.review_state,
        override_payload=override_payload if isinstance(override_payload, dict) else {},
        machine_payload=machine_payload if isinstance(machine_payload, dict) else {},
        source_evidence=source_evidence if isinstance(source_evidence, list) else [],
        reviewer=args.reviewer,
        review_notes=args.review_notes,
        apply_on_refresh=not bool(getattr(args, "no_apply_on_refresh", False)),
    )
    print(json.dumps(result, ensure_ascii=False))


def run_case_review_snapshot_impl(get_email_db: Callable[[], Any], args: Any) -> None:
    """Promote or otherwise update one persisted matter snapshot review state."""
    db = _require_email_db(get_email_db)
    result = db.set_matter_snapshot_review_state(
        snapshot_id=args.snapshot_id,
        review_state=args.review_state,
        reviewer=args.reviewer,
    )
    print(json.dumps(result, ensure_ascii=False))


def run_case_full_pack_impl(retriever: Any, get_email_db: Callable[[], Any], args: Any) -> int:
    """Compile and, when possible, execute the full-pack workflow from prompt plus materials."""
    prompt_text = _read_text_or_exit(args.prompt, label="prompt input")
    intake_overrides: dict[str, object] = {}
    if getattr(args, "overrides", None):
        loaded = _load_json_object_or_exit(args.overrides, label="full-pack overrides")
        if isinstance(loaded, dict):
            intake_overrides = loaded
        else:
            _cli_exit("full-pack overrides validation error: overrides must be a JSON object when provided.", code=3)
    params = _validate_full_pack_input_or_exit(
        {
            "prompt_text": prompt_text,
            "materials_dir": args.materials_dir,
            "output_language": args.output_language,
            "translation_mode": args.translation_mode,
            "default_source_scope": args.default_source_scope,
            "assume_date_to_today": args.assume_date_to_today,
            "compile_only": getattr(args, "compile_only", False),
            "privacy_mode": args.privacy_mode,
            "delivery_target": args.delivery_target,
            "delivery_format": args.delivery_format,
            "output_path": getattr(args, "output", None),
            "intake_overrides": intake_overrides,
        },
        label="case full-pack input",
    )
    deps = _SyncToolDeps(retriever, get_email_db())
    payload = asyncio.run(execute_case_full_pack(deps, params))
    rendered = _render_cli_json(payload, case_action="full-pack", indent=2)
    print(rendered)
    if str(payload.get("status") or "") == "blocked" and not bool(getattr(args, "allow_blocked_exit_zero", False)):
        return 1
    return 0
