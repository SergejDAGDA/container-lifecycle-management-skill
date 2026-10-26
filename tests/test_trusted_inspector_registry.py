"""Offline reviewed-inspector registry tests, with no Docker or network."""
from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "skills" / "container-lifecycle-management" / "scripts"
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(HERE))

from test_storage_provider_contract import scenario  # noqa: E402
from storage_provider_contract import validate_storage_provider  # noqa: E402
from trusted_inspector_registry import (  # noqa: E402
    ObservationTicket, RegistryRefusal, ReviewedInspector,
    ReviewedInspectorRegistry,
)


class ReviewedDemoInspector:
    """Test-defined object. The actual source file hash is checked at runtime."""

    def __init__(self):
        self.called = []
        self.fail = False
        self.snapshot = "c" * 64

    def inspect_repository(self):
        self.called.append("repository")
        if self.fail:
            raise RuntimeError("PRIVATE_CANARY")
        return {"repository_id": "test-repository",
                "repository_accessible": True, "key_retrievable": True}

    def lookup_snapshot_exact(self, immutable_snapshot_id):
        self.called.append("lookup")
        return {"snapshot_id": immutable_snapshot_id, "snapshot_exact_match": True}

    def inspect_repository_data(self, immutable_snapshot_id):
        self.called.append("check")
        return {"snapshot_id": immutable_snapshot_id, "repository_data_checked": True}


class RegistryTests(unittest.TestCase):
    def setUp(self):
        recovery, checkpoint, provider, observation, opts = scenario()
        self.recovery, self.checkpoint, self.provider = recovery, checkpoint, provider
        self.inspector = ReviewedDemoInspector()
        self.provider["adapter_source_digest"] = (
            "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        )
        self.fingerprint = validate_storage_provider(self.provider).fingerprint
        self.binding = ReviewedInspector(
            provider_id=self.provider["provider_id"], issuer_id="trusted-reader",
            provider_fingerprint=self.fingerprint,
            source_digest=self.provider["adapter_source_digest"],
            inspector=self.inspector,
        )
        self.registry = ReviewedInspectorRegistry(HERE, (self.binding,))

    def issue(self, **kwargs):
        return self.registry.issue(
            copy.deepcopy(self.provider), copy.deepcopy(self.recovery),
            copy.deepcopy(self.checkpoint), now_unix=1700000000,
        )

    def observe(self, ticket, *, provider=None, recovery=None, checkpoint=None, **kwargs):
        return self.registry.observe(
            ticket, copy.deepcopy(self.provider if provider is None else provider),
            copy.deepcopy(self.recovery if recovery is None else recovery),
            copy.deepcopy(self.checkpoint if checkpoint is None else checkpoint),
            now_unix=1700000001, **kwargs,
        )

    def test_valid_reviewed_inspector_called_in_registered_order(self):
        ticket = self.issue()
        result = self.observe(ticket)
        self.assertEqual(result.status, "CANDIDATE_ONLY")
        self.assertEqual(self.inspector.called, ["repository", "lookup", "check"])
        self.assertFalse(result.restore_authorized)
        self.assertFalse(result.off_host_proven)
        self.assertFalse(result.eligible_for_prune)

    def test_replay_refused_without_rerunning_inspector(self):
        ticket = self.issue()
        self.observe(ticket)
        calls = list(self.inspector.called)
        outcome = self.observe(ticket)
        self.assertEqual(outcome.status, "BLOCKED")
        self.assertIn("registry:replayed_or_forged_ticket", outcome.blockers)
        self.assertEqual(self.inspector.called, calls)

    def test_forged_identical_ticket_refused(self):
        ticket = self.issue()
        forged = ObservationTicket(**vars(ticket))
        result = self.observe(forged)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("registry:replayed_or_forged_ticket", result.blockers)
        self.assertEqual(self.inspector.called, [])
        self.assertEqual(self.observe(ticket).status, "BLOCKED")

    def test_ticket_expiration_and_future_clock_refused(self):
        for now in (1700000401, 1699999999):
            ticket = self.issue()
            result = self.registry.observe(
                ticket, self.provider, self.recovery, self.checkpoint,
                now_unix=now,
            )
            self.assertEqual(result.status, "BLOCKED")
            self.assertIn("registry:expired_attempt", result.blockers)
        self.assertEqual(self.inspector.called, [])

    def test_changed_repository_snapshot_source_refused_before_inspection(self):
        for dimension in ("repo", "source", "snapshot"):
            ticket = self.issue()
            p, r, cp = (copy.deepcopy(self.provider),
                        copy.deepcopy(self.recovery), copy.deepcopy(self.checkpoint))
            if dimension == "repo":
                p["repository_id"] = "other"
            elif dimension == "source":
                r["compose"]["source_digest"] = "sha256:" + "f" * 64
            else:
                cp["id"] = "d" * 64
            result = self.observe(ticket, provider=p, recovery=r, checkpoint=cp)
            self.assertEqual(result.status, "BLOCKED")
            self.assertIn("registry:attempt_scope_changed", result.blockers)
        self.assertEqual(self.inspector.called, [])

    def test_policy_cannot_select_implementation(self):
        ticket = self.issue()
        policy = copy.deepcopy(self.provider)
        policy["inspector"] = "untrusted.module:Callable"
        result = self.observe(ticket, provider=policy)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(self.inspector.called, [])

    def test_changed_adapter_pin_refused_before_issue(self):
        self.provider["adapter_source_digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(RegistryRefusal, "adapter_pin_mismatch"):
            self.issue()
        self.assertEqual(self.inspector.called, [])

    def test_unknown_provider_id_denied(self):
        self.provider["provider_id"] = "unregistered"
        with self.assertRaisesRegex(RegistryRefusal, "adapter_not_registered"):
            self.issue()

    def test_source_file_pin_is_checked_when_registering(self):
        wrong = ReviewedInspector(
            provider_id=self.binding.provider_id, issuer_id=self.binding.issuer_id,
            provider_fingerprint=self.binding.provider_fingerprint,
            source_digest="sha256:" + "f" * 64, inspector=self.inspector,
        )
        with self.assertRaisesRegex(RegistryRefusal, "inspector_source_pin_mismatch"):
            ReviewedInspectorRegistry(HERE, (wrong,))

    def test_duplicate_registration_refused(self):
        with self.assertRaisesRegex(RegistryRefusal, "invalid_or_duplicate_binding"):
            ReviewedInspectorRegistry(HERE, (self.binding, self.binding))

    def test_unreviewed_source_boundary_denied(self):
        with self.assertRaisesRegex(RegistryRefusal, "inspector_outside_reviewed_root"):
            ReviewedInspectorRegistry(SKILL, (self.binding,))

    def test_adapter_error_redacted_and_fail_closed(self):
        self.inspector.fail = True
        result = self.observe(self.issue())
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("registry:inspector_failed", result.blockers)
        self.assertNotIn("PRIVATE_CANARY", repr(result))
        self.assertFalse(result.restore_authorized)

    def test_snapshot_mismatch_returned_by_inspector_denied(self):
        self.inspector.lookup_snapshot_exact = lambda _: {
            "snapshot_id": "e" * 64, "snapshot_exact_match": True,
        }
        result = self.observe(self.issue())
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("registry:invalid_inspector_reply", result.blockers)

    def test_local_repository_cannot_be_promoted_by_registration(self):
        self.provider["storage_class"] = "local"
        self.provider["repository_fault_domain"] = "site-a"
        # Trust registry pins the complete provider descriptor, including class.
        changed_pin = validate_storage_provider(self.provider).fingerprint
        binding = ReviewedInspector(
            provider_id=self.binding.provider_id, issuer_id=self.binding.issuer_id,
            provider_fingerprint=changed_pin, source_digest=self.binding.source_digest,
            inspector=self.inspector,
        )
        registry = ReviewedInspectorRegistry(HERE, (binding,))
        ticket = registry.issue(self.provider, self.recovery, self.checkpoint,
                                now_unix=1700000000)
        result = registry.observe(ticket, self.provider, self.recovery,
                                  self.checkpoint, now_unix=1700000001)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("storage:off_host_required", result.blockers)

    def test_no_executor_exposed(self):
        self.assertFalse(hasattr(self.registry, "restore"))
        self.assertFalse(hasattr(self.registry, "capture"))
        self.assertFalse(hasattr(self.registry, "delete"))
        self.assertFalse(hasattr(self.registry, "prune"))


if __name__ == "__main__":
    unittest.main()
