"""Tests for configuration loading."""

import tempfile
from pathlib import Path

from codesieve.config import Config, DEFAULTS, generate_default_config


def test_default_config():
    config = Config()
    assert config.sieves == DEFAULTS["sieves"]
    assert config.fail_under == 0.0
    assert config.deterministic is False
    assert config.format == "terminal"
    assert len(config.exclude) > 0


def test_load_missing_file():
    config = Config.load("/nonexistent/path/.codesieve.yml")
    assert config.sieves == DEFAULTS["sieves"]
    assert config.fail_under == 0.0


def test_load_custom_yaml():
    yaml_content = """
sieves:
  - KISS
  - Naming
weights:
  KISS: 0.50
  Naming: 0.50
fail_under: 8.0
exclude:
  - "**/vendor/**"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        path = f.name

    try:
        config = Config.load(path)
        assert config.sieves == ["KISS", "Naming"]
        assert config.weights["KISS"] == 0.50
        assert config.weights["Naming"] == 0.50
        assert config.fail_under == 8.0
        assert "**/vendor/**" in config.exclude
    finally:
        Path(path).unlink()


def test_weight_merging():
    """Custom weights should merge with defaults, not replace them."""
    yaml_content = """
weights:
  KISS: 0.99
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        path = f.name

    try:
        config = Config.load(path)
        assert config.weights["KISS"] == 0.99
        # Default weights for other sieves should still be present
        assert "Nesting" in config.weights
        assert config.weights["Nesting"] == DEFAULTS["weights"]["Nesting"]
    finally:
        Path(path).unlink()


def test_generate_default_config_content():
    content = generate_default_config()
    assert "KISS" in content
    assert "Nesting" in content
    assert "fail_under" in content
    assert "exclude" in content
    assert "format: terminal" in content
