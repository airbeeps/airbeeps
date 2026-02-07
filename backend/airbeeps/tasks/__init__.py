"""
Airbeeps Task Queue Module

Provides Celery-based distributed task processing.
Celery is optional - when disabled, tasks run in-process.

Usage:
    # In application code, use the job queue abstraction
    from airbeeps.rag.job_queue import get_job_queue
    queue = get_job_queue()
    await queue.enqueue(job_id)

    # For direct Celery task access
    from airbeeps.tasks import celery_app
    from airbeeps.tasks.ingestion import run_ingestion_job
    run_ingestion_job.delay(str(job_id))
"""

from .celery_app import celery_app, get_celery_app, is_celery_enabled

__all__ = [
    "celery_app",
    "get_celery_app",
    "is_celery_enabled",
]
