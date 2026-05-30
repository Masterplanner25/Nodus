Start or continue a nodus-memory Phase 0 decisions doc, Phase 1 design doc, or
Phase A-Z implementation phase. Walks through the phase in order, checking
existing design docs before writing or implementing anything.

Arguments: $ARGUMENTS
(Pass "phase0" for v0.2 decisions, "phase1" for next design doc,
or a phase letter like "A", "B" to implement that phase. If omitted,
determine from context.)

## Repository

- Path: `C:\dev\nodus-memory`
- GitHub: `github.com/Masterplanner25/nodus-memory`
- Package: `nodus_memory` (src layout, hatchling)
- Python: `>=3.11`, shared venv at `C:\dev\Coding Language\.venv`

## Pre-flight checks

Before any work:

1. Read `C:\dev\nodus-memory\docs\design\00-decisions.md` — confirm D1-D10 are settled.
2. Read existing design docs in `C:\dev\nodus-memory\docs\design\` — understand
   what's already designed vs what's new in v0.2.
3. For v0.2 work: read `05-deferred.md` — this is the planning seed; each DD becomes
   a design decision or implementation phase.
4. Run tests to confirm baseline is green:
   ```powershell
   cd C:\dev\nodus-memory
   PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
   ```
   Expected: 192 passed (v0.1.0 baseline).

## v0.1.0 completed phases (do not re-implement)

- A — Package skeleton, MemoryConfig, error hierarchy
- B — MemoryNode frozen dataclass + MAS address space
- C — MemoryBackend ABC, InMemoryBackend, MemoryStore tenant enforcement
- D — Tag-based + path-prefix retrieval
- E — ScoreTracker, record_feedback, sort_by weight
- F — Causal chain: link(), recall_chain(), cycle detection
- G — SQLAlchemyBackend (optional [db] extra)
- H — EmbeddingProvider ABC, NoOpProvider, cosine_similarity, recall_similar stub
- I — Nodus language bindings: attach_to_runtime, nm_* host functions, index.nd
- J — CLI (python -m nodus_memory)
- K — Invariants + integration + packaging

## v0.2 deferred features (from 05-deferred.md)

| DD | Feature | Status | Notes |
|----|---------|--------|-------|
| DD-1 | pgvector / Production Vector Search | Not started | Needs PostgreSQL + embedding provider |
| DD-2 | NLTK Text Preprocessing | Not started | 50MB corpus download |
| DD-3 | Rust Native Scorer | **COMPLETE** | Done as nodus-native-memory-engine v0.1.0 at `C:\dev\nodus-native-memory-engine`. Auto-detected. |
| DD-4 | Embedding Provider Integrations | Not started | OpenAI, Cohere, SentenceTransformer |
| DD-5 | Memory Feedback Learning Loop | Not started | Bayesian weight updates, decay |
| DD-6 | Multi-Namespace Cross-Agent Sharing | Blocked | Needs nodus-events library first |

**DD-3 is already done** — nodus-native-memory-engine v0.1.0 provides the Rust scorer.
When implementing v0.2, update `05-deferred.md` to reflect this.

## v0.2 proposed phase sequence (Phase 0 must confirm these)

```
Phase 0: Lock v0.2 decisions (D11+): embedding provider contract, pgvector schema,
         async pipeline design, NLTK opt-in mechanism
Phase 1: Design docs — pgvector backend, embedding pipeline, provider integrations
Phase A: PgVectorBackend (extends SQLAlchemyBackend, vector(1536) column, IVFFlat)
Phase B: OpenAIEmbeddingProvider + AsyncEmbeddingProvider ABC
Phase C: Async embedding pipeline (queue + background worker)
Phase D: CohereEmbeddingProvider + SentenceTransformerProvider
Phase E: recall_similar() wired to pgvector ANN query (replaces pure-Python stub)
Phase F: NLTK TextPreprocessor (opt-in via MemoryConfig)
Phase G: Memory feedback learning loop (Bayesian impact_score updates, decay)
Phase H: Invariants + integration + packaging for v0.2
```

## Key existing surfaces (do not break)

- `MemoryBackend` ABC — all backends must implement all abstract methods
- `EmbeddingProvider` ABC — `embed(text) → list[float]`, `dimensions` property
- `cosine_similarity()` in `embedding.py` — routes to nodus-native-memory-engine if installed
- `ScoreTracker.compute_weight()` — routes to nodus-native-memory-engine if installed
- `attach_to_runtime(runtime, store)` — registers `nm_*` host functions
- `nm_*` prefix for host functions (not `ext_*`) — `nm_recall_from`, `nm_share`, etc.
- `recall_from()` and `share()` in index.nd use explicit `return` — required for Nodus

## Dev environment

```powershell
# Run tests
cd C:\dev\nodus-memory
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage gate: 80%
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=nodus_memory --cov-fail-under=80 -q

# Install dev mode (hatchling, --no-deps to skip nodus-lang 4.0 PyPI check)
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pip install -e . --no-deps

# Verify nodus.nd entry-point
python -c "import importlib.metadata as m; print([e for e in m.entry_points(group='nodus.nd') if e.name=='nodus-memory'])"
```

## Commit format

```powershell
git commit -m @'
feat(phaseX): description

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

Push to `github.com/Masterplanner25/nodus-memory` after each phase.
