from __future__ import annotations

from pathlib import Path
from typing import Any


EXTENSION_ABI_POLICY_VERSION = "2026-05-29"

SURFACE_MANIFEST = "manifest"
SURFACE_DYNAMIC_NODE = "dynamic-node-registration"
SURFACE_WEBHOOK = "webhook-registration"
SURFACE_FLOW = "flow-registration"
SURFACE_AGENT_TOOL = "agent-tool-registration"
SURFACE_PLANNER_BACKEND = "planner-backend-registration"

STABILITY_STABLE = "stable"
STABILITY_EXPERIMENTAL = "experimental"

MANIFEST_ABI_V1 = "nodus.extension.manifest/v1"
NODE_REGISTRATION_ABI_V1ALPHA1 = "nodus.extension.node-registration/v1alpha1"
WEBHOOK_REGISTRATION_ABI_V1ALPHA1 = "nodus.extension.webhook-registration/v1alpha1"
FLOW_REGISTRATION_ABI_V1ALPHA1 = "nodus.extension.flow-registration/v1alpha1"
AGENT_TOOL_REGISTRATION_ABI_V1ALPHA1 = "nodus.extension.agent-tool-registration/v1alpha1"
PLANNER_BACKEND_REGISTRATION_ABI_V1ALPHA1 = (
    "nodus.extension.planner-backend-registration/v1alpha1"
)

LEGACY_UNVERSIONED_MANIFEST = "legacy-unversioned"
MANIFEST_KIND = "nodus-extension-manifest"

_SURFACE_POLICY: dict[str, dict[str, Any]] = {
    SURFACE_MANIFEST: {
        "stability": STABILITY_STABLE,
        "supported_versions": [MANIFEST_ABI_V1],
        "default_version": MANIFEST_ABI_V1,
        "legacy_accepted": True,
        "notes": (
            "Versioned manifest v1 is the stable manifest ABI. Legacy unversioned "
            "manifests remain accepted for backward compatibility."
        ),
    },
    SURFACE_DYNAMIC_NODE: {
        "stability": STABILITY_EXPERIMENTAL,
        "supported_versions": [NODE_REGISTRATION_ABI_V1ALPHA1],
        "default_version": NODE_REGISTRATION_ABI_V1ALPHA1,
        "legacy_accepted": False,
        "notes": "Dynamic node registration is versioned but still experimental.",
    },
    SURFACE_WEBHOOK: {
        "stability": STABILITY_EXPERIMENTAL,
        "supported_versions": [WEBHOOK_REGISTRATION_ABI_V1ALPHA1],
        "default_version": WEBHOOK_REGISTRATION_ABI_V1ALPHA1,
        "legacy_accepted": False,
        "notes": "Webhook registration is versioned but still experimental.",
    },
    SURFACE_FLOW: {
        "stability": STABILITY_EXPERIMENTAL,
        "supported_versions": [FLOW_REGISTRATION_ABI_V1ALPHA1],
        "default_version": FLOW_REGISTRATION_ABI_V1ALPHA1,
        "legacy_accepted": False,
        "notes": "Flow registration is versioned but still experimental.",
    },
    SURFACE_AGENT_TOOL: {
        "stability": STABILITY_EXPERIMENTAL,
        "supported_versions": [AGENT_TOOL_REGISTRATION_ABI_V1ALPHA1],
        "default_version": AGENT_TOOL_REGISTRATION_ABI_V1ALPHA1,
        "legacy_accepted": False,
        "notes": "Agent tool registration is versioned but still experimental.",
    },
    SURFACE_PLANNER_BACKEND: {
        "stability": STABILITY_EXPERIMENTAL,
        "supported_versions": [PLANNER_BACKEND_REGISTRATION_ABI_V1ALPHA1],
        "default_version": PLANNER_BACKEND_REGISTRATION_ABI_V1ALPHA1,
        "legacy_accepted": False,
        "notes": "Planner backend registration is versioned but still experimental.",
    },
}


def extension_abi_policy() -> dict[str, Any]:
    return {
        "schema_version": EXTENSION_ABI_POLICY_VERSION,
        "surfaces": {
            surface: {
                "stability": metadata["stability"],
                "supported_versions": list(metadata["supported_versions"]),
                "default_version": metadata["default_version"],
                "legacy_accepted": bool(metadata["legacy_accepted"]),
                "notes": metadata["notes"],
            }
            for surface, metadata in _SURFACE_POLICY.items()
        },
    }


def extension_surface_stability(surface: str) -> str:
    return str(_SURFACE_POLICY[surface]["stability"])


def extension_surface_default_version(surface: str) -> str:
    return str(_SURFACE_POLICY[surface]["default_version"])


def validate_extension_abi_version(
    surface: str,
    abi_version: str | None,
    *,
    allow_legacy: bool = False,
) -> str:
    if surface not in _SURFACE_POLICY:
        raise ValueError(f"unknown extension ABI surface {surface!r}")
    policy = _SURFACE_POLICY[surface]
    if abi_version is None or not str(abi_version).strip():
        if allow_legacy and policy["legacy_accepted"]:
            return LEGACY_UNVERSIONED_MANIFEST
        raise ValueError(
            f"{surface} requires an explicit abi_version in {policy['supported_versions']}"
        )
    cleaned = str(abi_version).strip()
    if cleaned not in policy["supported_versions"]:
        raise ValueError(
            f"Unsupported abi_version {cleaned!r} for {surface}. "
            f"Supported versions: {policy['supported_versions']}"
        )
    return cleaned


def manifest_effective_abi_version(data: dict[str, Any]) -> str:
    return validate_extension_abi_version(
        SURFACE_MANIFEST,
        data.get("abi_version"),
        allow_legacy=True,
    )


def validate_extension_manifest_document(
    data: dict[str, Any],
    *,
    path: str | Path | None = None,
) -> str:
    if not isinstance(data, dict):
        raise ValueError(f"Plugin manifest at {path or '<memory>'} must be a JSON object")

    from .models import LegacyManifest, VersionedManifestV1

    effective_version = manifest_effective_abi_version(data)
    if effective_version == LEGACY_UNVERSIONED_MANIFEST:
        manifest = LegacyManifest.model_validate(data)
        if not isinstance(manifest.plugins, list) and not isinstance(manifest.profiles, dict):
            raise ValueError(
                f"Plugin manifest at {path or '<memory>'} must declare either top-level "
                "'plugins' or 'profiles'"
            )
        return effective_version

    manifest = VersionedManifestV1.model_validate(data)
    if manifest.kind != MANIFEST_KIND:
        raise ValueError(
            f"Plugin manifest at {path or '<memory>'} must declare kind={MANIFEST_KIND!r}"
        )
    validate_extension_abi_version(SURFACE_MANIFEST, manifest.abi_version)
    return manifest.abi_version
