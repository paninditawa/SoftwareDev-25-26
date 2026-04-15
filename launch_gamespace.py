"""
Entry point for the HelloWorld GameSpace launcher. #hi
Running this file directly opens the main launcher window.
It can also be called with --run-target to launch an individual game
script (the launcher does this to open games in their own process).
"""

# annotations keeps type hints as strings so they load faster
from __future__ import annotations

# argparse reads command-line options like --run-target
import argparse
# os lets us change the working directory before running a script
import os
# runpy runs a .py file as if it was the main script
import runpy
# sys is used to update the module search path
import sys
# Path is a safe, OS-independent way to work with file paths
from pathlib import Path


# folder that contains this file = root of the entire project
REPO_ROOT = Path(__file__).resolve().parent


def _resolve_target(relative_target: str) -> Path:
    # turn the relative path (e.g. "games/Battleship/client.py") into a full path
    return (REPO_ROOT / relative_target).resolve()


def _run_target(relative_target: str, target_args: list[str]) -> None:
    # locate the script; raise a clear error if it's missing
    target = _resolve_target(relative_target)
    if not target.exists():
        raise FileNotFoundError(f"Missing target script: {target}")

    # override sys.argv so the script sees its own arguments
    sys.argv = [str(target), *target_args]
    # remember where we started so we can restore it after
    original_cwd = Path.cwd()
    # run from the script's own folder so relative file paths inside it work
    os.chdir(target.parent)
    sys.path.insert(0, str(target.parent))
    try:
        # execute the script as __main__ (same as running it directly)
        runpy.run_path(str(target), run_name="__main__")
    finally:
        # always restore the original working directory
        os.chdir(original_cwd)


def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    # set up the argument parser with one optional flag
    parser = argparse.ArgumentParser(description="HelloWorld GameSpace launcher")
    parser.add_argument("--run-target", help="Run a script relative to the app root")
    # parse_known_args ignores extra flags that belong to the target script
    return parser.parse_known_args()


def _print_dependency_help(exc: ModuleNotFoundError) -> None:
    missing = exc.name or "a required package"
    print(f"Missing Python package: {missing}")
    print("Use the project virtual environment, then install requirements:")
    print("  Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1")
    print("  Then run: python -m pip install -r requirements.txt")
    print("If you already installed dependencies, check that 'python' points to .venv.")


if __name__ == "__main__":
    args, remaining = _parse_args()
    try:
        if args.run_target:
            # launcher called with --run-target: run a specific game script
            _run_target(args.run_target, remaining)
        else:
            # normal launch: open the main window
            from launcher.ui.application import main

            main()
    except ModuleNotFoundError as exc:
        _print_dependency_help(exc)
        raise SystemExit(1)
