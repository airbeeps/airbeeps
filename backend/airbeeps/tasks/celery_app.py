"""
Celery application configuration.

Celery is optional. Enable with AIRBEEPS_CELERY_ENABLED=true.
When disabled, tasks run in-process using asyncio.

Running Celery workers:
    celery -A airbeeps.tasks.celery_app worker --loglevel=info

Running Celery Beat (scheduled tasks):
    celery -A airbeeps.tasks.celery_app beat --loglevel=info

Running both (for development):
    celery -A airbeeps.tasks.celery_app worker --beat --loglevel=info
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy-loaded Celery app
_celery_app: Any = None


def is_celery_enabled() -> bool:
    """Check if Celery is enabled in configuration."""
    try:
        from airbeeps.config import settings

        return settings.CELERY_ENABLED
    except ImportError:
        return False


def get_celery_app():
    """
    Get or create the Celery application instance.

    Returns None if Celery is disabled or not installed.
    """
    global _celery_app

    if _celery_app is not None:
        return _celery_app

    if not is_celery_enabled():
        logger.debug("Celery is disabled (CELERY_ENABLED=false)")
        return None

    try:
        from celery import Celery
    except ImportError:
        logger.warning(
            "Celery package not installed. Install with: pip install 'celery[redis]'"
        )
        return None

    from airbeeps.config import settings

    # Create Celery app
    _celery_app = Celery(
        "airbeeps",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=[
            "airbeeps.tasks.ingestion",
            "airbeeps.tasks.memory",
            "airbeeps.tasks.maintenance",
        ],
    )

    # Configure Celery
    _celery_app.conf.update(
        # Serialization
        task_serializer=settings.CELERY_TASK_SERIALIZER,
        result_serializer=settings.CELERY_RESULT_SERIALIZER,
        accept_content=settings.CELERY_ACCEPT_CONTENT,
        # Task execution
        task_track_started=settings.CELERY_TASK_TRACK_STARTED,
        task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
        # Worker configuration
        worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
        worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
        # Result backend
        result_expires=3600,  # 1 hour
        # Error handling
        task_acks_late=True,  # Acknowledge after task completion
        task_reject_on_worker_lost=True,  # Requeue if worker dies
        # Priority support
        task_queue_max_priority=10,
        task_default_priority=5,
        # Timezone
        timezone="UTC",
        enable_utc=True,
    )

    logger.info(f"Celery app initialized: broker={settings.CELERY_BROKER_URL}")
    return _celery_app


# Create app for celery CLI compatibility
celery_app = get_celery_app()
