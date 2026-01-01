#!/usr/bin/env python3
"""
Build script for creating the Airbeeps wheel with bundled frontend.

This script:
1. Builds the Nuxt frontend
2. Copies the static assets to the backend package
3. Builds the Python wheel
"""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIR = PROJECT_ROOT / "backend"
STATIC_TARGET = BACKEND_DIR / "airbeeps" / "static"


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    shell: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    """Run a command and exit on failure."""
    print(f"Running: {' '.join(cmd)}")

    # On non-Windows systems, shell=True requires a string command string
    # otherwise only the first element is executed as the command
    if shell and sys.platform != "win32":
        cmd_run = shlex.join(cmd)
    else:
        cmd_run = cmd

    result = subprocess.run(cmd_run, check=False, cwd=cwd, shell=shell, env=env)  # noqa: S603
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        sys.exit(1)


def get_version(override_version: str | None = None) -> str:
    """Get version from override or git tags."""
    if override_version:
        return override_version

    try:
        # Check if git is available and repo is valid
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
        )
        # Get version
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "0.0.0-dev"


def clean_static():
    """Remove existing static directory."""
    if STATIC_TARGET.exists():
        print(f"Cleaning {STATIC_TARGET}")
        shutil.rmtree(STATIC_TARGET)


def build_frontend(version: str):
    """Build the Nuxt frontend."""
    print(f"\nBuilding frontend (version: {version})...")

    if not FRONTEND_DIR.exists():
        print("WARNING: Frontend directory not found. Skipping frontend build.")
        return False

    # Install dependencies
    print("Installing frontend dependencies...")
    run_command(["pnpm", "install"], cwd=FRONTEND_DIR, shell=True)

    # Inject version
    print(f"Injecting version into frontend: {version}")
    env = os.environ.copy()
    env["NUXT_PUBLIC_APP_VERSION"] = version

    # Build the frontend
    print("Building Nuxt application...")
    run_command(["pnpm", "run", "generate"], cwd=FRONTEND_DIR, env=env, shell=True)

    # Check if build output exists
    output_dir = FRONTEND_DIR / ".output" / "public"
    if not output_dir.exists():
        print("ERROR: Frontend build output not found!")
        return False

    print("SUCCESS: Frontend built successfully")
    return True


def copy_static_files():
    """Copy frontend build to backend static directory."""
    print("\nCopying static files...")

    output_dir = FRONTEND_DIR / ".output" / "public"
    if not output_dir.exists():
        print("WARNING: No frontend build found. Creating empty static directory.")
        STATIC_TARGET.mkdir(parents=True, exist_ok=True)
        return

    # Copy the entire public directory
    shutil.copytree(output_dir, STATIC_TARGET, dirs_exist_ok=True)

    # Count files
    file_count = sum(1 for _ in STATIC_TARGET.rglob("*") if _.is_file())
    print(f"SUCCESS: Copied {file_count} files to {STATIC_TARGET}")


def build_wheel(version: str | None = None):
    """Build the Python wheel."""
    print(
        f"\nBuilding Python wheel (force version: {version if version else 'auto'})..."
    )

    # Clean previous builds
    dist_dir = BACKEND_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    # Build using uv
    env = os.environ.copy()
    if version:
        # hatch-vcs uses setuptools-scm under the hood, this override often works
        env["SETUPTOOLS_SCM_PRETEND_VERSION"] = version
        # Some hatch plugins also look for these
        env["HATCH_VCS_VERSION_OVERRIDE"] = version

    run_command(["uv", "build"], cwd=BACKEND_DIR, env=env)

    # List built files
    if dist_dir.exists():
        wheels = list(dist_dir.glob("*.whl"))
        tarballs = list(dist_dir.glob("*.tar.gz"))

        print("\nBuild complete! Generated files:")
        for file in wheels + tarballs:
            size = file.stat().st_size / (1024 * 1024)  # MB
            print(f"  - {file.name} ({size:.2f} MB)")
    else:
        print("ERROR: Build failed - no dist directory created")
        sys.exit(1)


def cleanup_after_build():
    """Clean up static files after wheel is built."""
    print("\nCleaning up temporary files...")

    if STATIC_TARGET.exists():
        shutil.rmtree(STATIC_TARGET)
        print(f"Removed {STATIC_TARGET}")

    # Also clean frontend build output
    frontend_output = FRONTEND_DIR / ".output"
    if frontend_output.exists():
        shutil.rmtree(frontend_output)
        print(f"Removed {frontend_output}")


def main():
    """Main build process."""
    parser = argparse.ArgumentParser(
        description="Build Airbeeps wheel with bundled frontend."
    )
    parser.add_argument("--version", help="Override version number (e.g. 0.1.0)")
    args = parser.parse_args()

    version = get_version(args.version)

    print("=" * 60)
    print(f"Airbeeps - Wheel Build Script (Version: {version})")
    print("=" * 60)

    try:
        # Step 1: Clean
        clean_static()

        # Step 2: Build frontend
        frontend_built = build_frontend(version)

        # Step 3: Copy static files
        if frontend_built:
            copy_static_files()
        else:
            print("\nWARNING: Building wheel without frontend assets")

        # Step 4: Build wheel
        # We only pass the version to build_wheel if it was explicitly overridden
        # otherwise let hatch-vcs do its thing with git tags
        build_wheel(args.version)

        # Step 5: Cleanup (important!)
        cleanup_after_build()

        print("\n" + "=" * 60)
        print("Build process completed successfully!")
        print("=" * 60)
        print("\nTo install locally:")
        print(f"  uv pip install {BACKEND_DIR / 'dist' / '*.whl'}")
        print("\nTo test:")
        print("  airbeeps run")

    except Exception as e:
        print(f"\nERROR: Build failed: {e}")
        print("\nCleaning up temporary files...")
        cleanup_after_build()
        sys.exit(1)


if __name__ == "__main__":
    main()
