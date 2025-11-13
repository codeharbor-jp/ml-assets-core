#!/usr/bin/env python3
"""
最終リリース前に必ず通すべき自動チェックをまとめて実行するスクリプト。

実行内容:
    1. ruff lint
    2. mypy type check
    3. pytest (unit + integration)

使い方:
    $ python scripts/checks/run_release_gate.py

失敗したコマンドがある場合はスクリプトが非ゼロコードで終了し、
当該コマンドのログを確認できる。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMMANDS = [
    ["docker", "compose", "run", "--rm", "ml-core", "ruff", "check", "."],
    ["docker", "compose", "run", "--rm", "ml-core", "mypy", "src"],
    ["docker", "compose", "run", "--rm", "ml-core", "pytest"],
]


def run_command(command: list[str]) -> int:
    print(f"\n[INFO] Running command: {' '.join(command)}")
    process = subprocess.run(command, cwd=PROJECT_ROOT)
    if process.returncode != 0:
        print(f"[ERROR] Command failed: {' '.join(command)}", file=sys.stderr)
    return process.returncode


def main() -> int:
    failures: list[list[str]] = []
    for command in COMMANDS:
        if run_command(command) != 0:
            failures.append(command)

    if failures:
        print("\n[SUMMARY] Release gate failed.", file=sys.stderr)
        for failed_command in failures:
            print(f"  - {' '.join(failed_command)}", file=sys.stderr)
        return 1

    print("\n[SUMMARY] Release gate passed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

