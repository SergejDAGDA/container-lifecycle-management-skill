"""Experimental monotonic journal synthetic tests, all temporary files only."""
from __future__ import annotations

from contextlib import closing

import shutil
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "container-lifecycle-management" / "scripts"))
sys.path.insert(0, str(HERE / "integration"))
from ci_monotonic_fixture import bootstrap_test_only  # noqa: E402
from monotonic_head_contract import SyntheticMonotonicJournal  # noqa: E402

LEDGER = "ci-monotonic-ledger"
STORE = "a" * 64
G0 = "b" * 64
A1 = "c" * 64
B1 = "d" * 64
A2 = "e" * 64


class MonotonicHeadContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="msc-monotonic-only-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "heads.sqlite"
        self.db = sqlite3.connect(self.path, timeout=5)
        self.addCleanup(self.safe_close)
        bootstrap_test_only(self.db, ledger_id=LEDGER,
                            store_id=STORE, genesis_anchor=G0)
        self.journal = self.reader(self.db)

    def safe_close(self):
        try:
            self.db.close()
        except sqlite3.Error:
            pass

    def reader(self, db, store=STORE, genesis=G0):
        return SyntheticMonotonicJournal(
            db, ledger_id=LEDGER, expected_store_id=store,
            expected_genesis_anchor=genesis,
        )

    def publish(self, *, via=None, expected=0, old=G0, next_anchor=A1,
                floor=0, next_rev=None):
        return (via or self.journal).compare_and_swap(
            expected_revision=expected, expected_anchor_id=old,
            new_revision=expected + 1 if next_rev is None else next_rev,
            new_anchor_id=next_anchor, trusted_min_revision=floor,
        )

    def denied(self, decision, code):
        expected_status = ("CONFLICT" if code == "publish:compare_and_swap_conflict"
                           else "BLOCKED")
        self.assertEqual(decision.status, expected_status, decision)
        self.assertIn(code, decision.blockers)
        self.assertFalse(decision.restore_authorized)
        self.assertFalse(decision.off_host_proven)
        self.assertFalse(decision.eligible_for_prune)

    def test_genesis_read_without_granting_authority(self):
        current = self.journal.current(trusted_min_revision=0)
        self.assertEqual((current.status, current.revision, current.anchor_id),
                         ("OBSERVED_LOCAL", 0, G0))
        self.assertFalse(current.restore_authorized)
        self.assertFalse(current.eligible_for_prune)

    def test_cas_success_and_sequential_append(self):
        first = self.publish()
        self.assertEqual((first.status, first.revision, first.anchor_id),
                         ("PUBLISHED_LOCAL", 1, A1))
        second = self.publish(expected=1, old=A1, next_anchor=A2, floor=1)
        self.assertEqual(second.status, "PUBLISHED_LOCAL")
        self.assertEqual(self.journal.current(trusted_min_revision=2).revision, 2)
        self.denied(self.publish(), "publish:compare_and_swap_conflict")

    def test_concurrent_writers_only_one_success_one_conflict(self):
        barrier = Barrier(3)
        def attempt(anchor):
            with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
                writer = self.reader(connection)
                barrier.wait(timeout=8)
                return self.publish(via=writer, next_anchor=anchor).status
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(attempt, anchor) for anchor in (A1, B1)]
            barrier.wait(timeout=8)
            states = sorted(f.result(timeout=12) for f in pending)
        self.assertEqual(states, ["CONFLICT", "PUBLISHED_LOCAL"])
        self.assertIn(self.journal.current(trusted_min_revision=1).anchor_id,
                      (A1, B1))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM synthetic_anchor_history").fetchone()[0], 2)

    def test_no_two_heads_at_same_revision_even_with_racing_retry(self):
        self.assertEqual(self.publish().status, "PUBLISHED_LOCAL")
        with closing(sqlite3.connect(self.path)) as another, another:
            other = self.reader(another)
            result = self.publish(via=other, next_anchor=B1)
            self.denied(result, "publish:compare_and_swap_conflict")

    def test_revision_gap_reversal_same_anchor_and_bool_rejected(self):
        for rev in (0, 2, True, -1):
            with self.subTest(rev=rev):
                self.denied(self.publish(next_rev=rev),
                            "publish:nonmonotonic_transition"
                            if isinstance(rev, int) and rev in (0, 2) else
                            "publish:invalid_request")
        self.denied(self.publish(next_anchor=G0), "publish:nonmonotonic_transition")
        self.denied(self.publish(old="unknown"), "publish:invalid_request")

    def test_duplicate_old_anchor_cannot_be_republished(self):
        self.assertEqual(self.publish().status, "PUBLISHED_LOCAL")
        self.denied(self.publish(expected=1, old=A1, next_anchor=G0),
                    "publish:duplicate_or_fork")

    def test_wrong_expected_previous_refused(self):
        self.denied(self.publish(old=A1, next_anchor=B1),
                    "publish:compare_and_swap_conflict")
        self.assertEqual(self.journal.current(trusted_min_revision=0).revision, 0)

    def test_trusted_revision_floor_refuses_rollback(self):
        self.denied(self.journal.current(trusted_min_revision=2),
                    "publish:below_trusted_minimum")
        self.denied(self.publish(floor=2), "publish:below_trusted_minimum")

    def test_restart_preserves_head_and_history(self):
        self.assertEqual(self.publish().status, "PUBLISHED_LOCAL")
        self.db.close()
        self.db = sqlite3.connect(self.path)
        self.journal = self.reader(self.db)
        self.assertEqual(self.journal.current(trusted_min_revision=1).anchor_id, A1)
        self.assertEqual(self.publish(expected=1, old=A1,
                                      next_anchor=A2, floor=1).status,
                         "PUBLISHED_LOCAL")

    def test_rolled_back_sqlite_refused_against_trusted_floor(self):
        older = Path(self.temp.name) / "previous.sqlite"
        with closing(sqlite3.connect(older)) as copy, copy:
            self.db.backup(copy)
        self.assertEqual(self.publish().status, "PUBLISHED_LOCAL")
        with closing(sqlite3.connect(older)) as rollback, rollback:
            stale = self.reader(rollback)
            self.denied(stale.current(trusted_min_revision=1),
                        "publish:below_trusted_minimum")
            self.denied(self.publish(via=stale, floor=1),
                        "publish:below_trusted_minimum")

    def test_missing_database_cannot_be_trusted_without_bootstrap(self):
        lost = Path(self.temp.name) / "missing.sqlite"
        with closing(sqlite3.connect(lost)) as fresh, fresh:
            empty = self.reader(fresh)
            self.denied(empty.current(trusted_min_revision=0),
                        "publish:invalid_or_unavailable_store")
            self.denied(self.publish(via=empty),
                        "publish:invalid_or_unavailable_store")

    def test_cloned_database_with_wrong_store_identity_refused(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            other = self.reader(connection, store="f" * 64)
            self.denied(other.current(trusted_min_revision=0),
                        "publish:invalid_or_unavailable_store")

    def test_altered_genesis_refused_even_if_current_is_valid(self):
        other = self.reader(self.db, genesis="f" * 64)
        self.denied(other.current(trusted_min_revision=0),
                    "publish:invalid_or_unavailable_store")

    def test_history_tampering_refused(self):
        self.assertEqual(self.publish().status, "PUBLISHED_LOCAL")
        self.db.execute(
            "UPDATE synthetic_anchor_history SET previous_anchor=? WHERE revision=1",
            (B1,),
        )
        self.db.commit()
        self.denied(self.journal.current(trusted_min_revision=1),
                    "publish:invalid_or_unavailable_store")
        self.denied(self.publish(expected=1, old=A1,
                                 next_anchor=A2, floor=1),
                    "publish:invalid_or_unavailable_store")

    def test_history_truncation_refused(self):
        self.assertEqual(self.publish().status, "PUBLISHED_LOCAL")
        self.db.execute("DELETE FROM synthetic_anchor_history WHERE revision=1")
        self.db.commit()
        self.denied(self.journal.current(trusted_min_revision=1),
                    "publish:invalid_or_unavailable_store")

    def test_forged_head_refused(self):
        self.db.execute("UPDATE synthetic_anchor_store SET anchor_id=?", (B1,))
        self.db.commit()
        self.denied(self.journal.current(trusted_min_revision=0),
                    "publish:invalid_or_unavailable_store")

    def test_unreviewed_trigger_refused(self):
        self.db.execute(
            "CREATE TRIGGER malicious AFTER INSERT ON synthetic_anchor_history "
            "BEGIN SELECT 1; END"
        )
        self.db.commit()
        self.denied(self.publish(), "publish:invalid_or_unavailable_store")

    def test_closed_connection_denied_not_exception(self):
        self.db.close()
        self.denied(self.journal.current(trusted_min_revision=0),
                    "publish:invalid_or_unavailable_store")
        self.denied(self.publish(), "publish:invalid_or_unavailable_store")

    def test_active_transaction_denied_not_implicitly_committed(self):
        self.db.execute("BEGIN IMMEDIATE")
        self.denied(self.publish(), "publish:invalid_or_unavailable_store")
        self.db.rollback()

    def test_bootstrap_existing_store_refused(self):
        with self.assertRaisesRegex(RuntimeError, "existing tables"):
            bootstrap_test_only(self.db, ledger_id=LEDGER,
                                store_id=STORE, genesis_anchor=G0)

    def test_no_arbitrary_sql_or_restore_methods(self):
        for name in ("restore", "execute_sql", "run_command", "delete",
                     "prune", "capture", "docker"):
            self.assertFalse(hasattr(self.journal, name))


if __name__ == "__main__":
    unittest.main()
