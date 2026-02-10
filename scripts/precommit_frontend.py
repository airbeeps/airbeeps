from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"


def _to_posix(path: str) -> str:
    return path.replace("\\", "/")


def _iter_frontend_relpaths(files: Sequence[str]) -> list[str]:
    relpaths: list[str] = []
    for f in files:
        f_posix = _to_posix(f)
        if not f_posix.startswith("frontend/"):
            continue

        abs_path = (REPO_ROOT / Path(f_posix)).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            continue

        relpaths.append(f_posix.removeprefix("frontend/"))

    return sorted(set(relpaths))


def _run(cmd: list[str]) -> int:
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False, shell=True)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run frontend tooling (pnpm) on files passed by pre-commit.",
    )
    parser.add_argument("tool", choices=["prettier", "eslint"])
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not FRONTEND_DIR.is_dir():
        parser.error("frontend/ directory not found (expected at repository root).")

    relpaths = _iter_frontend_relpaths(args.files)
    if not relpaths:
        return 0

    if args.tool == "prettier":
        cmd = [
            "pnpm",
            "-C",
            "frontend",
            "exec",
            "prettier",
            "--write",
            "--ignore-unknown",
            *relpaths,
        ]
        return _run(cmd)

    if args.tool == "eslint":
        cmd = [
            "pnpm",
            "-C",
            "frontend",
            "exec",
            "eslint",
            "--fix",
            *relpaths,
        ]
        return _run(cmd)

    raise AssertionError(f"Unhandled tool: {args.tool}")


if __name__ == "__main__":
    raise SystemExit(main())
