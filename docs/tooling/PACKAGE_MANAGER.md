# Package Manager

Nodus includes a minimal, local-first package manager intended for small automation projects.

## Project Files

- `nodus.toml` manifest
- `nodus.lock` lockfile
- `deps/` installed dependencies

## Manifest Format

```toml
name = "example"
version = "0.1.0"

[dependencies]
utils = "git+https://github.com/user/utils.nodus"
```

Supported sources:
- `git+<url>` (cloned into `deps/<name>`)

## Commands

- `nodus init` initializes `nodus.toml` and `deps/`
- `nodus install` installs dependencies from the manifest
- `nodus deps` lists resolved dependencies and lockfile status

## Lockfile
`nodus.lock` records resolved dependency revisions as `spec@commit`.

Example:

```toml
utils = "git+https://github.com/user/utils.nodus@<commit>"
```

## Import Resolution
Dependencies are imported using the `package:module` syntax:

```nd
import "utils:strings"
```

This resolves to `deps/utils/strings.nd`.

## Notes
- The package manager is intentionally minimal and does not implement a registry or semver resolution yet.
- Dependency installation is destructive for existing `deps/<name>` directories (they are removed and re-cloned).
