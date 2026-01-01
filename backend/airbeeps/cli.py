"""
Command-line interface for Airbeeps.

Provides commands to run the server, manage migrations, and create users.
"""

import asyncio
import logging
import signal
import sys

import typer
import uvicorn
from rich.console import Console
from rich.prompt import Prompt

app = typer.Typer(
    name="airbeeps",
    help="Airbeeps - Local-first, self-hosted AI assistant for chat and RAG",
    add_completion=False,
)

console = Console()
logger = logging.getLogger(__name__)


@app.command()
def run(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8500, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(
        False, "--reload", help="Enable auto-reload (dev mode)"
    ),
    with_migrations: bool = typer.Option(
        True, "--with-migrations/--no-migrations", help="Run migrations before starting"
    ),
    log_level: str = typer.Option("info", "--log-level", help="Log level"),
):
    """
    Start the Airbeeps server.

    This command will:
    1. Check and run database migrations (if needed)
    2. Start the FastAPI server with uvicorn
    3. Serve both API and frontend (if bundled)
    """
    from .config import settings
    from .migrations import (
        ensure_tables_exist,
        get_current_revision,
        get_database_path,
        needs_migration,
        run_migrations,
    )

    console.print("\n[bold cyan]Airbeeps[/bold cyan]\n")

    # Show actual paths
    console.print(f"Data directory: {settings.DATA_ROOT}")
    console.print(f"Database: {get_database_path()}")

    # Check if we need to run migrations
    if with_migrations:
        try:
            current_rev = get_current_revision()

            if current_rev is None:
                console.print(
                    "[yellow]Database not initialized. Running initial migrations...[/yellow]"
                )
                run_migrations()
                console.print("[green]OK: Database initialized successfully[/green]")
            elif needs_migration():
                console.print("[yellow]Database needs migration. Upgrading...[/yellow]")
                run_migrations()
                console.print("[green]OK: Database migrated successfully[/green]")
            # Even if "up to date", verify tables exist (handles broken migrations)
            elif ensure_tables_exist():
                console.print("[green]OK: Database is up to date[/green]")
            else:
                console.print("[red]ERROR: Failed to verify database tables[/red]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]ERROR: Migration failed: {e}[/red]")
            console.print(
                "[yellow]You can skip migrations with --no-migrations flag[/yellow]"
            )
            raise typer.Exit(1)

    # Run initial seed if this is the first run
    console.print("\n[cyan]Checking initial data...[/cyan]")
    try:
        from .seeder import has_been_seeded, run_initial_seed

        if has_been_seeded():
            console.print("[dim]Database already seeded[/dim]")
        else:
            console.print("[yellow]Running initial seed...[/yellow]")
            seed_success = asyncio.run(run_initial_seed())
            if seed_success:
                console.print("[green]OK: Initial data seeded successfully[/green]")
            else:
                console.print(
                    "[yellow]Warning: Initial seed failed, you may need to create users manually[/yellow]"
                )
    except Exception as e:
        console.print(f"[yellow]Warning: Could not run initial seed: {e}[/yellow]")
        console.print("[dim]You can create users with: airbeeps create-user[/dim]")

    # Check if SECRET_KEY is still default
    if settings.SECRET_KEY == "change-me-in-production":
        console.print(
            "[yellow]WARNING: Using default SECRET_KEY. "
            "Set AIRBEEPS_SECRET_KEY environment variable for production![/yellow]"
        )

    # Start the server
    console.print(f"\n[bold green]Starting server at http://{host}:{port}[/bold green]")
    console.print("[dim]Press CTRL+C to stop[/dim]\n")

    # Setup signal handlers for graceful shutdown
    # This handles CTRL+C properly since uvicorn.run() blocks the main thread
    def signal_handler(sig, frame):
        console.print("\n[yellow]Shutting down gracefully...[/yellow]")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        uvicorn.run(
            "airbeeps.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
            timeout_graceful_shutdown=5,  # 5 seconds for graceful shutdown
        )
    except KeyboardInterrupt:
        # Catch any KeyboardInterrupt that makes it through
        console.print("\n[yellow]Server stopped[/yellow]")
        sys.exit(0)


@app.command()
def migrate(
    revision: str = typer.Argument("head", help="Target revision (default: head)"),
    show_current: bool = typer.Option(False, "--show", help="Show current revision"),
):
    """
    Run database migrations.

    Examples:
        airbeeps migrate              # Migrate to latest
        airbeeps migrate --show       # Show current revision
        airbeeps migrate <revision>   # Migrate to specific revision
    """
    from .migrations import run_migrations, show_current_revision

    if show_current:
        show_current_revision()
        return

    console.print(f"[cyan]Running migrations to: {revision}[/cyan]")
    try:
        run_migrations(revision)
        console.print("[green]OK: Migrations completed[/green]")
    except Exception as e:
        console.print(f"[red]ERROR: Migration failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def create_user(
    email: str | None = typer.Option(None, "--email", "-e", help="User email"),
    password: str | None = typer.Option(None, "--password", "-p", help="User password"),
    superuser: bool = typer.Option(False, "--superuser", help="Create as superuser"),
):
    """
    Create a new user.

    If email/password are not provided, you'll be prompted interactively.
    """
    from .database import async_session_maker
    from .users.models import User

    async def _create_user():
        # Prompt for email if not provided
        if not email:
            user_email = Prompt.ask("Email")
        else:
            user_email = email

        # Prompt for password if not provided
        if not password:
            user_password = Prompt.ask("Password", password=True)
        else:
            user_password = password

        # Create user
        async with async_session_maker() as session:
            from fastapi_users.password import PasswordHelper

            password_helper = PasswordHelper()
            hashed_password = password_helper.hash(user_password)

            user = User(
                email=user_email,
                hashed_password=hashed_password,
                is_active=True,
                is_verified=True,
                is_superuser=superuser,
            )

            session.add(user)
            await session.commit()
            await session.refresh(user)

            return user

    try:
        user = asyncio.run(_create_user())
        role = "superuser" if superuser else "user"
        console.print(
            f"[green]OK: Created {role}: {user.email} (ID: {user.id})[/green]"
        )
    except Exception as e:
        console.print(f"[red]ERROR: Failed to create user: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    from . import __version__

    console.print(f"Airbeeps version: {__version__}")


@app.command()
def info():
    """Show configuration information."""
    from .config import BASE_DIR, PROJECT_ROOT, _is_installed_package, settings

    console.print("\n[bold cyan]Airbeeps Configuration[/bold cyan]\n")
    console.print(
        f"Installation mode: {'Installed Package' if _is_installed_package() else 'Development'}"
    )
    console.print(f"Base directory: {BASE_DIR}")
    console.print(f"Project root: {PROJECT_ROOT}")
    console.print(f"Data directory: {settings.DATA_ROOT}")
    # Redact credentials from database URL if present
    db_url = settings.DATABASE_URL
    if "@" in db_url:
        # URL contains credentials - redact them
        import re

        db_url = re.sub(r"://[^:]+:[^@]+@", "://*****:*****@", db_url)
    console.print(f"Database URL: {db_url}")
    console.print(
        f"Chroma mode: {'Embedded' if not settings.CHROMA_SERVER_HOST else 'Server'}"
    )
    if settings.CHROMA_SERVER_HOST:
        console.print(
            f"Chroma server: {settings.CHROMA_SERVER_HOST}:{settings.CHROMA_SERVER_PORT}"
        )
    console.print(f"Chroma persist dir: {settings.CHROMA_PERSIST_DIR}")
    console.print()


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
