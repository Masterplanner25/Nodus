Start or continue work on a nodus-memory phase.

⚠️ **IMPORTANT: Two nodus-memory implementations exist.**
Read this before doing anything.

Arguments: $ARGUMENTS

## Which nodus-memory are you working on?

### Option A — Original nodus-lang adapter (on GitHub, NO local copy)

The Phase A–K implementation (192 tests, nodus-lang dep, Pydantic-backed,
`src/nodus_memory/` layout, hatchling) lives at:
- GitHub: `github.com/Masterplanner25/nodus-memory` (git history intact)
- **NOT at `C:\dev\nodus-memory`** — that path was replaced by Option B

If you need to work on the original: clone it to a new path first:
```powershell
git clone https://github.com/Masterplanner25/nodus-memory C:\dev\nodus-memory-v1
```

v0.2 work for this version (pgvector, NLTK, embedding providers, adaptive weights)
would follow Phase 0 decisions using `docs/design/05-deferred.md` as the seed.

### Option B — Tier 2 full memory library (current local copy at C:\dev\nodus-memory)

The replacement implementation (28 tests, `nodus-events>=0.1.0` dep, flat layout):
- Path: `C:\dev\nodus-memory`
- GitHub: `github.com/Masterplanner25/nodus-memory` (latest commit)
- Package: `nodus_memory` (flat `nodus_memory/` dir, setuptools)
- Python: `>=3.11`, shared venv at `C:\dev\Coding Language\.venv`

**Modules:** `models.py`, `store.py`, `address.py`, `scoring.py`, `embedding.py`, `search.py`

**Key abstractions:**
- `MemoryNode` — core data model
- `InMemoryStore` — in-memory backend
- MAS `build_path()`/`glob_match()` — address space
- `score_nodes()`, `update_feedback()` — scoring and feedback
- `recall()`/`recall_async()` — retrieval
- `EmbeddingProvider` — protocol for vector embedding backends

## Pre-flight (Option B)

Before any work on the local Tier 2 version:

1. Run tests to confirm baseline is green:
   ```powershell
   cd C:\dev\nodus-memory
   "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
   ```
   Expected: 28 passed

2. Confirm `nodus-events` is installed:
   ```powershell
   "C:/dev/Coding Language/.venv/Scripts/python.exe" -c "import nodus_events; print(nodus_events.__file__)"
   ```

3. Install if needed: `pip install -e C:\dev\nodus-events --no-deps`

## Dev environment (Option B)

```powershell
# Run tests
cd C:\dev\nodus-memory
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Install dev mode
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pip install -e . --no-deps
```

## Commit format

```powershell
git commit -m @'
feat: description

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```
