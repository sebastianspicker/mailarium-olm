#!/usr/bin/env python3
"""Validate that release archives contain templates and no local workspace data.

Run this after building into ``dist/`` or pass a release directory or archives:

    python scripts/check_release_artifacts.py dist
"""

from __future__ import annotations

import argparse
import email
import sys
import tarfile
import tomllib
import zipfile
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "mailarium" / "templates"
PRIVATE_PATH_PREFIXES = (
    ".agents/",
    ".codex/",
    ".env",
    "archive/local/",
    "audit/",
    "docs/agent/",
    "local/",
    "pre-clean/",
    "private/",
)
ARCHIVE_SUFFIXES = (".whl", ".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".tar")


def expected_version(pyproject_path: Path = ROOT / "pyproject.toml") -> str:
    """Read the canonical package version from the project metadata."""
    with pyproject_path.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return str(project["version"])


def required_template_paths(template_root: Path = TEMPLATE_ROOT) -> set[str]:
    """Enumerate every dossier HTML template that release archives must contain."""
    root = template_root.parents[1]
    return {path.relative_to(root).as_posix() for path in template_root.rglob("*.html")}


def _archive_members(artifact: Path) -> tuple[set[str], str | None]:
    """Read wheel, ZIP, or source-distribution members and extract their embedded package version."""
    if artifact.suffix == ".whl" or artifact.suffix == ".zip":
        return _zip_archive_members(artifact)

    if artifact.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tar")):
        return _tar_archive_members(artifact)

    raise ValueError(f"unsupported artifact type: {artifact}")


def _zip_archive_members(artifact: Path) -> tuple[set[str], str | None]:
    """Read ZIP member names and package version metadata."""
    with zipfile.ZipFile(artifact) as archive:
        names = set(archive.namelist())
        metadata = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        version = _metadata_version(archive.read(metadata).decode("utf-8")) if metadata else None
    return names, version


def _tar_archive_members(artifact: Path) -> tuple[set[str], str | None]:
    """Read source-distribution member names and package version metadata."""
    with tarfile.open(artifact) as archive:
        names = {member.name for member in archive.getmembers()}
        metadata = next((name for name in names if name.endswith("/PKG-INFO") or name == "PKG-INFO"), None)
        member = archive.extractfile(metadata) if metadata else None
        version = _metadata_version(member.read().decode("utf-8")) if member else None
    return names, version


def _metadata_version(contents: str) -> str | None:
    """Parse the Version field from wheel METADATA or source PKG-INFO contents."""
    message = email.message_from_string(contents)
    return message.get("Version")


def _matches_required_path(member: str, required_path: str) -> bool:
    """Match required files regardless of an archive's top-level prefix."""
    return member == required_path or member.endswith(f"/{required_path}")


def _is_private_or_workspace_path(member: str) -> bool:
    """Reject private data and local-workspace paths from release artifacts."""
    normalized = member.lstrip("./")
    parts = normalized.split("/")
    relative = "/".join(parts[1:]) if len(parts) > 1 and parts[0] else normalized
    candidate_paths = (normalized, relative)
    for candidate in candidate_paths:
        path_parts = set(candidate.split("/"))
        if path_parts & {".agents", ".codex", "audit", "local", "pre-clean", "private"}:
            return True
        if candidate.startswith(PRIVATE_PATH_PREFIXES) or Path(candidate).name.startswith("AUDIT_REPORT_"):
            return True
        if "/.env" in f"/{candidate}" or "/docs/agent/" in f"/{candidate}":
            return True
    return False


def validate_artifact(
    artifact: Path,
    *,
    version: str | None = None,
    required_templates: set[str] | None = None,
) -> list[str]:
    """Verify one archive's version, required templates, and absence of private workspace paths."""
    version = version or expected_version()
    required_templates = required_templates if required_templates is not None else required_template_paths()
    try:
        members, archive_version = _archive_members(artifact)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        return [f"{artifact}: cannot read artifact ({exc})"]

    errors: list[str] = []
    if archive_version != version:
        errors.append(f"{artifact}: metadata version {archive_version!r} does not match pyproject version {version!r}")

    missing = sorted(path for path in required_templates if not any(_matches_required_path(member, path) for member in members))
    if missing:
        errors.append(f"{artifact}: missing required templates: {', '.join(missing)}")

    forbidden = sorted(member for member in members if _is_private_or_workspace_path(member))
    if forbidden:
        errors.append(f"{artifact}: contains private, local, audit, or agent-workspace paths: {', '.join(forbidden)}")
    return errors


def validate_artifacts(artifacts: Iterable[Path]) -> list[str]:
    """Validate an artifact set against one shared project version and template inventory."""
    version = expected_version()
    templates = required_template_paths()
    errors: list[str] = []
    for artifact in artifacts:
        errors.extend(validate_artifact(artifact, version=version, required_templates=templates))
    return errors


def _is_archive(path: Path) -> bool:
    """Recognize supported release archive suffixes before inspection."""
    return path.name.endswith(ARCHIVE_SUFFIXES)


def _expand_artifact_inputs(inputs: Iterable[Path]) -> tuple[list[Path], list[str]]:
    """Expand release directories while retaining explicit invalid-file errors."""
    artifacts: list[Path] = []
    errors: list[str] = []
    for candidate in inputs:
        if candidate.is_dir():
            constraints = candidate / "requirements.locked.txt"
            if not constraints.is_file():
                errors.append(f"{candidate}: missing requirements.locked.txt")
            artifacts.extend(sorted(path for path in candidate.iterdir() if path.is_file() and _is_archive(path)))
        else:
            artifacts.append(candidate)
    return artifacts, errors


def _artifact_set_errors(artifacts: Iterable[Path]) -> list[str]:
    """Require exactly one wheel and one source distribution in the release set."""
    names = [artifact.name for artifact in artifacts]
    wheels = [name for name in names if name.endswith(".whl")]
    sdists = [name for name in names if name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tar"))]
    other_archives = [name for name in names if name not in wheels and name not in sdists]
    errors: list[str] = []
    if not wheels:
        errors.append("release artifact set is missing a wheel")
    elif len(wheels) != 1:
        errors.append(f"release artifact set must contain exactly one wheel; found {len(wheels)}")
    if not sdists:
        errors.append("release artifact set is missing a source distribution")
    elif len(sdists) != 1:
        errors.append(f"release artifact set must contain exactly one source distribution; found {len(sdists)}")
    if other_archives:
        errors.append(f"release artifact set contains unsupported release archives: {', '.join(sorted(other_archives))}")
    return errors


def main(argv: list[str] | None = None) -> int:
    """Expand artifact inputs, enforce wheel/sdist completeness, and report release validation failures."""
    parser = argparse.ArgumentParser(description="Validate release wheel and sdist contents.")
    parser.add_argument("artifacts", nargs="*", type=Path, help="wheel or source-distribution archive (defaults to dist/)")
    args = parser.parse_args(argv)
    inputs = args.artifacts or [ROOT / "dist"]
    artifacts, errors = _expand_artifact_inputs(inputs)
    if not artifacts:
        parser.error("no wheel or source-distribution artifacts found")

    errors.extend(_artifact_set_errors(artifacts))
    errors.extend(validate_artifacts(artifacts))
    if errors:
        print("Release artifact validation failed:", file=sys.stderr)
        print(*errors, sep="\n", file=sys.stderr)
        return 1
    print(f"Release artifact validation passed for {len(artifacts)} artifact(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
