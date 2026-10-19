"""No Docker, network, credentials or storage mutations in these tests."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SKILL))
from recovery_contract import validate_recovery_set  # noqa: E402
from storage_provider_contract import (  # noqa: E402
    BackupStorageInspector, assess_storage_evidence, validate_storage_provider,
)

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SNAP = "c" * 64


def scenario():
    recovery = {
        "schema": "recovery-set/v1", "application": "synthetic-only",
        "compose": {"project": "synthetic-group", "source_digest": SHA_A},
        "images": {"database": SHA_B},
        "assets": [
            {"id": "db", "kind": "database", "backend": "postgresql",
             "consistency": "pg_dump", "reference": "synthetic-pg",
             "recovery_required": True},
            {"id": "files", "kind": "user_files", "backend": "filesystem",
             "consistency": "snapshot_quiesced", "reference": "test-files",
             "recovery_required": True},
            {"id": "key", "kind": "secret_reference", "backend": "external_reference",
             "consistency": "immutable_reference", "reference": "test-key",
             "recovery_required": True},
        ],
    }
    fp = validate_recovery_set(recovery).fingerprint
    cp = {
        "id": SNAP, "recovery_fingerprint": fp, "class": "PRE_UPGRADE",
        "provider": "restic", "capture_complete": True,
        "repository_checked": True, "isolated_restore_tested": True,
        "application_smoke_passed": True, "holds": ["last_known_good"],
    }
    provider = {
        "schema": "backup-storage-provider/v1",
        "provider_id": "test-restic-reader", "engine": "restic",
        "adapter_source_digest": SHA_A,
        "repository_id": "test-repository", "storage_class": "off_host",
        "source_fault_domain": "site-a", "repository_fault_domain": "site-b",
        "key_authority_id": "test-independent-key",
        "key_fault_domain": "site-c", "key_recovery_mode": "independent",
        "capabilities": ["exact_snapshot_lookup", "repository_data_check",
                         "isolated_restore_observation"],
    }
    pin = validate_storage_provider(provider).fingerprint
    observation = {
        "schema": "backup-storage-observation/v1",
        "provider_fingerprint": pin, "issuer_id": "trusted-reader",
        "repository_id": provider["repository_id"],
        "snapshot_id": SNAP, "recovery_fingerprint": fp,
        "compose_source_digest": SHA_A, "observed_at_unix": 1700000000,
        "repository_accessible": True, "snapshot_exact_match": True,
        "repository_data_checked": True, "key_retrievable": True,
    }
    return recovery, cp, provider, observation, {
        "expected_provider_fingerprint": pin,
        "expected_issuer_id": "trusted-reader",
        "now_unix": 1700000060,
        "max_age_seconds": 900,
    }


class StorageProviderContractTests(unittest.TestCase):
    def setUp(self):
        self.recovery, self.checkpoint, self.provider, self.observation, self.options = (
            scenario()
        )

    def check(self, **options):
        return assess_storage_evidence(
            copy.deepcopy(self.recovery),
            copy.deepcopy(self.checkpoint),
            copy.deepcopy(self.provider),
            copy.deepcopy(self.observation),
            **(dict(self.options) | options),
        )

    def blocked(self, code, **options):
        result = self.check(**options)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertIn(code, result.blockers)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.eligible_for_prune)

    def test_declaration_and_pin_canonical_order(self):
        p = validate_storage_provider(self.provider)
        self.assertTrue(p.valid, p.blockers)
        reordered = dict(reversed(list(self.provider.items())))
        self.assertEqual(validate_storage_provider(reordered).fingerprint, p.fingerprint)
        changed = copy.deepcopy(self.provider)
        changed["repository_id"] = "different-repo"
        self.assertNotEqual(validate_storage_provider(changed).fingerprint, p.fingerprint)

    def test_self_asserted_remote_status_is_never_authority(self):
        result = self.check()
        self.assertEqual(result.status, "CANDIDATE_ONLY")
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)
        self.assertFalse(hasattr(result, "execute"))
        self.assertFalse(hasattr(result, "prune"))

    def test_local_storage_is_valid_inventory_but_not_disaster_ready(self):
        self.provider["storage_class"] = "local"
        self.provider["repository_fault_domain"] = "site-a"
        self.blocked("storage:off_host_required")
        self.blocked("storage:shared_source_repository_domain")

    def test_source_equal_repository_not_independent(self):
        self.provider["repository_fault_domain"] = "site-a"
        self.blocked("storage:shared_source_repository_domain")

    def test_key_authority_on_source_or_repository_denied(self):
        for domain in ("site-a", "site-b"):
            with self.subTest(domain=domain):
                self.provider["key_fault_domain"] = domain
                self.blocked("storage:nonindependent_key_domain")

    def test_missing_key_recovery_contract_denied(self):
        self.provider["key_recovery_mode"] = "unverified"
        self.blocked("storage:key_recovery_not_independent")

    def test_provider_pin_changed_even_if_observation_claims_success(self):
        self.options["expected_provider_fingerprint"] = SHA_B
        self.blocked("storage:provider_pin_mismatch")

    def test_checkpoint_provider_engine_mismatch_denied(self):
        self.checkpoint["provider"] = "kopia"
        self.blocked("storage:checkpoint_provider_mismatch")

    def test_source_digest_drift_denied(self):
        self.observation["compose_source_digest"] = SHA_B
        self.blocked("storage:observation_source_mismatch")

    def test_repository_and_snapshot_mismatch_denied(self):
        self.observation["repository_id"] = "different"
        self.blocked("storage:observation_repository_mismatch")
        self.observation["repository_id"] = "test-repository"
        self.observation["snapshot_id"] = "d" * 64
        self.blocked("storage:observation_snapshot_mismatch")

    def test_wrong_recovery_set_fingerprint_denied(self):
        self.observation["recovery_fingerprint"] = SHA_B
        self.blocked("storage:observation_recovery_mismatch")

    def test_claimed_issuer_must_match_external_registration(self):
        self.observation["issuer_id"] = "policy-chosen"
        self.blocked("storage:untrusted_issuer_claim")
        self.observation["issuer_id"] = "trusted-reader"
        self.blocked("storage:missing_trusted_issuer_reference",
                     expected_issuer_id=None)

    def test_repository_missing_or_wrong_key_fail_closed(self):
        for field in ("repository_accessible", "snapshot_exact_match",
                      "repository_data_checked", "key_retrievable"):
            for value in (False, None, "true", 1):
                with self.subTest(field=field, value=value):
                    self.observation[field] = value
                    self.blocked("storage:" + field + "_unproven")
            self.observation[field] = True

    def test_stale_future_and_unknown_observation_time_denied(self):
        self.blocked("storage:stale_or_invalid_observation", now_unix=1700001000)
        self.observation["observed_at_unix"] = 1700000080
        self.blocked("storage:stale_or_invalid_observation")
        self.observation["observed_at_unix"] = True
        self.blocked("storage:stale_or_invalid_observation")

    def test_tampered_schema_or_extra_credentials_denied_without_leak(self):
        self.observation["auth_token"] = "PRIVATE_CANARY"
        result = self.check()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("storage:observation_schema_or_fields", result.blockers)
        self.assertNotIn("PRIVATE_CANARY", repr(result))
        self.provider["password"] = "PRIVATE_CANARY"
        self.blocked("storage:invalid_provider")
        self.assertNotIn("PRIVATE_CANARY", repr(self.check()))

    def test_unsupported_engine_invalid(self):
        self.provider["engine"] = ["restic"]
        self.blocked("storage:invalid_provider")
        self.assertIn("storage:invalid_engine",
                      validate_storage_provider(self.provider).blockers)

    def test_malformed_capabilities_and_unresolved_domain(self):
        for caps in ([], ["exact_snapshot_lookup"], ["unknown"], [None],
                     ["exact_snapshot_lookup"] * 3):
            with self.subTest(caps=caps):
                self.provider["capabilities"] = caps
                self.blocked("storage:invalid_provider")
        self.provider["capabilities"] = scenario()[2]["capabilities"]
        self.provider["repository_fault_domain"] = "unknown"
        self.blocked("storage:invalid_provider")

    def test_missing_application_restore_smoke_denied(self):
        self.checkpoint["application_smoke_passed"] = False
        self.blocked("storage:missing_restore_tested_checkpoint")

    def test_no_unreviewed_restore_or_mutation_implementation(self):
        self.assertFalse(hasattr(BackupStorageInspector, "restore"))
        self.assertFalse(hasattr(BackupStorageInspector, "delete"))
        self.assertFalse(hasattr(BackupStorageInspector, "capture"))

    def test_bad_scope_or_clock_denied(self):
        self.blocked("storage:invalid_scope", require_off_host="false")
        self.blocked("storage:stale_or_invalid_observation", now_unix=True)
        self.blocked("storage:stale_or_invalid_observation", max_age_seconds=0)


if __name__ == "__main__":
    unittest.main()
