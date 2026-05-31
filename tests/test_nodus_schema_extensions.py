import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from pydantic import ValidationError  # noqa: E402

from nodus_lang_schema.extensions import (  # noqa: E402
    LEGACY_UNVERSIONED_MANIFEST,
    MANIFEST_ABI_V1,
    MANIFEST_KIND,
    NODE_REGISTRATION_ABI_V1ALPHA1,
    STABILITY_STABLE,
    SURFACE_DYNAMIC_NODE,
    WEBHOOK_REGISTRATION_ABI_V1ALPHA1,
    extension_abi_policy,
    manifest_effective_abi_version,
    validate_extension_abi_version,
    validate_extension_manifest_document,
)
from nodus_lang_schema.extensions.models import (  # noqa: E402
    ManifestDeclarativeNodeEntry,
)


class ExtensionAbiPolicyTests(unittest.TestCase):
    def test_policy_marks_only_manifest_stable(self):
        policy = extension_abi_policy()
        self.assertEqual(policy["surfaces"]["manifest"]["stability"], STABILITY_STABLE)
        self.assertEqual(
            policy["surfaces"]["dynamic-node-registration"]["supported_versions"],
            [NODE_REGISTRATION_ABI_V1ALPHA1],
        )

    def test_validate_unknown_surface_raises(self):
        with self.assertRaises(ValueError):
            validate_extension_abi_version("missing-surface", "v1")

    def test_validate_supported_extension_version(self):
        resolved = validate_extension_abi_version(
            SURFACE_DYNAMIC_NODE, NODE_REGISTRATION_ABI_V1ALPHA1
        )
        self.assertEqual(resolved, NODE_REGISTRATION_ABI_V1ALPHA1)


class ManifestValidationTests(unittest.TestCase):
    def test_versioned_manifest_v1_validates(self):
        version = validate_extension_manifest_document(
            {
                "kind": MANIFEST_KIND,
                "abi_version": MANIFEST_ABI_V1,
                "default_profile": "default",
                "profiles": {
                    "default": {
                        "plugins": [{"module": "pkg.bootstrap"}],
                    }
                },
            }
        )
        self.assertEqual(version, MANIFEST_ABI_V1)

    def test_unsupported_manifest_version_rejected(self):
        with self.assertRaises(ValueError):
            validate_extension_manifest_document(
                {
                    "kind": MANIFEST_KIND,
                    "abi_version": "nodus.extension.manifest/v9",
                    "profiles": {"default": {"plugins": []}},
                }
            )

    def test_legacy_manifest_remains_accepted(self):
        version = manifest_effective_abi_version(
            {
                "profiles": {
                    "default": {
                        "plugins": ["pkg.bootstrap"],
                    }
                }
            }
        )
        self.assertEqual(version, LEGACY_UNVERSIONED_MANIFEST)

    def test_manifest_rejects_wrong_kind(self):
        with self.assertRaises(ValueError):
            validate_extension_manifest_document(
                {
                    "kind": "wrong-kind",
                    "abi_version": MANIFEST_ABI_V1,
                    "profiles": {"default": {"plugins": []}},
                }
            )


class DeclarativeEntryTests(unittest.TestCase):
    def test_manifest_node_entry_validates_abi_version(self):
        entry = ManifestDeclarativeNodeEntry.model_validate(
            {
                "kind": "dynamic-node",
                "abi_version": NODE_REGISTRATION_ABI_V1ALPHA1,
                "name": "node.echo",
                "type": "echo",
                "handler": "pkg.nodes.echo",
                "owner_class": "first-party",
            }
        )
        self.assertEqual(entry.abi_version, NODE_REGISTRATION_ABI_V1ALPHA1)

    def test_manifest_node_entry_rejects_extra_fields(self):
        with self.assertRaises(ValidationError):
            ManifestDeclarativeNodeEntry.model_validate(
                {
                    "kind": "dynamic-node",
                    "abi_version": NODE_REGISTRATION_ABI_V1ALPHA1,
                    "name": "node.echo",
                    "type": "echo",
                    "handler": "pkg.nodes.echo",
                    "owner_class": "first-party",
                    "unexpected": True,
                }
            )

    def test_webhook_version_is_exported_in_policy(self):
        policy = extension_abi_policy()
        self.assertEqual(
            policy["surfaces"]["webhook-registration"]["supported_versions"],
            [WEBHOOK_REGISTRATION_ABI_V1ALPHA1],
        )


if __name__ == "__main__":
    unittest.main()
