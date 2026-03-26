"""Project-local filtering rules loading and validation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern

from .constants import PROJECT_RULES_FILE


@dataclass(frozen=True)
class ProjectRules:
    """Validated project filtering rules."""

    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    include_regex: List[str] = field(default_factory=list)
    exclude_regex: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompiledProjectRules:
    """Compiled filtering rules plus metadata."""

    source_path: Optional[str]
    source_type: str
    found: bool
    rules: ProjectRules = field(default_factory=ProjectRules)
    include_regex: List[Pattern[str]] = field(default_factory=list)
    exclude_regex: List[Pattern[str]] = field(default_factory=list)

    def to_metadata(self) -> dict:
        return {
            "source_path": self.source_path,
            "source_type": self.source_type,
            "found": self.found,
            "include_count": len(self.rules.include),
            "exclude_count": len(self.rules.exclude),
            "include_regex_count": len(self.rules.include_regex),
            "exclude_regex_count": len(self.rules.exclude_regex),
        }


def resolve_project_rules_path(
    base_path: str,
    explicit_path: Optional[str] = None,
) -> tuple[Optional[str], str, bool]:
    """Resolve the project rules file path and source type."""
    if explicit_path:
        resolved = os.path.abspath(explicit_path)
        return resolved, "cli_override", os.path.exists(resolved)

    if base_path:
        resolved = os.path.join(base_path, PROJECT_RULES_FILE)
        return resolved, "project_default", os.path.exists(resolved)

    return None, "none", False


def load_project_rules(
    base_path: str,
    explicit_path: Optional[str] = None,
) -> CompiledProjectRules:
    """Load and compile filtering rules from disk."""
    source_path, source_type, found = resolve_project_rules_path(
        base_path, explicit_path
    )
    if not source_path or not found:
        return CompiledProjectRules(
            source_path=source_path,
            source_type=source_type,
            found=False,
        )

    try:
        with open(source_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid filtering config JSON in {source_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"Unable to read filtering config {source_path}: {exc}"
        ) from exc

    rules = validate_project_rules(data, source_path)
    return CompiledProjectRules(
        source_path=source_path,
        source_type=source_type,
        found=True,
        rules=rules,
        include_regex=_compile_regex_list(
            rules.include_regex, source_path, "include_regex"
        ),
        exclude_regex=_compile_regex_list(
            rules.exclude_regex, source_path, "exclude_regex"
        ),
    )


def validate_project_rules(data: object, source_path: str = "<memory>") -> ProjectRules:
    """Validate JSON payload for project rules."""
    if not isinstance(data, dict):
        raise ValueError(f"Filtering config {source_path} must be a JSON object")

    version = data.get("version", 1)
    if version != 1:
        raise ValueError(
            f"Filtering config {source_path} has unsupported version: {version}"
        )

    rules_data = data.get("rules", {})
    if not isinstance(rules_data, dict):
        raise ValueError(
            f"Filtering config {source_path} field 'rules' must be an object"
        )

    return ProjectRules(
        include=_validate_string_list(
            rules_data.get("include", []), source_path, "include"
        ),
        exclude=_validate_string_list(
            rules_data.get("exclude", []), source_path, "exclude"
        ),
        include_regex=_validate_string_list(
            rules_data.get("include_regex", []),
            source_path,
            "include_regex",
        ),
        exclude_regex=_validate_string_list(
            rules_data.get("exclude_regex", []),
            source_path,
            "exclude_regex",
        ),
    )


def _validate_string_list(
    value: object, source_path: str, field_name: str
) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            f"Filtering config {source_path} field '{field_name}' must be a list of strings"
        )

    result: List[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"Filtering config {source_path} field '{field_name}' item {index} must be a string"
            )
        normalized = item.strip()
        if not normalized:
            raise ValueError(
                f"Filtering config {source_path} field '{field_name}' item {index} cannot be empty"
            )
        result.append(normalized)
    return result


def _compile_regex_list(
    patterns: List[str],
    source_path: str,
    field_name: str,
) -> List[Pattern[str]]:
    compiled: List[Pattern[str]] = []
    for index, pattern in enumerate(patterns):
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ValueError(
                f"Invalid regex in {source_path} field '{field_name}' item {index}: {exc}"
            ) from exc
    return compiled
