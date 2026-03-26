# Plan: Add Filtering Support

## Goal

Add support for a filtering configuration file that defines inclusion and exclusion
rules for files and directories used by indexing, search, file discovery, and file
watcher rebuilds.

The feature should:

- support repo-local include/exclude rules
- support glob-based path matching
- optionally support regex-based path matching
- allow passing the filtering config file path explicitly to the executable
- keep current behavior unchanged when no filtering config file exists
- apply the same effective rules across indexing, search, and watcher flows

## Current State

Filtering behavior is currently fragmented:

- built-in defaults live in `src/code_index_mcp/constants.py`
- filtering logic is centered in `src/code_index_mcp/utils/file_filter.py`
- indexing uses `FileFilter` through `JSONIndexBuilder`
- search builds its own filter from file watcher config
- project and rebuild services read excludes from file watcher config
- watcher-triggered rebuilds do not consistently reuse configured excludes

There is no real repo-local config file today, and no first-class include rule model.

## Recommended Configuration Model

Support both of these entry points:

- default repo-local config file in the project root
- explicit CLI override passed to the executable

Recommended default repo-local filename:

- `.code-index.json`

Recommended CLI option:

- `--filter-config <path>`

This gives:

- a simple default for normal project usage
- a way to test alternate filtering definitions
- a way to share one config outside the repo
- a way to use different configs in different environments

## Config Source Precedence

Recommended precedence order:

1. explicit CLI `--filter-config`
2. repo-local default file in project root
3. no file, which means current behavior

Recommended v1 behavior:

- if `--filter-config` is provided, it overrides repo-local auto-discovery
- do not merge CLI and repo-local configs in v1
- expose the effective source in diagnostics as either `cli_override` or `project_default`

## Recommended Config File Format

Use JSON for v1 to keep parsing and validation simple.

Recommended schema:

```json
{
  "version": 1,
  "rules": {
    "include": [
      "src/**/*.py",
      "tests/**/*.py"
    ],
    "exclude": [
      "**/vendor/**",
      "**/*.generated.*"
    ],
    "include_regex": [
      "^packages/[^/]+/src/"
    ],
    "exclude_regex": [
      "^legacy/",
      "/dist/"
    ]
  }
}
```

## Matching Semantics

Rules should apply to normalized repo-relative paths using `/`.

Recommended order:

1. apply built-in extension support filtering
2. apply built-in default excludes
3. if include rules exist, require a path to match at least one include rule
4. if any exclude rule matches, reject the path
5. exclude always wins over include

Additional notes:

- regex rules apply to normalized relative paths only
- glob rules remain the default and easiest-to-use format
- if no filtering config file exists, behavior remains unchanged
- supported extensions should remain limited by `SUPPORTED_EXTENSIONS` for v1

## Canonical Design

Introduce one canonical filtering model shared by:

- project initialization
- shallow indexing
- deep indexing
- search
- file watcher event filtering
- watcher-triggered rebuilds
- settings and diagnostics output

Do not continue using file watcher config as the main source for index/search excludes.

Instead:

- built-in defaults remain in constants
- filtering config is loaded either from CLI path or project root
- runtime overrides such as `additional_exclude_patterns` remain supported
- all of these are merged into one effective filter config

Recommended precedence for effective rule merging:

1. built-in defaults
2. filtering config file
3. runtime overrides

## Main Implementation Areas

### 1. Add a first-class filtering rules model

Create a new module, for example:

- `src/code_index_mcp/config/project_rules.py`
- or `src/code_index_mcp/utils/project_rules.py`

Add typed structures for:

- raw rules file payload
- validated rules config
- compiled regex rules
- merged effective filter config

Responsibilities:

- discover the config file source
- load JSON
- validate schema
- normalize paths
- compile regex patterns
- surface clear validation errors

Recommended functions:

- `load_project_rules(base_path, explicit_path=None)`
- `validate_project_rules(data)`
- `compile_project_rules(config)`
- `resolve_project_rules_path(base_path, explicit_path=None)`

Recommended metadata fields:

- `source_type`
- `source_path`
- `found`
- `valid`
- `version`
- `include_count`
- `exclude_count`
- `include_regex_count`
- `exclude_regex_count`

### 2. Extend CLI argument handling

File:

- `src/code_index_mcp/server.py`

Add a new CLI option in `_parse_args()`:

- `--filter-config`

Recommended behavior:

- accept an absolute or relative path
- validate the path early if provided
- resolve relative paths against the process working directory
- store the value in lifespan context or equivalent startup state
- make it available to project initialization and settings loading

Recommended startup flow:

1. parse CLI args
2. if `--filter-config` is set, normalize and store it
3. when project path is initialized, load filtering rules using:
   - explicit CLI path if present
   - otherwise repo-local default in project root
4. build effective filter config
5. reuse that effective config everywhere

Recommended error handling for CLI mode:

- missing CLI file path: fail startup or `set_project_path` with a clear error
- invalid JSON: fail fast with path included in error
- invalid regex: fail fast with regex and error reason

### 3. Extend `ProjectSettings`

File:

- `src/code_index_mcp/project_settings.py`

Add methods such as:

- `get_project_rules_path(explicit_path=None)`
- `load_project_rules(explicit_path=None)`
- `get_effective_filter_config(explicit_path=None, runtime_overrides=None)`
- optionally `build_file_filter(explicit_path=None, runtime_overrides=None)`

Responsibilities:

- load filtering config from explicit CLI path or from `base_path`
- keep temp `config.json` for runtime/server settings
- merge built-in defaults, filtering config rules, and runtime overrides
- expose metadata for diagnostics

Important:

- repo-local rules must be loaded from the project root, not the temp settings directory
- explicit CLI override must bypass repo-local auto-discovery in v1

### 4. Refactor `FileFilter` into the rules engine

File:

- `src/code_index_mcp/utils/file_filter.py`

Extend `FileFilter` so it supports:

- default excluded directories
- default excluded file globs
- include globs
- exclude globs
- include regexes
- exclude regexes
- supported extensions

Recommended additions:

- constructor or factory for effective config
- path normalization helpers
- explicit include/exclude match methods
- one final `should_process_path()` decision path

Recommended internal methods:

- `_normalize_relative_path()`
- `_matches_include_glob()`
- `_matches_exclude_glob()`
- `_matches_include_regex()`
- `_matches_exclude_regex()`
- `_is_supported_extension()`
- `_is_under_excluded_directory()`

Recommended matching logic:

1. reject unsupported file types
2. reject temporary files and current built-in exclusions
3. reject if the path is under an excluded directory
4. if include rules exist, require at least one include match
5. if any exclude glob or exclude regex matches, reject
6. otherwise allow

`FileFilter` should become the single source of truth for file eligibility.

### 5. Fix project initialization propagation

File:

- `src/code_index_mcp/services/project_management_service.py`

Current project initialization should be updated so the `ProjectSettings`
instance initialized for a project is reliably pushed into context.

Recommended change:

- ensure initialized settings are stored via context helper
- stop deriving indexing excludes only from watcher config
- use `get_effective_filter_config()` or `build_file_filter()` instead

This avoids downstream services using stale or partial config.

### 6. Update shallow and deep indexing

Files:

- `src/code_index_mcp/indexing/json_index_builder.py`
- `src/code_index_mcp/indexing/shallow_index_manager.py`
- `src/code_index_mcp/indexing/sqlite_index_manager.py`
- possibly `src/code_index_mcp/indexing/sqlite_index_builder.py`

Current design passes flat exclude lists.
That is too limited for include rules and regex rules.

Recommended direction:

- allow managers/builders to accept a `FileFilter` or structured filter config
- use the same `FileFilter` instance throughout filesystem scanning

Best long-term option:

- managers accept a `FileFilter`
- builders use that exact `FileFilter`

This avoids lossy conversion from structured rules back into raw exclude strings.

### 7. Update search to use the same effective rules

File:

- `src/code_index_mcp/services/search_service.py`

Search should stop using watcher config as the source of filtering rules.

Instead:

- build its `FileFilter` from project effective rules
- continue post-filtering matches for correctness
- propagate exclude globs to external search strategies where possible

Files involved:

- `src/code_index_mcp/search/base.py`
- `src/code_index_mcp/search/ripgrep.py`
- `src/code_index_mcp/search/ag.py`
- `src/code_index_mcp/search/grep.py`
- `src/code_index_mcp/search/ugrep.py`
- `src/code_index_mcp/search/basic.py`

Recommended behavior for v1:

- external tools may still over-scan
- final correctness comes from post-filtering with `FileFilter`
- regex excludes do not need immediate backend-specific translation
- include rules may optionally be translated later for performance, but not required for correctness

### 8. Fix watcher event filtering and rebuild consistency

Files:

- `src/code_index_mcp/services/file_watcher_service.py`
- `src/code_index_mcp/services/project_management_service.py`

This is a critical correctness area.

The watcher should:

- receive the same effective `FileFilter` used by indexing
- use that filter in `DebounceEventHandler`
- pass the same effective rules into rebuild callbacks

The watcher rebuild callback must not call shallow indexing without the active filter rules.

Otherwise startup indexing and watcher-triggered rebuilds will diverge.

### 9. Keep `find_files` behavior aligned through indexing

If `find_files` uses the shallow index, it will naturally inherit filtering behavior
from indexed files.

That is desirable and should be preserved.

Document that changing the filtering config may require reindexing to refresh indexed file lists.

### 10. Add diagnostics and config visibility

Files:

- `src/code_index_mcp/services/settings_service.py`
- `src/code_index_mcp/services/project_management_service.py`
- optionally `src/code_index_mcp/services/system_management_service.py`

Expose fields such as:

- `project_rules_file`
- `project_rules_source_type`
- `project_rules_found`
- `project_rules_valid`
- `effective_include_count`
- `effective_exclude_count`
- `effective_regex_include_count`
- `effective_regex_exclude_count`
- `filter_source_summary`

This makes the feature understandable and debuggable.

## Validation and Error Handling

Recommended behavior:

- missing repo-local file: no error, use existing behavior
- missing CLI-provided file: fail with a clear error
- invalid JSON: fail project initialization with clear message
- invalid schema: fail project initialization with clear message
- invalid regex: fail project initialization with regex and reason
- malformed runtime overrides: preserve current validation approach

Fail-fast is recommended over silently ignoring bad rules.

## Test Plan

### Unit tests for rules loading

Add tests for:

- missing config file
- explicit CLI path resolution
- valid config file
- invalid JSON
- invalid schema
- invalid regex
- path normalization behavior
- precedence between CLI override and repo-local file

### Unit tests for `FileFilter`

Add tests for:

- include-only glob rules
- exclude-only glob rules
- include + exclude precedence
- include regex
- exclude regex
- default excludes still work
- normalized relative path matching works
- hidden/temp file behavior remains correct

### Indexing tests

Extend:

- `tests/indexing/test_index_exclusions.py`

Add tests for:

- config file excludes a directory
- config file includes only a subset of files
- config file regex excludes a subtree
- runtime additional excludes still apply
- shallow and deep indexing both honor effective rules
- CLI-provided config file is used instead of repo-local default

### Search tests

Extend:

- `tests/search/test_search_filters.py`

Add tests for:

- search respects config include rules
- search respects config exclude rules
- external tool strategies still receive glob excludes when possible
- regex excludes are enforced by post-filtering
- CLI-provided config file changes effective filtering behavior

### Service-level tests

Add or extend tests for:

- project initialization loads filtering config
- rebuild uses same effective rules as initialization
- search builds filter from effective config
- watcher receives and reuses effective filter rules
- watcher-triggered rebuilds do not drift from initial indexing
- startup context carries CLI `--filter-config` into project settings resolution

### Diagnostics tests

Add tests for:

- settings info reports filtering config file path
- diagnostics show whether source is CLI or project default
- effective rule counts are exposed
- invalid rules status is visible when relevant

## Documentation Plan

Update `README.md` with:

- config filename and location
- CLI option `--filter-config`
- full schema
- precedence rules
- examples for common use cases
- note that rules affect indexing/search/watcher behavior
- note that reindexing may be required after config changes
- note that regex matches normalized repo-relative paths

Suggested examples:

- only index `src/` and `tests/`
- exclude generated code
- exclude a legacy subtree with regex
- run the executable with `--filter-config ../shared/code-index-rules.json`

## Rollout Plan

### Phase 1: Rules infrastructure

- add filtering rules loader and schema validation
- add effective filter config model
- add config path resolution and CLI override support
- add unit tests for loading and validation

### Phase 2: Filtering engine

- refactor `FileFilter` to support include/exclude glob and regex rules
- add unit tests for matching semantics

### Phase 3: Indexing integration

- wire effective filter config into shallow and deep indexing
- replace flat exclude-list propagation
- add indexing regression tests

### Phase 4: Search integration

- wire search to effective filter config
- preserve post-filter correctness
- add search regression tests

### Phase 5: Watcher integration

- pass effective rules to watcher event filtering
- pass effective rules into watcher-triggered rebuilds
- add regression tests for consistency

### Phase 6: Diagnostics and docs

- expose rules info in settings/config responses
- document config format and precedence
- run full test suite

## Key Risks

- startup indexing honors rules but watcher rebuilds do not
- search post-filter honors rules but backend scans still over-collect before filtering
- flat exclude-list APIs force lossy conversion of include/regex rules
- regex applied to absolute paths becomes confusing
- include rules accidentally hide everything with poor visibility
- CLI override path resolution differs between startup environments unless clearly defined

## Recommended Decisions for V1

- use `.code-index.json`
- add CLI support with `--filter-config`
- support `include`, `exclude`, `include_regex`, `exclude_regex`
- apply rules to normalized repo-relative paths
- keep `exclude` higher priority than `include`
- do not expand supported extensions via include rules in v1
- centralize all rule evaluation through `FileFilter`
- treat CLI config as an override, not a merge source, in v1

## Concrete File Touchpoints

- `src/code_index_mcp/project_settings.py`
- `src/code_index_mcp/utils/file_filter.py`
- `src/code_index_mcp/services/project_management_service.py`
- `src/code_index_mcp/services/index_management_service.py`
- `src/code_index_mcp/services/search_service.py`
- `src/code_index_mcp/services/file_watcher_service.py`
- `src/code_index_mcp/tools/config/project_config_tool.py`
- `src/code_index_mcp/services/settings_service.py`
- `src/code_index_mcp/constants.py`
- `src/code_index_mcp/indexing/json_index_builder.py`
- `src/code_index_mcp/indexing/shallow_index_manager.py`
- likely `src/code_index_mcp/indexing/sqlite_index_manager.py`
- `src/code_index_mcp/server.py`

## Suggested Follow-Up Before Implementation

Confirm this product decision before coding:

- inclusion rules only filter paths already eligible by supported extension list
- they do not expand indexing to arbitrary new file types

That keeps the first implementation smaller and safer.
