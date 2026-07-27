"""Threshold helpers for generic QA evaluation reports."""

from __future__ import annotations

from typing import Any

_ACTIVE_BOOLEAN_METRICS = (
    "support_uid_hit",
    "support_source_id_hit",
    "ambiguity_match",
    "answer_content_match",
    "forbidden_support_ids_excluded",
)


def infer_threshold_profile(report: dict[str, Any]) -> str:
    """Infer a small generic profile from the report path/backend."""
    path = str(report.get("questions_path") or "").casefold()
    backend = str(report.get("live_backend") or "").casefold()
    if backend == "embedding" or ".embedding." in path:
        return "embedding"
    if "live_expanded" in path:
        return "live_expanded"
    return "generic"


def _metric_value(summary: dict[str, Any], metric: str, field: str) -> float | None:
    payload = summary.get(metric)
    if not isinstance(payload, dict):
        return None
    scorable = int(payload.get("scorable") or 0)
    if scorable == 0:
        return None
    if field == "passed_ratio":
        return float(payload.get("passed") or 0) / scorable
    if field in {"average", "average_when_scorable"}:
        return float(payload.get("average") or 0.0)
    raw = payload.get(field)
    return float(raw) if isinstance(raw, (int, float)) else None


def _check_delta_when_baseline_present(
    summary: dict[str, Any],
    baseline_summary: dict[str, Any],
    *,
    metric: str,
    field: str,
    min_delta: float,
) -> dict[str, Any] | None:
    current = _metric_value(summary, metric, field)
    baseline = _metric_value(baseline_summary, metric, field)
    if current is None or baseline is None:
        return None
    delta = current - baseline
    if delta >= min_delta:
        return None
    return {
        "metric": metric,
        "field": field,
        "expected": {"min_delta": min_delta},
        "actual": current,
        "baseline": baseline,
        "delta": delta,
    }


def evaluate_report_thresholds(report: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    """Require every labeled active boolean metric to pass."""
    selected_profile = profile or infer_threshold_profile(report)
    if report.get("source_mode") == "mixed":
        return {
            "profile": selected_profile,
            "status": "informational",
            "failure_count": 0,
            "failures": [],
        }
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {
            "profile": selected_profile,
            "status": "fail",
            "failure_count": 1,
            "failures": [
                {
                    "metric": "summary",
                    "field": "present",
                    "expected": True,
                    "actual": False,
                }
            ],
        }
    failures: list[dict[str, Any]] = []
    for metric in _ACTIVE_BOOLEAN_METRICS:
        payload = summary.get(metric)
        if not isinstance(payload, dict):
            continue
        scorable = int(payload.get("scorable") or 0)
        passed = int(payload.get("passed") or 0)
        if scorable and passed != scorable:
            failures.append(
                {
                    "metric": metric,
                    "field": "passed",
                    "expected": {"equals_scorable": scorable},
                    "actual": passed,
                }
            )
    return {
        "profile": selected_profile,
        "status": "pass" if not failures else "fail",
        "failure_count": len(failures),
        "failures": failures,
    }
