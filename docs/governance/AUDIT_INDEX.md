# Audit Prompt Index

Reusable evaluation prompts for auditing a language runtime. Each prompt is
language-agnostic — applicable to any compiled, embeddable runtime — but
written with the specific concerns of production language runtimes in mind.

Run these periodically (pre-release, post-major-refactor, or when onboarding
a new contributor who will evaluate the system from the outside).

## The six audits

| Prompt | What it answers |
|--------|----------------|
| [AUDIT_ARCHITECTURE.md](AUDIT_ARCHITECTURE.md) | Does the end-to-end pipeline work correctly and are the layer boundaries real? |
| [AUDIT_RUNTIME_READINESS.md](AUDIT_RUNTIME_READINESS.md) | Is this a complete, self-sufficient runtime? Includes bootstrap readiness stage. |
| [AUDIT_BOUNDARY_INTEGRITY.md](AUDIT_BOUNDARY_INTEGRITY.md) | Is the core contaminated with domain/product logic that belongs in the application layer? |
| [AUDIT_USER_REALITY.md](AUDIT_USER_REALITY.md) | What can the three user types actually do today, and where do they hit the first blocker? |
| [AUDIT_CAPABILITY.md](AUDIT_CAPABILITY.md) | What class of system is this, scored across five axes including bootstrap readiness? |
| [AUDIT_LIMITS.md](AUDIT_LIMITS.md) | Where does the runtime stop being useful, and what is the single highest-leverage extension? |
| [AUDIT_SECURITY_MODEL.md](AUDIT_SECURITY_MODEL.md) | Where does security enforcement live, is it consistent, and what are the gaps? |

## When to run each

| Trigger | Audits to run |
|---------|--------------|
| Pre-release | Architecture, Runtime Readiness, Security Model |
| Post-major-refactor | Boundary Integrity, Architecture |
| Evaluating adoption readiness | User Reality, Capability, Limits |
| Bootstrap milestone planning | Runtime Readiness (§Bootstrap), Capability (Axis 5) |
| Security incident or report | Security Model, Architecture (§Embedding API, §Failure Handling) |

## Stored results

Completed audit results live in `docs/evals/` alongside the creator validation
and independent eval results. Name them: `docs/evals/vX.Y.Z/AUDIT_<NAME>.md`.

## Bootstrap readiness

Two audits track the bootstrap milestone independently:

- **AUDIT_RUNTIME_READINESS.md** §Bootstrap Readiness — stage classification
  (Stage 0–5) and gap analysis for the next stage
- **AUDIT_CAPABILITY.md** Axis 5 — single-score summary for the capability profile

Both must be updated when a new language feature changes the bootstrap stage.
