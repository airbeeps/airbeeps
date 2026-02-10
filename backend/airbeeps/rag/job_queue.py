"""
Job Queue abstraction for async ingestion.

Provides a pluggable backend for job execution:
- InProcessJobQueue: runs jobs in asyncio tasks (dev/laptop mode)
- CeleryJobQueue: placeholder for production-scale distributed workers

Features:
- Priority queue support (higher priority jobs processed first)
- Automatic retry with exponential backoff for failed jobs
- Job tracking statistics (success/failure counts, timings)
- Graceful shutdown with job persistence

Usage:
    queue = get_job_queue()
    await queue.enqueue(job_id, priority=JobPriority.HIGH)
    await queue.cancel(job_id)
    stats = await queue.get_stats()
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


class JobPriority(IntEnum):
    """Job priority levels (higher value = higher priority)."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass
class JobStats:
    """Statistics for job queue operations."""

    total_enqueued: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    total_retried: int = 0
    currently_running: int = 0
    currently_queued: int = 0
    avg_execution_time_ms: float = 0.0
    last_job_started: datetime | None = None
    last_job_completed: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "total_enqueued": self.total_enqueued,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "total_cancelled": self.total_cancelled,
            "total_retried": self.total_retried,
            "currently_running": self.currently_running,
            "currently_queued": self.currently_queued,
            "avg_execution_time_ms": round(self.avg_execution_time_ms, 2),
            "last_job_started": self.last_job_started.isoformat()
            if self.last_job_started
            else None,
            "last_job_completed": self.last_job_completed.isoformat()
            if self.last_job_completed
            else None,
            "success_rate": round(
                self.total_completed
                / max(self.total_completed + self.total_failed, 1)
                * 100,
                1,
            ),
        }


@dataclass
class RetryConfig:
    """Configuration for job retry behavior."""

    max_retries: int = 3
    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0  # 5 minutes
    exponential_base: float = 2.0

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt using exponential backoff."""
        delay = self.base_delay_seconds * (self.exponential_base**attempt)
        return min(delay, self.max_delay_seconds)


@dataclass(order=True)
class QueuedJob:
    """A job in the priority queue."""

    priority: int  # Higher = more priority (negated for heapq min-heap)
    enqueued_at: datetime = field(compare=False)
    job_id: uuid.UUID = field(compare=False)
    retry_count: int = field(default=0, compare=False)


class JobQueueBackend(ABC):
    """
    Abstract base for job queue backends.

    Implementations must provide enqueue, cancel, and status methods.
    The actual job execution is handled by IngestionRunner.
    """

    @abstractmethod
    async def enqueue(
        self,
        job_id: uuid.UUID,
        priority: JobPriority = JobPriority.NORMAL,
    ) -> bool:
        """
        Enqueue a job for background execution.

        Args:
            job_id: The IngestionJob ID to process
            priority: Job priority level

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
    async def is_queued(self, job_id: uuid.UUID) -> bool:
        """
        Check if a job is queued but not yet running.

        Args:
            job_id: The IngestionJob ID to check

        Returns:
            True if job is in the queue
        """

    @abstractmethod
    async def get_stats(self) -> JobStats:
        """
        Get queue statistics.

        Returns:
            JobStats with current queue metrics
        """

    @abstractmethod
    async def retry_failed(self, job_id: uuid.UUID) -> bool:
        """
        Retry a failed job.

        Args:
            job_id: The IngestionJob ID to retry

        Returns:
            True if job was re-queued for retry
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
    In-process job queue using asyncio tasks with priority support.

    Features:
    - Priority queue (higher priority jobs processed first)
    - Configurable concurrency limit
    - Automatic retry with exponential backoff
    - Statistics tracking

    Suitable for development and single-server deployments.
    Jobs run as background tasks in the same process.
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        retry_config: RetryConfig | None = None,
    ):
        """
        Initialize the job queue.

        Args:
            max_concurrent: Maximum number of concurrent jobs
            retry_config: Configuration for retry behavior
        """
        self._max_concurrent = max_concurrent
        self._retry_config = retry_config or RetryConfig()

        # Job tracking
        self._running_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._pending_queue: list[QueuedJob] = []  # Priority queue (heap)
        self._retry_counts: dict[uuid.UUID, int] = {}
        self._cancel_requested: set[uuid.UUID] = set()

        # Statistics
        self._stats = JobStats()
        self._execution_times: list[float] = []  # Last N execution times for avg

        # Synchronization
        self._lock = asyncio.Lock()
        self._queue_event = asyncio.Event()
        self._shutdown_requested = False

        # Worker task
        self._worker_task: asyncio.Task | None = None

    def _start_worker(self) -> None:
        """Start the background worker if not already running."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self._queue_worker(), name="job-queue-worker"
            )

    async def _queue_worker(self) -> None:
        """Background worker that processes jobs from the priority queue."""
        import heapq

        while not self._shutdown_requested:
            try:
                async with self._lock:
                    # Check if we can run more jobs
                    can_run = len(self._running_tasks) < self._max_concurrent

                    if can_run and self._pending_queue:
                        # Get highest priority job (lowest negative priority value)
                        queued_job = heapq.heappop(self._pending_queue)
                        self._stats.currently_queued = len(self._pending_queue)

                        # Start the job
                        task = asyncio.create_task(
                            self._run_job(queued_job),
                            name=f"ingestion-job-{queued_job.job_id}",
                        )
                        self._running_tasks[queued_job.job_id] = task
                        self._stats.currently_running = len(self._running_tasks)
                        self._stats.last_job_started = datetime.now(UTC)
                        continue

                # Wait for new jobs or running jobs to complete
                self._queue_event.clear()
                try:
                    await asyncio.wait_for(self._queue_event.wait(), timeout=1.0)
                except TimeoutError:
                    pass

            except Exception as e:
                logger.error(f"Queue worker error: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def enqueue(
        self,
        job_id: uuid.UUID,
        priority: JobPriority = JobPriority.NORMAL,
    ) -> bool:
        """Enqueue a job with priority for background execution."""
        import heapq

        async with self._lock:
            # Check if already running or queued
            if job_id in self._running_tasks:
                logger.warning(f"Job {job_id} is already running")
                return False

            if any(qj.job_id == job_id for qj in self._pending_queue):
                logger.warning(f"Job {job_id} is already queued")
                return False

            # Create queued job with negative priority for min-heap
            queued_job = QueuedJob(
                priority=-priority,  # Negate for min-heap (higher priority = lower value)
                enqueued_at=datetime.now(UTC),
                job_id=job_id,
                retry_count=self._retry_counts.get(job_id, 0),
            )

            heapq.heappush(self._pending_queue, queued_job)
            self._stats.total_enqueued += 1
            self._stats.currently_queued = len(self._pending_queue)

            logger.info(
                f"Enqueued ingestion job {job_id} with priority {priority.name}"
            )

        # Start worker if needed and signal new job
        self._start_worker()
        self._queue_event.set()
        return True

    async def _run_job(self, queued_job: QueuedJob) -> None:
        """Execute the job and handle retry on failure."""
        from .ingestion_runner import IngestionRunner

        job_id = queued_job.job_id
        start_time = datetime.now(UTC)
        success = False

        try:
            runner = IngestionRunner(
                job_id, cancel_check=lambda: job_id in self._cancel_requested
            )
            await runner.run()

            # Check if job actually succeeded (runner doesn't raise on failure)
            from airbeeps.database import get_async_session_context

            from .models import IngestionJob

            async with get_async_session_context() as session:
                job = await session.get(IngestionJob, job_id)
                if job and job.status == "SUCCEEDED":
                    success = True
                elif job and job.status == "CANCELED":
                    async with self._lock:
                        self._stats.total_cancelled += 1
                    return

        except Exception as e:
            logger.error(
                f"Ingestion job {job_id} failed with exception: {e}", exc_info=True
            )

        finally:
            # Calculate execution time
            end_time = datetime.now(UTC)
            execution_ms = (end_time - start_time).total_seconds() * 1000

            async with self._lock:
                self._running_tasks.pop(job_id, None)
                self._cancel_requested.discard(job_id)
                self._stats.currently_running = len(self._running_tasks)
                self._stats.last_job_completed = end_time

                # Update execution time average
                self._execution_times.append(execution_ms)
                if len(self._execution_times) > 100:
                    self._execution_times = self._execution_times[-100:]
                self._stats.avg_execution_time_ms = sum(self._execution_times) / len(
                    self._execution_times
                )

                if success:
                    self._stats.total_completed += 1
                    self._retry_counts.pop(job_id, None)
                    logger.info(f"Job {job_id} completed successfully")
                else:
                    self._stats.total_failed += 1

                    # Check if we should retry
                    retry_count = self._retry_counts.get(job_id, 0)
                    if retry_count < self._retry_config.max_retries:
                        delay = self._retry_config.get_delay(retry_count)
                        self._retry_counts[job_id] = retry_count + 1
                        self._stats.total_retried += 1

                        logger.info(
                            f"Scheduling retry {retry_count + 1}/{self._retry_config.max_retries} "
                            f"for job {job_id} in {delay:.1f}s"
                        )

                        # Schedule retry
                        asyncio.create_task(
                            self._schedule_retry(job_id, delay, queued_job.priority)
                        )
                    else:
                        logger.warning(
                            f"Job {job_id} failed after {retry_count} retries, giving up"
                        )
                        self._retry_counts.pop(job_id, None)

            # Signal worker
            self._queue_event.set()

    async def _schedule_retry(
        self, job_id: uuid.UUID, delay: float, priority: int
    ) -> None:
        """Schedule a job retry after delay."""
        await asyncio.sleep(delay)

        # Re-enqueue with same priority
        await self.enqueue(job_id, JobPriority(-priority))

    async def cancel(self, job_id: uuid.UUID) -> bool:
        """Request cancellation of a running or queued job."""
        import heapq

        async with self._lock:
            # If running, request cancellation
            if job_id in self._running_tasks:
                self._cancel_requested.add(job_id)
                logger.info(f"Cancellation requested for running job {job_id}")
                return True

            # If queued, remove from queue
            for i, qj in enumerate(self._pending_queue):
                if qj.job_id == job_id:
                    self._pending_queue.pop(i)
                    heapq.heapify(self._pending_queue)
                    self._stats.currently_queued = len(self._pending_queue)
                    self._stats.total_cancelled += 1
                    logger.info(f"Removed queued job {job_id} from queue")
                    return True

            logger.warning(f"Cannot cancel job {job_id}: not running or queued")
            return False

    async def is_running(self, job_id: uuid.UUID) -> bool:
        """Check if a job is currently running."""
        async with self._lock:
            return job_id in self._running_tasks

    async def is_queued(self, job_id: uuid.UUID) -> bool:
        """Check if a job is queued but not yet running."""
        async with self._lock:
            return any(qj.job_id == job_id for qj in self._pending_queue)

    async def get_stats(self) -> JobStats:
        """Get current queue statistics."""
        async with self._lock:
            # Return a copy of stats
            return JobStats(
                total_enqueued=self._stats.total_enqueued,
                total_completed=self._stats.total_completed,
                total_failed=self._stats.total_failed,
                total_cancelled=self._stats.total_cancelled,
                total_retried=self._stats.total_retried,
                currently_running=len(self._running_tasks),
                currently_queued=len(self._pending_queue),
                avg_execution_time_ms=self._stats.avg_execution_time_ms,
                last_job_started=self._stats.last_job_started,
                last_job_completed=self._stats.last_job_completed,
            )

    async def retry_failed(self, job_id: uuid.UUID) -> bool:
        """Manually retry a failed job."""
        # Reset retry count for manual retry
        async with self._lock:
            self._retry_counts[job_id] = 0

        return await self.enqueue(job_id, JobPriority.HIGH)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Wait for all running jobs to complete or timeout."""
        self._shutdown_requested = True

        async with self._lock:
            tasks = list(self._running_tasks.values())
            if self._worker_task:
                tasks.append(self._worker_task)

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

    Features:
    - Distributed task execution across workers
    - Priority queue support
    - Task status tracking via Redis
    - Automatic retry with backoff
    - Task cancellation via revoke

    Requires:
    - CELERY_ENABLED=true in configuration
    - Redis or RabbitMQ broker
    - Celery workers running separately
    """

    def __init__(self):
        from airbeeps.tasks.celery_app import get_celery_app

        self._celery_app = get_celery_app()
        if self._celery_app is None:
            raise RuntimeError(
                "CeleryJobQueue requires Celery to be enabled and installed. "
                "Set AIRBEEPS_CELERY_ENABLED=true and install celery[redis]."
            )

        # Map job_id -> Celery task_id for tracking
        self._task_ids: dict[uuid.UUID, str] = {}
        self._stats = JobStats()
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        job_id: uuid.UUID,
        priority: JobPriority = JobPriority.NORMAL,
    ) -> bool:
        """Send job to Celery queue with priority."""
        from airbeeps.tasks.ingestion import run_ingestion_job

        async with self._lock:
            # Check if already submitted
            if job_id in self._task_ids:
                logger.warning(f"Job {job_id} already submitted to Celery")
                return False

            # Create cancellation key for this job
            cancel_key = f"celery:cancel:{job_id}"

            # Submit to Celery with priority
            result = run_ingestion_job.apply_async(
                args=[str(job_id), cancel_key],
                priority=priority.value,
                task_id=f"ingestion-{job_id}",
            )

            self._task_ids[job_id] = result.id
            self._stats.total_enqueued += 1

            logger.info(
                f"Sent ingestion job {job_id} to Celery "
                f"(task_id={result.id}, priority={priority.name})"
            )
            return True

    async def cancel(self, job_id: uuid.UUID) -> bool:
        """Request cancellation via Celery revoke and cancel flag."""
        async with self._lock:
            task_id = self._task_ids.get(job_id)
            if not task_id:
                logger.warning(f"Cannot cancel job {job_id}: not found in Celery queue")
                return False

            # Set cancellation flag in cache
            try:
                from airbeeps.cache import get_cache

                cache = await get_cache()
                cancel_key = f"celery:cancel:{job_id}"
                await cache.set(cancel_key, True, ttl=3600)
            except Exception as e:
                logger.warning(f"Failed to set cancel flag: {e}")

            # Revoke the task (soft terminate)
            try:
                self._celery_app.control.revoke(
                    task_id, terminate=True, signal="SIGTERM"
                )
            except Exception as e:
                logger.warning(f"Failed to revoke Celery task: {e}")

            self._task_ids.pop(job_id, None)
            self._stats.total_cancelled += 1

            logger.info(
                f"Cancellation requested for Celery job {job_id} (task_id={task_id})"
            )
            return True

    async def is_running(self, job_id: uuid.UUID) -> bool:
        """Check job status in Celery."""
        async with self._lock:
            task_id = self._task_ids.get(job_id)
            if not task_id:
                return False

            try:
                from celery.result import AsyncResult

                result = AsyncResult(task_id, app=self._celery_app)
                return result.state in ("PENDING", "STARTED", "RETRY")
            except Exception:
                return False

    async def is_queued(self, job_id: uuid.UUID) -> bool:
        """Check if job is in Celery queue but not yet started."""
        async with self._lock:
            task_id = self._task_ids.get(job_id)
            if not task_id:
                return False

            try:
                from celery.result import AsyncResult

                result = AsyncResult(task_id, app=self._celery_app)
                return result.state == "PENDING"
            except Exception:
                return False

    async def get_stats(self) -> JobStats:
        """Get queue statistics from Celery/Redis."""
        # Try to get stats from Celery inspect
        try:
            inspect = self._celery_app.control.inspect()

            active = inspect.active() or {}
            reserved = inspect.reserved() or {}
            scheduled = inspect.scheduled() or {}

            currently_running = sum(len(tasks) for tasks in active.values())
            currently_queued = sum(len(tasks) for tasks in reserved.values())
            currently_queued += sum(len(tasks) for tasks in scheduled.values())

            async with self._lock:
                return JobStats(
                    total_enqueued=self._stats.total_enqueued,
                    total_completed=self._stats.total_completed,
                    total_failed=self._stats.total_failed,
                    total_cancelled=self._stats.total_cancelled,
                    total_retried=self._stats.total_retried,
                    currently_running=currently_running,
                    currently_queued=currently_queued,
                    avg_execution_time_ms=self._stats.avg_execution_time_ms,
                    last_job_started=self._stats.last_job_started,
                    last_job_completed=self._stats.last_job_completed,
                )
        except Exception as e:
            logger.warning(f"Failed to get Celery stats: {e}")
            async with self._lock:
                return self._stats

    async def retry_failed(self, job_id: uuid.UUID) -> bool:
        """Retry a failed job via Celery."""
        # Remove from tracking so it can be re-enqueued
        async with self._lock:
            self._task_ids.pop(job_id, None)

        return await self.enqueue(job_id, JobPriority.HIGH)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Celery workers manage their own lifecycle.

        This just cleans up local tracking state.
        """
        async with self._lock:
            self._task_ids.clear()
        logger.info("CeleryJobQueue shutdown (workers are external)")


# =============================================================================
# Singleton / factory
# =============================================================================

_job_queue: JobQueueBackend | None = None


def get_job_queue() -> JobQueueBackend:
    """
    Get the configured job queue backend.

    Backend selection:
    - If CELERY_ENABLED=true, uses CeleryJobQueue (distributed workers)
    - Otherwise, uses InProcessJobQueue (asyncio tasks)

    The backend is cached after first call.
    """
    global _job_queue
    if _job_queue is not None:
        return _job_queue

    from airbeeps.config import settings

    if settings.CELERY_ENABLED:
        try:
            _job_queue = CeleryJobQueue()
            logger.info("Using CeleryJobQueue for background tasks")
        except RuntimeError as e:
            logger.warning(f"Failed to initialize CeleryJobQueue: {e}")
            logger.warning("Falling back to InProcessJobQueue")
            _job_queue = InProcessJobQueue()
    else:
        _job_queue = InProcessJobQueue()
        logger.info("Using InProcessJobQueue for background tasks (Celery disabled)")

    return _job_queue


def configure_job_queue(backend: JobQueueBackend) -> None:
    """
    Configure the job queue backend explicitly.

    Call at app startup to override automatic backend selection.
    """
    global _job_queue
    _job_queue = backend
    logger.info(f"Configured job queue backend: {type(backend).__name__}")


async def shutdown_job_queue() -> None:
    """Gracefully shutdown the job queue."""
    global _job_queue
    if _job_queue is not None:
        await _job_queue.shutdown()
        _job_queue = None
