"""Tests for file watcher observer selection and docs."""

import platform
import select
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from code_index_mcp.services.file_watcher_service import (
    DebounceEventHandler,
    _get_observer_class,
)
from code_index_mcp.utils.file_filter import FileFilter
from code_index_mcp.server import configure_file_watcher


def test_auto_uses_platform_default():
    """Verify auto mode uses platform default observer."""
    # Auto should use the default Observer class (platform default)
    # On macOS this is FSEventsObserver, on Linux InotifyObserver, etc.
    ObserverClass = _get_observer_class("auto")
    assert ObserverClass is not None
    # Should NOT be kqueue (that's opt-in now)
    assert "Kqueue" not in ObserverClass.__name__


def test_auto_docstring_matches_platform_default_contract():
    """Verify auto mode docs describe the platform default contract."""
    observer_doc = _get_observer_class.__doc__ or ""
    tool_doc = configure_file_watcher.__doc__ or ""

    assert '"auto": platform default observer' in observer_doc
    assert '"auto" (default): platform default observer' in tool_doc


def test_auto_uses_default_on_linux():
    """Verify auto mode uses platform default on Linux."""
    with patch(
        "code_index_mcp.services.file_watcher_service.platform.system",
        return_value="Linux",
    ):
        ObserverClass = _get_observer_class("auto")
        # On Linux, should get the default Observer (InotifyObserver)
        assert ObserverClass is not None


def test_auto_uses_default_on_windows():
    """Verify auto mode uses platform default on Windows."""
    with patch(
        "code_index_mcp.services.file_watcher_service.platform.system",
        return_value="Windows",
    ):
        ObserverClass = _get_observer_class("auto")
        # On Windows, should get the default Observer (WindowsApiObserver or ReadDirectoryChangesW)
        assert ObserverClass is not None


def test_explicit_kqueue():
    """Verify explicit kqueue selection works."""
    if platform.system() == "Windows":
        pytest.skip("kqueue observer import fails on Windows")
    if not hasattr(select, "KQ_FILTER_VNODE"):
        pytest.skip("kqueue observer not supported on this platform")
    ObserverClass = _get_observer_class("kqueue")
    assert "Kqueue" in ObserverClass.__name__


def test_explicit_polling():
    """Verify explicit polling selection works."""
    ObserverClass = _get_observer_class("polling")
    assert "Polling" in ObserverClass.__name__


def test_fsevents_only_on_macos():
    """Verify fsevents raises error on non-macOS."""
    with patch(
        "code_index_mcp.services.file_watcher_service.platform.system",
        return_value="Linux",
    ):
        with pytest.raises(ValueError, match="only available on macOS"):
            _get_observer_class("fsevents")


def test_fsevents_works_on_macos():
    """Verify fsevents can be selected on macOS."""
    # Only run this test on actual macOS since fsevents module won't exist elsewhere
    if platform.system() == "Darwin":
        ObserverClass = _get_observer_class("fsevents")
        assert "FSEvents" in ObserverClass.__name__


def test_invalid_observer_type_falls_back_to_auto():
    """Verify invalid observer_type falls back to auto behavior."""
    # Invalid types should fall through to the else (auto) branch
    ObserverClass = _get_observer_class("invalid_type")
    # Should get the platform default (auto behavior), not kqueue
    assert ObserverClass is not None
    assert "Kqueue" not in ObserverClass.__name__


def test_debounce_handler_processes_filter_config_changes(tmp_path):
    config_path = tmp_path / ".code-index.json"
    config_path.write_text('{"version":1,"rules":{}}', encoding="utf-8")

    handler = DebounceEventHandler(
        debounce_seconds=0.1,
        rebuild_callback=lambda: True,
        base_path=tmp_path,
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
            debug=lambda *a, **k: None,
        ),
        file_filter=FileFilter(),
        filter_config_path=config_path,
    )

    event = SimpleNamespace(
        is_directory=False, event_type="modified", src_path=str(config_path)
    )

    assert handler.should_process_event(event) is True


def test_debounce_handler_refreshes_filter_after_rebuild(tmp_path):
    settings = SimpleNamespace(
        build_file_filter=lambda: FileFilter(include_patterns=["src/**/*.py"]),
        get_project_rules_path=lambda: str(tmp_path / ".code-index.json"),
    )
    logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    called = {"count": 0}

    def rebuild_callback():
        called["count"] += 1
        return True

    handler = DebounceEventHandler(
        debounce_seconds=0.1,
        rebuild_callback=rebuild_callback,
        base_path=tmp_path,
        logger=logger,
        settings=settings,
        file_filter=FileFilter(),
    )

    handler.trigger_rebuild()

    assert called["count"] == 1
    assert handler.file_filter.should_process_path(
        tmp_path / "src" / "main.py", tmp_path
    )
    assert not handler.file_filter.should_process_path(
        tmp_path / "tests" / "main.py", tmp_path
    )
