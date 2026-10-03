#!/usr/bin/env python3
"""Assert that the dependency-free public demo keeps its privacy boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"
REQUIRED_FILES = ("index.html", "styles.css", "mock-data.js", "app.js", "favicon.svg")
REQUIRED_MARKERS = (
    "Synthetic data only",
    "No archive or mailbox is connected.",
    "command-palette",
    "mailbox-grid",
)
FORBIDDEN_MARKERS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "sendBeacon",
    "http://",
    "https://",
    "@import",
    "url(",
    "private/",
)


def main() -> None:
    missing = [name for name in REQUIRED_FILES if not (DEMO / name).is_file()]
    if missing:
        raise SystemExit(f"missing Pages demo files: {', '.join(missing)}")
    index = (DEMO / "index.html").read_text(encoding="utf-8")
    script = (DEMO / "app.js").read_text(encoding="utf-8")
    combined = "\n".join(
        (
            index,
            script,
            (DEMO / "mock-data.js").read_text(encoding="utf-8"),
            (DEMO / "styles.css").read_text(encoding="utf-8"),
        )
    )
    absent = [marker for marker in REQUIRED_MARKERS if marker not in index]
    if absent:
        raise SystemExit(f"missing required demo boundary or interaction markers: {', '.join(absent)}")
    violations = [marker for marker in FORBIDDEN_MARKERS if marker in combined]
    if violations:
        raise SystemExit(f"unexpected network or private-path marker: {', '.join(violations)}")
    if "URL.createObjectURL" not in script or "toggleEvidence" not in script:
        raise SystemExit("demo is missing local export or evidence interaction")
    print("pages demo static assertions passed")


if __name__ == "__main__":
    main()
