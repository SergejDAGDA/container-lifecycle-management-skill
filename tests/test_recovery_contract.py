"""Pure provider-neutral recovery proof and retention planner regressions.

No Restic, Docker, SSH, network or real state.
"""
import copy
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from recovery_contract import (  # noqa: E402
    validate_recovery_set, validate_checkpoint, plan_retention_dry_run,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SNAPSHOT_A = "a" * 64
SNAPSHOT_B = "b" * 64
SNAPSHOT_C = "c" * 64


def recovery_set():
    return {
        "schema": "recovery-set/v1",
        "application": "synthetic-fixture",
        "compose": {"project": "disposable-demo", "source_digest": DIGEST_A},
        "images": {"fixture": DIGEST_B},
        "assets": [
            {"id": "database", "kind": "database", "backend": "sqlite",
             "consistency": "sqlite_backup_api", "reference": "logical-db",
             "recovery_required": True},
            {"id": "uploads", "kind": "user_files", "backend": "filesystem",
             "consistency": "snapshot_quiesced", "reference": "logical-files",
             "recovery_required": True},
            {"id": "key-recovery", "kind": "secret_reference",
             "backend": "external_reference", "consistency": "immutable_reference",
             "reference": "approved-key-authority", "recovery_required": True},
        ],
    }


def checkpoint(sid, fp, cls="PRE_UPGRADE", *, checked=True, restored=True, smoke=True, holds=None):
    return {"id": sid, "recovery_fingerprint": fp, "class": cls,
            "provider": "restic", "capture_complete": True,
            "repository_checked": checked, "isolated_restore_tested": restored,
            "application_smoke_passed": smoke, "holds": list(holds or [])}


class RecoveryContractTests(unittest.TestCase):
    def setUp(self):
        self.record = recovery_set()
        result = validate_recovery_set(self.record)
        self.assertTrue(result.valid, result.errors)
        self.fp = result.fingerprint

    def test_complete_declared_recovery_set(self):
        result = validate_recovery_set(self.record)
        self.assertEqual(result.errors, ())
        self.assertTrue(result.fingerprint.startswith("sha256:"))

    def test_fingerprint_is_canonical_independent_of_key_order(self):
        reordered = dict(reversed(list(self.record.items())))
        self.assertEqual(validate_recovery_set(reordered).fingerprint, self.fp)
        changed = copy.deepcopy(self.record)
        changed["images"]["fixture"] = DIGEST_A
        self.assertNotEqual(validate_recovery_set(changed).fingerprint, self.fp)

    def test_missing_secret_recovery_boundary_is_rejected(self):
        invalid = copy.deepcopy(self.record)
        invalid["assets"] = invalid["assets"][:2]
        result = validate_recovery_set(invalid)
        self.assertFalse(result.valid)
        self.assertIn("recovery_set:secret_recovery_reference_missing", result.errors)

    def test_database_requires_proven_consistency_method(self):
        invalid = copy.deepcopy(self.record)
        invalid["assets"][0]["consistency"] = "copy_live_file"
        self.assertFalse(validate_recovery_set(invalid).valid)

    def test_malformed_values_cannot_crash_or_echo_untrusted_content(self):
        for field, injected in [
            ("kind", ["database"]),
            ("backend", {"raw_secret": "secret-would-leak"}),
            ("consistency", ["sqlite_backup_api"]),
            ("id", {"key": "private"}),
            ("reference", "password=secret-would-leak"),
        ]:
            invalid = copy.deepcopy(self.record)
            invalid["assets"][0][field] = injected
            checked = validate_recovery_set(invalid)
            self.assertFalse(checked.valid)
            self.assertNotIn("secret-would-leak", str(checked.errors))

    def test_unknown_fields_fail_closed(self):
        invalid = copy.deepcopy(self.record)
        invalid["unreviewed"] = {"value": "private"}
        self.assertFalse(validate_recovery_set(invalid).valid)

    def test_duplicate_recovery_asset_identifiers_fail_closed(self):
        invalid = copy.deepcopy(self.record)
        invalid["assets"][1]["id"] = "database"
        self.assertFalse(validate_recovery_set(invalid).valid)

    def test_unresolved_recovery_required_is_rejected(self):
        invalid = copy.deepcopy(self.record)
        invalid["assets"][1]["recovery_required"] = "unknown"
        self.assertFalse(validate_recovery_set(invalid).valid)

    def test_incomplete_checkpoint_is_valid_declaration_not_restore_proof(self):
        cp = checkpoint(SNAPSHOT_A, self.fp, checked=False, restored=False, smoke=False)
        result = validate_checkpoint(cp, recovery_fingerprint=self.fp)
        self.assertTrue(result.valid)
        self.assertFalse(result.restore_tested)

    def test_restoration_smoke_without_restore_is_rejected(self):
        cp = checkpoint(SNAPSHOT_A, self.fp, checked=True, restored=False, smoke=True)
        self.assertFalse(validate_checkpoint(cp, recovery_fingerprint=self.fp).valid)

    def test_mismatched_state_declaration_blocks_checkpoint(self):
        cp = checkpoint(SNAPSHOT_A, DIGEST_B)
        self.assertFalse(validate_checkpoint(cp, recovery_fingerprint=self.fp).valid)

    def test_malformed_hold_is_rejected_without_exception(self):
        cp = checkpoint(SNAPSHOT_A, self.fp)
        cp["holds"] = [{"bad": "secret"}]
        result = validate_checkpoint(cp, recovery_fingerprint=self.fp)
        self.assertFalse(result.valid)
        self.assertNotIn("secret", str(result.errors))

    def test_malformed_class_and_unknown_evidence_fail_closed(self):
        cp = checkpoint(SNAPSHOT_A, self.fp)
        cp["class"] = ["PRE_UPGRADE"]
        cp["repository_checked"] = "unknown"
        self.assertFalse(validate_checkpoint(cp, recovery_fingerprint=self.fp).valid)

    def test_retention_protects_all_verified_recovery_checkpoints(self):
        good = checkpoint(SNAPSHOT_A, self.fp)
        disposable = checkpoint(SNAPSHOT_B, self.fp, checked=False, restored=False, smoke=False)
        result = plan_retention_dry_run(self.fp, [good, disposable], [SNAPSHOT_A, SNAPSHOT_B])
        self.assertEqual(result.blockers, ())
        self.assertEqual(result.permitted_candidates, (SNAPSHOT_B,))
        self.assertIn("restore_tested_protected", result.protected[0][1])

    def test_critical_event_checkpoints_are_never_candidates(self):
        good = checkpoint(SNAPSHOT_A, self.fp)
        premigration = checkpoint(SNAPSHOT_B, self.fp, "PRE_MIGRATION", checked=False, restored=False, smoke=False)
        decom = checkpoint(SNAPSHOT_C, self.fp, "PRE_DECOMMISSION", checked=False, restored=False, smoke=False)
        result = plan_retention_dry_run(self.fp, [good, premigration, decom], [SNAPSHOT_B, SNAPSHOT_C])
        self.assertEqual(result.permitted_candidates, ())
        self.assertEqual(len(result.protected), 2)

    def test_active_rollback_and_legal_holds_remain_protected(self):
        good = checkpoint(SNAPSHOT_A, self.fp)
        cp = checkpoint(SNAPSHOT_B, self.fp, checked=False, restored=False, smoke=False,
                        holds=["active_rollback", "legal_hold"])
        result = plan_retention_dry_run(self.fp, [good, cp], [SNAPSHOT_B])
        self.assertEqual(result.permitted_candidates, ())
        self.assertIn("legal_hold", result.protected[0][1])

    def test_without_verified_restore_every_delete_blocked(self):
        cp = checkpoint(SNAPSHOT_A, self.fp, checked=True, restored=False, smoke=False)
        result = plan_retention_dry_run(self.fp, [cp], [SNAPSHOT_A])
        self.assertEqual(result.permitted_candidates, ())
        self.assertIn("retention:no_restore_tested_checkpoint", result.blockers)

    def test_unknown_snapshot_id_blocks_entire_retention_plan(self):
        cp = checkpoint(SNAPSHOT_A, self.fp)
        result = plan_retention_dry_run(self.fp, [cp], [SNAPSHOT_B])
        self.assertEqual(result.permitted_candidates, ())
        self.assertIn("retention:unknown_snapshot", result.blockers)

    def test_malformed_checkpoint_blocks_entire_retention_plan(self):
        good = checkpoint(SNAPSHOT_A, self.fp)
        malformed = checkpoint(SNAPSHOT_B, self.fp)
        malformed["holds"] = None
        result = plan_retention_dry_run(self.fp, [good, malformed], [SNAPSHOT_A])
        self.assertEqual(result.permitted_candidates, ())
        self.assertIn("retention:invalid_checkpoint_inventory", result.blockers)

    def test_duplicate_ids_and_unknown_requested_ids_block_all(self):
        good = checkpoint(SNAPSHOT_A, self.fp)
        self.assertTrue(plan_retention_dry_run(self.fp, [good, good], [SNAPSHOT_A]).blockers)
        self.assertTrue(plan_retention_dry_run(self.fp, [good], ["latest"]).blockers)
        self.assertTrue(plan_retention_dry_run(self.fp, [good], [SNAPSHOT_A, SNAPSHOT_A]).blockers)

    def test_not_a_mutation_engine(self):
        result = plan_retention_dry_run(self.fp, [checkpoint(SNAPSHOT_A, self.fp)], [SNAPSHOT_A])
        self.assertFalse(hasattr(result, "execute"))
        self.assertFalse(hasattr(result, "delete"))


if __name__ == "__main__":
    unittest.main()
