"""Offline refusal tests: no Docker, Restic, network, or real data."""
import copy
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from migration_contract import evaluate_image_only_rollback  # noqa: E402
from recovery_contract import validate_recovery_set  # noqa: E402

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
SNAP = "c" * 64


def sample():
    recovery = {
        "schema": "recovery-set/v1", "application": "artificial",
        "compose": {"project": "synthetic", "source_digest": OLD},
        "images": {"fixture": OLD},
        "assets": [
            {"id": "db", "kind": "database", "backend": "sqlite",
             "consistency": "sqlite_backup_api", "reference": "fake-db",
             "recovery_required": True},
            {"id": "files", "kind": "user_files", "backend": "filesystem",
             "consistency": "snapshot_quiesced", "reference": "fake-files",
             "recovery_required": True},
            {"id": "key", "kind": "secret_reference", "backend": "external_reference",
             "consistency": "immutable_reference", "reference": "fake-key-ref",
             "recovery_required": True},
        ],
    }
    fp = validate_recovery_set(recovery).fingerprint
    cp = {"id": SNAP, "recovery_fingerprint": fp, "class": "PRE_MIGRATION",
          "provider": "restic", "capture_complete": True, "repository_checked": True,
          "isolated_restore_tested": True, "application_smoke_passed": True,
          "holds": ["pre_migration", "last_known_good"]}
    runtime = {"compose_source_digest": OLD, "images": {"fixture": NEW},
               "schema_revision": "v2"}
    return {
        "recovery_set": recovery, "checkpoint": cp, "expected_fingerprint": fp,
        "expected_runtime": runtime, "observed_runtime": copy.deepcopy(runtime),
        "rollback_images": {"fixture": OLD}, "migration_scope": ["db"],
        "baseline_schema": "v1", "observed_schema": "v2",
        "interrupted_after_commit": True,
    }


class MigrationRefusalTests(unittest.TestCase):
    def setUp(self):
        self.inputs = sample()

    def decide(self, **changes):
        args = copy.deepcopy(self.inputs)
        args.update(changes)
        return evaluate_image_only_rollback(**args)

    def denied(self, decision, code):
        self.assertFalse(decision.image_only_allowed)
        self.assertEqual(decision.status, "BLOCKED")
        self.assertIsNone(decision.recovery_checkpoint_id)
        self.assertIn(code, decision.blockers)

    def test_incompatible_schema_requires_state_aware_recovery(self):
        decision = self.decide()
        self.assertEqual(decision.status, "RECOVERY_REQUIRED")
        self.assertEqual(decision.recovery_checkpoint_id, SNAP)
        self.assertFalse(decision.image_only_allowed)
        self.assertEqual(decision.next_action, "plan_separately_authorized_state_aware_recovery")

    def test_missing_restore_proof(self):
        cp = copy.deepcopy(self.inputs["checkpoint"])
        cp["isolated_restore_tested"] = False
        cp["application_smoke_passed"] = False
        self.denied(self.decide(checkpoint=cp), "rollback:missing_restore_tested_checkpoint")

    def test_missing_repository_check(self):
        cp = copy.deepcopy(self.inputs["checkpoint"])
        cp["repository_checked"] = False
        cp["isolated_restore_tested"] = False
        cp["application_smoke_passed"] = False
        self.denied(self.decide(checkpoint=cp), "rollback:missing_restore_tested_checkpoint")

    def test_wrong_checkpoint_identity(self):
        cp = copy.deepcopy(self.inputs["checkpoint"])
        cp["recovery_fingerprint"] = OLD
        self.denied(self.decide(checkpoint=cp), "rollback:missing_restore_tested_checkpoint")

    def test_pre_migration_checkpoint_and_hold_required(self):
        cp = copy.deepcopy(self.inputs["checkpoint"])
        cp["class"] = "PRE_UPGRADE"
        cp["holds"] = []
        self.denied(self.decide(checkpoint=cp), "rollback:pre_migration_protection_missing")

    def test_stale_recovery_identity(self):
        self.denied(self.decide(expected_fingerprint=OLD), "rollback:stale_recovery_identity")

    def test_stale_runtime_identity(self):
        observed = copy.deepcopy(self.inputs["observed_runtime"])
        observed["images"]["fixture"] = OLD
        self.denied(self.decide(observed_runtime=observed), "rollback:stale_runtime_identity")

    def test_compose_source_drift(self):
        observed = copy.deepcopy(self.inputs["observed_runtime"])
        observed["compose_source_digest"] = NEW
        self.denied(self.decide(observed_runtime=observed), "rollback:invalid_observed_runtime")

    def test_foreign_rollback_image(self):
        self.denied(self.decide(rollback_images={"fixture": NEW}),
                    "rollback:wrong_rollback_image_identity")

    def test_foreign_or_partial_migration_scope(self):
        for scope in (["external-db"], [], ["db", "files"], ["db", "db"], "db"):
            with self.subTest(scope=scope):
                self.denied(self.decide(migration_scope=scope),
                            "rollback:unbounded_migration_scope")

    def test_unknown_schema_blocks_even_if_evidence_says_restored(self):
        self.denied(self.decide(observed_schema="unknown"),
                    "rollback:incompatible_schema_not_proven")

    def test_no_schema_change_does_not_authorize_image_only_downgrade(self):
        runtime = copy.deepcopy(self.inputs["observed_runtime"])
        runtime["schema_revision"] = "v1"
        self.denied(self.decide(expected_runtime=runtime, observed_runtime=runtime,
                                observed_schema="v1"),
                    "rollback:incompatible_schema_not_proven")

    def test_unconfirmed_interruption(self):
        self.denied(self.decide(interrupted_after_commit="unknown"),
                    "rollback:interruption_not_proven")

    def test_malformed_declaration_fails_closed(self):
        self.denied(self.decide(recovery_set=None), "rollback:invalid_recovery_set")

    def test_no_executor_or_sensitive_data_in_diagnostics(self):
        decision = self.decide(observed_runtime={"secret": "password=fake-canary"})
        self.assertFalse(hasattr(decision, "execute"))
        self.assertFalse(hasattr(decision, "restore"))
        self.assertNotIn("fake-canary", repr(decision))


if __name__ == "__main__":
    unittest.main()
