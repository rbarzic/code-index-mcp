"""
Request Context - Per-request project context using contextvars.

This module provides request-scoped project path management to support
multiple Claude Code sessions using different projects simultaneously.

The context is set from the `Mcp-Project-Path` HTTP header by the proxy,
allowing each request to operate on its own project without interference.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Context variable for request-scoped project path
_project_path_var: ContextVar[Optional[str]] = ContextVar("project_path", default=None)
_profile_var: ContextVar[Optional[str]] = ContextVar("profile", default=None)


@dataclass
class RequestContext:
    """Immutable snapshot of request context."""

    project_path: Optional[str] = None
    profile: Optional[str] = None


def get_request_project_path() -> Optional[str]:
    """Get the current request's project path.

    Returns:
        Project path from HTTP header, or None if not set
    """
    return _project_path_var.get()


def get_request_profile() -> Optional[str]:
    """Get the current request's storage profile."""
    return _profile_var.get()


def set_request_project_path(path: Optional[str]) -> None:
    """Set the current request's project path.

    Args:
        path: Project path from Mcp-Project-Path header
    """
    if path:
        logger.debug(f"[RequestContext] Setting project path: {path}")
    _project_path_var.set(path)


def set_request_profile(profile: Optional[str]) -> None:
    """Set the current request's storage profile."""
    if profile:
        logger.debug(f"[RequestContext] Setting profile: {profile}")
    _profile_var.set(profile)


def clear_request_project_path() -> None:
    """Clear the current request's project path."""
    _project_path_var.set(None)
    _profile_var.set(None)


class RequestContextManager:
    """Context manager for request-scoped project path.

    Usage:
        with RequestContextManager(project_path):
            # All operations in this block use project_path
            pass
    """

    def __init__(self, project_path: Optional[str], profile: Optional[str] = None):
        self.project_path = project_path
        self.profile = profile
        self._token = None
        self._profile_token = None

    def __enter__(self) -> "RequestContextManager":
        self._token = _project_path_var.set(self.project_path)
        self._profile_token = _profile_var.set(self.profile)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token is not None:
            _project_path_var.reset(self._token)
        if self._profile_token is not None:
            _profile_var.reset(self._profile_token)
        return None
