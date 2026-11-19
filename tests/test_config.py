"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import pytest

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


def _load(tmp_path, body):
    p = tmp_path / ".codesieve.yml"
    p.write_text(body)
    return Config.load(p)


def test_exclude_null_loads_as_empty_list(tmp_path):
    assert _load(tmp_path, "exclude:\n").exclude == []


def test_exclude_string_loads_as_one_item_list(tmp_path):
    assert _load(tmp_path, "exclude: tests\n").exclude == ["tests"]


def test_exclude_non_string_entries_are_stringified(tmp_path):
    assert _load(tmp_path, "exclude: [123, build]\n").exclude == ["123", "build"]


def test_exclude_normalized_values_scan_without_crash(tmp_path):
    from codesieve.engine import _collect_files

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("x = 1\n")
    (tmp_path / "m.py").write_text("x = 1\n")
    config = _load(tmp_path, "exclude: tests\n")
    assert [f.name for f in _collect_files(tmp_path, config.exclude)] == ["m.py"]


def test_every_selected_sieve_at_weight_zero_is_refused(tmp_path):
    from codesieve.config import ConfigError

    with pytest.raises(ConfigError, match="weight 0"):
        _load(tmp_path, "sieves: [KISS]\nweights:\n  KISS: 0\n")


def test_retired_weight_names_are_still_accepted(tmp_path):
    """A `.codesieve.yml` from an older `codesieve init` must keep loading."""
    config = _load(tmp_path, "weights:\n  KISS: 0.2\n  SRP: 0.15\n  Complexity: 0.1\n")
    assert config.weights["KISS"] == 0.2
    assert "SRP" not in DEFAULTS["weights"]
