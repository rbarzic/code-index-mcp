"""Tests for include and exclude filtering rules."""

from pathlib import Path

from code_index_mcp.utils.file_filter import FileFilter


def test_include_patterns_limit_processing(tmp_path):
    file_filter = FileFilter(include_patterns=["src/**/*.py"])
    base_path = tmp_path

    assert file_filter.should_process_path(
        base_path / "src" / "pkg" / "main.py", base_path
    )
    assert not file_filter.should_process_path(
        base_path / "tests" / "test_main.py", base_path
    )


def test_exclude_patterns_override_include(tmp_path):
    file_filter = FileFilter(
        include_patterns=["src/**/*.py"],
        exclude_patterns=["src/generated/**"],
    )
    base_path = tmp_path

    assert not file_filter.should_process_path(
        base_path / "src" / "generated" / "main.py",
        base_path,
    )


def test_regex_rules_match_normalized_relative_paths(tmp_path):
    file_filter = FileFilter(exclude_regex=[r"^legacy/", r"/dist/"])
    base_path = tmp_path

    assert not file_filter.should_process_path(
        base_path / "legacy" / "old.py", base_path
    )
    assert not file_filter.should_process_path(
        base_path / "packages" / "a" / "dist" / "out.py", base_path
    )
    assert file_filter.should_process_path(base_path / "src" / "main.py", base_path)


def test_filter_file_list_accepts_relative_paths(tmp_path):
    file_filter = FileFilter(include_patterns=["src/**/*.py"])
    files = ["src/app.py", "tests/test_app.py"]

    filtered = file_filter.filter_file_list(files, str(tmp_path))

    assert filtered == ["src/app.py"]
