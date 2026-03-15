# Package Manager

Nodus includes a minimal, local-first package manager intended for small automation projects.

## Project Files

- `nodus.toml` manifest
- `nodus.lock` lockfile
- `.nodus/modules/` installed dependencies
- `src/main.nd` default project entrypoint

## Manifest Format

```toml
[package]
name = "example"
version = "0.1.0"

[dependencies]
utils = "1.0.0"
```

Supported sources:
- version requirements resolved from a registry (local or remote HTTP)
- `{ path = "./relative/path" }` for local dependencies

### Semver constraint syntax

| Constraint | Meaning |
|---|---|
| `"^1.0.0"` | Compatible: `>=1.0.0, <2.0.0` |
| `"~1.0.0"` | Patch-level: `>=1.0.0, <1.1.0` |
| `"1.0.0"` | Exact version only |
| `">=1.0.0"` | Minimum version (no upper bound) |

Example manifest with constraints:

```toml
[package]
name = "myapp"
version = "0.1.0"

[dependencies]
mypackage = "^1.0.0"
otherlib  = "~2.1.0"
exactpkg  = "1.0.0"
locallib  = { path = "../locallib" }
```

Resolution is tooling-only. Runtime execution never contacts the network.

## Commands

- `nodus init` initializes `nodus.toml`, `src/main.nd`, and `.nodus/modules/`
- `nodus install` installs dependencies from the manifest
- `nodus install --registry <url>` installs using the specified HTTP registry URL
- `nodus add <package> "<constraint>"` adds a registry dependency to `nodus.toml` (e.g. `nodus add mypackage "^1.0.0"`), installs it, and updates `nodus.lock`
- `nodus add <package> --path <rel-path>` adds a local path dependency
- `nodus remove <package>` removes a dependency from `nodus.toml`, prunes the local install, and updates `nodus.lock`
- `nodus package-list` lists resolved dependencies and lockfile status
- `nodus login [--registry <url>]` stores a registry token interactively in `~/.nodus/config.toml`
- `nodus logout [--registry <url>]` removes a stored registry token
- `nodus publish [--registry <url>] [--registry-token <token>]` publishes the current project to a registry

`nodus deps` is reserved for the runtime module dependency graph used by incremental compilation.

## Lockfile
`nodus.lock` records the resolved dependency set in a deterministic array-of-tables format.

Example:

```toml
[[package]]
name = "json"
version = "1.2.0"
source = "registry"
hash = "sha256:abc123..."

[[package]]
name = "workflow_utils"
version = "0.1.0"
source = "path"
path = "../workflow_utils"
hash = "sha256:def456..."
```

Entries are sorted by package name so repeated installs produce stable output.

## Install Layout

Installed dependencies are copied into:

```text
.nodus/
  modules/
    json/
      module.nd
    workflow_utils/
      module.nd
```

Resolution and installation order is:

1. read `nodus.toml`
2. resolve the dependency graph
3. populate `.nodus/modules/`
4. write `nodus.lock`

## Import Resolution
Dependencies are imported using the `package:module` syntax:

```nd
import "utils:strings"
```

This resolves to `.nodus/modules/utils/strings.nd`.

## Registry Installation

Version dependencies (e.g. `utils = "^1.0.0"`) can be resolved and installed from an HTTP registry.

### Configuration priority

1. `--registry <url>` CLI flag (wired to `nodus install` as of v0.9.0)
2. `NODUS_REGISTRY_URL` environment variable
3. `registry_url` field in `[package]` section of `nodus.toml`
4. If none set: falls back to the local `.nodus/registry.toml`

### nodus.toml with registry URL

```toml
[package]
name = "myapp"
version = "0.1.0"
registry_url = "https://registry.example.com"

[dependencies]
utils = "^1.0.0"
```

### Registry protocol

The registry must serve JSON at `GET {registry_url}/packages/{name}`:

```json
{
  "name": "utils",
  "versions": [
    {
      "version": "1.0.0",
      "url": "https://registry.example.com/dist/utils-1.0.0.tar.gz",
      "sha256": "abcdef..."
    }
  ]
}
```

Archives may be `.tar.gz`, `.tgz`, or `.zip`. A leading top-level directory inside the archive is automatically stripped.

SHA-256 of the downloaded archive is verified before extraction. The lockfile records `source = "registry"`.

### Lockfile output for registry deps

```toml
[[package]]
name = "utils"
version = "1.0.0"
source = "registry"
url = "https://registry.example.com/dist/utils-1.0.0.tar.gz"
hash = "sha256:..."
path = ".nodus/modules/utils"
```

### Error handling

- `RegistryError` is raised on network failures, HTTP errors, or checksum mismatches.
- On version constraint mismatch, the error message lists all available versions returned by the registry.
- Checksum verification happens before extraction; a mismatch aborts install and raises `RegistryError`.

## Registry Protocol

### Fetch endpoint (existing)

```
GET {registry_url}/packages/{name}
```

Response:
```json
{
  "name": "pkg-name",
  "versions": [
    {"version": "1.0.0", "url": "https://...", "sha256": "abc..."}
  ]
}
```

### Publish endpoint (v0.9)

```
POST {registry_url}/packages/{name}/{version}
Headers:
  Authorization: Bearer <token>
  Content-Type: application/octet-stream
  X-SHA256: <hex digest of archive>
Body: raw .tar.gz archive bytes
```

**Success response — 201 Created:**
```json
{"name": "pkg-name", "version": "1.0.0", "url": "https://.../pkg-1.0.0.tar.gz"}
```

**Error responses:**
- `400 Bad Request` — invalid manifest or malformed archive
- `401 Unauthorized` — missing or invalid token
- `403 Forbidden` — token does not have publish permission
- `409 Conflict` — version already exists (cannot overwrite published versions)
- `422 Unprocessable` — archive does not match declared metadata

## Authentication

Package registries may require authentication to fetch private packages or to publish. Nodus
uses Bearer token authentication.

### Token resolution order

When making authenticated registry requests, Nodus resolves a token using this priority:

1. `--registry-token <token>` CLI flag (highest priority)
2. `NODUS_REGISTRY_TOKEN` environment variable
3. `~/.nodus/config.toml` — user-level config file
4. No token (unauthenticated request)

### Environment variable

```
export NODUS_REGISTRY_TOKEN="your-token-here"
nodus install
```

### User-level config file

Run `nodus login` to store a token interactively:

```
nodus login                              # store global default token
nodus login --registry https://reg.example.com  # store per-registry token
```

This writes to `~/.nodus/config.toml`. Run `nodus logout` to remove:

```
nodus logout
nodus logout --registry https://reg.example.com
```

### Config file format

`~/.nodus/config.toml`:

```toml
[registry]
token = "global-default-token"

[registry."https://specific-registry.com"]
token = "registry-specific-token"
```

**Security:** `~/.nodus/config.toml` contains credentials. Do not commit it to version
control. Add `~/.nodus/` to your global `.gitignore`.

### NODUS_SERVER_TOKEN vs NODUS_REGISTRY_TOKEN

These are two separate tokens for two separate concerns:

- `NODUS_SERVER_TOKEN` — authenticates requests to a running **Nodus server** process
  (`nodus serve`, `nodus snapshot`, `nodus worker`). Set on the server to require auth.
- `NODUS_REGISTRY_TOKEN` — authenticates requests to a **package registry**
  (`nodus install`, `nodus publish`). Set by the package author/consumer.

They are independent: you can use a registry token without running a server, and vice versa.

## Publish Workflow

To publish your package to a registry:

1. Ensure `nodus.toml` has a `[package]` section with `name` and `version`.
2. Authenticate: `nodus login --registry https://your-registry.example.com`
3. Publish: `nodus publish --registry https://your-registry.example.com`

Or set the registry URL in `nodus.toml` and just run:

```bash
nodus login
nodus publish
```

Example `nodus.toml` with registry URL:

```toml
[package]
name = "mypackage"
version = "1.0.0"
registry_url = "https://your-registry.example.com"
```

Published versions are immutable — the registry returns 409 Conflict if you attempt
to publish a version that already exists. Increment the version in `nodus.toml` for
each publish.

## Archive Exclusions

When `nodus publish` creates a `.tar.gz` archive, the following paths are excluded:

| Pattern | Reason |
|---|---|
| `.nodus/` | Build artifacts and local install cache |
| `__pycache__/` | Python bytecode cache |
| `.git/` | Version control history |
| `*.pyc` / `*.pyo` | Compiled Python files |
| `nodus.lock` | Lockfile (recipients resolve their own) |
| `.gitignore` | VCS metadata |
| `.github/` | CI/CD configuration |

The archive root is named `{name}-{version}/` so extraction strips the prefix correctly.

**Planned:** `.ndignore` support — a `.ndignore` file in the project root will give
package authors fine-grained control over what is included. Target: post-v0.9.

## Notes
- The package manager is local-first and keeps runtime execution separate from manifest parsing and dependency resolution.
- Legacy manifests that place `name` and `version` at the top level still load, but new projects should use `[package]`.
- Module resolution checks project modules first, then `.nodus/modules`, then stdlib.
- Published versions are immutable. The registry returns 409 Conflict if you attempt to publish an existing version. Use a new version number in `nodus.toml` for each publish.
