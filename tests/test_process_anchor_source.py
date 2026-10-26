"""Process-isolated synthetic anchor-head fault tests (no network/production)."""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

HERE = Path(__file__).resolve().parent
INTEGRATION = HERE / "integration"
sys.path.insert(0, str(HERE.parent / "skills" / "container-lifecycle-management" / "scripts"))
sys.path.insert(0, str(INTEGRATION))
import test_current_anchor_source_contract as fixtures  # noqa: E402
from ci_forked_head import SyntheticProcessHead, WORKER  # noqa: E402
from current_anchor_source_contract import ReviewedHeadReader, ReviewedHeadSource  # noqa: E402

NOW = fixtures.NOW


class ProcessSeparatedHeadTests(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.CurrentAnchorHeadTests(
            "test_signed_fresh_source_and_sqlite_match_non_authorizing")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.addCleanup(self.base.close)
        self.key = Ed25519PrivateKey.generate()
        self.source = SyntheticProcessHead(
            self.key, anchor_id=self.base.anchor_id, revision=self.base.revision,
            worker_sha256="sha256:" + hashlib.sha256(WORKER.read_bytes()).hexdigest(),
            now_unix=NOW,
        )
        self.reader = ReviewedHeadReader(INTEGRATION, ReviewedHeadSource(
            source_id="ci-process-head", key_id="ci-process-key",
            fault_domain="synthetic-process-only",
            public_key=self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
            source_file_sha256="sha256:" + hashlib.sha256(
                (INTEGRATION / "ci_forked_head.py").read_bytes()).hexdigest(),
            source=self.source,
        ))

    def evaluate(self, *, connection=None, revision=None):
        return self.reader.evaluate(
            self.base.connection if connection is None else connection,
            self.base.anchor, self.base.trust,
            ledger_id="synthetic-ledger", now_unix=NOW + 1,
            trusted_min_revision=(self.base.revision if revision is None else revision),
        )

    def refused(self, code, *, connection=None, revision=None):
        result = self.evaluate(connection=connection, revision=revision)
        self.assertEqual(result.status, "BLOCKED", result)
        self.assertIn(code, result.blockers)
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)

    def test_two_separate_children_have_distinct_pids(self):
        first = self.evaluate()
        second = self.evaluate()
        self.assertEqual(first.status, "SIGNED_SOURCE_CLAIM_MATCHED")
        self.assertEqual(second.status, "SIGNED_SOURCE_CLAIM_MATCHED")
        self.assertEqual(len(set(self.source.pids_seen)), 2)
        self.assertFalse(first.restore_authorized)

    def test_concurrent_requests_are_distinct_processes(self):
        # New SQLite connection per thread, sharing only a disposable file.
        def read():
            with sqlite3.connect(self.base.dbpath) as connection:
                return self.evaluate(connection=connection)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: read(), range(3)))
        self.assertEqual([x.status for x in results],
                         ["SIGNED_SOURCE_CLAIM_MATCHED"] * 3)
        self.assertEqual(len(set(self.source.pids_seen)), 3)

    def test_child_crash_and_partial_json_fail_closed(self):
        for mode in ("crash", "drop"):
            with self.subTest(mode=mode):
                self.source.mode = mode
                self.refused("head:source_unavailable")

    def test_child_timeout_killed_and_fail_closed(self):
        self.source.mode = "silence"
        self.refused("head:source_unavailable")

    def test_child_key_substitution_denied(self):
        self.source.mode = "foreign_key"
        self.refused("head:invalid_source_signature")

    def test_old_signed_head_below_independent_floor_denied(self):
        self.source.mode = "old_revision"
        self.refused("head:below_trusted_minimum")

    def test_different_head_with_valid_signature_denied(self):
        self.source.mode = "wrong_anchor"
        self.refused("head:source_head_mismatch")

    def test_process_signed_response_replay_denied_on_new_challenge(self):
        self.assertEqual(self.evaluate().status, "SIGNED_SOURCE_CLAIM_MATCHED")
        self.source.mode = "replay"
        self.refused("head:challenge_mismatch")
        self.assertEqual(len(set(self.source.pids_seen)), 2)

    def test_missing_or_changed_child_pin_denied(self):
        self.source.worker_sha256 = "sha256:" + "f" * 64
        self.refused("head:source_unavailable")

    def test_stale_current_ledger_after_revocation_denied(self):
        old_path = Path(self.base.temp.name) / "old-worker-ledger.sqlite"
        with sqlite3.connect(old_path) as previous:
            self.base.connection.backup(previous)
        self.assertTrue(self.base.ledger.revoke("key", "synthetic-w:key-1"))
        self.base.make_anchor()
        self.source.anchor_id = self.base.anchor_id
        self.source.revision = self.base.revision
        with sqlite3.connect(old_path) as before:
            self.refused("continuity:ledger_state_mismatch", connection=before)

    def test_lost_ledger_connection_denied(self):
        self.base.connection.close()
        self.refused("continuity:unreadable_or_invalid_ledger")

    def test_fixture_not_general_purpose_subprocess_executor(self):
        for forbidden in ("restore", "delete", "prune", "shell", "run_command"):
            self.assertFalse(hasattr(self.source, forbidden))
            self.assertFalse(hasattr(self.reader, forbidden))


if __name__ == "__main__":
    unittest.main()
