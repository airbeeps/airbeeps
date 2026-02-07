"""
Test configuration loading with YAML support
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml


def test_yaml_config_loading():
    """Test that YAML configuration is loaded and merged correctly"""
    from airbeeps.config import _deep_merge, _flatten_dict, _load_yaml_config

    # Test deep merge
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    merged = _deep_merge(base, override)

    assert merged["a"] == 1
    assert merged["b"]["c"] == 99
    assert merged["b"]["d"] == 3
    assert merged["e"] == 5


def test_flatten_dict():
    """Test dictionary flattening for env var mapping"""
    from airbeeps.config import _flatten_dict

    nested = {
        "vector_store": {"type": "qdrant", "qdrant": {"url": "http://localhost:6333"}}
    }

    flat = _flatten_dict(nested)

    assert flat["VECTOR_STORE__TYPE"] == "qdrant"
    assert flat["VECTOR_STORE__QDRANT__URL"] == "http://localhost:6333"


def test_settings_from_yaml(tmp_path, monkeypatch):
    """Test that settings load from YAML files"""
    # Create temporary config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create base settings YAML
    base_config = {
        "vector_store": {
            "type": "qdrant",
            "qdrant": {"url": "http://yaml-qdrant:6333"},
        },
        "rag": {"features": {"enable_hybrid_search": True}},
    }

    with open(config_dir / "settings.yaml", "w") as f:
        yaml.dump(base_config, f)

    # Monkey-patch CONFIG_DIR
    import airbeeps.config as config_module

    original_config_dir = config_module.CONFIG_DIR
    config_module.CONFIG_DIR = config_dir

    try:
        # Reload config
        loaded = config_module._load_yaml_config()
        assert loaded["vector_store"]["type"] == "qdrant"
        assert loaded["vector_store"]["qdrant"]["url"] == "http://yaml-qdrant:6333"
    finally:
        config_module.CONFIG_DIR = original_config_dir


def test_env_override_yaml(tmp_path, monkeypatch):
    """Test that environment variables override YAML config"""
    # Set environment variable (use flat format which Pydantic supports natively)
    monkeypatch.setenv("AIRBEEPS_VECTOR_STORE_TYPE", "chromadb")

    # The Settings class should respect env vars over YAML
    from airbeeps.config import Settings

    settings = Settings()
    assert settings.VECTOR_STORE_TYPE == "chromadb"


def test_nested_env_delimiter():
    """Test that nested delimiter works for environment variables"""
    from airbeeps.config import Settings

    # Check that model_config has nested delimiter
    assert Settings.model_config["env_nested_delimiter"] == "__"


def test_settings_defaults():
    """Test that default settings are properly set"""
    from airbeeps.config import settings

    # Check critical defaults
    assert isinstance(settings.PROJECT_NAME, str) and len(settings.PROJECT_NAME) > 0
    assert settings.VECTOR_STORE_TYPE in ["qdrant", "chromadb", "pgvector", "milvus"]
    assert settings.RAG_ENABLE_HYBRID_SEARCH in [True, False]
    assert settings.AGENT_MAX_ITERATIONS > 0


def test_environment_specific_config(tmp_path, monkeypatch):
    """Test that environment-specific config overrides base config"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create base config
    base_config = {"logging": {"level": "INFO"}, "agent": {"max_iterations": 10}}
    with open(config_dir / "settings.yaml", "w") as f:
        yaml.dump(base_config, f)

    # Create dev config
    dev_config = {"logging": {"level": "DEBUG"}, "agent": {"max_iterations": 15}}
    with open(config_dir / "settings.dev.yaml", "w") as f:
        yaml.dump(dev_config, f)

    # Set environment
    monkeypatch.setenv("AIRBEEPS_CONFIG_ENV", "dev")

    # Monkey-patch CONFIG_DIR
    import airbeeps.config as config_module

    original_config_dir = config_module.CONFIG_DIR
    config_module.CONFIG_DIR = config_dir

    try:
        loaded = config_module._load_yaml_config()
        assert loaded["logging"]["level"] == "DEBUG"
        assert loaded["agent"]["max_iterations"] == 15
    finally:
        config_module.CONFIG_DIR = original_config_dir


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
