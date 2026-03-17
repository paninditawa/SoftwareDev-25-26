from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

from launcher.app import main


REPO_ROOT = Path(__file__).resolve().parent


def _resolve_target(relative_target: str) -> Path:
    return (REPO_ROOT / relative_target).resolve()


def _run_target(relative_target: str, target_args: list[str]) -> None:
    target = _resolve_target(relative_target)
    if not target.exists():
        raise FileNotFoundError(f"Missing target script: {target}")

    sys.argv = [str(target), *target_args]
    original_cwd = Path.cwd()
    os.chdir(target.parent)
    sys.path.insert(0, str(target.parent))
    try:
        runpy.run_path(str(target), run_name="__main__")
    finally:
        os.chdir(original_cwd)


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="HelloWorld GameSpace launcher")
    parser.add_argument("--run-target", help="Run a script relative to the app root")
    return parser.parse_known_args()


if __name__ == "__main__":
    args, remaining = _parse_args()
    if args.run_target:
        _run_target(args.run_target, remaining)
    else:
        main()
