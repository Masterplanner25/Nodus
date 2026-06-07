# Nodus Modules And Packaging

Read this for imports, stdlib questions, and companion-library layout.

## Import rules

- Keep imports at the top level of the file.
- Standard library imports use the `std:` prefix.
- Channels are built-in and are not imported.

```nd
import "std:json" as json
import "std:strings" as strings
```

## Common stdlib modules

- `std:json` for parse/stringify
- `std:strings` for split/join/trim/upper/lower
- `std:collections` for map/filter/reduce helpers
- `std:async` for cooperative sleep and async helpers
- `std:hash` for hashes such as SHA-256
- `std:memory` for in-memory key/value state

## Local modules

```text
my-project/
|-- main.nd
`-- .nodus/
    `-- modules/
        `-- my-lib/
            `-- index.nd
```

```nd
import "my-lib" as lib
```

Local `.nodus/modules/` packages take precedence over installed packages with the same name.

## Library exports

- If a module has no `export` declarations, top-level bindings are exported by default.
- If a module has any `export`, only exported names are visible to importers.

```nd
export fn greet(name) {
    return "hi \(name)"
}
```

## Python companion libraries

Companion libraries can expose Nodus modules through Python packaging entry points. When the user asks about library packaging or `pip install` import behavior, also inspect:

- `docs/guide/build-a-library.md`
- the package `pyproject.toml`
- any `get_nd_root()` helper exported by the package

## Debugging imports

```bash
nodus run --trace-imports script.nd
```
