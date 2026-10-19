# Deployment record adapter and pending synchronization

The deployment project owns the *operational* record of which release actually
runs. The application project owns approved source/builds and product docs.
Project memory is a secondary evidence index, never the runtime source of truth.

For separately developed pet projects, the deployment workflow must produce a verified runtime receipt and **orchestrate** feedback into the application's existing project files through their respective owners: `$project-documentation update` for maintained technical/deployment documentation and `$maintain-project-memory Checkpoint` for current status and coordination artifacts. The deployment skill itself owns only its operational record and evidence receipt; it does not directly author app-project documentation or project memory. This handoff requires actual access and project-policy authorization. The pet-project files are a time-stamped projection of observed deployment facts, not a second source of runtime authority; the development chat must reread them when work resumes. If tools, access or permission are missing, report `DEPLOYED_RECORD_SYNC_PENDING` with the exact evidence/destination rather than falsely claiming cross-chat synchronization. No implicit commit/push of application code or documents is authorized.

## Discover rather than invent

Find the established project record and its owner through project instructions,
existing deployment descriptors, current runtime source records and repository
structure. Choose *one* authoritative operational record for each project
identity. Do not assume the newest file, chat handoff, or `STATUS.md` has
deployment authority. If multiple records disagree, stop before mutation.

Only if no existing record convention exists, agree a small schema and stable
location with the deployment owner before the first deployment. Do not silently
place a new file inside canonical project memory.

## Minimal adapter contract

A project-specific adapter should provide these semantics regardless of
whether its record is JSON, YAML, a database or an existing release manifest:

- `discover(project_id)`: locate the owner and canonical record location
- `read(project_id)`: read the current record and revision/fingerprint
- `prepare(release)`: verify that the new receipt can represent the target
- `commit_verified(revision, receipt)`: update **only after runtime verification**
  using a compare-and-swap/atomic write where practical
- `reconcile_pending(revision)`: check runtime and source again, then finish
  only uncompleted owner-scoped documentation/memory synchronization

The following *logical fields* need representation. Field labels may map to
preexisting local naming; this is not a mandatory new JSON file:

```json
{
  "schema": "maintenance-deployment-record/v1",
  "project_id": "example-app",
  "release": {
    "approved_release_id": "example-release-1",
    "source_revision": "0123456789abcdef",
    "immutable_artifact": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "deployment": {
    "compose_sources": ["deploy/app.compose.yaml"],
    "source_fingerprint": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "runtime": {
    "observed_at": "2026-01-01T00:00:00Z",
    "image_ids": ["sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"]
  },
  "checks": {
    "runtime_health": "VERIFIED",
    "application_smoke": "VERIFIED",
    "persistent_state_identity": "VERIFIED",
    "restore_evidence": "VERIFIED_BEFORE_DEPLOY"
  },
  "recovery": {"previous_release": "example-release-0", "method_ref": "approved-runbook"},
  "sync": {
    "server_memory": "PENDING",
    "application_memory": "PENDING",
    "documentation": "UNCHANGED",
    "pending_operations": ["server-memory-checkpoint", "application-memory-checkpoint"]
  }
}
```

Secret values never belong in the receipt: store *references only*. If there
is no current restore evidence or backup requirement does not apply (isolated
new installation), use an explicit justified `NOT_APPLICABLE` rather than
inventing `VERIFIED`.

## Reconciliation without a handoff

`DEPLOYED_RECORD_SYNC_PENDING` means the target runtime was verified but
at least one authorized record update did not complete. Preserve its exact
owner/root and intended change in the deployment record where supported or,
when no record write is possible, the operator's completion report.

On a later run, re-read the operational record and **independently** verify
current source, runtime identity and fingerprints. Do not apply a stale pending
memory diff to a newer build. Invoke optional memory/documentation skills only
when available and permitted by that project's current protocol and write
policy; otherwise keep the pending status visible.

A missing optional Agent Skill cannot invalidate a healthy deployment,
authorize a rewrite of canonical memory, or justify creating a duplicate
`HANDOFF.md`. Statuses are `UPDATED`, `UNCHANGED`, `PENDING`, or `BLOCKED`;
these are coordination outcomes, not proof of application health.

## Consuming-project integration rules

A deployment adapter should discover the consuming project's requirements,
which can include app/dashboard metadata labels, service grouping, firewall/
ingress policy, directory conventions, secret storage, policy paths, and
deployment record formats. These belong in that project's own maintained
instructions or checked-in configuration, **not** as hardcoded names in the
public skill.

Before an authorized first installation, enumerate such local obligations and
verify them alongside normal Compose, image, state, permission and network
checks. Unknown obligations are an integration blocker, not a reason to
invent environment-specific defaults.
