"""Refresh helpers for realistic legal-support full-pack goldens."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .legal_support_acceptance_cases import acceptance_case_ids
from .legal_support_acceptance_fixtures import build_golden_projection, execute_fixture_full_pack_sync

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_AGENT_DIR = ROOT / "docs" / "agent"
FULL_PACK_GOLDEN_ALIAS = "legal_support_full_pack_goldens"


@dataclass(frozen=True)
class LegalSupportGoldenScenario:
    """Filesystem contract for one realistic full-pack golden."""

    name: str
    case_id: str
    golden_filename: str

    def resolve(self, docs_agent_dir: Path = DEFAULT_DOCS_AGENT_DIR) -> ResolvedLegalSupportGoldenScenario:
        return ResolvedLegalSupportGoldenScenario(
            name=self.name,
            case_id=self.case_id,
            golden_path=docs_agent_dir / self.golden_filename,
        )


@dataclass(frozen=True)
class ResolvedLegalSupportGoldenScenario:
    """Resolved on-disk location for one realistic full-pack golden."""

    name: str
    case_id: str
    golden_path: Path


LEGAL_SUPPORT_GOLDEN_SCENARIOS: tuple[LegalSupportGoldenScenario, ...] = tuple(
    LegalSupportGoldenScenario(
        name=f"legal_support_full_pack_{case_id}",
        case_id=case_id,
        golden_filename=f"legal_support_full_pack_golden.{case_id}.json",
    )
    for case_id in acceptance_case_ids()
)


def legal_support_golden_scenarios(
    docs_agent_dir: Path = DEFAULT_DOCS_AGENT_DIR,
) -> tuple[ResolvedLegalSupportGoldenScenario, ...]:
    """Return the resolved legal-support full-pack golden manifest."""
    return tuple(item.resolve(docs_agent_dir) for item in LEGAL_SUPPORT_GOLDEN_SCENARIOS)


def render_legal_support_golden(scenario: ResolvedLegalSupportGoldenScenario) -> dict[str, object]:
    """Render one realistic full-pack golden subset from the committed fixture case."""
    payload = execute_fixture_full_pack_sync(scenario.case_id)
    return {
        "golden_version": "1",
        "scenario": scenario.name,
        "case_id": scenario.case_id,
        "projection": build_golden_projection(payload),
    }


def refresh_legal_support_goldens(
    *,
    docs_agent_dir: Path = DEFAULT_DOCS_AGENT_DIR,
    scenario_names: set[str] | None = None,
    check_only: bool = False,
) -> list[dict[str, object]]:
    """Refresh or check the committed realistic full-pack goldens."""
    expanded_names = set(scenario_names or [])
    if FULL_PACK_GOLDEN_ALIAS in expanded_names:
        expanded_names.remove(FULL_PACK_GOLDEN_ALIAS)
        expanded_names.update(item.name for item in LEGAL_SUPPORT_GOLDEN_SCENARIOS)

    outcomes: list[dict[str, object]] = []
    for scenario in legal_support_golden_scenarios(docs_agent_dir):
        if expanded_names and scenario.name not in expanded_names:
            continue
        rendered = json.dumps(render_legal_support_golden(scenario), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        existing = scenario.golden_path.read_text(encoding="utf-8") if scenario.golden_path.exists() else None
        status = "match" if existing == rendered else "updated"
        if not check_only and status == "updated":
            scenario.golden_path.write_text(rendered, encoding="utf-8")
        outcomes.append(
            {
                "scenario": scenario.name,
                "case_id": scenario.case_id,
                "golden_path": str(scenario.golden_path),
                "status": status if check_only else ("written" if status == "updated" else "unchanged"),
            }
        )
    return outcomes
