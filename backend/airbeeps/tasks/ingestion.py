"""
Celery tasks for document ingestion.

These tasks are executed by Celery workers when CELERY_ENABLED=true.
"""

import asyncio
import logging
from uuid import UUID

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async function in sync context (for Celery tasks)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_celery_app():
    """Get Celery app, raising if not available."""
    from .celery_app import get_celery_app

    app = get_celery_app()
    if app is None:
        raise RuntimeError("Celery is not enabled or not installed")
    return app


# Only define tasks if Celery is available
try:
    from celery import shared_task
    from celery.exceptions import SoftTimeLimitExceeded

    @shared_task(
        bind=True,
        name="airbeeps.tasks.run_ingestion_job",
        max_retries=3,
        default_retry_delay=60,
        soft_time_limit=3600,  # 1 hour soft limit
        time_limit=3900,  # 1 hour 5 min hard limit
        acks_late=True,
        reject_on_worker_lost=True,
    )
    def run_ingestion_job(self, job_id: str, cancel_check_key: str | None = None):
        """
        Execute document ingestion job.

        Args:
            job_id: UUID of the IngestionJob to process
            cancel_check_key: Optional Redis key to check for cancellation
        """
        logger.info(f"Starting ingestion job {job_id} (task_id={self.request.id})")

        try:
            _run_async(_run_ingestion_async(job_id, cancel_check_key))
            logger.info(f"Ingestion job {job_id} completed successfully")
            return {"status": "success", "job_id": job_id}

        except SoftTimeLimitExceeded:
            logger.error(f"Ingestion job {job_id} exceeded time limit")
            _run_async(_mark_job_failed(job_id, "Job exceeded time limit"))
            raise

        except Exception as e:
            logger.error(f"Ingestion job {job_id} failed: {e}", exc_info=True)

            # Retry on transient errors
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            _run_async(_mark_job_failed(job_id, str(e)))
            return {"status": "failed", "job_id": job_id, "error": str(e)}

    @shared_task(
        bind=True,
        name="airbeeps.tasks.batch_ingestion",
        max_retries=1,
    )
    def batch_ingestion(self, job_ids: list[str]):
        """
        Enqueue multiple ingestion jobs.

        Args:
            job_ids: List of IngestionJob UUIDs to process
        """
        logger.info(f"Starting batch ingestion for {len(job_ids)} jobs")

        from celery import group

        tasks = [run_ingestion_job.s(job_id) for job_id in job_ids]
        job = group(tasks)
        result = job.apply_async()

        return {
            "status": "enqueued",
            "job_count": len(job_ids),
            "group_id": str(result.id),
        }

except ImportError:
    # Celery not installed - define stub functions
    def run_ingestion_job(job_id: str, cancel_check_key: str | None = None):
        raise RuntimeError("Celery is not installed")

    def batch_ingestion(job_ids: list[str]):
        raise RuntimeError("Celery is not installed")


async def _run_ingestion_async(job_id: str, cancel_check_key: str | None = None):
    """Async implementation of ingestion job."""
    from airbeeps.rag.ingestion_runner import IngestionRunner

    job_uuid = UUID(job_id)

    # Create cancel check function
    async def check_cancelled():
        if cancel_check_key:
            try:
                from airbeeps.cache import get_cache

                cache = await get_cache()
                return await cache.exists(cancel_check_key)
            except Exception:
                return False
        return False

    runner = IngestionRunner(
        job_uuid,
        cancel_check=lambda: asyncio.get_event_loop().run_until_complete(
            check_cancelled()
        ),
    )
    await runner.run()


async def _mark_job_failed(job_id: str, error: str):
    """Mark job as failed in database."""
    from airbeeps.database import get_async_session_context
    from airbeeps.rag.models import IngestionJob

    try:
        async with get_async_session_context() as session:
            job = await session.get(IngestionJob, UUID(job_id))
            if job:
                job.status = "FAILED"
                job.error = error
                await session.commit()
    except Exception as e:
        logger.error(f"Failed to mark job {job_id} as failed: {e}")
