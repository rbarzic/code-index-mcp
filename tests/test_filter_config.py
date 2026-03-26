"""Tests for filtering config discovery and loading."""

import json
from unittest.mock import MagicMock

import pytest

from code_index_mcp.project_settings import ProjectSettings
from code_index_mcp.services.project_management_service import ProjectManagementService
from code_index_mcp.services.settings_service import SettingsService
from code_index_mcp.server import _parse_args
from code_index_mcp.indexing.shallow_index_manager import ShallowIndexManager


def test_parse_args_supports_filter_config():
    args = _parse_args(["--filter-config", "rules.json"])
    assert args.filter_config == "rules.json"


def test_parse_args_supports_profile():
    args = _parse_args(["--profile", "soc-a"])
    assert args.profile == "soc-a"


def test_project_settings_loads_repo_local_filter_config(tmp_path):
    config_path = tmp_path / ".code-index.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": {
                    "include": ["src/**/*.py"],
                    "exclude": ["**/vendor/**"],
                    "exclude_regex": ["^legacy/"],
                },
            }
        ),
        encoding="utf-8",
    )

    settings = ProjectSettings(str(tmp_path), skip_load=True)
    config = settings.get_effective_filter_config()

    assert config["config_found"] is True
    assert config["source_path"] == str(config_path)
    assert config["include_patterns"] == ["src/**/*.py"]
    assert config["exclude_patterns"] == ["**/vendor/**"]
    assert config["exclude_regex"] == ["^legacy/"]


def test_project_settings_prefers_explicit_filter_config(tmp_path):
    repo_config = tmp_path / ".code-index.json"
    repo_config.write_text(
        json.dumps({"version": 1, "rules": {"exclude": ["repo/**"]}}), encoding="utf-8"
    )

    external_config = tmp_path / "external-rules.json"
    external_config.write_text(
        json.dumps({"version": 1, "rules": {"exclude": ["external/**"]}}),
        encoding="utf-8",
    )

    settings = ProjectSettings(
        str(tmp_path),
        skip_load=True,
        filter_config_path=str(external_config),
    )
    config = settings.get_effective_filter_config()

    assert config["source_type"] == "cli_override"
    assert config["source_path"] == str(external_config)
    assert config["exclude_patterns"] == ["external/**"]


def test_invalid_filter_regex_raises(tmp_path):
    config_path = tmp_path / ".code-index.json"
    config_path.write_text(
        json.dumps({"version": 1, "rules": {"exclude_regex": ["("]}}),
        encoding="utf-8",
    )

    settings = ProjectSettings(str(tmp_path), skip_load=True)

    with pytest.raises(ValueError, match="Invalid regex"):
        settings.get_effective_filter_config()


def test_settings_info_reports_filtering_metadata(tmp_path):
    config_path = tmp_path / ".code-index.json"
    config_path.write_text(
        json.dumps({"version": 1, "rules": {"exclude": ["generated/**"]}}),
        encoding="utf-8",
    )

    settings = ProjectSettings(str(tmp_path), skip_load=True)
    service = SettingsService(MagicMock())
    service.helper = MagicMock()
    service.helper.base_path = str(tmp_path)
    service.helper.settings = settings

    info = service.get_settings_info()

    assert info["config"]["filtering"]["config_found"] is True
    assert info["config"]["filtering"]["source_path"] == str(config_path)
    assert info["config"]["filtering"]["exclude_patterns"] == ["generated/**"]


def test_project_config_reports_filtering_metadata(tmp_path):
    config_path = tmp_path / ".code-index.json"
    config_path.write_text(
        json.dumps({"version": 1, "rules": {"include": ["src/**/*.py"]}}),
        encoding="utf-8",
    )

    settings = ProjectSettings(str(tmp_path), skip_load=True)
    service = ProjectManagementService(MagicMock())
    service.helper = MagicMock()
    service.helper.base_path = str(tmp_path)
    service.helper.file_count = 1
    service.helper.settings = settings

    config = json.loads(service.get_project_config())

    assert config["filtering"]["config_found"] is True
    assert config["filtering"]["source_path"] == str(config_path)
    assert config["filtering"]["include_patterns"] == ["src/**/*.py"]


def test_get_filtering_config_returns_effective_rules(tmp_path):
    config_path = tmp_path / ".code-index.json"
    config_path.write_text(
        json.dumps({"version": 1, "rules": {"exclude": ["build/**"]}}),
        encoding="utf-8",
    )

    settings = ProjectSettings(str(tmp_path), skip_load=True)
    service = SettingsService(MagicMock())
    service.helper = MagicMock()
    service.helper.base_path = str(tmp_path)
    service.helper.settings = settings

    result = service.get_filtering_config()

    assert result["status"] == "configured"
    assert result["filtering"]["source_path"] == str(config_path)
    assert result["filtering"]["exclude_patterns"] == ["build/**"]


def test_same_project_different_profiles_use_different_storage_paths(tmp_path):
    settings_a = ProjectSettings(str(tmp_path), skip_load=True, profile="soc-a")
    settings_b = ProjectSettings(str(tmp_path), skip_load=True, profile="soc-b")

    assert settings_a.profile == "soc-a"
    assert settings_b.profile == "soc-b"
    assert settings_a.settings_path != settings_b.settings_path
    assert settings_a.get_storage_identity() != settings_b.get_storage_identity()


def test_same_project_different_profiles_use_different_shallow_index_dirs(tmp_path):
    manager_a = ShallowIndexManager()
    manager_b = ShallowIndexManager()
    settings_a = ProjectSettings(str(tmp_path), skip_load=True, profile="soc-a")
    settings_b = ProjectSettings(str(tmp_path), skip_load=True, profile="soc-b")

    assert manager_a.set_project_path(
        str(tmp_path),
        storage_identity=settings_a.get_storage_identity(),
    )
    assert manager_b.set_project_path(
        str(tmp_path),
        storage_identity=settings_b.get_storage_identity(),
    )

    assert manager_a.temp_dir != manager_b.temp_dir
