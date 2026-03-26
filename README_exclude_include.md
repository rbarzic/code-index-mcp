# Include/Exclude Filtering

This project supports a filtering configuration that controls which files are
considered during indexing, search, file discovery, and file watcher rebuilds.

## Ways To Provide The Config

- repo-local auto-discovery with `.code-index.json` at the project root
- explicit CLI override with `--filter-config path/to/rules.json`
- optional storage isolation with `--profile <name>`

If `--filter-config` is provided, it overrides repo-local auto-discovery.

If `--profile` is provided, on-disk indexes and settings are isolated even when
the project path is the same.

## Example

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

## Rule Types

- `include`: glob patterns matched against normalized repo-relative paths
- `exclude`: glob patterns matched against normalized repo-relative paths
- `include_regex`: regex patterns matched against normalized repo-relative paths
- `exclude_regex`: regex patterns matched against normalized repo-relative paths

Paths are normalized to use `/` separators before matching.

## Matching Behavior

The filtering logic applies in this order:

1. supported file extensions are checked first
2. built-in default excludes are applied
3. if include rules exist, a file must match at least one include rule
4. if an exclude rule matches, the file is rejected

`exclude` always wins over `include`.

## CLI Usage

Use the project-local file:

```bash
code-index-mcp --project-path /path/to/project
```

Use an explicit shared config file:

```bash
code-index-mcp --project-path /path/to/project --filter-config /path/to/rules.json
```

Use two isolated profiles for the same repository:

```bash
code-index-mcp --project-path /soc/repo --profile codebase-a --filter-config /configs/a.json
code-index-mcp --project-path /soc/repo --profile codebase-b --filter-config /configs/b.json
```

This prevents the two instances from reusing the same shallow/deep index files.

## Diagnostics

Filtering metadata is exposed through project/settings responses and includes:

- the resolved config path
- whether the config was found
- whether it came from CLI override or project default
- include/exclude rule counts
- the active profile

There is also a dedicated tool that returns the resolved effective filtering
configuration:

- `get_filtering_config`

This includes the active source, include/exclude rules, runtime additional
exclude patterns, and supported extensions.

## File Watcher Reload Behavior

When file watching is enabled, changes to the active filtering config file also
trigger a rebuild.

This means:

- editing `.code-index.json` causes the watcher to refresh the index
- the watcher reloads the filtering rules after the rebuild
- subsequent file events use the updated include/exclude logic

## Notes

- If no config file is present, current default behavior is preserved.
- Invalid JSON or invalid regex patterns fail fast during config loading.
- Changing filtering rules may require a reindex to fully refresh indexed file lists.
- Include rules do not expand supported file extensions in the current implementation.
