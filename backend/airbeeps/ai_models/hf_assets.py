from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from airbeeps.ai_models.models import ModelAsset, ModelAssetStatusEnum
from airbeeps.config import data_root_path
from airbeeps.database import async_session_maker

if TYPE_CHECKING:
    import uuid

logger = logging.getLogger(__name__)


ASSET_TYPE_HF_EMBEDDING = "HUGGINGFACE_EMBEDDING"

_download_tasks: dict[uuid.UUID, asyncio.Task] = {}
_lock = asyncio.Lock()


def _safe_dir_name(repo_id: str, revision: str | None = None) -> str:
    # Windows-safe-ish directory name
    base = repo_id.strip().replace("/", "__").replace("\\", "__")
    if revision:
        base = f"{base}__{revision.strip().replace('/', '__').replace('\\\\', '__')}"
    return base


def hf_models_root() -> Path:
    root = data_root_path / "models" / "huggingface"
    root.mkdir(parents=True, exist_ok=True)
    return root


def hf_local_dir(repo_id: str, revision: str | None = None) -> Path:
    return hf_models_root() / _safe_dir_name(repo_id, revision)


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                continue
    return total


async def enqueue_hf_embedding_download(asset_id: uuid.UUID) -> bool:
    """Enqueue a Hugging Face embedding snapshot download in-process."""
    async with _lock:
        if asset_id in _download_tasks:
            return False
        task = asyncio.create_task(
            _run_hf_download(asset_id), name=f"hf-asset-{asset_id}"
        )
        _download_tasks[asset_id] = task
        return True


async def _run_hf_download(asset_id: uuid.UUID) -> None:
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ModelAsset).where(ModelAsset.id == asset_id)
            )
            asset = result.scalar_one_or_none()
            if not asset:
                logger.warning(f"HF asset not found: {asset_id}")
                return

            asset.status = ModelAssetStatusEnum.DOWNLOADING
            asset.error_message = None
            await session.commit()

            repo_id = asset.identifier
            revision = asset.revision
            local_dir = hf_local_dir(repo_id, revision)

        # Download in a thread (blocking IO + CPU work)
        await asyncio.to_thread(_download_snapshot, repo_id, revision, local_dir)

        size_bytes = await asyncio.to_thread(_dir_size_bytes, local_dir)

        async with async_session_maker() as session:
            result = await session.execute(
                select(ModelAsset).where(ModelAsset.id == asset_id)
            )
            asset = result.scalar_one_or_none()
            if not asset:
                return
            asset.local_path = str(local_dir)
            asset.size_bytes = int(size_bytes)
            asset.status = ModelAssetStatusEnum.READY
            await session.commit()

    except Exception as e:
        logger.error(f"HF download failed for asset {asset_id}: {e}", exc_info=True)
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(ModelAsset).where(ModelAsset.id == asset_id)
                )
                asset = result.scalar_one_or_none()
                if asset:
                    asset.status = ModelAssetStatusEnum.FAILED
                    asset.error_message = str(e)
                    await session.commit()
        except Exception:
            logger.exception("Failed to persist HF download failure")
    finally:
        async with _lock:
            _download_tasks.pop(asset_id, None)


def _download_snapshot(repo_id: str, revision: str | None, local_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except Exception as e:
        raise RuntimeError(
            "huggingface_hub is required to download Hugging Face models. "
            "Install `huggingface-hub` (usually included via sentence-transformers)."
        ) from e

    local_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        # Avoid pulling giant training artifacts; keep it broad but safe.
        ignore_patterns=["*.ckpt", "*.h5", "*.ot", "*.msgpack"],
    )


def hf_hub_cache_root() -> Path:
    """
    Best-effort Hugging Face hub cache root.

    This is the default location used by huggingface_hub for cached snapshots
    (distinct from our AirBeeps-managed local_dir downloads).
    """
    # Prefer env vars
    env = os.getenv("HF_HUB_CACHE") or os.getenv("HUGGINGFACE_HUB_CACHE")
    if env:
        return Path(env)

    # Try huggingface_hub constants (version-dependent)
    try:
        from huggingface_hub.constants import HF_HUB_CACHE  # type: ignore

        return Path(HF_HUB_CACHE)
    except Exception:
        pass

    hf_home = os.getenv("HF_HOME") or os.getenv("HUGGINGFACE_HOME")
    if hf_home:
        return Path(hf_home) / "hub"

    return Path.home() / ".cache" / "huggingface" / "hub"


def list_hf_hub_cached_model_repo_ids() -> list[str]:
    """
    List model repo_ids present in the Hugging Face hub cache.

    We intentionally do a fast directory listing rather than a deep scan.
    """
    root = hf_hub_cache_root()
    if not root.exists() or not root.is_dir():
        return []

    out: list[str] = []
    try:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            if not entry.name.startswith("models--"):
                continue
            # Example: models--BAAI--bge-small-en-v1.5 -> BAAI/bge-small-en-v1.5
            raw = entry.name.removeprefix("models--")
            repo_id = raw.replace("--", "/")

            snapshots_dir = entry / "snapshots"
            if snapshots_dir.exists() and any(
                p.is_dir() for p in snapshots_dir.iterdir()
            ):
                out.append(repo_id)
    except Exception as e:
        logger.debug(f"Failed to list HF hub cache: {e}")
        return []

    return sorted(set(out))


def resolve_hf_hub_cached_snapshot_dir(repo_id: str) -> Path | None:
    """
    Resolve a local snapshot directory for a cached HF model repo.

    Returns:
      Path to a snapshot directory (e.g. .../models--ORG--REPO/snapshots/<hash>)
      or None if not found.
    """
    repo_id = (repo_id or "").strip()
    if not repo_id:
        return None

    root = hf_hub_cache_root()
    repo_dir = root / f"models--{repo_id.replace('/', '--')}"
    snapshots_dir = repo_dir / "snapshots"
    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return None

    # Pick the most recently modified snapshot dir (best-effort)
    candidates: list[Path] = [p for p in snapshots_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]
