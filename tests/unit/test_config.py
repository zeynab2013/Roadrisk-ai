"""Configuration tests."""

from pathlib import Path

from roadrisk.config import load_settings


def test_relative_data_dir_uses_project_root(tmp_path: Path) -> None:
    settings = load_settings({"ROADRISK_DATA_DIR": "data"}, project_root=tmp_path)
    assert settings.data_dir == (tmp_path / "data").resolve()
    assert settings.log_level == "INFO"


def test_absolute_data_dir_is_kept(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    settings = load_settings(
        {"ROADRISK_DATA_DIR": str(target), "ROADRISK_LOG_LEVEL": "debug"},
        project_root=tmp_path,
    )
    assert settings.data_dir == target.resolve()
    assert settings.log_level == "DEBUG"
