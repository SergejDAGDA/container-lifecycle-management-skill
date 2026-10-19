"""Static backup-control skill contract checks; not runtime restore evidence."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "container-lifecycle-management"
CONTROL = SKILL / "references" / "backup-control.md"
REVIEW = ROOT / "docs" / "RC-ACCEPTANCE-0.5.0.md"


class BackupControlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        cls.control = CONTROL.read_text(encoding="utf-8")
        cls.rc = REVIEW.read_text(encoding="utf-8")

    def test_backup_operations_discoverable_without_claiming_a_new_cli(self):
        for required in ("backup-audit [service]", "backup-verify <service>",
                         "references/backup-control.md"):
            with self.subTest(required=required):
                self.assertIn(required, self.skill)
        self.assertIn("not bundled Restic orchestration commands", self.control)

    def test_creation_event_triggered_audit_may_be_periodic(self):
        for required in ("deployment events", "before approved updates",
                         "Monitoring can be periodic without creating backups",
                         "Existing project-owned scheduled backups"):
            with self.subTest(required=required):
                self.assertIn(required, self.control)

    def test_coverage_restore_offhost_have_separate_evidence(self):
        for required in ("exact immutable snapshot ID", "named volumes",
                         "Authoritative, ordered Compose", "database-and-files",
                         "application-level", "OFF_HOST_VERIFIED",
                         "RESTORE_VERIFIED", "ALERT_DELIVERY_VERIFIED",
                         "NOT VERIFIED"):
            with self.subTest(required=required):
                self.assertIn(required, self.control)

    def test_protected_historical_checkpoints_are_not_pruned_on_fault(self):
        for required in ("historical/**milestone** checkpoints",
                         "suspend all deletion/prune",
                         "restic forget --prune",
                         "separately reviewed, owner-approved"):
            with self.subTest(required=required):
                self.assertIn(required, self.control)

    def test_read_only_audit_preserves_real_server_authority(self):
        for required in ("must **not** run a backup",
                         "NO_TOUCH", "external-admin",
                         "unexpected backup-caused restarts",
                         "notification/monitoring mechanism",
                         "verified delivery path"):
            with self.subTest(required=required):
                self.assertIn(required, self.control)

    def test_rc_requires_backup_failure_cases_and_does_not_claim_disaster_recovery(self):
        for required in ("missing restore evidence", "milestone retention",
                         "off-host disaster recovery remain NOT VERIFIED",
                         "No built-in backup scheduler"):
            with self.subTest(required=required):
                self.assertIn(required, self.rc)


if __name__ == "__main__":
    unittest.main()
