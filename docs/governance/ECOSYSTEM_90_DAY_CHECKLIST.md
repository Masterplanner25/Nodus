<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Ecosystem 90-Day Pre-Launch Checklist

**Status:** Working document — to be executed before the coordinated three-artifact launch
**Maintainer:** Shawn Knight (Masterplanner25)

This checklist defines what must be done before the coordinated launch of
nodus-lang 4.0.0, nodus-mcp 0.1.0, and nodus-a2a 0.1.0 is credible.
It is sequenced: earlier items unblock later ones.

---

## Block 1: nodus-lang 4.0.0 completion

- [ ] All v4.0 cycle phases complete (verify `V4_0_PLAN.md`)
- [ ] All v4.0 stdlib modules implemented: `std:http`, `std:env`, `std:time`, `std:hash`,
      `std:encoding`, `std:secrets`, `std:subprocess`, `std:test`, `std:tool`
- [ ] String interpolation implemented (design doc 05)
- [ ] All v4.0 eval bugs resolved or deferred with rationale
- [ ] Eval score ≥ 8.0/10 (or documented rationale for shipping below target)
- [ ] Test suite: all tests pass, coverage ≥ 60%
- [ ] Ruff lint: no new violations
- [ ] Doc-vs-code gate: passes `--all`
- [ ] Version sync: `version.py` and `pyproject.toml` both say `4.0.0`
- [ ] CHANGELOG.md has complete v4.0 section
- [ ] `docs/migration/v3-to-v4.md` is complete and accurate
- [ ] `LANGUAGE_STABILITY_INDEX.md` updated to reflect v4.0 surface changes

---

## Block 2: nodus-mcp 0.1.0 readiness

- [ ] All 280+ tests pass against nodus-lang 4.0.0 source
- [ ] Spec verification pass: confirm implementation matches 2026-07-28 RC (or final spec)
- [ ] README accurately describes limitations (OAuth, SSE, HTTP push)
- [ ] `docs/governance/TECH_DEBT.md` is current (TD-001 through TD-010 verified)
- [ ] CHANGELOG.md records MCP spec version history accurately
- [ ] `pyproject.toml` `nodus-lang>=4.0.0` dependency correct
- [ ] Entry-point contract verified: `import "nodus-mcp"` works in a Nodus script
- [ ] Authentication warning is in the first screen of README

---

## Block 3: nodus-a2a 0.1.0 readiness

- [ ] All 169+ tests pass against nodus-lang 4.0.0 source
- [ ] Coverage ≥ 80% (gate is configured)
- [ ] A2A 1.0.0 wire format verified (Content-Type, A2A-Version header, well-known URI)
- [ ] `inversion-note` standing assertion passes
- [ ] Production auth warning is prominent in README (first screen)
- [ ] `docs/governance/TECH_DEBT.md` created with known limitations
- [ ] `pyproject.toml` metadata complete (authors, license, classifiers, description)
- [ ] `pyproject.toml` `nodus-lang>=4.0.0` dependency correct
- [ ] D6 inversion documented in a permanent location (currently `05-deferred-features.md §2`)

---

## Block 4: Docset readiness for launch

- [ ] `README.md` JSON-LD version updated to 4.0.0
- [ ] `LIBRARY_ECOSYSTEM.md` Tier 3 entries reflect v0.1 actual scope (done in 3.0.2 sweep)
- [ ] `STDLIB_PHILOSOPHY.md` created or references removed from `LIBRARY_ECOSYSTEM.md`
- [ ] `LANGUAGE_STABILITY_INDEX.md` updated for v4.0 surfaces
- [ ] `ECOSYSTEM_READINESS_ASSESSMENT.md` updated post-launch to reflect published status
- [ ] All new v4.0 guide docs written and tested against dev source
- [ ] `docs/release.md` is current

---

## Block 5: Publication sequence

Execute in this order to ensure no artifact is published against an unpublished dependency:

1. Build nodus-lang 4.0.0 wheel from the tagged commit
2. Install the wheel in a clean virtualenv
3. Run closed-issue regression tests against the installed wheel
4. Publish nodus-lang 4.0.0 to PyPI
5. Wait for PyPI to confirm availability (pip install nodus-lang==4.0.0 succeeds)
6. Build nodus-mcp 0.1.0 distribution using the published nodus-lang 4.0.0
7. Publish nodus-mcp 0.1.0 to registry
8. Build nodus-a2a 0.1.0 distribution using the published nodus-lang 4.0.0
9. Publish nodus-a2a 0.1.0 to registry
10. Create GitHub releases for all three artifacts
11. Update `ECOSYSTEM_READINESS_ASSESSMENT.md` to reflect published status

---

## Block 6: Post-launch (first 30 days)

- [ ] Monitor for installation issues (pip resolution, dependency conflicts)
- [ ] Monitor for protocol compatibility issues (MCP spec changes, A2A deployment issues)
- [ ] File GitHub issues for any bugs reported against v0.1 of companion libraries
- [ ] Update `ECOSYSTEM_READINESS_ASSESSMENT.md` with first real-world usage data
- [ ] Begin v0.2 design: OAuth for nodus-mcp, Task lifecycle for nodus-a2a

---

## Gate for claiming "production-credible"

The ecosystem cannot be called production-credible until:
- At least one companion library is used in a real system under real load
- Operational procedures (monitoring, upgrade, failure handling) are exercised
- At least one bug report has been received, triaged, and resolved in a patch release

This typically takes 30-90 days post-launch for a v0.1 library with a small early-adopter
community.
