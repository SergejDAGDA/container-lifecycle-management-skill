"""Offline Ed25519 witness/revocation contract regression tests.

All keys and bytes are synthetic, ephemeral and generated at test runtime.
Only an explicitly opened SQLite file under a TemporaryDirectory is written.
No Docker, secrets, external storage, live server or network access.
"""
from __future__ import annotations

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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "container-lifecycle-management" / "scripts"))
sys.path.insert(0, str(HERE))
from test_storage_provider_contract import scenario  # noqa: E402
from recovery_contract import validate_recovery_set  # noqa: E402
from storage_provider_contract import validate_storage_provider  # noqa: E402
from witness_attestation_contract import (  # noqa: E402
    CLAIM, SCHEMA, DurableWitnessLedger, TrustedWitness, WitnessTrustStore,
    canonical_statement, verify_and_record,
)

ISSUED = 1700000000


class WitnessAttestationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="msc-witness-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "witness.sqlite"
        self.connection = sqlite3.connect(self.db_path, timeout=5)
        self.addCleanup(self.close_connection)
        self.ledger = DurableWitnessLedger(self.connection)
        self.recovery, self.checkpoint, self.provider, _, _ = scenario()
        self.private_key = Ed25519PrivateKey.generate()
        self.trust = WitnessTrustStore((TrustedWitness(
            witness_id="synthetic-witness",
            key_id="key-01",
            public_key=self.private_key.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw),
            fault_domain="site-d",
        ),))
        self.statement = {
            "schema": SCHEMA, "witness_id": "synthetic-witness",
            "key_id": "key-01", "witness_fault_domain": "site-d",
            "nonce": "d" * 64,
            "provider_fingerprint": validate_storage_provider(self.provider).fingerprint,
            "recovery_fingerprint": validate_recovery_set(self.recovery).fingerprint,
            "snapshot_id": self.checkpoint["id"],
            "compose_source_digest": self.recovery["compose"]["source_digest"],
            "repository_id": self.provider["repository_id"],
            "issued_at_unix": ISSUED, "expires_at_unix": ISSUED + 600,
            "claim": CLAIM,
        }

    def close_connection(self):
        try:
            self.connection.close()
        except Exception:
            pass

    def sign(self, statement=None):
        data = self.statement if statement is None else statement
        return {
            "statement": copy.deepcopy(data),
            "signature": self.private_key.sign(canonical_statement(data)).hex(),
        }

    def verify(self, envelope=None, *, now=ISSUED + 10, trust=None, ledger=None,
               provider=None, recovery=None, checkpoint=None):
        return verify_and_record(
            self.sign() if envelope is None else envelope,
            self.trust if trust is None else trust,
            self.ledger if ledger is None else ledger,
            self.recovery if recovery is None else recovery,
            self.checkpoint if checkpoint is None else checkpoint,
            self.provider if provider is None else provider,
            now_unix=now,
        )

    def blocked(self, code, *, envelope=None, **kwargs):
        result = self.verify(envelope, **kwargs)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertIn(code, result.blockers)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)

    def test_valid_signature_is_only_recorded_never_approved(self):
        result = self.verify()
        self.assertEqual(result.status, "CRYPTO_VERIFIED_RECORDED")
        self.assertEqual(len(result.attestation_id), 64)
        self.assertTrue(self.ledger.is_current(result.attestation_id, now_unix=ISSUED + 10))
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)

    def test_canonical_json_order_is_signature_stable(self):
        envelope = self.sign()
        envelope["statement"] = dict(reversed(list(envelope["statement"].items())))
        result = self.verify(envelope)
        self.assertEqual(result.status, "CRYPTO_VERIFIED_RECORDED")

    def test_tampered_signature_refused_before_record(self):
        envelope = self.sign()
        envelope["signature"] = "0" * 128
        self.blocked("witness:signature_invalid", envelope=envelope)
        self.assertEqual(self.verify().status, "CRYPTO_VERIFIED_RECORDED")

    def test_tampered_statement_scope_refused(self):
        envelope = self.sign()
        envelope["statement"]["repository_id"] = "foreign"
        self.blocked("witness:signature_invalid", envelope=envelope)
        self.assertEqual(self.verify().status, "CRYPTO_VERIFIED_RECORDED")

    def test_unknown_trust_root_refused(self):
        envelope = self.sign()
        envelope["statement"]["key_id"] = "missing-key"
        self.blocked("witness:unknown_or_revoked_trust_root", envelope=envelope)

    def test_declaration_scope_changed_invalidates_signature_use(self):
        changed = copy.deepcopy(self.provider)
        changed["repository_id"] = "different"
        self.blocked("witness:scope_mismatch", provider=changed)
        changed_recovery = copy.deepcopy(self.recovery)
        changed_recovery["compose"]["source_digest"] = "sha256:" + "f" * 64
        self.blocked("witness:scope_mismatch", recovery=changed_recovery)
        changed_cp = copy.deepcopy(self.checkpoint)
        changed_cp["id"] = "e" * 64
        self.blocked("witness:scope_mismatch", checkpoint=changed_cp)

    def test_missing_restore_smoke_refused(self):
        changed = copy.deepcopy(self.checkpoint)
        changed["application_smoke_passed"] = False
        self.blocked("witness:missing_restore_test_proof", checkpoint=changed)

    def test_not_independent_from_source_repository_or_key_domain(self):
        for domain in ("site-a", "site-b", "site-c"):
            with self.subTest(domain=domain):
                key = self.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                trust = WitnessTrustStore((TrustedWitness(
                    witness_id="synthetic-witness", key_id="key-01",
                    public_key=key, fault_domain=domain,
                ),))
                signed = copy.deepcopy(self.statement)
                signed["witness_fault_domain"] = domain
                self.blocked("witness:not_independent_from_claimed_domains",
                             envelope=self.sign(signed), trust=trust)

    def test_changed_declared_domain_refused(self):
        altered = copy.deepcopy(self.statement)
        altered["witness_fault_domain"] = "site-a"
        self.blocked("witness:untrusted_fault_domain",
                     envelope=self.sign(altered))

    def test_expired_future_and_invalid_clock_refused(self):
        self.blocked("witness:stale_or_future_statement", now=ISSUED - 1)
        self.blocked("witness:stale_or_future_statement", now=ISSUED + 601)
        self.blocked("witness:stale_or_future_statement", now=True)

    def test_extra_key_and_secret_are_not_echoed(self):
        statement = copy.deepcopy(self.statement)
        statement["password"] = "PRIVATE_CANARY"
        with self.assertRaises(ValueError):
            canonical_statement(statement)
        envelope = {"statement": statement, "signature": "0" * 128}
        decision = self.verify(envelope)
        self.assertEqual(decision.status, "BLOCKED")
        self.assertNotIn("PRIVATE_CANARY", repr(decision))

    def test_malformed_nonce_or_bool_timestamp_refused(self):
        for key, value in (("nonce", "latest"), ("issued_at_unix", True),
                           ("expires_at_unix", ISSUED + 4000)):
            statement = copy.deepcopy(self.statement)
            statement[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                canonical_statement(statement)

    def test_replay_blocked_after_reopen_of_durable_sqlite(self):
        envelope = self.sign()
        prior = self.verify(envelope)
        self.connection.close()
        self.connection = sqlite3.connect(self.db_path, timeout=5)
        self.ledger = DurableWitnessLedger(self.connection)
        self.blocked("witness:replayed", envelope=envelope)
        self.assertTrue(self.ledger.is_current(prior.attestation_id, now_unix=ISSUED + 11))

    def test_attestation_revocation_persists_across_reopen(self):
        prior = self.verify()
        self.assertTrue(self.ledger.revoke("attestation", prior.attestation_id))
        self.assertFalse(self.ledger.is_current(prior.attestation_id, now_unix=ISSUED + 11))
        self.connection.close()
        self.connection = sqlite3.connect(self.db_path, timeout=5)
        self.ledger = DurableWitnessLedger(self.connection)
        self.blocked("witness:revoked", envelope=self.sign())

    def test_key_revocation_invalidates_previously_recorded(self):
        prior = self.verify()
        self.assertTrue(self.ledger.revoke("key", "synthetic-witness:key-01"))
        self.assertFalse(self.ledger.is_current(prior.attestation_id, now_unix=ISSUED + 11))
        altered = copy.deepcopy(self.statement)
        altered["nonce"] = "e" * 64
        self.blocked("witness:revoked", envelope=self.sign(altered))

    def test_witness_revocation_blocks_different_signed_nonce(self):
        self.assertTrue(self.ledger.revoke("witness", "synthetic-witness"))
        self.blocked("witness:revoked")

    def test_revocation_journal_is_append_only(self):
        self.assertTrue(self.ledger.revoke("witness", "synthetic-witness"))
        self.assertTrue(self.ledger.revoke("witness", "synthetic-witness"))
        self.assertFalse(self.ledger.revoke("attestation", "latest"))
        self.blocked("witness:revoked")

    def test_inmemory_ledger_is_refused_as_nonpersistent(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(ValueError, "nonpersistent"):
            DurableWitnessLedger(connection)

    def test_same_signed_statement_is_not_reusable_with_new_nonce(self):
        self.assertEqual(self.verify().status, "CRYPTO_VERIFIED_RECORDED")
        altered = copy.deepcopy(self.statement)
        altered["nonce"] = "f" * 64
        second = self.verify(self.sign(altered))
        self.assertEqual(second.status, "CRYPTO_VERIFIED_RECORDED")
        self.blocked("witness:replayed", envelope=self.sign(altered))

    def test_record_expiry_fails_closed_on_read(self):
        result = self.verify()
        self.assertFalse(self.ledger.is_current(result.attestation_id, now_unix=ISSUED + 601))

    def test_no_restore_or_deletion_executor(self):
        for forbidden in ("restore", "delete", "prune", "rollback", "docker"):
            self.assertFalse(hasattr(self.ledger, forbidden))
            self.assertFalse(hasattr(self.trust, forbidden))


if __name__ == "__main__":
    unittest.main()
