"""Offline failure-domain and credential-loss refusal tests, no Docker/network."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from failure_domain_contract import assess_disaster_recovery  # noqa: E402
from recovery_contract import validate_recovery_set  # noqa: E402

DIGEST = "sha256:" + "a" * 64
SID = "b" * 64


def sample():
    recovery = {
        "schema": "recovery-set/v1", "application": "test-only",
        "compose": {"project": "test-fixture", "source_digest": DIGEST},
        "images": {"db": DIGEST, "worker": DIGEST},
        "assets": [
            {"id": "pg", "kind": "database", "backend": "postgresql",
             "consistency": "pg_dump", "reference": "test-db",
             "recovery_required": True},
            {"id": "files", "kind": "user_files", "backend": "filesystem",
             "consistency": "snapshot_quiesced", "reference": "test-files",
             "recovery_required": True},
            {"id": "key", "kind": "secret_reference",
             "backend": "external_reference", "consistency": "immutable_reference",
             "reference": "test-key", "recovery_required": True},
        ],
    }
    fp = validate_recovery_set(recovery).fingerprint
    cp = {
        "id": SID, "recovery_fingerprint": fp, "class": "PRE_MIGRATION",
        "provider": "restic", "capture_complete": True,
        "repository_checked": True, "isolated_restore_tested": True,
        "application_smoke_passed": True,
        "holds": ["last_known_good", "pre_migration"],
    }
    topology = {
        "schema": "failure-domain/v1", "recovery_fingerprint": fp,
        "checkpoint_id": SID,
        "source": {"node_id": "primary-host", "fault_domain": "primary-site"},
        "repository": {"storage_id": "remote-repo", "fault_domain": "backup-site",
                       "storage_class": "off_host"},
        "key_authority": {"authority_id": "offline-custodian",
                          "fault_domain": "third-site",
                          "key_recovery": "independent"},
    }
    availability = {
        "source_unavailable": True, "repository_accessible": True,
        "key_retrievable": True, "snapshot_readable": True,
    }
    return recovery, cp, topology, availability


class DisasterRecoveryGateTests(unittest.TestCase):
    def setUp(self):
        self.inputs = list(sample())

    def decide(self):
        return assess_disaster_recovery(*copy.deepcopy(self.inputs))

    def blocked(self, code):
        result = self.decide()
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertIn(code, result.blockers)

    def test_even_claimed_independence_is_not_execution_authority(self):
        result = self.decide()
        self.assertEqual(result.status, "CANDIDATE_ONLY")
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)

    def test_local_repository_cannot_be_disaster_ready(self):
        self.inputs[2]["repository"]["storage_class"] = "on_host"
        self.blocked("disaster:repository_not_off_host")

    def test_same_host_repository_and_primary_denied(self):
        self.inputs[2]["repository"]["fault_domain"] = "primary-site"
        self.blocked("disaster:shared_or_unknown_fault_domain")

    def test_key_authority_on_lost_primary_denied(self):
        self.inputs[2]["key_authority"]["fault_domain"] = "primary-site"
        self.blocked("disaster:shared_or_unknown_fault_domain")

    def test_key_and_repository_same_failure_domain_denied(self):
        self.inputs[2]["key_authority"]["fault_domain"] = "backup-site"
        self.blocked("disaster:shared_or_unknown_fault_domain")

    def test_missing_key_after_source_loss_denied(self):
        self.inputs[3]["key_retrievable"] = False
        self.blocked("disaster:key_retrievable_unproven")

    def test_repository_unavailable_after_source_loss_denied(self):
        self.inputs[3]["repository_accessible"] = False
        self.blocked("disaster:repository_accessible_unproven")

    def test_corrupt_unreadable_snapshot_denied(self):
        self.inputs[3]["snapshot_readable"] = False
        self.blocked("disaster:snapshot_readable_unproven")

    def test_unknown_or_string_evidence_denied(self):
        for field in self.inputs[3]:
            with self.subTest(field=field):
                self.inputs[3][field] = "true"
                self.blocked("disaster:" + field + "_unproven")
                self.inputs[3][field] = True

    def test_incomplete_checkpoint_denied(self):
        self.inputs[1]["application_smoke_passed"] = False
        self.blocked("disaster:missing_restore_tested_checkpoint")

    def test_stale_checkpoint_or_fingerprint_denied(self):
        self.inputs[2]["checkpoint_id"] = "c" * 64
        self.blocked("disaster:stale_checkpoint_identity")
        self.inputs[2]["checkpoint_id"] = SID
        self.inputs[2]["recovery_fingerprint"] = DIGEST
        self.blocked("disaster:stale_checkpoint_identity")

    def test_unknown_domain_or_missing_field_denied(self):
        self.inputs[2]["source"]["fault_domain"] = "unknown"
        # A string 'unknown' is syntactically a valid ID but must not
        # become a distinct attested fault domain.
        self.blocked("disaster:invalid_source_boundary")

    def test_bad_topology_cannot_leak_sensitive_values(self):
        self.inputs[2]["repository"] = {"password": "SECRET_CANARY"}
        result = self.decide()
        self.assertEqual(result.status, "BLOCKED")
        self.assertNotIn("SECRET_CANARY", repr(result))
        self.assertFalse(hasattr(result, "execute"))
        self.assertFalse(hasattr(result, "delete"))

    def test_missing_availability_fails_closed(self):
        self.inputs[3] = None
        self.blocked("disaster:invalid_availability")

    def test_invalid_declaration_fails_closed(self):
        self.inputs[0]["assets"][0]["consistency"] = "unknown"
        self.blocked("disaster:invalid_recovery_set")


if __name__ == "__main__":
    unittest.main()
