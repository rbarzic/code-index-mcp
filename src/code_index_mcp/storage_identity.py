"""Helpers for deriving profile-aware on-disk storage identities."""

from __future__ import annotations

import hashlib
import os


def normalize_profile(profile: str | None) -> str:
    """Normalize a storage profile name."""
    value = (profile or "default").strip()
    return value or "default"


def compute_storage_identity(
    base_path: str | None,
    *,
    profile: str | None = None,
    filter_config_path: str | None = None,
) -> str:
    """Compute a stable storage identity for a project/profile/config tuple."""
    normalized_base = os.path.abspath(base_path) if base_path else ""
    normalized_profile = normalize_profile(profile)
    normalized_filter = (
        os.path.abspath(filter_config_path) if filter_config_path else ""
    )
    raw = f"{normalized_base}\n{normalized_profile}\n{normalized_filter}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
