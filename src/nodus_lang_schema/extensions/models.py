from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _policy():
    from .policy import (
        SURFACE_DYNAMIC_NODE,
        SURFACE_FLOW,
        SURFACE_WEBHOOK,
        validate_extension_abi_version,
    )

    return {
        "SURFACE_DYNAMIC_NODE": SURFACE_DYNAMIC_NODE,
        "SURFACE_FLOW": SURFACE_FLOW,
        "SURFACE_WEBHOOK": SURFACE_WEBHOOK,
        "validate_extension_abi_version": validate_extension_abi_version,
    }


class ManifestPluginEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str = Field(..., min_length=1)
    owner_class: str | None = None
    provenance: dict[str, Any] | None = None


class ManifestDeclarativeNodeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field("dynamic-node")
    abi_version: str = Field("nodus.extension.node-registration/v1alpha1")
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    handler: str = Field(..., min_length=1)
    artifact_path: str | None = None
    timeout_seconds: int = Field(10, ge=1, le=30)
    secret: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    owner_class: str = Field(..., min_length=1)
    provenance: dict[str, Any] | None = None
    overwrite: bool = False

    @model_validator(mode="after")
    def _validate_entry(self) -> "ManifestDeclarativeNodeEntry":
        policy = _policy()
        if self.kind != "dynamic-node":
            raise ValueError("manifest declarative node entry must declare kind='dynamic-node'")
        self.abi_version = policy["validate_extension_abi_version"](
            policy["SURFACE_DYNAMIC_NODE"], self.abi_version
        )
        return self


class ManifestDeclarativeWebhookEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field("webhook-subscription")
    abi_version: str = Field("nodus.extension.webhook-registration/v1alpha1")
    event_type: str = Field(..., min_length=1)
    callback_url: str = Field(..., min_length=1)
    secret: str | None = None
    owner_class: str = Field(..., min_length=1)
    provenance: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_entry(self) -> "ManifestDeclarativeWebhookEntry":
        policy = _policy()
        if self.kind != "webhook-subscription":
            raise ValueError(
                "manifest declarative webhook entry must declare kind='webhook-subscription'"
            )
        self.abi_version = policy["validate_extension_abi_version"](
            policy["SURFACE_WEBHOOK"], self.abi_version
        )
        return self


class ManifestDeclarativeFlowEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field("dynamic-flow")
    abi_version: str = Field("nodus.extension.flow-registration/v1alpha1")
    name: str = Field(..., min_length=1)
    nodes: list[str] = Field(..., min_length=1)
    edges: dict[str, list[str]] = Field(default_factory=dict)
    start: str = Field(..., min_length=1)
    end: list[str] = Field(..., min_length=1)
    owner_class: str = Field(..., min_length=1)
    provenance: dict[str, Any] | None = None
    overwrite: bool = False

    @model_validator(mode="after")
    def _validate_entry(self) -> "ManifestDeclarativeFlowEntry":
        policy = _policy()
        if self.kind != "dynamic-flow":
            raise ValueError("manifest declarative flow entry must declare kind='dynamic-flow'")
        self.abi_version = policy["validate_extension_abi_version"](
            policy["SURFACE_FLOW"], self.abi_version
        )
        return self


class ManifestProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugins: list[str | ManifestPluginEntry] = Field(default_factory=list)
    extensions: list[
        ManifestDeclarativeNodeEntry
        | ManifestDeclarativeWebhookEntry
        | ManifestDeclarativeFlowEntry
    ] = Field(default_factory=list)


class VersionedManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(...)
    abi_version: str = Field(...)
    default_profile: str | None = None
    profiles: dict[str, ManifestProfile] = Field(..., min_length=1)


class LegacyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_profile: str | None = None
    profiles: dict[str, ManifestProfile] | None = None
    plugins: list[str | ManifestPluginEntry] | None = None
