"""Only synthetic local SQLite and temporary Ed25519 keys, no real services."""
from __future__ import annotations

from contextlib import closing

import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SKILL = Path(__file__).resolve().parents[1] / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SKILL))
from ledger_continuity_contract import (  # noqa: E402
    CLAIM, SCHEMA, canonical_anchor, read_ledger_state, verify_ledger_continuity,
)
from witness_attestation_contract import (  # noqa: E402
    DurableWitnessLedger, TrustedWitness, WitnessTrustStore,
)

EPOCH = 1700000000


class LedgerContinuityContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="msc-ledger-rollback-only-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "current.sqlite"
        self.connection = sqlite3.connect(self.db, timeout=5)
        self.addCleanup(self.close_connection)
        self.ledger = DurableWitnessLedger(self.connection)
        self.signer = Ed25519PrivateKey.generate()
        self.trust = WitnessTrustStore((TrustedWitness(
            witness_id="test-independent-anchor", key_id="test-anchor-key",
            public_key=self.signer.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw),
            fault_domain="synthetic-other-domain",
        ),))
        self.add_event("a")

    def close_connection(self):
        try:
            self.connection.close()
        except sqlite3.Error:
            pass

    def add_event(self, char):
        from witness_attestation_contract import _identifier
        self.assertTrue(_identifier("test-witness"))
        record = {"witness_id": "test-witness", "key_id": "test-key",
                  "expires_at_unix": EPOCH + 600}
        # The underlying ledger tests cover signed attestation recording.
        self.assertEqual(self.ledger._change(
            {"witness_id": record["witness_id"], "key_id": record["key_id"],
             "expires_at_unix": record["expires_at_unix"]}, char * 64,
        ), "recorded")

    def anchor(self, *, nonce="d", issue=EPOCH, expiry=EPOCH + 500):
        state = read_ledger_state(self.connection)
        self.assertTrue(state.valid, state.blockers)
        stmt = {
            "schema": SCHEMA, "claim": CLAIM, "ledger_id": "ci-synthetic-ledger",
            "witness_id": "test-independent-anchor", "key_id": "test-anchor-key",
            "witness_fault_domain": "synthetic-other-domain",
            "nonce": nonce * 64,
            "state_digest": state.digest, "used_count": state.used_count,
            "revoked_count": state.revoked_count,
            "revision": state.used_count + state.revoked_count,
            "issued_at_unix": issue, "expires_at_unix": expiry,
        }
        return self.sign(stmt)

    def sign(self, stmt):
        signed = canonical_anchor(stmt)
        return {"statement": copy.deepcopy(stmt), "signature": self.signer.sign(signed).hex()}

    def anchor_id(self, envelope):
        return hashlib.sha256(canonical_anchor(envelope["statement"])).hexdigest()

    def assess(self, envelope, *, connection=None, expected_id=None, trust=None,
               ledger_id="ci-synthetic-ledger", now=EPOCH + 50):
        return verify_ledger_continuity(
            self.connection if connection is None else connection,
            envelope, self.trust if trust is None else trust,
            ledger_id=ledger_id,
            expected_current_anchor_id=(self.anchor_id(envelope) if expected_id is None
                                        else expected_id),
            now_unix=now,
        )

    def denied(self, envelope, code, **kwargs):
        outcome = self.assess(envelope, **kwargs)
        self.assertEqual(outcome.status, "BLOCKED", outcome)
        self.assertIn(code, outcome.blockers)
        self.assertFalse(outcome.restore_authorized)
        self.assertFalse(outcome.off_host_proven)
        self.assertFalse(outcome.eligible_for_prune)

    def test_valid_state_only_crypto_matches_never_authorizes(self):
        attestation = self.anchor()
        verified = self.assess(attestation)
        self.assertEqual(verified.status, "CRYPTO_MATCHED")
        self.assertFalse(verified.restore_authorized)
        self.assertFalse(verified.off_host_proven)
        self.assertFalse(verified.eligible_for_prune)

    def test_stable_digest_after_reconnect(self):
        before = read_ledger_state(self.connection)
        self.connection.close()
        self.connection = sqlite3.connect(self.db)
        self.ledger = DurableWitnessLedger(self.connection)
        self.assertEqual(read_ledger_state(self.connection), before)
        self.assertEqual(self.assess(self.anchor()).status, "CRYPTO_MATCHED")

    def test_revocation_causes_old_state_mismatch(self):
        old = self.anchor(nonce="1")
        self.assertTrue(self.ledger.revoke("key", "test-witness:test-key"))
        self.denied(old, "continuity:ledger_state_mismatch")
        latest = self.anchor(nonce="2")
        self.assertEqual(self.assess(latest).status, "CRYPTO_MATCHED")

    def test_rollback_to_previous_sqlite_rejected_with_latest_anchor(self):
        old_path = self.root / "old.sqlite"
        with closing(sqlite3.connect(old_path)) as previous, previous:
            self.connection.backup(previous)
        old_anchor = self.anchor(nonce="1")
        self.assertTrue(self.ledger.revoke("witness", "test-witness"))
        newest_anchor = self.anchor(nonce="2")
        current_pin = self.anchor_id(newest_anchor)
        with closing(sqlite3.connect(old_path)) as rolled_back, rolled_back:
            self.denied(newest_anchor, "continuity:ledger_state_mismatch",
                        connection=rolled_back, expected_id=current_pin)
            self.denied(old_anchor, "continuity:not_latest_external_anchor",
                        connection=rolled_back, expected_id=current_pin)
        self.assertEqual(self.assess(newest_anchor, expected_id=current_pin).status,
                         "CRYPTO_MATCHED")

    def test_foreign_database_same_structure_does_not_match(self):
        foreign_path = self.root / "foreign.sqlite"
        with closing(sqlite3.connect(foreign_path)) as foreign, foreign:
            DurableWitnessLedger(foreign)
            foreign.execute(
                "INSERT INTO witness_used VALUES (?,?,?,?)",
                ("b" * 64, "test-witness", "test-key", EPOCH + 600),
            )
            foreign.commit()
            self.denied(self.anchor(), "continuity:ledger_state_mismatch",
                        connection=foreign)

    def test_same_row_count_different_contents_denied(self):
        attestation = self.anchor()
        self.connection.execute(
            "UPDATE witness_used SET key_id=? WHERE attestation_id=?",
            ("replaced-key", "a" * 64),
        )
        self.connection.commit()
        self.denied(attestation, "continuity:ledger_state_mismatch")

    def test_missing_current_anchor_pin_denied(self):
        self.denied(self.anchor(), "continuity:missing_independent_anchor_pin",
                    expected_id="latest")

    def test_signed_historic_anchor_denied_against_current_external_pin(self):
        old = self.anchor(nonce="1")
        newest = self.anchor(nonce="2")
        self.denied(old, "continuity:not_latest_external_anchor",
                    expected_id=self.anchor_id(newest))

    def test_changed_ledger_identifier_denied(self):
        self.denied(self.anchor(), "continuity:ledger_identity_mismatch",
                    ledger_id="not-this-ledger")

    def test_invalid_signature_denied(self):
        envelope = self.anchor()
        envelope["signature"] = "0" * 128
        self.denied(envelope, "continuity:invalid_signature")

    def test_unknown_or_wrong_signer_rejected(self):
        other = Ed25519PrivateKey.generate()
        wrong = WitnessTrustStore((TrustedWitness(
            witness_id="test-independent-anchor", key_id="test-anchor-key",
            public_key=other.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            fault_domain="synthetic-other-domain",
        ),))
        self.denied(self.anchor(), "continuity:invalid_signature", trust=wrong)

    def test_expired_future_or_boolean_clock_denied(self):
        envelope = self.anchor()
        for clock in (EPOCH - 1, EPOCH + 501, True):
            with self.subTest(clock=clock):
                self.denied(envelope, "continuity:stale_anchor", now=clock)

    def test_extra_secret_fields_never_echoed(self):
        envelope = self.anchor()
        envelope["statement"]["token"] = "PRIVATE_CANARY"
        value = self.assess(envelope, expected_id="0" * 64)
        self.assertEqual(value.status, "BLOCKED")
        self.assertNotIn("PRIVATE_CANARY", repr(value))

    def test_invalid_revision_and_bools_rejected(self):
        for key, value in (("revision", 99), ("revision", True),
                           ("used_count", "1"), ("expires_at_unix", EPOCH + 4000),
                           ("nonce", "latest")):
            attestation = self.anchor()
            attestation["statement"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                canonical_anchor(attestation["statement"])

    def test_active_sqlite_transaction_refused(self):
        self.connection.execute("BEGIN IMMEDIATE")
        state = read_ledger_state(self.connection)
        self.assertFalse(state.valid)
        self.assertIn("continuity:active_transaction", state.blockers)
        self.connection.rollback()

    def test_missing_or_replaced_table_refused(self):
        signed = self.anchor()
        self.connection.execute("DROP TABLE witness_revoked")
        self.connection.commit()
        self.assertFalse(read_ledger_state(self.connection).valid)
        self.denied(signed, "continuity:unreadable_or_invalid_ledger")

    def test_unexpected_witness_trigger_blocks(self):
        signed = self.anchor()
        self.connection.execute(
            "CREATE TRIGGER witness_modify AFTER INSERT ON witness_used BEGIN "
            "SELECT 1; END"
        )
        self.connection.commit()
        self.denied(signed, "continuity:unreadable_or_invalid_ledger")

    def test_closed_connection_is_blocked_not_exception(self):
        signed = self.anchor()
        self.connection.close()
        state = read_ledger_state(self.connection)
        self.assertFalse(state.valid)
        self.assertIn("continuity:unreadable_or_invalid_ledger", state.blockers)
        self.denied(signed, "continuity:unreadable_or_invalid_ledger")

    def test_memory_database_denied(self):
        with closing(sqlite3.connect(":memory:")) as memory, memory:
            self.assertIn("continuity:nonpersistent_ledger",
                          read_ledger_state(memory).blockers)

    def test_invalid_extra_rows_fail_closed(self):
        signed = self.anchor()
        self.connection.execute(
            "INSERT INTO witness_revoked VALUES (?,?)", ("unknown", "PRIVATE_CANARY")
        )
        self.connection.commit()
        self.denied(signed, "continuity:unreadable_or_invalid_ledger")

    def test_no_mutation_executor_surface(self):
        from ledger_continuity_contract import LedgerState, ContinuityDecision
        for target in (LedgerState, ContinuityDecision):
            for name in ("restore", "capture", "delete", "prune", "docker"):
                self.assertFalse(hasattr(target, name))


if __name__ == "__main__":
    unittest.main()
