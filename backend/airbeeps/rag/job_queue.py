"""
Job Queue abstraction for async ingestion.

Provides a pluggable backend for job execution:
- InProcessJobQueue: runs jobs in asyncio tasks (dev/laptop mode)
- CeleryJobQueue: placeholder for production-scale distributed workers

Usage:
    queue = get_job_queue()
    await queue.enqueue(job_id)
    await queue.cancel(job_id)
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class JobQueueBackend(ABC):
    """
    Abstract base for job queue backends.

    Implementations must provide enqueue, cancel, and status methods.
    The actual job execution is handled by IngestionRunner.
    """

    @abstractmethod
    async def enqueue(self, job_id: uuid.UUID) -> bool:
        """
        Enqueue a job for background execution.

        Args:
            job_id: The IngestionJob ID to process

        Returns:
            True if enqueued successfully
        """

    @abstractmethod
    async def cancel(self, job_id: uuid.UUID) -> bool:
        """
        Request cancellation of a running job.

        Args:
            job_id: The IngestionJob ID to cancel

        Returns:
            True if cancellation was requested (job may still be finishing)
        """

    @abstractmethod
    async def is_running(self, job_id: uuid.UUID) -> bool:
        """
        Check if a job is currently running.

        Args:
            job_id: The IngestionJob ID to check

        Returns:
            True if job is actively running
        """

    @abstractmethod
    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Gracefully shutdown the queue, waiting for running jobs.

        Args:
            timeout: Max seconds to wait for jobs to complete
        """


class InProcessJobQueue(JobQueueBackend):
    """
    In-process job queue using asyncio tasks.

    Suitable for development and single-server deployments.
    Jobs run as background tasks in the same process.
    """

    def __init__(self):
        self._running_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._cancel_requested: set[uuid.UUID] = set()
        self._lock = asyncio.Lock()

    async def enqueue(self, job_id: uuid.UUID) -> bool:
        """Start a background task to run the ingestion job."""

        async with self._lock:
            if job_id in self._running_tasks:
                logger.warning(f"Job {job_id} is already running")
                return False

            # Create and start the background task
            task = asyncio.create_task(
                self._run_job(job_id), name=f"ingestion-job-{job_id}"
            )
            self._running_tasks[job_id] = task
            logger.info(f"Enqueued ingestion job {job_id} for in-process execution")
            return True

    async def _run_job(self, job_id: uuid.UUID) -> None:
        """Execute the job and clean up when done."""
        from .ingestion_runner import IngestionRunner

        try:
            runner = IngestionRunner(
                job_id, cancel_check=lambda: job_id in self._cancel_requested
            )
            await runner.run()
        except Exception as e:
            logger.error(
                f"Ingestion job {job_id} failed with exception: {e}", exc_info=True
            )
        finally:
            async with self._lock:
                self._running_tasks.pop(job_id, None)
                self._cancel_requested.discard(job_id)

    async def cancel(self, job_id: uuid.UUID) -> bool:
        """Request cancellation of a running job."""
        async with self._lock:
            if job_id not in self._running_tasks:
                logger.warning(f"Cannot cancel job {job_id}: not running")
                return False

            self._cancel_requested.add(job_id)
            logger.info(f"Cancellation requested for job {job_id}")
            return True

    async def is_running(self, job_id: uuid.UUID) -> bool:
        """Check if a job is currently running."""
        async with self._lock:
            return job_id in self._running_tasks

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Wait for all running jobs to complete or timeout."""
        async with self._lock:
            tasks = list(self._running_tasks.values())

        if not tasks:
            return

        logger.info(f"Waiting for {len(tasks)} running jobs to complete...")
        _done, pending = await asyncio.wait(tasks, timeout=timeout)

        if pending:
            logger.warning(f"Timeout: {len(pending)} jobs still running, cancelling...")
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


class CeleryJobQueue(JobQueueBackend):
    """
    Celery-based job queue for production deployments.

    This is a placeholder implementation. Wire up actual Celery
    when adding distributed worker support.
    """

    def __init__(self, celery_app=None):
        self._celery_app = celery_app
        # Track job IDs sent to Celery (not the same as "running")
        self._pending_jobs: set[uuid.UUID] = set()

    async def enqueue(self, job_id: uuid.UUID) -> bool:
        """Send job to Celery queue."""
        if self._celery_app is None:
            raise NotImplementedError(
                "CeleryJobQueue requires a configured Celery app. "
                "Set CELERY_BROKER_URL and wire up the Celery integration."
            )

        # Example Celery task call (to be implemented):
        # from .celery_tasks import run_ingestion_job
        # run_ingestion_job.delay(str(job_id))

        self._pending_jobs.add(job_id)
        logger.info(f"Sent ingestion job {job_id} to Celery queue")
        return True

    async def cancel(self, job_id: uuid.UUID) -> bool:
        """Request cancellation via Celery revoke."""
        if self._celery_app is None:
            raise NotImplementedError(
                "CeleryJobQueue requires a configured Celery app."
            )

        # Example: self._celery_app.control.revoke(task_id, terminate=True)
        # Need to store task_id mapping

        logger.info(f"Cancellation requested for Celery job {job_id}")
        return True

    async def is_running(self, job_id: uuid.UUID) -> bool:
        """Check job status in Celery."""
        # Would query Celery AsyncResult or job status from DB
        return job_id in self._pending_jobs

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Celery workers manage their own lifecycle."""
        logger.info("CeleryJobQueue shutdown (workers are external)")


# =============================================================================
# Singleton / factory
# =============================================================================

_job_queue: JobQueueBackend | None = None


def get_job_queue() -> JobQueueBackend:
    """
    Get the configured job queue backend.

    Returns InProcessJobQueue by default. To switch to Celery,
    call configure_job_queue() at app startup.
    """
    global _job_queue
    if _job_queue is None:
        _job_queue = InProcessJobQueue()
    return _job_queue


def configure_job_queue(backend: JobQueueBackend) -> None:
    """
    Configure the job queue backend.

    Call at app startup to switch from default InProcessJobQueue
    to CeleryJobQueue or another implementation.
    """
    global _job_queue
    _job_queue = backend
    logger.info(f"Configured job queue backend: {type(backend).__name__}")
