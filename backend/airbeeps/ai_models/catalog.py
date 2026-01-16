from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(:-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} or ${VAR:-default} in YAML-loaded data."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(3)
            return os.getenv(var_name, default if default is not None else "")

        return _ENV_VAR_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent / "catalog.yaml"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    """
    Load the built-in provider/model catalog.

    This is intentionally a *static suggestion registry* (templates), not the source
    of truth for configured providers/models (those live in the DB).
    """
    path = _catalog_path()
    if not path.exists():
        return {"version": 1, "providers": []}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _expand_env(raw)


def list_provider_templates() -> list[dict[str, Any]]:
    catalog = load_catalog()
    providers = catalog.get("providers", []) or []
    # Return summary only (models excluded)
    out: list[dict[str, Any]] = []
    for p in providers:
        out.append(
            {
                "id": str(p.get("id", "")).strip(),
                "display_name": p.get("display_name"),
                "description": p.get("description"),
                "website": p.get("website"),
                "api_base_url": p.get("api_base_url"),
                "category": p.get("category"),
                "is_openai_compatible": p.get("is_openai_compatible", False),
                "litellm_provider": p.get("litellm_provider"),
            }
        )
    # Stable ordering by display name
    out.sort(key=lambda x: (x.get("display_name") or x.get("id") or "").lower())
    return out


def get_provider_template(template_id: str) -> dict[str, Any] | None:
    template_id = (template_id or "").strip()
    if not template_id:
        return None
    catalog = load_catalog()
    for p in catalog.get("providers", []) or []:
        if str(p.get("id", "")).strip() == template_id:
            # Return full entry including models
            return p
    return None


def list_model_templates(
    provider_template_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    List model templates.

    If provider_template_id is provided, only models from that provider template
    are returned.
    """
    if provider_template_id:
        p = get_provider_template(provider_template_id)
        models = (p or {}).get("models", []) or []
        return list(models)

    # Flatten across providers
    catalog = load_catalog()
    out: list[dict[str, Any]] = []
    for p in catalog.get("providers", []) or []:
        pid = str(p.get("id", "")).strip()
        for m in p.get("models", []) or []:
            out.append({**m, "provider_template_id": pid})
    return out
