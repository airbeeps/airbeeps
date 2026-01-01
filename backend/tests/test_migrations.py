"""
Migration smoke tests.

These tests verify that Alembic migrations can be applied successfully
to a fresh database.

Note: These tests use the run_migrations() helper from airbeeps.migrations
which handles the async SQLite driver correctly, rather than directly
calling alembic commands with sync URLs.
"""

import os

import pytest


class TestMigrations:
    """Test that migrations apply cleanly."""

    def test_alembic_upgrade_head(self, session_tmp_path, setup_test_environment):
        """
        Verify that running migrations on a fresh DB succeeds.

        This test creates a completely fresh temporary database and runs
        all migrations to ensure they apply without errors.
        """
        # Create a fresh temp database for this test
        db_path = session_tmp_path / "migration_smoke_test.db"
        # Use async URL since alembic env.py uses async_engine_from_config
        db_url = f"sqlite+aiosqlite:///{db_path}"

        # Set the environment variable so settings picks it up
        old_db_url = os.environ.get("AIRBEEPS_DATABASE_URL")
        os.environ["AIRBEEPS_DATABASE_URL"] = db_url

        try:
            # Need to reload settings to pick up new DATABASE_URL
            # Use run_migrations which handles async correctly
            from airbeeps.migrations import run_migrations

            # Run migrations to head
            run_migrations()

            # Verify the database was created
            assert db_path.exists(), "Database file should exist after migrations"
        finally:
            # Restore original
            if old_db_url is not None:
                os.environ["AIRBEEPS_DATABASE_URL"] = old_db_url
            else:
                os.environ.pop("AIRBEEPS_DATABASE_URL", None)

    def test_migrations_match_models(self, session_tmp_path, setup_test_environment):
        """
        Verify that migrations result in the same schema as create_all.

        This is a basic sanity check that compares table names between:
        1. A database created via migrations
        2. A database created via Base.metadata.create_all
        """
        from sqlalchemy import create_engine, inspect

        import airbeeps.agents.models
        import airbeeps.ai_models.models
        import airbeeps.assistants.models
        import airbeeps.auth.oauth_models
        import airbeeps.auth.refresh_token_models
        import airbeeps.feedback.models
        import airbeeps.files.models
        import airbeeps.rag.models
        import airbeeps.system_config.models

        # Import all models to register them
        import airbeeps.users.models  # noqa: F401
        from airbeeps.models import Base

        # Create DB via migrations
        migration_db_path = session_tmp_path / "via_migrations.db"
        migration_db_url = f"sqlite+aiosqlite:///{migration_db_path}"

        # Set the environment variable for migrations
        old_db_url = os.environ.get("AIRBEEPS_DATABASE_URL")
        os.environ["AIRBEEPS_DATABASE_URL"] = migration_db_url

        try:
            from airbeeps.migrations import run_migrations

            run_migrations()
        finally:
            if old_db_url is not None:
                os.environ["AIRBEEPS_DATABASE_URL"] = old_db_url
            else:
                os.environ.pop("AIRBEEPS_DATABASE_URL", None)

        # Create DB via create_all (sync URL for sync engine)
        models_db_path = session_tmp_path / "via_models.db"
        models_db_url = f"sqlite:///{models_db_path}"

        models_engine = create_engine(models_db_url)
        Base.metadata.create_all(bind=models_engine)

        # Compare table names (sync URL for inspection)
        migration_sync_url = f"sqlite:///{migration_db_path}"
        migration_engine = create_engine(migration_sync_url)

        migration_inspector = inspect(migration_engine)
        models_inspector = inspect(models_engine)

        migration_tables = set(migration_inspector.get_table_names())
        models_tables = set(models_inspector.get_table_names())

        # alembic_version is only in migration DB, which is expected
        migration_tables.discard("alembic_version")

        # Tables should match
        missing_in_migrations = models_tables - migration_tables
        extra_in_migrations = migration_tables - models_tables

        if missing_in_migrations:
            pytest.fail(
                f"Tables in models but not in migrations: {missing_in_migrations}. "
                "Run 'alembic revision --autogenerate' to create a new migration."
            )

        if extra_in_migrations:
            pytest.fail(
                f"Tables in migrations but not in models: {extra_in_migrations}. "
                "Check for orphaned migrations or missing model imports."
            )

        # Compare columns for each table
        column_diffs = []
        for table_name in models_tables:
            migration_cols = {
                col["name"]: col for col in migration_inspector.get_columns(table_name)
            }
            models_cols = {
                col["name"]: col for col in models_inspector.get_columns(table_name)
            }

            missing_cols = set(models_cols.keys()) - set(migration_cols.keys())
            extra_cols = set(migration_cols.keys()) - set(models_cols.keys())

            if missing_cols:
                column_diffs.append(f"  {table_name}: missing columns {missing_cols}")
            if extra_cols:
                column_diffs.append(f"  {table_name}: extra columns {extra_cols}")

            # Check for type mismatches in common columns
            common_cols = set(models_cols.keys()) & set(migration_cols.keys())
            for col_name in common_cols:
                model_type = str(models_cols[col_name]["type"])
                migration_type = str(migration_cols[col_name]["type"])
                # Normalize type names for comparison (SQLite can be loose with types)
                if model_type.upper() != migration_type.upper():
                    # Only report significant type differences
                    model_base = model_type.split("(")[0].upper()
                    migration_base = migration_type.split("(")[0].upper()
                    if model_base != migration_base:
                        column_diffs.append(
                            f"  {table_name}.{col_name}: type mismatch "
                            f"(model={model_type}, migration={migration_type})"
                        )

        if column_diffs:
            pytest.fail(
                "Column differences between models and migrations:\n"
                + "\n".join(column_diffs)
                + "\nRun 'alembic revision --autogenerate' to create a new migration."
            )

        # Compare indexes for each table
        index_diffs = []
        for table_name in models_tables:
            migration_indexes = {
                idx["name"]: idx
                for idx in migration_inspector.get_indexes(table_name)
                if idx["name"] is not None  # SQLite auto-indexes may have None name
            }
            models_indexes = {
                idx["name"]: idx
                for idx in models_inspector.get_indexes(table_name)
                if idx["name"] is not None
            }

            missing_indexes = set(models_indexes.keys()) - set(migration_indexes.keys())
            extra_indexes = set(migration_indexes.keys()) - set(models_indexes.keys())

            if missing_indexes:
                index_diffs.append(f"  {table_name}: missing indexes {missing_indexes}")
            if extra_indexes:
                index_diffs.append(f"  {table_name}: extra indexes {extra_indexes}")

        if index_diffs:
            pytest.fail(
                "Index differences between models and migrations:\n"
                + "\n".join(index_diffs)
                + "\nRun 'alembic revision --autogenerate' to create a new migration."
            )

        migration_engine.dispose()
        models_engine.dispose()
