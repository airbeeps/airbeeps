#!/usr/bin/env python3
"""
Clean up build artifacts and temporary files.

This script removes:
- backend/airbeeps/static/ (bundled frontend)
- backend/dist/ (built wheels)
- frontend/.output/ (Nuxt build output)
"""

import shutil
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIR = PROJECT_ROOT / "backend"

PATHS_TO_CLEAN = [
    BACKEND_DIR / "airbeeps" / "static",
    BACKEND_DIR / "dist",
    FRONTEND_DIR / ".output",
]


def main():
    """Clean up build artifacts."""
    print("🧹 Cleaning build artifacts...\n")

    cleaned = 0
    for path in PATHS_TO_CLEAN:
        if path.exists():
            print(f"  Removing: {path}")
            shutil.rmtree(path)
            cleaned += 1
        else:
            print(f"  Skipping (not found): {path}")

    print(f"\n✅ Cleaned {cleaned} directories")


if __name__ == "__main__":
    main()
