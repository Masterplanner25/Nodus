"""Contracts phase: verify HandlerContract infrastructure is wired correctly."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContractsFinding:
    message: str
    detail: str = ""


@dataclass
class ContractsResult:
    findings: list[ContractsFinding] = field(default_factory=list)
    checks_run: int = 0

    @property
    def passed(self) -> int:
        return self.checks_run - len(self.findings)


def run_contracts_phase(root: str) -> ContractsResult:
    """Smoke-test the HandlerContract infrastructure."""
    src = str(Path(root) / "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    result = ContractsResult()

    # Check 1: HandlerContract is importable from nodus_lang_schema
    # (in-tree ABI contracts package; renamed from nodus_schema in NAME-COL-001
    # so it no longer collides with the standalone nodus-schema PyPI package).
    result.checks_run += 1
    try:
        from nodus_lang_schema import HandlerContract, VALID_EFFECTS
    except ImportError as exc:
        result.findings.append(ContractsFinding(
            message="HandlerContract not importable from nodus_lang_schema",
            detail=str(exc),
        ))
        return result  # Can't run further checks without the type

    # Check 2: Valid contract passes validation
    result.checks_run += 1
    c = HandlerContract(name="test.action", description="a test handler")
    errors = c.validate()
    if errors:
        result.findings.append(ContractsFinding(
            message="Valid HandlerContract failed validate()",
            detail="; ".join(errors),
        ))

    # Check 3: Missing dot in name is caught
    result.checks_run += 1
    c_bad = HandlerContract(name="nodot", description="bad name")
    if not c_bad.validate():
        result.findings.append(ContractsFinding(
            message="HandlerContract.validate() should reject names without a dot",
        ))

    # Check 4: Unknown effect is caught
    result.checks_run += 1
    c_bad_fx = HandlerContract(name="test.action", description="d", effects=["unknown_fx"])
    if not c_bad_fx.validate():
        result.findings.append(ContractsFinding(
            message="HandlerContract.validate() should reject unknown effects",
        ))

    # Check 5: pure + other effect is caught
    result.checks_run += 1
    c_mixed = HandlerContract(name="test.action", description="d", effects=["pure", "network"])
    if not c_mixed.validate():
        result.findings.append(ContractsFinding(
            message="HandlerContract.validate() should reject pure combined with other effects",
        ))

    # Check 6: VALID_EFFECTS has the expected vocabulary
    result.checks_run += 1
    expected = {"pure", "reads_state", "writes_state", "network", "filesystem", "spawns_task"}
    if set(VALID_EFFECTS) != expected:
        result.findings.append(ContractsFinding(
            message="VALID_EFFECTS vocabulary mismatch",
            detail=f"got {sorted(VALID_EFFECTS)!r}, expected {sorted(expected)!r}",
        ))

    return result
