"""Offline current-anchor head contract. Synthetic keys, sqlite and source only."""
from __future__ import annotations

from contextlib import closing

import copy
import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "container-lifecycle-management" / "scripts"))
from current_anchor_source_contract import (  # noqa: E402
    CLAIM, SCHEMA, ReviewedHeadReader, ReviewedHeadSource, canonical_head,
)
from ledger_continuity_contract import (  # noqa: E402
    CLAIM as ANCHOR_CLAIM, SCHEMA as ANCHOR_SCHEMA,
    canonical_anchor, read_ledger_state,
)
from witness_attestation_contract import (  # noqa: E402
    DurableWitnessLedger, TrustedWitness, WitnessTrustStore,
)

NOW = 1700000000


class SyntheticHead:
    """Source object explicitly registered by this test, not policy selected."""

    def __init__(self, signing_key, anchor_id, revision):
        self.signer = signing_key
        self.anchor_id = anchor_id
        self.revision = revision
        self.mode = "valid"
        self.previous = None
        self.calls = 0

    def read_current_head(self, ledger_id, challenge):
        self.calls += 1
        if self.mode == "unavailable":
            raise OSError("PRIVATE_SOURCE_PASSWORD")
        if self.mode == "replay":
            return self.previous
        statement = {
            "schema": SCHEMA, "claim": CLAIM, "source_id": "synthetic-head-source",
            "key_id": "ci-head-key", "ledger_id": ledger_id,
            "challenge": challenge,
            "anchor_id": self.anchor_id, "revision": self.revision,
            "issued_at_unix": NOW, "expires_at_unix": NOW + 90,
        }
        if self.mode == "stale":
            statement["issued_at_unix"] = NOW - 100
            statement["expires_at_unix"] = NOW + 1
        if self.mode == "future":
            statement["issued_at_unix"] = NOW + 10
            statement["expires_at_unix"] = NOW + 90
        if self.mode == "wrong-ledger":
            statement["ledger_id"] = "foreign"
        if self.mode == "bad-revision":
            statement["revision"] = self.revision + 1
        if self.mode == "bad-anchor":
            statement["anchor_id"] = "e" * 64
        raw = canonical_head(statement)
        envelope = {"message": statement,
                    "signature": self.signer.sign(raw).hex()}
        if self.mode == "bad-signature":
            envelope["signature"] = "0" * 128
        if self.mode == "extra-field":
            envelope["message"]["PRIVATE_CANARY"] = "SECRET"
        self.previous = copy.deepcopy(envelope)
        return envelope


class CurrentAnchorHeadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="msc-head-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.dbpath = Path(self.temp.name) / "witness.sqlite"
        self.connection = sqlite3.connect(self.dbpath, timeout=5)
        self.addCleanup(self.close)
        self.ledger = DurableWitnessLedger(self.connection)
        self.assertEqual(self.ledger._change(
            {"witness_id": "synthetic-w", "key_id": "key-1",
             "expires_at_unix": NOW + 500}, "a" * 64,
        ), "recorded")
        self.witness_signer = Ed25519PrivateKey.generate()
        self.trust = WitnessTrustStore((TrustedWitness(
            "synthetic-anchor-witness", "anchor-key-1",
            self.witness_signer.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw), "synthetic-witness-domain",
        ),))
        self.head_signer = Ed25519PrivateKey.generate()
        self.make_anchor()
        self.source = SyntheticHead(self.head_signer, self.anchor_id, self.revision)
        self.reader = self.register(self.source)

    def close(self):
        try:
            self.connection.close()
        except sqlite3.Error:
            pass

    def make_anchor(self):
        current = read_ledger_state(self.connection)
        self.assertTrue(current.valid, current.blockers)
        self.revision = current.used_count + current.revoked_count
        statement = {
            "schema": ANCHOR_SCHEMA, "claim": ANCHOR_CLAIM,
            "ledger_id": "synthetic-ledger", "witness_id": "synthetic-anchor-witness",
            "key_id": "anchor-key-1", "witness_fault_domain": "synthetic-witness-domain",
            "nonce": "c" * 64,
            "state_digest": current.digest, "used_count": current.used_count,
            "revoked_count": current.revoked_count, "revision": self.revision,
            "issued_at_unix": NOW, "expires_at_unix": NOW + 1000,
        }
        signed = canonical_anchor(statement)
        self.anchor_id = hashlib.sha256(signed).hexdigest()
        self.anchor = {"statement": statement,
                       "signature": self.witness_signer.sign(signed).hex()}

    def register(self, source, *, digest=None, public_key=None, fault_domain=None):
        return ReviewedHeadReader(
            HERE,
            ReviewedHeadSource(
                source_id="synthetic-head-source", key_id="ci-head-key",
                fault_domain=fault_domain or "synthetic-head-domain",
                public_key=public_key or self.head_signer.public_key().public_bytes(
                    Encoding.Raw, PublicFormat.Raw),
                source_file_sha256=digest or (
                    "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
                source=source,
            ),
        )

    def evaluate(self, *, reader=None, connection=None, min_revision="DEFAULT", now=NOW + 1):
        return (reader or self.reader).evaluate(
            self.connection if connection is None else connection,
            self.anchor, self.trust, ledger_id="synthetic-ledger",
            now_unix=now,
            trusted_min_revision=(self.revision if min_revision == "DEFAULT" else min_revision),
        )

    def blocked(self, code, **kwargs):
        result = self.evaluate(**kwargs)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertIn(code, result.blockers)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)

    def test_signed_fresh_source_and_sqlite_match_non_authorizing(self):
        result = self.evaluate()
        self.assertEqual(result.status, "SIGNED_SOURCE_CLAIM_MATCHED")
        self.assertEqual(result.anchor_id, self.anchor_id)
        self.assertEqual(self.source.calls, 1)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)

    def test_source_outage_fails_closed_without_secrets(self):
        self.source.mode = "unavailable"
        result = self.evaluate()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("head:source_unavailable", result.blockers)
        self.assertNotIn("PRIVATE_SOURCE_PASSWORD", repr(result))

    def test_replayed_signed_response_fails_new_challenge(self):
        self.assertEqual(self.evaluate().status, "SIGNED_SOURCE_CLAIM_MATCHED")
        self.source.mode = "replay"
        self.blocked("head:challenge_mismatch")

    def test_wrong_anchor_even_when_newly_signed_denied(self):
        self.source.mode = "bad-anchor"
        self.blocked("head:source_head_mismatch")

    def test_wrong_revision_even_when_newly_signed_denied(self):
        self.source.mode = "bad-revision"
        self.blocked("head:source_head_mismatch")

    def test_old_signed_head_below_trusted_revision_floor_denied(self):
        self.blocked("head:below_trusted_minimum", min_revision=self.revision + 1)

    def test_stale_and_future_source_reply_denied(self):
        for mode in ("stale", "future"):
            with self.subTest(mode=mode):
                self.source.mode = mode
                self.blocked("head:stale_or_future_source_reply")

    def test_signature_tampering_denied(self):
        self.source.mode = "bad-signature"
        self.blocked("head:invalid_source_signature")

    def test_wrong_registered_key_denied(self):
        other = Ed25519PrivateKey.generate()
        r = self.register(self.source, public_key=other.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw))
        self.blocked("head:invalid_source_signature", reader=r)

    def test_wrong_ledger_reply_denied(self):
        self.source.mode = "wrong-ledger"
        self.blocked("head:unexpected_source_identity")

    def test_unexpected_reply_data_never_echoed(self):
        self.source.mode = "extra-field"
        result = self.evaluate()
        self.assertEqual(result.status, "BLOCKED")
        self.assertNotIn("PRIVATE_CANARY", repr(result))
        self.assertIn("head:invalid_signed_reply", result.blockers)

    def test_source_file_changed_or_unreviewed_directory_denied(self):
        with self.assertRaisesRegex(ValueError, "head:source_pin_mismatch"):
            self.register(self.source, digest="sha256:" + "f" * 64)
        with self.assertRaisesRegex(ValueError, "head:unreviewed_source"):
            ReviewedHeadReader(Path(self.temp.name), self.reader._binding)

    def test_same_claimed_failure_domain_denied_without_call(self):
        r = self.register(self.source, fault_domain="synthetic-witness-domain")
        self.blocked("head:untrusted_or_shared_signer_domain", reader=r)
        self.assertEqual(self.source.calls, 0)

    def test_rolled_back_sqlite_denied_against_fresh_signed_head(self):
        previous = Path(self.temp.name) / "old.sqlite"
        with closing(sqlite3.connect(previous)) as old, old:
            self.connection.backup(old)
        self.assertTrue(self.ledger.revoke("key", "synthetic-w:key-1"))
        self.make_anchor()
        self.source.anchor_id = self.anchor_id
        self.source.revision = self.revision
        with closing(sqlite3.connect(previous)) as rolled_back, rolled_back:
            self.blocked("continuity:ledger_state_mismatch", connection=rolled_back)

    def test_current_sqlite_plus_old_source_id_refused(self):
        self.source.anchor_id = "e" * 64
        self.blocked("head:source_head_mismatch")

    def test_missing_or_untrusted_revision_denied(self):
        for value in (-1, True, "1", None, 200_001):
            with self.subTest(value=value):
                self.blocked("head:untrusted_clock_or_minimum", min_revision=value)

    def test_zero_source_calls_for_invalid_clock(self):
        self.blocked("head:untrusted_clock_or_minimum", now=True)
        self.assertEqual(self.source.calls, 0)

    def test_unsigned_policy_cannot_select_execution(self):
        # The registry is passed an actual inspected instance, no module string.
        for method in ("restore", "prune", "delete", "capture"):
            self.assertFalse(hasattr(self.reader, method))
        bad_message = {
            "schema": SCHEMA, "claim": CLAIM, "source_id": "synthetic-head-source",
            "key_id": "ci-head-key", "ledger_id": "synthetic-ledger",
            "challenge": "d" * 64, "anchor_id": self.anchor_id,
            "revision": self.revision, "issued_at_unix": NOW,
            "expires_at_unix": NOW + 60, "execute": "untrusted.module:run",
        }
        with self.assertRaises(ValueError):
            canonical_head(bad_message)


if __name__ == "__main__":
    unittest.main()
