#!/usr/bin/env python3
"""Enforce Mailarium's exhaustive package dependency policy.

The policy lists every intentional top-level architectural package and every
allowed cross-package dependency. Imports outside ``mailarium`` remain out of
scope so standard-library and third-party dependencies are unconstrained.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PACKAGE_NAME = "mailarium"

# This is a complete allow-list, not a forbidden-edge exception table. Adding
# a package or an inter-package import requires deliberately extending it.
PACKAGE_DEPENDENCIES = {
    "archive": frozenset({"model"}),
    "ingestion": frozenset({"archive", "investigation", "model", "platform", "retrieval"}),
    "interfaces": frozenset({"archive", "ingestion", "investigation", "mailbox", "model", "platform", "retrieval"}),
    "investigation": frozenset({"archive", "model", "platform", "retrieval"}),
    "mailbox": frozenset({"archive", "ingestion", "model", "retrieval"}),
    "model": frozenset(),
    "platform": frozenset(),
    "privacy": frozenset(),
    "retrieval": frozenset({"archive", "model", "platform"}),
}
KNOWN_PACKAGES = frozenset(PACKAGE_DEPENDENCIES)

# Root modules are composition or entry-point adapters, not feature packages.
# Keeping their dependencies explicit prevents a new top-level module from
# silently bypassing the package policy.
ROOT_MODULE_DEPENDENCIES = {
    "__init__": frozenset(),
    "__main__": frozenset({"mcp_server"}),
    "cli": frozenset({"config", "interfaces", "platform", "runtime"}),
    "config": frozenset({"model", "platform"}),
    "ingest": frozenset({"interfaces"}),
    "mcp_server": frozenset({"archive", "config", "interfaces", "mailbox", "platform", "retrieval", "runtime"}),
    "runtime": frozenset({"archive", "config", "mailbox", "retrieval"}),
    "web_app": frozenset({"config", "interfaces", "investigation", "mailbox", "platform", "retrieval", "runtime"}),
}
KNOWN_ROOT_MODULES = frozenset(ROOT_MODULE_DEPENDENCIES)

# ``config`` is the sole root support module intentionally used inside feature
# packages.  Entry points and runtime composition stay one-way at the root.
PACKAGE_ROOT_DEPENDENCIES = {
    "ingestion": frozenset({"config"}),
    "interfaces": frozenset({"config"}),
    "investigation": frozenset({"config"}),
    "retrieval": frozenset({"config"}),
}


@dataclass(frozen=True)
class Violation:
    """One architecture-policy violation with a stable diagnostic."""

    path: Path
    line: int
    source: str
    target: str
    reason: str

    def render(self, root: Path) -> str:
        return f"{self.path.relative_to(root)}:{self.line} -> {self.source} -> {self.target} ({self.reason})"


@dataclass(frozen=True)
class ImportEdge:
    """A local cross-package import, retained for policy and cycle checks."""

    path: Path
    line: int
    source_module: str
    target_module: str
    source_component: str
    target_component: str


def module_name(path: Path, root: Path) -> str | None:
    """Return the importable module name for a Python file below *root*."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    if relative.suffix != ".py" or not relative.parts or relative.parts[0] != PACKAGE_NAME:
        return None
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _root_exports(package_root: Path) -> frozenset[str]:
    """Return statically declared root-package symbols for explicit imports."""
    init_path = package_root / "__init__.py"
    if not init_path.is_file():
        return frozenset()
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except SyntaxError:
        return frozenset()

    exports: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exports.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            exports.update(target.id for target in targets if isinstance(target, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            exports.update(alias.asname or alias.name.split(".")[0] for alias in node.names if alias.name != "*")
    return frozenset(exports)


def _expanded_root_names(names: Iterable[str], root_exports: frozenset[str]) -> Iterable[str]:
    """Expand child-module imports from the package root without flagging symbols."""
    for name in names:
        if name in KNOWN_PACKAGES or name in KNOWN_ROOT_MODULES:
            yield f"{PACKAGE_NAME}.{name}"
        elif name not in root_exports:
            # Keep an unresolved root import visible so it cannot masquerade
            # as a compatibility alias or a newly added architectural node.
            yield f"{PACKAGE_NAME}.{name}"


def _root_import_names(node: ast.ImportFrom, root_exports: frozenset[str]) -> Iterable[str]:
    """Expand explicit imports from the package root."""
    yield from _expanded_root_names((alias.name for alias in node.names), root_exports)


def imported_modules(
    node: ast.Import | ast.ImportFrom,
    source_module: str,
    *,
    source_is_package: bool,
    root_exports: frozenset[str],
) -> Iterable[str]:
    """Yield absolute module names represented by one import statement."""
    if isinstance(node, ast.Import):
        yield from (alias.name for alias in node.names)
        return
    if node.level == 0:
        if node.module:
            if node.module == PACKAGE_NAME:
                yield from _root_import_names(node, root_exports)
            else:
                yield node.module
        return

    source_package = source_module if source_is_package else source_module.rpartition(".")[0]
    package_parts = source_package.split(".")
    keep = len(package_parts) - (node.level - 1)
    if keep <= 0:
        return
    base = ".".join(package_parts[:keep])
    if node.module:
        yield f"{base}.{node.module}"
        return
    if base == PACKAGE_NAME:
        yield from _root_import_names(node, root_exports)
        return
    for alias in node.names:
        if alias.name != "*":
            yield f"{base}.{alias.name}"


def architectural_component(name: str) -> str | None:
    """Return a local top-level package or root module referenced by *name*."""
    parts = name.split(".")
    if len(parts) < 2 or parts[0] != PACKAGE_NAME:
        return None
    return parts[1]


def source_component(name: str) -> str | None:
    """Return the policy component that owns a local source module."""
    parts = name.split(".")
    if not parts or parts[0] != PACKAGE_NAME:
        return None
    if len(parts) == 1:
        return "__init__"
    if len(parts) == 2:
        return parts[1]
    return parts[1]


def discovered_packages(package_root: Path) -> frozenset[str]:
    """Find all top-level directories that contain Python source files."""
    return frozenset(
        child.name
        for child in package_root.iterdir()
        if child.is_dir() and child.name != "__pycache__" and any("__pycache__" not in path.parts for path in child.rglob("*.py"))
    )


def discovered_root_modules(package_root: Path) -> frozenset[str]:
    """Find top-level Python modules, including the package initializer."""
    return frozenset(path.stem for path in package_root.glob("*.py"))


def _is_root_import(node: ast.ImportFrom, source_module: str, *, source_is_package: bool) -> bool:
    """Return whether an absolute or relative import resolves to ``mailarium``."""
    if node.level == 0:
        return node.module == PACKAGE_NAME
    if node.module is not None:
        return False
    source_package = source_module if source_is_package else source_module.rpartition(".")[0]
    package_parts = source_package.split(".")
    keep = len(package_parts) - (node.level - 1)
    return keep == 1 and package_parts[0] == PACKAGE_NAME


def import_edges(root: Path) -> tuple[list[ImportEdge], list[Violation]]:  # noqa: C901 - AST import forms need one traversal.
    """Parse local imports and report malformed source files."""
    package_root = root / PACKAGE_NAME
    root_exports = _root_exports(package_root)
    edges: list[ImportEdge] = []
    violations: list[Violation] = []
    for path in sorted(package_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source_module = module_name(path, root)
        if source_module is None:
            continue
        owner = source_component(source_module)
        if owner is None:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            line = exc.lineno or 1
            violations.append(Violation(path, line, source_module, source_module, f"invalid Python syntax: {exc.msg}"))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            source_is_package = path.name == "__init__.py"
            if (
                isinstance(node, ast.ImportFrom)
                and any(alias.name == "*" for alias in node.names)
                and _is_root_import(node, source_module, source_is_package=source_is_package)
            ):
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        source_module,
                        PACKAGE_NAME,
                        "root star imports are prohibited",
                    )
                )
                continue
            for target_module in imported_modules(
                node,
                source_module,
                source_is_package=source_is_package,
                root_exports=root_exports,
            ):
                target = architectural_component(target_module)
                if target is not None:
                    edges.append(
                        ImportEdge(
                            path,
                            node.lineno,
                            source_module,
                            target_module,
                            owner,
                            target,
                        )
                    )
    return edges, violations


def _unknown_component_violations(root: Path, edges: Iterable[ImportEdge]) -> list[Violation]:
    """Reject root modules and package directories absent from the policy."""
    package_root = root / PACKAGE_NAME
    violations: list[Violation] = []
    for module in sorted(discovered_root_modules(package_root) - KNOWN_ROOT_MODULES):
        path = package_root / f"{module}.py"
        source = f"{PACKAGE_NAME}.{module}"
        violations.append(Violation(path, 1, source, source, f"unknown root module: {module}"))
    for package in sorted(discovered_packages(package_root) - KNOWN_PACKAGES):
        init_path = package_root / package / "__init__.py"
        path = init_path if init_path.exists() else next((package_root / package).rglob("*.py"))
        source = f"{PACKAGE_NAME}.{package}"
        violations.append(Violation(path, 1, source, source, f"unknown architectural package: {package}"))
    for edge in edges:
        if edge.target_component not in KNOWN_PACKAGES | KNOWN_ROOT_MODULES:
            violations.append(
                Violation(
                    edge.path,
                    edge.line,
                    edge.source_module,
                    edge.target_module,
                    f"unknown root or package: {edge.target_component}",
                )
            )
    return violations


def _forbidden_edge_violations(edges: Iterable[ImportEdge]) -> list[Violation]:
    """Reject every local policy edge absent from the allow-list."""
    violations: list[Violation] = []
    for edge in edges:
        if edge.source_component in KNOWN_PACKAGES:
            allowed = PACKAGE_DEPENDENCIES[edge.source_component] | PACKAGE_ROOT_DEPENDENCIES.get(
                edge.source_component, frozenset()
            )
        elif edge.source_component in KNOWN_ROOT_MODULES:
            allowed = ROOT_MODULE_DEPENDENCIES[edge.source_component]
        else:
            continue
        if edge.target_component not in KNOWN_PACKAGES | KNOWN_ROOT_MODULES:
            continue
        if edge.source_component == edge.target_component:
            continue
        if edge.target_component not in allowed:
            violations.append(
                Violation(
                    edge.path,
                    edge.line,
                    edge.source_module,
                    edge.target_module,
                    f"{edge.source_component} must not import {edge.target_component}",
                )
            )
    return violations


def _cycle_for_component(component: frozenset[str], graph: dict[str, set[str]]) -> tuple[str, ...]:
    """Return one deterministic directed cycle from a strongly connected component."""
    start = min(component)
    trail = [start]

    def visit(node: str) -> tuple[str, ...] | None:
        for neighbor in sorted(graph[node] & component):
            if neighbor == start:
                return (*trail, start)
            if neighbor in trail:
                continue
            trail.append(neighbor)
            cycle = visit(neighbor)
            if cycle is not None:
                return cycle
            trail.pop()
        return None

    cycle = visit(start)
    if cycle is None:
        raise AssertionError("strongly connected component did not contain a cycle")
    return cycle


def _cyclic_components(graph: dict[str, set[str]]) -> list[frozenset[str]]:  # noqa: C901 - Tarjan's algorithm is intentionally compact.
    """Return every cyclic strongly connected component in deterministic order."""
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[frozenset[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in sorted(graph[node]):
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])
        if lowlinks[node] != indices[node]:
            return
        component: set[str] = set()
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.add(member)
            if member == node:
                break
        if len(component) > 1 or node in graph[node]:
            components.append(frozenset(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components, key=lambda component: tuple(sorted(component)))


def _cycle_violations(edges: Iterable[ImportEdge]) -> list[Violation]:
    """Reject every package cycle, including one introduced by a shim package."""
    edge_list = [
        edge
        for edge in edges
        if edge.source_component != edge.target_component
        and edge.source_component not in KNOWN_ROOT_MODULES
        and edge.target_component not in KNOWN_ROOT_MODULES
    ]
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edge_list:
        graph[edge.source_component].add(edge.target_component)
        graph.setdefault(edge.target_component, set())
    violations: list[Violation] = []
    for component in _cyclic_components(graph):
        cycle = _cycle_for_component(component, graph)
        first_source, first_target = cycle[0], cycle[1]
        edge = min(
            (
                candidate
                for candidate in edge_list
                if candidate.source_component == first_source and candidate.target_component == first_target
            ),
            key=lambda candidate: (candidate.path, candidate.line, candidate.source_module, candidate.target_module),
        )
        violations.append(
            Violation(
                edge.path,
                edge.line,
                edge.source_module,
                edge.target_module,
                f"package cycle: {' -> '.join(cycle)}",
            )
        )
    return violations


def check(root: Path) -> list[Violation]:
    """Collect all package-policy violations below ``root/mailarium``."""
    package_root = root / PACKAGE_NAME
    if not package_root.is_dir():
        raise ValueError(f"missing package directory: {package_root}")
    edges, syntax_violations = import_edges(root)
    violations = [
        *syntax_violations,
        *_unknown_component_violations(root, edges),
        *_forbidden_edge_violations(edges),
        *_cycle_violations(edges),
    ]
    return sorted(violations, key=lambda item: (item.path, item.line, item.source, item.target, item.reason))


def main(argv: list[str] | None = None) -> int:
    """Run the architecture gate for a repository root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        violations = check(root)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"Architecture check failed: {exc}")
        return 1

    if violations:
        print("Architectural dependency violations:")
        for violation in violations:
            print(violation.render(root))
        return 1

    print("Architecture dependency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
