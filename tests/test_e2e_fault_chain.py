"""Pure, offline test-only composite fault gate regressions."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, create_autospec

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "container-lifecycle-management" / "scripts"))
sys.path.insert(0, str(HERE / "integration"))
from ci_e2e_fault_chain import evaluate_test_chain  # noqa: E402
from current_anchor_source_contract import (  # noqa: E402
    AnchorHeadDecision, ReviewedHeadReader,
)
from monotonic_head_contract import PublishedHead, SyntheticMonotonicJournal  # noqa: E402
from witness_attestation_contract import TrustedWitness, WitnessTrustStore  # noqa: E402

ANCHOR = "a" * 64


class SyntheticEndToEndGateTests(unittest.TestCase):
    def setUp(self):
        signing = Ed25519PrivateKey.generate()
        self.trust = WitnessTrustStore((TrustedWitness(
            witness_id="ci-anchor", key_id="test-key",
            public_key=signing.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw),
            fault_domain="synthetic-witness-domain",
        ),))
        self.snapshot = Mock(return_value=None)
        self.reader = create_autospec(ReviewedHeadReader, instance=True)
        self.reader.evaluate.return_value = AnchorHeadDecision(
            "SIGNED_SOURCE_CLAIM_MATCHED", (), ANCHOR,
        )
        self.journal = create_autospec(SyntheticMonotonicJournal, instance=True)
        self.journal.current.return_value = PublishedHead(
            "OBSERVED_LOCAL", 2, ANCHOR,
        )

    def check(self, **changed):
        params = {
            "snapshot_check": self.snapshot,
            "signed_reader": self.reader,
            "ledger_connection": object(),
            "signed_anchor": {},
            "anchor_trust": self.trust,
            "publication": self.journal,
            "ledger_id": "ci-ledger",
            "expected_anchor_id": ANCHOR,
            "trusted_ledger_revision": 2,
            "trusted_publication_revision": 2,
            "now_unix": 1700000000,
        }
        params.update(changed)
        return evaluate_test_chain(**params)

    def blocked(self, code, **kwargs):
        result = self.check(**kwargs)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertIn(code, result.blockers)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)

    def test_all_local_evidence_never_promotes_to_off_host(self):
        result = self.check()
        self.assertEqual(result.status, "LOCAL_EVIDENCE_CONSISTENT_ONLY")
        self.assertIn("chain:independent_off_host_not_proven", result.blockers)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)
        self.snapshot.assert_called_once_with()
        self.reader.evaluate.assert_called_once()
        self.journal.current.assert_called_once_with(trusted_min_revision=2)

    def test_lost_snapshot_or_key_denied_before_signed_reader(self):
        self.snapshot.side_effect = RuntimeError("PRIVATE_RESTIC_PASSWORD_CANARY")
        decision = self.check()
        self.assertEqual(decision.status, "BLOCKED")
        self.assertIn("chain:snapshot_or_key_unavailable", decision.blockers)
        self.assertNotIn("PRIVATE_RESTIC_PASSWORD_CANARY", repr(decision))
        self.reader.evaluate.assert_not_called()

    def test_missing_signing_source_refused(self):
        self.reader.evaluate.side_effect = OSError("PRIVATE_SIGNER_KEY")
        decision = self.check()
        self.assertIn("chain:signed_source_unavailable", decision.blockers)
        self.assertNotIn("PRIVATE_SIGNER_KEY", repr(decision))
        self.journal.current.assert_not_called()

    def test_source_crash_refusal_not_ignored(self):
        self.reader.evaluate.return_value = AnchorHeadDecision(
            "BLOCKED", ("head:source_unavailable",),
        )
        self.blocked("chain:signed_head_or_ledger_mismatch")
        self.journal.current.assert_not_called()

    def test_wrong_signed_head_refused_before_cas(self):
        self.reader.evaluate.return_value = AnchorHeadDecision(
            "SIGNED_SOURCE_CLAIM_MATCHED", (), "b" * 64,
        )
        self.blocked("chain:signed_head_or_ledger_mismatch")
        self.journal.current.assert_not_called()

    def test_rolled_back_sqlite_signed_refusal_is_fatal(self):
        self.reader.evaluate.return_value = AnchorHeadDecision(
            "BLOCKED", ("continuity:ledger_state_mismatch",),
        )
        self.blocked("chain:signed_head_or_ledger_mismatch")

    def test_monotonic_store_loss_blocks_even_signed_source(self):
        self.journal.current.return_value = PublishedHead(
            "BLOCKED", blockers=("publish:invalid_or_unavailable_store",),
        )
        self.blocked("chain:publication_unavailable")

    def test_monotonic_store_exception_redacted(self):
        self.journal.current.side_effect = OSError("PRIVATE_DB_PATH")
        result = self.check()
        self.assertIn("chain:publication_unavailable", result.blockers)
        self.assertNotIn("PRIVATE_DB_PATH", repr(result))

    def test_publication_head_drift_blocks_all_evidence(self):
        self.journal.current.return_value = PublishedHead(
            "OBSERVED_LOCAL", 2, "b" * 64,
        )
        self.blocked("chain:publication_head_mismatch")

    def test_missing_revision_floor_and_bad_clock_fail_preflight(self):
        for param, value in (
            ("trusted_ledger_revision", True),
            ("trusted_publication_revision", -1),
            ("trusted_publication_revision", "2"),
            ("now_unix", False),
            ("expected_anchor_id", "LATEST"),
            ("snapshot_check", None),
        ):
            with self.subTest(param=param):
                self.blocked("chain:invalid_trusted_context", **{param: value})
        self.snapshot.assert_not_called()

    def test_no_automation_executor_or_mutation_permissions(self):
        result = self.check()
        for method in ("deploy", "restore", "prune", "delete", "capture", "shell"):
            self.assertFalse(hasattr(result, method))
        self.assertFalse(result.restore_authorized)


if __name__ == "__main__":
    unittest.main()
