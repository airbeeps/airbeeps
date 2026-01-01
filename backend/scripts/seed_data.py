#!/usr/bin/env python3
"""
Command-line script for seeding the database from a YAML config file.

This script is a thin wrapper around the airbeeps.seeder module,
providing a CLI interface for manual database seeding during development.

For production use, seeding happens automatically via the CLI's run command.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make project importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from airbeeps.seeder import seed_from_file  # noqa: E402


def main() -> None:
    """CLI entry point for manual database seeding."""
    parser = argparse.ArgumentParser(
        description="Seed database from YAML config file (idempotent)."
    )
    parser.add_argument(
        "--file",
        "-f",
        default=str(PROJECT_ROOT / "airbeeps" / "config" / "seed.yaml"),
        help="Path to seed YAML file (default: airbeeps/config/seed.yaml)",
    )
    args = parser.parse_args()

    seed_file = Path(args.file)
    if not seed_file.exists():
        print(f"Error: Seed file not found: {seed_file}")
        sys.exit(1)

    print(f"Seeding database from: {seed_file}")
    try:
        asyncio.run(seed_from_file(seed_file))
        print("\nSeeding completed successfully!")
    except Exception as e:
        print(f"\nError: Seeding failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
