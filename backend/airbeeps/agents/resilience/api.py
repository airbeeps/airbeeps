"""
API endpoints for resilience and health monitoring.

Provides endpoints for:
- Health checks for all services
- Circuit breaker status
- Retry statistics
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from airbeeps.agents.resilience.circuit_breaker import (
    CircuitBreakerRegistry,
)
from airbeeps.agents.resilience.health import (
    HealthStatus,
    get_health_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


# ============================================================================
# Health Check Endpoints
# ============================================================================


@router.get("")
async def health_check() -> dict[str, Any]:
    """
    Overall health check endpoint.

    Returns aggregated health status of all registered services.
    """
    registry = get_health_registry()

    # Run all health checks
    results = await registry.check_all()

    # Get overall status
    overall = registry.get_overall_status()

    return {
        "status": overall.value,
        "services": {
            name: {
                "status": health.status.value,
                "message": health.message,
                "latency_ms": health.latency_ms,
            }
            for name, health in results.items()
        },
    }


@router.get("/ready")
async def readiness_check() -> dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.

    Returns 200 if the service is ready to receive traffic.
    """
    registry = get_health_registry()
    overall = registry.get_overall_status()

    if overall == HealthStatus.UNHEALTHY:
        raise HTTPException(status_code=503, detail="Service not ready")

    return {"status": "ready"}


@router.get("/live")
async def liveness_check() -> dict[str, Any]:
    """
    Kubernetes liveness probe endpoint.

    Returns 200 if the service is alive.
    """
    # Simple check - if we can respond, we're alive
    return {"status": "alive"}


@router.get("/services/{service_name}")
async def service_health(service_name: str) -> dict[str, Any]:
    """
    Health check for a specific service.

    Args:
        service_name: Name of the service to check
    """
    registry = get_health_registry()

    result = await registry.check(service_name, force=True)

    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Service '{service_name}' not found"
        )

    return {
        "name": result.name,
        "status": result.status.value,
        "message": result.message,
        "latency_ms": result.latency_ms,
        "last_check": result.last_check,
        "metadata": result.metadata,
    }


# ============================================================================
# Circuit Breaker Endpoints
# ============================================================================


@router.get("/circuits")
async def list_circuits() -> dict[str, Any]:
    """
    List all circuit breakers and their states.
    """
    registry = CircuitBreakerRegistry.get_instance()

    return {
        "circuits": registry.get_all_stats(),
        "open_circuits": registry.get_open_circuits(),
    }


@router.get("/circuits/{circuit_name}")
async def circuit_status(circuit_name: str) -> dict[str, Any]:
    """
    Get status of a specific circuit breaker.
    """
    registry = CircuitBreakerRegistry.get_instance()
    breaker = registry.get(circuit_name)

    if breaker is None:
        raise HTTPException(
            status_code=404, detail=f"Circuit '{circuit_name}' not found"
        )

    return breaker.get_stats()


@router.post("/circuits/{circuit_name}/reset")
async def reset_circuit(circuit_name: str) -> dict[str, Any]:
    """
    Manually reset a circuit breaker to closed state.
    """
    registry = CircuitBreakerRegistry.get_instance()
    breaker = registry.get(circuit_name)

    if breaker is None:
        raise HTTPException(
            status_code=404, detail=f"Circuit '{circuit_name}' not found"
        )

    breaker.reset()

    return {
        "status": "reset",
        "circuit": circuit_name,
        "new_state": breaker.state.value,
    }


# ============================================================================
# Infrastructure Health Endpoints
# ============================================================================


@router.get("/storage")
async def storage_health() -> dict[str, Any]:
    """
    Check storage backend health (S3/local).
    """
    try:
        from airbeeps.files.storage import storage_service

        result = await storage_service.health_check()
        if not result.get("healthy"):
            raise HTTPException(
                status_code=503,
                detail=f"Storage unhealthy: {result.get('details', {})}",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/cache")
async def cache_health() -> dict[str, Any]:
    """
    Check cache backend health (Redis/in-memory).
    """
    try:
        from airbeeps.cache import get_cache
        from airbeeps.config import settings

        cache = await get_cache()
        healthy = await cache.health_check()

        return {
            "healthy": healthy,
            "backend": "redis" if settings.REDIS_ENABLED else "memory",
            "enabled": settings.REDIS_ENABLED,
        }
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        return {
            "healthy": False,
            "backend": "unknown",
            "error": str(e),
        }


@router.get("/celery")
async def celery_health() -> dict[str, Any]:
    """
    Check Celery workers health.
    """
    from airbeeps.config import settings

    if not settings.CELERY_ENABLED:
        return {
            "enabled": False,
            "status": "disabled",
            "message": "Celery is disabled. Tasks run in-process.",
        }

    try:
        from airbeeps.tasks.celery_app import get_celery_app

        app = get_celery_app()
        if app is None:
            return {
                "enabled": True,
                "status": "unavailable",
                "message": "Celery app not initialized",
            }

        # Try to ping workers
        inspect = app.control.inspect(timeout=2.0)
        ping_result = inspect.ping()

        if not ping_result:
            return {
                "enabled": True,
                "status": "no_workers",
                "message": "No Celery workers responding",
            }

        active = inspect.active() or {}
        reserved = inspect.reserved() or {}

        return {
            "enabled": True,
            "status": "healthy",
            "workers": list(ping_result.keys()),
            "active_tasks": sum(len(tasks) for tasks in active.values()),
            "reserved_tasks": sum(len(tasks) for tasks in reserved.values()),
        }
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {
            "enabled": True,
            "status": "error",
            "error": str(e),
        }


# ============================================================================
# Summary Endpoint
# ============================================================================


@router.get("/summary")
async def health_summary() -> dict[str, Any]:
    """
    Get a summary of all health and resilience information.
    """
    health_registry = get_health_registry()
    circuit_registry = CircuitBreakerRegistry.get_instance()

    health_results = await health_registry.check_all()

    # Add infrastructure health
    storage = await storage_health()
    cache = await cache_health()
    celery = await celery_health()

    return {
        "overall_health": health_registry.get_overall_status().value,
        "services": {
            name: health.status.value for name, health in health_results.items()
        },
        "infrastructure": {
            "storage": storage.get("healthy", False),
            "cache": cache.get("healthy", False),
            "celery": celery.get("status") == "healthy",
        },
        "circuits": {
            name: stats["state"]
            for name, stats in circuit_registry.get_all_stats().items()
        },
        "open_circuits": circuit_registry.get_open_circuits(),
    }
