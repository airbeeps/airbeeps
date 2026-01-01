#!/usr/bin/env python3
"""
CLI bootstrap (Typer) mirroring backend/entrypoint.sh with extras.

Commands:
  init             Run migrations + seed safe defaults (system configs)
  migrate          Run alembic upgrade head
  config-init      Seed system config defaults from seed.yaml
  superuser        Create a superuser (interactive or via env/options)
  list-superusers  List superusers
  reset-db         Danger: downgrade to base then upgrade head (data loss)

Note: Airbeeps does not ship with a default admin credential.
The first registered user becomes an admin automatically.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

# On Windows, some terminals still default to legacy encodings (e.g. cp1252),
# which can raise UnicodeEncodeError when printing emoji/log symbols.
# Reconfigure to UTF-8 so CLI output is robust cross-platform.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = typer.Typer(no_args_is_help=True, help="Backend bootstrap helper.")


def run_step(title: str, cmd: list[str], env: dict[str, str] | None = None) -> None:
    typer.echo(title)
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=True)  # noqa: S603
        typer.echo("✅ Done\n")
    except subprocess.CalledProcessError as exc:
        typer.echo(f"❌ Failed: {exc}", err=True)
        raise typer.Exit(exc.returncode)


def build_env(email: str | None, password: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if email:
        env["SUPERUSER_EMAIL"] = email
    if password:
        env["SUPERUSER_PASSWORD"] = password
    return env


@app.command()
def migrate() -> None:
    """Run alembic upgrade head."""
    run_step(
        "📦 Running database migrations...",
        [sys.executable, "-m", "alembic", "upgrade", "head"],
    )


@app.command("config-init")
def config_init() -> None:
    """Seed system configuration defaults (idempotent)."""
    run_step(
        "⚙️  Seeding system configuration defaults...",
        [sys.executable, "scripts/seed_data.py", "--file", "airbeeps/config/seed.yaml"],
    )


@app.command()
def superuser(
    email: str | None = typer.Option(
        None, "--email", "-e", help="Superuser email (overrides env/default)"
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        "-p",
        help="Superuser password (overrides env/default; use with care in shells)",
    ),
) -> None:
    """Create a superuser."""
    env = build_env(email, password)
    run_step(
        "👤 Creating superuser...",
        [sys.executable, "scripts/create_superuser.py"],
        env=env,
    )


@app.command("list-superusers")
def list_superusers() -> None:
    """List existing superusers."""
    run_step(
        "📜 Listing superusers...",
        [sys.executable, "scripts/create_superuser.py", "--list"],
    )


@app.command()
def init(
    skip_migrate: bool = typer.Option(
        False, "--skip-migrate", help="Skip alembic migrations"
    ),
    skip_seed: bool = typer.Option(
        False, "--skip-seed", help="Skip seeding safe defaults from seed.yaml"
    ),
    seed_file: str = typer.Option(
        "airbeeps/config/seed.yaml",
        "--seed-file",
        help="Seed file path (used unless --skip-seed)",
    ),
) -> None:
    """Run full initialization (migrate + seed safe defaults)."""

    if not skip_migrate:
        run_step(
            "📦 Running database migrations...",
            [sys.executable, "-m", "alembic", "upgrade", "head"],
        )

    if not skip_seed:
        run_step(
            f"🌱 Seeding database from {seed_file}...",
            [sys.executable, "scripts/seed_data.py", "--file", seed_file],
        )

    typer.echo("✨ Initialization completed!")


@app.command("seed")
def seed(
    file: str = typer.Option(
        "airbeeps/config/seed.yaml",
        "--file",
        "-f",
        help="Path to seed YAML file (default: airbeeps/config/seed.yaml)",
    ),
) -> None:
    """Seed database with providers/models/assistants/users from YAML."""
    run_step(
        f"🌱 Seeding database from {file}...",
        [sys.executable, "scripts/seed_data.py", "--file", file],
    )


@app.command("reset-db")
def reset_db(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Do not prompt for confirmation (danger: drops all data)",
    ),
) -> None:
    """
    Drop all data by downgrading to base then re-upgrading to head.
    This will wipe the database managed by Alembic.
    """
    if not force:
        typer.confirm(
            "This will DROP all data (alembic downgrade base then upgrade head). Continue?",
            abort=True,
        )

    run_step(
        "🧹 Downgrading database to base (dropping schema)...",
        [sys.executable, "-m", "alembic", "downgrade", "base"],
    )
    run_step(
        "📦 Re-applying migrations to head...",
        [sys.executable, "-m", "alembic", "upgrade", "head"],
    )
    typer.echo("✅ Database reset complete.")


if __name__ == "__main__":
    app()
