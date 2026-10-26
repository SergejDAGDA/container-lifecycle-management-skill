"""Experimental monotonic, compare-and-swap anchor publication contract.

This is a narrowly scoped SQLite journal owned by a *synthetic test caller*.
It neither creates the store nor selects its path. Opening requires the
expected store identity and genesis anchor from trusted calling code.
The caller MUST obtain the trusted revision floor from separately protected
state. No such external authority, independent host, backup executor,
signing service or production capability is implemented here.

A local SQLite transaction prevents competing updates to the *same* store
file from publishing two different heads for one revision. It cannot stop
rollback, deletion, cloning or coordinated forks of that underlying file.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ledger_continuity_contract import _id, _hex64

SCHEMA = "synthetic-monotonic-anchor-journal/v1"
MAX_REVISION = 200_000
GENESIS_PREVIOUS = "0" * 64


@dataclass(frozen=True)
class PublishedHead:
    status: str
    revision: int | None = None
    anchor_id: str | None = None
    blockers: tuple[str, ...] = ()
    restore_authorized: bool = False
    off_host_proven: bool = False
    eligible_for_prune: bool = False


def _chain_hash(ledger_id: str, store_id: str, revision: int,
                previous: str, anchor_id: str, previous_hash: str) -> str:
    record = [SCHEMA, ledger_id, store_id, revision, previous, anchor_id,
              previous_hash]
    raw = json.dumps(record, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _untrusted_db() -> PublishedHead:
    return PublishedHead("BLOCKED", blockers=("publish:invalid_or_unavailable_store",))


class SyntheticMonotonicJournal:
    """Does not bootstrap, generate authority or expose generalized SQL."""

    def __init__(
        self, connection: sqlite3.Connection, *, ledger_id: str,
        expected_store_id: str, expected_genesis_anchor: str,
    ):
        if (not isinstance(connection, sqlite3.Connection)
                or not _id(ledger_id)
                or not _hex64(expected_store_id)
                or not _hex64(expected_genesis_anchor)):
            raise ValueError("publish:invalid_trusted_registration")
        self._db = connection
        self._ledger_id = ledger_id
        self._store_id = expected_store_id
        self._genesis = expected_genesis_anchor

    @staticmethod
    def _valid_clockless_floor(value: Any) -> bool:
        return type(value) is int and 0 <= value <= MAX_REVISION

    def _inspect(self) -> tuple[int, str]:
        db = self._db
        registered = db.execute("PRAGMA database_list").fetchall()
        files = [row[2] for row in registered if row[1] == "main"]
        if (len(files) != 1 or not files[0]
                or not Path(files[0]).is_file() or Path(files[0]).is_symlink()):
            raise ValueError("publish:nonpersistent_store")
        if db.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
            raise ValueError("publish:corrupt_store")
        # Deliberately fixed SQL only, no table/column names from caller data.
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('synthetic_anchor_store','synthetic_anchor_history')"
        ).fetchall()
        if {row[0] for row in tables} != {
                "synthetic_anchor_store", "synthetic_anchor_history"}:
            raise ValueError("publish:missing_schema")
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND "
            "(tbl_name='synthetic_anchor_store' OR "
            "tbl_name='synthetic_anchor_history') LIMIT 1"
        ).fetchone():
            raise ValueError("publish:unreviewed_trigger")
        stored = db.execute(
            "SELECT store_id,ledger_id,revision,anchor_id FROM synthetic_anchor_store"
        ).fetchmany(2)
        if len(stored) != 1:
            raise ValueError("publish:ambiguous_store")
        store_id, ledger_id, revision, head = stored[0]
        if (store_id != self._store_id or ledger_id != self._ledger_id
                or not self._valid_clockless_floor(revision) or not _hex64(head)):
            raise ValueError("publish:store_identity_mismatch")
        rows = db.execute(
            "SELECT revision,previous_anchor,anchor_id,chain_digest "
            "FROM synthetic_anchor_history ORDER BY revision"
        ).fetchmany(MAX_REVISION + 2)
        if len(rows) != revision + 1:
            raise ValueError("publish:history_gap_or_truncation")
        previous = GENESIS_PREVIOUS
        previous_hash = GENESIS_PREVIOUS
        for index, record in enumerate(rows):
            n, prior, anchor, chain = record
            if (type(n) is not int or n != index or prior != previous
                    or not _hex64(anchor) or not _hex64(chain)):
                raise ValueError("publish:history_fork_or_invalid_row")
            if (index == 0 and anchor != self._genesis):
                raise ValueError("publish:genesis_mismatch")
            calculated = _chain_hash(
                self._ledger_id, self._store_id, index,
                previous, anchor, previous_hash,
            )
            if chain != calculated:
                raise ValueError("publish:history_hash_mismatch")
            previous, previous_hash = anchor, chain
        if previous != head:
            raise ValueError("publish:head_history_mismatch")
        return revision, head

    def current(self, *, trusted_min_revision: Any) -> PublishedHead:
        if not self._valid_clockless_floor(trusted_min_revision):
            return PublishedHead("BLOCKED",
                                 blockers=("publish:untrusted_minimum",))
        db = self._db
        try:
            if db.in_transaction:
                return _untrusted_db()
            db.execute("BEGIN")
            revision, anchor = self._inspect()
            db.rollback()
            if revision < trusted_min_revision:
                return PublishedHead("BLOCKED",
                                     blockers=("publish:below_trusted_minimum",))
            return PublishedHead("OBSERVED_LOCAL", revision, anchor)
        except (sqlite3.Error, ValueError, TypeError, OverflowError):
            self._rollback()
            return _untrusted_db()

    def compare_and_swap(
        self, *, expected_revision: Any, expected_anchor_id: Any,
        new_revision: Any, new_anchor_id: Any, trusted_min_revision: Any,
    ) -> PublishedHead:
        """Atomic conditional append only, never grant external permissions."""
        if (not self._valid_clockless_floor(trusted_min_revision)
                or not self._valid_clockless_floor(expected_revision)
                or not self._valid_clockless_floor(new_revision)
                or not _hex64(expected_anchor_id)
                or not _hex64(new_anchor_id)):
            return PublishedHead("BLOCKED", blockers=("publish:invalid_request",))
        if new_revision != expected_revision + 1 or new_anchor_id == expected_anchor_id:
            return PublishedHead("BLOCKED",
                                 blockers=("publish:nonmonotonic_transition",))
        db = self._db
        try:
            if db.in_transaction:
                return _untrusted_db()
            # SQLite serializes competing writers on this *same* file.
            db.execute("BEGIN IMMEDIATE")
            revision, anchor = self._inspect()
            if revision < trusted_min_revision:
                db.rollback()
                return PublishedHead("BLOCKED",
                                     blockers=("publish:below_trusted_minimum",))
            if revision != expected_revision or anchor != expected_anchor_id:
                db.rollback()
                return PublishedHead("CONFLICT",
                                     blockers=("publish:compare_and_swap_conflict",))
            prior_hash = db.execute(
                "SELECT chain_digest FROM synthetic_anchor_history WHERE revision=?",
                (revision,),
            ).fetchone()[0]
            calculated = _chain_hash(
                self._ledger_id, self._store_id, new_revision,
                anchor, new_anchor_id, prior_hash,
            )
            db.execute(
                "INSERT INTO synthetic_anchor_history "
                "(revision,previous_anchor,anchor_id,chain_digest) VALUES (?,?,?,?)",
                (new_revision, anchor, new_anchor_id, calculated),
            )
            db.execute(
                "UPDATE synthetic_anchor_store SET revision=?,anchor_id=? "
                "WHERE store_id=? AND ledger_id=? AND revision=? AND anchor_id=?",
                (new_revision, new_anchor_id, self._store_id,
                 self._ledger_id, revision, anchor),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise ValueError("publish:compare_and_swap_invariant")
            db.commit()
            return PublishedHead("PUBLISHED_LOCAL", new_revision, new_anchor_id)
        except sqlite3.IntegrityError:
            self._rollback()
            return PublishedHead("BLOCKED", blockers=("publish:duplicate_or_fork",))
        except (sqlite3.Error, ValueError, TypeError, OverflowError):
            self._rollback()
            return _untrusted_db()

    def _rollback(self) -> None:
        try:
            if self._db.in_transaction:
                self._db.rollback()
        except sqlite3.Error:
            pass
