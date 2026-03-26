"""Centralized file filtering logic for the Code Index MCP server."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Iterable, List, Optional, Pattern

from ..constants import FILTER_CONFIG


class FileFilter:
    """Centralized file filtering logic."""

    def __init__(
        self,
        additional_excludes: Optional[List[str]] = None,
        *,
        include_patterns: Optional[Iterable[str]] = None,
        exclude_patterns: Optional[Iterable[str]] = None,
        include_regex: Optional[Iterable[Pattern[str] | str]] = None,
        exclude_regex: Optional[Iterable[Pattern[str] | str]] = None,
        supported_extensions: Optional[Iterable[str]] = None,
    ):
        self.exclude_dirs = set(FILTER_CONFIG["exclude_directories"])
        self.exclude_files = set(FILTER_CONFIG["exclude_files"])
        self.supported_extensions = set(
            supported_extensions or FILTER_CONFIG["supported_extensions"]
        )

        self.include_patterns = {
            self._normalize_pattern(pattern)
            for pattern in (include_patterns or [])
            if isinstance(pattern, str) and pattern.strip()
        }
        self.path_exclude_patterns = {
            self._normalize_pattern(pattern)
            for pattern in (exclude_patterns or [])
            if isinstance(pattern, str) and pattern.strip()
        }
        self.include_regex = self._normalize_regexes(include_regex)
        self.exclude_regex = self._normalize_regexes(exclude_regex)

        if additional_excludes:
            for pattern in additional_excludes:
                if not isinstance(pattern, str):
                    continue
                normalized = pattern.strip()
                if not normalized:
                    continue
                self.exclude_dirs.add(normalized)
                self.path_exclude_patterns.add(self._normalize_pattern(normalized))
                if self._looks_like_file_pattern(normalized):
                    self.exclude_files.add(normalized)

        for pattern in self.path_exclude_patterns:
            self._register_directory_exclude(pattern)
            if self._looks_like_file_pattern(pattern):
                self.exclude_files.add(pattern)

    @classmethod
    def from_effective_config(cls, config: Optional[dict]) -> "FileFilter":
        """Build a filter from an effective config mapping."""
        config = config or {}
        return cls(
            additional_excludes=list(config.get("additional_exclude_patterns") or []),
            include_patterns=list(config.get("include_patterns") or []),
            exclude_patterns=list(config.get("exclude_patterns") or []),
            include_regex=list(
                config.get("compiled_include_regex")
                or config.get("include_regex")
                or []
            ),
            exclude_regex=list(
                config.get("compiled_exclude_regex")
                or config.get("exclude_regex")
                or []
            ),
            supported_extensions=list(
                config.get("supported_extensions")
                or FILTER_CONFIG["supported_extensions"]
            ),
        )

    def should_exclude_directory(self, dir_name: str) -> bool:
        if dir_name.startswith(".") and dir_name not in {".env", ".gitignore"}:
            return True
        return dir_name in self.exclude_dirs

    def should_exclude_file(self, file_path: Path) -> bool:
        if not self.is_supported_file_type(file_path):
            return True

        if file_path.name.startswith(".") and file_path.name not in {
            ".gitignore",
            ".env",
        }:
            return True

        for pattern in self.exclude_files:
            if fnmatch.fnmatch(file_path.name, pattern):
                return True

        return False

    def should_process_path(self, path: Path, base_path: Path) -> bool:
        try:
            absolute_path = path if path.is_absolute() else (base_path / path)
            relative_path = self._normalize_relative_path(absolute_path, base_path)
        except (ValueError, OSError):
            return False

        if self._is_under_excluded_directory(relative_path):
            return False

        if self.should_exclude_file(absolute_path):
            return False

        if self.include_patterns or self.include_regex:
            if not self._matches_include(relative_path):
                return False

        if self._matches_exclude(relative_path):
            return False

        return True

    def is_supported_file_type(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions

    def is_temporary_file(self, file_path: Path) -> bool:
        name = file_path.name
        temp_patterns = ["*.tmp", "*.temp", "*.swp", "*.swo", "*~"]

        for pattern in temp_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True

        if name.endswith((".bak", ".orig")):
            return True

        return False

    def filter_file_list(self, files: List[str], base_path: str) -> List[str]:
        base = Path(base_path)
        filtered = []

        for file_path_str in files:
            file_path = Path(file_path_str)
            if self.should_process_path(file_path, base):
                filtered.append(file_path_str)

        return filtered

    def get_exclude_summary(self) -> dict:
        return {
            "exclude_directories_count": len(self.exclude_dirs),
            "exclude_files_count": len(self.exclude_files),
            "supported_extensions_count": len(self.supported_extensions),
            "include_patterns_count": len(self.include_patterns),
            "exclude_patterns_count": len(self.path_exclude_patterns),
            "include_regex_count": len(self.include_regex),
            "exclude_regex_count": len(self.exclude_regex),
            "exclude_directories": sorted(self.exclude_dirs),
            "exclude_files": sorted(self.exclude_files),
            "include_patterns": sorted(self.include_patterns),
            "exclude_patterns": sorted(self.path_exclude_patterns),
        }

    def _matches_include(self, relative_path: str) -> bool:
        return self._matches_any_glob(
            relative_path, self.include_patterns
        ) or self._matches_any_regex(
            relative_path,
            self.include_regex,
        )

    def _matches_exclude(self, relative_path: str) -> bool:
        return self._matches_any_glob(
            relative_path, self.path_exclude_patterns
        ) or self._matches_any_regex(
            relative_path,
            self.exclude_regex,
        )

    def _is_under_excluded_directory(self, relative_path: str) -> bool:
        parts = Path(relative_path).parts[:-1]
        for part in parts:
            if self.should_exclude_directory(part):
                return True
        return False

    @staticmethod
    def _matches_any_glob(relative_path: str, patterns: Iterable[str]) -> bool:
        file_name = Path(relative_path).name
        for pattern in patterns:
            variants = {pattern}
            if "**/" in pattern:
                variants.add(pattern.replace("**/", ""))
            if not pattern.startswith("**/"):
                variants.add(f"**/{pattern}")

            if any(fnmatch.fnmatch(relative_path, variant) for variant in variants):
                return True
            if fnmatch.fnmatch(file_name, pattern):
                return True
        return False

    @staticmethod
    def _matches_any_regex(
        relative_path: str, patterns: Iterable[Pattern[str]]
    ) -> bool:
        return any(pattern.search(relative_path) for pattern in patterns)

    @staticmethod
    def _normalize_relative_path(path: Path, base_path: Path) -> str:
        relative_path = path.relative_to(base_path)
        return relative_path.as_posix()

    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        normalized = pattern.strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    @staticmethod
    def _looks_like_file_pattern(pattern: str) -> bool:
        return any(char in pattern for char in "*?[") or "." in Path(pattern).name

    @staticmethod
    def _normalize_regexes(
        patterns: Optional[Iterable[Pattern[str] | str]],
    ) -> List[Pattern[str]]:
        result: List[Pattern[str]] = []
        for pattern in patterns or []:
            if isinstance(pattern, re.Pattern):
                result.append(pattern)
            elif isinstance(pattern, str) and pattern.strip():
                result.append(re.compile(pattern.strip()))
        return result

    def _register_directory_exclude(self, pattern: str) -> None:
        parts = [part for part in Path(pattern).parts if part not in {".", ".."}]
        if len(parts) == 1 and not self._looks_like_file_pattern(pattern):
            self.exclude_dirs.add(parts[0])
