#!/usr/bin/env python3
"""Prepare clean case workflow inputs from prompt-preflight or curated case JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.repo_paths import validate_local_read_path, validate_new_output_path  # noqa: E402

_HELPER_KEYS = {"extraction_basis", "date_confidence"}


def _sanitize_case_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_case_payload(item) for key, item in value.items() if key not in _HELPER_KEYS}
    if isinstance(value, list):
        return [_sanitize_case_payload(item) for item in value]
    return value


def _read_json(path: str, *, label: str) -> Any:
    try:
        payload_path = validate_local_read_path(path, field_name=label)
        return json.loads(payload_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{label} path rejected: {exc}") from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {payload_path} ({exc})") from exc


def _write_json(path: str, payload: Any) -> Path:
    output_path = validate_new_output_path(path, field_name="case input output")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _case_input_from_preflight(preflight_payload: Any) -> dict[str, Any]:
    from src.case_prompt_preflight_normalization import normalize_prompt_preflight_case_input

    try:
        normalized = normalize_prompt_preflight_case_input(preflight_payload)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    sanitized = _sanitize_case_payload(normalized)
    if not isinstance(sanitized, dict):
        raise SystemExit("sanitized case input must remain a JSON object")
    return sanitized


def _case_input_from_case_json(case_payload: Any) -> dict[str, Any]:
    if not isinstance(case_payload, dict):
        raise SystemExit("case JSON input must be a JSON object")
    sanitized = _sanitize_case_payload(case_payload)
    if not isinstance(sanitized, dict):
        raise SystemExit("sanitized case input must remain a JSON object")
    return sanitized


def _full_pack_overrides(case_input: dict[str, Any]) -> dict[str, Any]:
    overrides = dict(case_input)
    overrides.pop("review_mode", None)
    overrides.pop("matter_manifest", None)
    return overrides


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/prepare_case_inputs.py",
        description=(
            "Build a strict case.json and/or matching full_pack_overrides.json from prompt-preflight output "
            "or a curated case JSON file."
        ),
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--preflight",
        help="Path to prompt-preflight JSON containing draft_case_analysis_input.",
    )
    source_group.add_argument(
        "--case-json",
        help="Path to an existing curated case JSON file.",
    )
    parser.add_argument(
        "--case-json-out",
        default=None,
        help="Optional output path for a cleaned strict case JSON file.",
    )
    parser.add_argument(
        "--overrides-out",
        default=None,
        help="Optional output path for a matching full-pack overrides JSON file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.case_json_out and not args.overrides_out:
        parser.error("at least one of --case-json-out or --overrides-out is required")

    if args.preflight:
        case_input = _case_input_from_preflight(_read_json(args.preflight, label="prompt-preflight payload"))
    else:
        case_input = _case_input_from_case_json(_read_json(args.case_json, label="case JSON"))

    written_paths: list[Path] = []
    if args.case_json_out:
        written_paths.append(_write_json(args.case_json_out, case_input))
    if args.overrides_out:
        written_paths.append(_write_json(args.overrides_out, _full_pack_overrides(case_input)))

    for path in written_paths:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
