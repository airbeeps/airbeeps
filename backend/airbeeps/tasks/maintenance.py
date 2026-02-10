"""
Celery tasks for maintenance and scheduled operations.

These tasks run periodically via Celery Beat.
"""

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


try:
    from celery import shared_task
    from celery.schedules import crontab

    @shared_task(name="airbeeps.tasks.cleanup_old_traces")
    def cleanup_old_traces():
        """
        Clean up agent traces older than retention period.

        Runs daily via Celery Beat.
        """
        logger.info("Starting trace cleanup")
        return _run_async(_cleanup_traces_async())

    @shared_task(name="airbeeps.tasks.cleanup_expired_sessions")
    def cleanup_expired_sessions():
        """
        Clean up expired refresh tokens and sessions.

        Runs hourly via Celery Beat.
        """
        logger.info("Starting session cleanup")
        return _run_async(_cleanup_sessions_async())

    @shared_task(name="airbeeps.tasks.update_model_analytics")
    def update_model_analytics():
        """
        Update aggregated model analytics.

        Runs every 15 minutes via Celery Beat.
        """
        logger.info("Updating model analytics")
        return _run_async(_update_analytics_async())

    @shared_task(name="airbeeps.tasks.health_report")
    def health_report():
        """
        Generate and log system health report.

        Runs hourly via Celery Beat.
        """
        logger.info("Generating health report")
        return _run_async(_health_report_async())

    # Celery Beat schedule configuration
    # Add this to celery_app.conf.beat_schedule in celery_app.py
    CELERYBEAT_SCHEDULE = {
        "cleanup-old-traces": {
            "task": "airbeeps.tasks.cleanup_old_traces",
            "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        },
        "cleanup-expired-sessions": {
            "task": "airbeeps.tasks.cleanup_expired_sessions",
            "schedule": crontab(minute=0),  # Every hour
        },
        "cleanup-expired-memories": {
            "task": "airbeeps.tasks.cleanup_expired_memories",
            "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM
        },
        "update-model-analytics": {
            "task": "airbeeps.tasks.update_model_analytics",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
        "health-report": {
            "task": "airbeeps.tasks.health_report",
            "schedule": crontab(minute=30),  # Every hour at :30
        },
    }

except ImportError:

    def cleanup_old_traces():
        raise RuntimeError("Celery is not installed")

    def cleanup_expired_sessions():
        raise RuntimeError("Celery is not installed")

    def update_model_analytics():
        raise RuntimeError("Celery is not installed")

    def health_report():
        raise RuntimeError("Celery is not installed")

    CELERYBEAT_SCHEDULE = {}


async def _cleanup_traces_async() -> dict:
    """Clean up old agent traces."""
    from datetime import timedelta

    from sqlalchemy import delete

    from airbeeps.agents.tracing.storage import AgentTrace
    from airbeeps.config import settings
    from airbeeps.database import get_async_session_context

    cutoff = datetime.now(UTC) - timedelta(days=settings.TRACING_RETENTION_DAYS)

    async with get_async_session_context() as session:
        stmt = delete(AgentTrace).where(AgentTrace.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()

        return {
            "deleted_count": result.rowcount,
            "cutoff_date": cutoff.isoformat(),
        }


async def _cleanup_sessions_async() -> dict:
    """Clean up expired refresh tokens."""
    from sqlalchemy import delete

    from airbeeps.auth.refresh_token_models import RefreshToken
    from airbeeps.database import get_async_session_context

    now = datetime.now(UTC)

    async with get_async_session_context() as session:
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < now)
        result = await session.execute(stmt)
        await session.commit()

        return {
            "deleted_count": result.rowcount,
            "timestamp": now.isoformat(),
        }


async def _update_analytics_async() -> dict:
    """Update aggregated model analytics."""
    # This would aggregate model usage data for dashboards
    # For now, return a stub
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def _health_report_async() -> dict:
    """Generate system health report."""
    from airbeeps.agents.resilience.health import get_health_service

    try:
        service = get_health_service()
        health = await service.check_all()

        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "healthy"
            if all(c.get("healthy") for c in health.values())
            else "degraded",
            "components": health,
        }

        if report["status"] != "healthy":
            logger.warning(f"System health degraded: {report}")

        return report
    except Exception as e:
        logger.error(f"Health report failed: {e}")
        return {"status": "error", "error": str(e)}
