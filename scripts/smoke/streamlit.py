#!/usr/bin/env python3
"""Execute a Streamlit app body and assert its first meaningful screen renders."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Running this file directly would otherwise resolve ``streamlit`` to this
# script instead of the installed package.
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path = [entry for entry in sys.path if Path(entry or ".").resolve() != SCRIPT_DIRECTORY]

ROOT = Path(__file__).resolve().parents[2]
VISIBLE_ELEMENT = "Search the archive"
DEFAULT_TIMEOUT_SECONDS = 45


def _mailarium_package_root(app_path: Path) -> Path | None:
    """Return the containing import root for a Mailarium app, if this is one."""
    package_directory = app_path.parent
    if package_directory.name != "mailarium" or not (package_directory / "__init__.py").is_file():
        return None
    return package_directory.parent


def _remove_mailarium_modules() -> None:
    """Remove the active Mailarium package tree so the selected app root wins."""
    for module_name in tuple(sys.modules):
        if module_name == "mailarium" or module_name.startswith("mailarium."):
            sys.modules.pop(module_name, None)


@contextmanager
def _app_import_context(app_path: Path) -> Iterator[None]:
    """Run a Mailarium app against its exact package root and restore the caller state."""
    package_root = _mailarium_package_root(app_path)
    if package_root is None:
        yield
        return

    original_path = list(sys.path)
    original_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name == "mailarium" or module_name.startswith("mailarium.")
    }
    resolved_root = package_root.resolve()
    sys.path[:] = [
        str(resolved_root),
        *[entry for entry in original_path if Path(entry or ".").resolve() not in {SCRIPT_DIRECTORY, resolved_root}],
    ]
    _remove_mailarium_modules()
    importlib.invalidate_caches()
    try:
        import mailarium

        package_file = getattr(mailarium, "__file__", None)
        if package_file is None or not Path(package_file).resolve().is_relative_to(resolved_root):
            raise RuntimeError(f"Mailarium import does not resolve from app package root: {resolved_root}")
        yield
    finally:
        _remove_mailarium_modules()
        sys.modules.update(original_modules)
        sys.path[:] = original_path
        importlib.invalidate_caches()


def run_app_test(app_path: Path) -> None:
    """Execute one Streamlit script through AppTest and reject app-body failures."""
    from streamlit.testing.v1 import AppTest

    with _app_import_context(app_path):
        app = AppTest.from_file(str(app_path), default_timeout=DEFAULT_TIMEOUT_SECONDS)
        app.run(timeout=DEFAULT_TIMEOUT_SECONDS)
    exceptions = [str(exception.value) for exception in app.exception]
    if exceptions:
        details = "\n".join(exceptions)
        raise RuntimeError(f"Streamlit app raised an exception:\n{details}")
    visible_markdown = [str(element.value) for element in app.markdown]
    if not any(VISIBLE_ELEMENT in value for value in visible_markdown):
        raise RuntimeError(f"Streamlit app did not render the expected visible element: {VISIBLE_ELEMENT!r}")


def main(argv: list[str] | None = None) -> int:
    """Run the app-body smoke for a source checkout or installed package script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=ROOT / "mailarium" / "web_app.py")
    args = parser.parse_args(argv)
    app_path = args.app.resolve()
    if not app_path.is_file():
        print(f"Streamlit app does not exist: {app_path}", file=sys.stderr)
        return 1
    try:
        run_app_test(app_path)
    except (OSError, RuntimeError, TimeoutError) as exc:
        print(f"Streamlit AppTest smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"Streamlit AppTest smoke passed: {app_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
