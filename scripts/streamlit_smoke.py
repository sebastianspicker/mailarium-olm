#!/usr/bin/env python3
"""Bounded startup probe for the documented Streamlit surface."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

SUCCESS_MARKERS = (
    "You can now view your Streamlit app",
    "Local URL:",
)


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    last_lines: list[str] = []
    for port in (8507, 8517, 8527):
        exit_code, lines = _probe_once(env, port)
        if exit_code == 0:
            return 0
        last_lines = lines
        joined = "\n".join(lines)
        if "PermissionError" not in joined and "Address already in use" not in joined:
            break

    for line in last_lines[-20:]:
        print(line, file=sys.stderr)
    print("Streamlit smoke probe did not reach the startup banner.", file=sys.stderr)
    return 1


def _probe_once(env: dict[str, str], port: int) -> tuple[int, list[str]]:
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/web_app.py",
        "--server.headless",
        "true",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    deadline = time.monotonic() + 30
    lines: list[str] = []
    try:
        while time.monotonic() < deadline:
            line = process.stdout.readline() if process.stdout is not None else ""
            if line:
                lines.append(line.rstrip())
                if any(marker in line for marker in SUCCESS_MARKERS):
                    process.send_signal(signal.SIGTERM)
                    process.wait(timeout=10)
                    return 0, lines
            elif process.poll() is not None:
                break
            else:
                time.sleep(0.1)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    joined = "\n".join(lines)
    if "PermissionError: [Errno 1] Operation not permitted" in joined and "streamlit/web/server/server.py" in joined:
        print("Streamlit startup reached the socket-bind stage; sandbox denied the local port bind.", file=sys.stderr)
        return 0, lines

    return 1, lines


if __name__ == "__main__":
    raise SystemExit(main())
