# Backup control and restore assurance

Portable **agent workflows**, not bundled Restic orchestration commands:
`backup-audit [service]` is read-only; `backup-verify <service>` requires a separately authorized, isolated restore test. The application/deployment owner owns backup scheduling, repositories, encryption keys, storage and retention. Use native existing Restic/database/Compose tooling; do not create another scheduler or backup engine.

## 1. Discover the actual contract (read-only)

For every discovered Compose service and dependency group, including unregistered or partly documented projects, map:

- Protected user-created files, media, databases, application accounts, attachments, encryption identities, and project configuration. Resolve bind mounts, named volumes, database instances and cross-project dependencies on the **Docker host**, not the client machine.
- Authoritative, ordered Compose sources/overrides, build inputs or immutable image/Git provenance, non-secret configuration, state mounts, and **secret/key references**. Never copy secret values into a report, test fixture, project memory or Git.
- Actual backup owner, backup mechanism, execution trigger, job/scheduler identity if any, log/status location, repository identity and restoration procedure. Record unknown ownership as `NOT VERIFIED`, never invent a backup task.
- Explicit coverage **per data class**: source/config, database (application-consistent method), bind files, named-volume content, attached service state and required credential availability. A container image by itself is not a user-data backup.
- Distinguish recovery goals: app-state restore, app plus configuration/source restore, and full-host/off-host disaster recovery. Do not imply that proving the first proves the third.

`NO_TOUCH`, external-admin or shared backup resources remain read-only unless their owner authorizes operations. An unregistered application remains `UNMANAGED / NOT ELIGIBLE`; do not silently treat it as covered by another app's archive.

## 2. Event-driven backup versus monitoring cadence

**Backup creation is triggered by relevant deployment events**, not by imposing a new periodic backup schedule: before approved updates, rebuilds, schema migrations, state replacement or irreversible cleanup; a fresh baseline after an application's initial accepted state where required. Capture the baseline **before** mutation if protected state exists and restoration is needed. Existing project-owned scheduled backups remain intact and may additionally run as configured.

**Monitoring can be periodic without creating backups**. Inspect whatever scheduled jobs/timers/CI workflows and event receipts already exist; check their declared cadence/last execution, missed/failed runs, repository reachability and exact snapshot IDs. A service with event-only backups should be judged against relevant change events and declared freshness requirements, not arbitrarily called stale for lacking nightly snapshots. Unknown cadence, missing event records or silent job failure is `NOT VERIFIED` / a reported finding.

Do not install, modify, enable or disable a timer, job, alert transport, backup container or daemon during `backup-audit`. Do not claim continuous monitoring or delivered notifications just because a workflow document asks for them.

## 3. Evidence for each recovery set

For each protected service/group report, without exposing sensitive values:

1. Backup source, owner, repository/storage location reference and whether the target is truly separate from the source host/failure domain. A second directory, mounted disk or Restic repository on the same host is **not proven off-host** merely by name.
2. The most recent relevant successful run/event, time, **exact immutable snapshot ID** or equivalent, job exit/result, applicable pre-change version/Compose source identity and data scope.
3. The application-consistency procedure: SQLite checkpoint/consistent copy or logical database dump/snapshot as appropriate; for PostgreSQL or another transactional database, show a coherent database-and-files boundary, not a live raw-copy assumption.
4. Restic `snapshots` and `check` evidence (or tool-equivalent), with result/time, but do not convert repository integrity into a successful *application restore*. A failed/inaccessible repository, missing key reference or unspecified decryption recovery is a blocker for claiming recoverability.
5. Actual isolated restore evidence: exact snapshot, verified artifacts/checksums, database/file compatibility, usable app-level fixture result, dependencies and image/source correspondence. Record when it was last executed. A synthetically restored database is not proven production recovery.
6. Restore prerequisites and any known missing elements: encryption keys, DB users, external services, permissions, network identity, downtime, and exclusive ownership. Mark incomplete sets `BACKUP_COVERAGE_GAP`.

Never print credentials, command output containing secrets, Restic repository passwords, authentication tokens or sensitive file names. Record existence/availability and owner-controlled recovery method only.

## 4. Verification and failure handling

`backup-audit` uses existing read-only list/metadata/log checks where authorized, and must **not** run a backup, restart containers, create a restore volume or execute destructive retention operations.

`backup-verify <service>` requires an explicit approved scope for an **isolated disposable** restore. Confirm repository read rights, key availability without disclosure, exact snapshot identity, acceptable resources and cleanup boundary before creation. Restore database **plus** protected files and required source identity, run a representative application-level read/write or authentication smoke with synthetic data when possible, and verify retention of the source application's original state and identity. Never restore test data into live persistent volumes or make the real app available under the test identity.

Exercise fail-closed negative cases in synthetic fixtures, not against real backup availability: lost source state, missing/unavailable repository and missing/unavailable recovery key. For unavailable access or restoration evidence, report `RESTORE_NOT_VERIFIED` or `RECOVERY_BLOCKED`, not PASS. Do not provoke a real production outage to test these cases.

Any backup method that would stop/restart containers (especially a global backup job impacting other services) is a **runtime mutation**. Inspect and declare its blast radius; do not run it in a read-only audit or as an unreviewed side effect of an application update.

### Application-scoped checkpoints are the default for maintenance

For an authorized update, rebuild or project deployment, choose an application-consistent checkpoint covering the named service and its verified, necessary dependency group only. A checkpoint may pause those named components if required for database/file consistency; it must **not** stop or restart unrelated applications merely because an existing host-wide backup script does so. Do not invoke a global stop/start backup script as an implicit fallback. Keep existing administrator-owned scheduled jobs untouched.

Reuse approved native database tools, Compose and backup utilities (such as a project-owned Restic wrapper) rather than adding another backup engine. Record the precise paused services, source/image and state coverage, snapshot identity and recovery prerequisites. This rule does not permit skipping a needed database-consistent snapshot, required restore proof or encryption key. If the scoped method is missing or cannot produce a safe checkpoint, mark the target update `BLOCKED` and explain the smallest missing application-level procedure. A wider outage/backup is a **separately authorized operation** with its own explicit impact scope, never authority inferred from a request to update one application. Respect external-admin and `NO_TOUCH` ownership.

## 5. Retention, historical checkpoints and alerts

- Respect project-owned retention rules. Keep protected historical/**milestone** checkpoints separate from the rolling window; the newest N backups must not silently evict the only known-good recovery point. Record actual depth, age, expected capacity, recoverability and any retention exceptions.
- If corruption, incomplete backup, unclear snapshot lineage, missing key or failed restore is suspected, **suspend all deletion/prune** until investigated. Never execute `restic forget --prune`, repository cleanup or backup deletion from a read-only audit, and never infer deletion authority from an application-update request. Any destructive retention change needs a separately reviewed, owner-approved bounded plan.
- Report missed or failed jobs, unexpected backup-caused restarts, insufficient coverage, untested restore, retention risk, and loss of off-host independence. Check whether a project-provided notification/monitoring mechanism exists and has a **verified delivery path**; missing or untested alerting is `ALERTING_NOT_VERIFIED`, not evidence that an alert was sent.
- The agent may recommend alert configuration or an external periodic audit, but must not promise unattended watches/notifications until an authorized scheduler and tested delivery integration actually exist.

## 6. Minimum backup-control receipt

For each service or dependency group, output a compact matrix with:
`owner | state classes covered | source/config covered | trigger/schedule observed | last successful event/snapshot | verification of archive | last independent restore | off-host status | retention/milestone protection | notification status | gaps / next action`.

Keep **BACKUP_PRESENT**, **BACKUP_COMPLETE**, **RESTORE_VERIFIED**, **OFF_HOST_VERIFIED** and **ALERT_DELIVERY_VERIFIED** as separate evidence statements; use `NOT VERIFIED` or explicit blockers for missing proof. A passing read-only `maintenance.py` policy validation, Docker healthcheck, Restic snapshot list, or synthetic CI fixture cannot promote any of those dimensions to production PASS.

Before an authorized stateful update, block deployment if required app-consistent baseline, key availability or safe recovery path cannot be evidenced. An expressly owner-disposable `REPLACE` state class does not require a backup/restore exercise, but that permission does not cover protected data or shared resources.

## Scope limit

This skill audits and guides bounded, owner-approved backups and isolated restore checks. It does **not** include an always-on daemon, scheduled backup creation, Restic retention executor, production disaster-recovery guarantees, or off-host storage provisioning. These must be separately built/configured and verified in the consuming deployment.