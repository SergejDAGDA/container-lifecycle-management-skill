# Security and architecture audit — 2026-10-13

**Repository:** `SergejDAGDA/agent-maintain-server-containers`  
**Audited baseline:** `main` at `b4cccaf34832a16692b32587be04ffa70cb82a25` (merged PR #20)  
**Published baseline:** `v0.2.0` (manifest versions `0.2.0`)  
**Scope:** repository code and documents, GitHub Actions results, synthetic test contracts through H31.  
**Not performed:** independent penetration test, production-system test, live remote backup, restore of user data, third-party dependency vulnerability scan, proof of external witness independence, or installed-skill verification.

## Executive decision

- **GO for the existing narrowly described read-only CLI and agent runbooks at their documented v0.2.0 capability level**, with the input-hardening follow-ups below. A read-only policy report is not an approved change plan.
- **GO for keeping synthetic recovery/evidence fixtures as experimental development tools**. They demonstrate the stated fault/refusal contracts on an ephemeral GitHub runner, not recoverability of arbitrary applications.
- **NO-GO for claiming a production-safe, unattended or deterministic Docker maintenance/backup/restore/decommission executor.** Its independent backup authority, trusted evidence source, action-specific authorization, operational mutation lifecycle and installed-artifact provenance have not been built or certified.
- **NO release/version bump from this audit.** The next clean-up PR may fix scoped defects and documentation, but should not describe those changes as completion of E01–E04 or independent disaster-recovery readiness.

This decision distinguishes *design completeness*, *CI-backed local exercise*, *installed skill capability*, and *real operational authority*. No amount of same-runner signed synthetic evidence can establish an off-host failure domain.

## Audit method and evidence

1. Inspected `README.md`, `README.ru.md`, `SKILL.md`, the roadmap and lifecycle/recovery design, installation manifests, policy schemas and the safety-adapter contract.
2. Reviewed the production-facing Python path: `maintenance.py`, `native_policy.py`, `native_runtime.py`, `native_safety.py`, `safety_adapter.py`, and `release_management.py`.
3. Reviewed the experimental contract stack: recovery-set, migration/failure domain, storage provider, registered inspector, Ed25519 witness, SQLite replay ledger, signed continuity, current-head reader and monotonic CAS.
4. Inspected unit tests, `.github/workflows/tests.yml`, `.github/workflows/integration.yml`, and the isolated SQLite/Restic + PostgreSQL/Restic harness, including H20–H31.
5. Checked the GitHub Actions **main-branch results associated with the exact audited commit**: `Tests` and `Disposable Compose recovery fixture` both completed successfully. The main suite reports **360/360 tests PASS**; the integration harness reports H31 PASS and synthetic owned-resource cleanup PASS. This proves only the checks exercised by those workflows. The reviewer did not independently execute the suite against production or clone the repository to a local workstation.

### Traceability to the original lifecycle roadmap

| Roadmap | Observed repository state | Audit classification |
| --- | --- | --- |
| C01–C02: state vocabulary, typed persistence | Documented state vocabulary, strict existing policy gate and experimental typed recovery-set declarations; no new production-validated policy migration | **Design / partial experimental** |
| C03–C04: trusted adapters and evidence levels | Pre-registered safety-adapter API; experimental source-pinned inspectors and witness/continuity contracts; no installed independently secured authority | **API and synthetic tests, not deployed trust** |
| B01–B03: recovery sets and consistent capture | Generic recovery-set contract, Restic ADR and real **synthetic** SQLite/PostgreSQL+files capture in disposable CI | **Synthetic integration achieved; no production provider** |
| B04–B06: checkpoints, restore, retention | Immutable snapshot/checkpoint identity, tested synthetic restore and protected dry-run; no operational scheduler, live backup policy or authorized pruning executor | **Synthetic restore + advisory only** |
| T01–T03: harness, failures and CI | Two CI workflows, strict disposable fixture scope, migration/recovery faults through H31 | **Demonstrated on GitHub runner** |
| E01–E04: deterministic executor, lifecycle, records and approval | Read-only CLI and agent-operated procedures; no implemented state-changing executor with fresh scoped authorization, locks, durable resumption and rollback | **Not implemented** |
| D01: installed-tree integrity | Manifests at v0.2.0 and update caveat; no independently verified installed-tree digest/rollback workflow | **Not implemented** |
| D02: truthful public documentation | Both READMEs distinguish current read-only CLI from future features; recovery documentation repeatedly flags same-runner trust limits | **Mostly complete, audit link/maintenance needed** |

## Findings and required disposition

### A-01 · P0 release blocker: missing deterministic operation executor

**Evidence:** [CLI supported operations](../skills/container-lifecycle-management/scripts/maintenance.py#L18-L22) contain only `validate/audit/status/plan`; [README capability table](../README.md) explicitly states no bundled production mutation executor; [roadmap E01–E04](ROADMAP.md) requires an action plan, bounded authorization, revalidation, locks, actual mutation record, health check and recovery policy.

**Risk:** treating an agent runbook or a passing safety schema as an authorization to update or destroy Docker state bypasses the unimplemented executable gates. This is a *capability gap*, not evidence of a hidden mutation path in the CLI.

**Disposition:** hard NO-GO for unattended/container-mutating claims. **Separate future project**: implement a deterministic executor *first only in disposable CI*, with action/scope-bound authorization, revalidation, concurrency locks, crash recovery and state-aware rollback. Do not declare the next minor version complete merely after documentation cleanup.

### A-02 · P0 release blocker: no genuinely independent recovery or current-head authority

**Evidence:** [Restic ADR](ADR-001-DISPOSABLE-RESTIC.md) accepts Restic for **local runner-only** testing; [experimental H24–H31 record](RECOVERY-CONTRACT-EXPERIMENTAL.md) explicitly declines off-host proof; [current-head source](../skills/container-lifecycle-management/scripts/current_anchor_source_contract.py) and [local CAS](../skills/container-lifecycle-management/scripts/monotonic_head_contract.py) rely on caller-registered code, a trusted external revision floor, and filesystem-backed SQLite. Synthetic signing material, data and test authorities are on the same runner.

**Risk:** a privileged actor can roll back both the database and locally supplied revision/anchor reference, or cause shared-fault-domain loss. Cryptographic signature verification establishes control of a configured signing key, not physical separation or the truth of a remote recovery claim.

**Disposition:** do not advertise independent disaster recovery or readiness for automatic state-changing operation. A future live milestone requires independently secured and operator-reviewed off-host storage, separate key custody, protected monotonic authority, real restore drills and a defined RPO/RTO. Those require *separately authorized* infrastructure work; this audit does not permit it.

### A-03 · P0 release blocker: no production backup/restore integration across arbitrary apps

**Evidence:** [recovery_contract.py](../skills/container-lifecycle-management/scripts/recovery_contract.py) is read-only and its `RESTORE_TESTED` fields are declarations; [synthetic PostgreSQL fixture](../tests/integration/pg_group_harness.py) restores an isolated two-service sample; [roadmap B01–B06](ROADMAP.md) includes still-missing production adapters, complete external-state inventories, consented restore and separately authorized destructive retention.

**Risk:** the synthetic PostgreSQL/SQLite proof does not establish correctness for unknown user databases, upload stores, object storage, key rotations, migration hooks or application-specific health probes.

**Disposition:** define the minimum *real* app recovery contract separately, including consistent DB capture and file/reference semantics, and validate it on explicitly chosen disposable applications before a bounded live pilot. Never convert local `LOCAL_EVIDENCE_CONSISTENT_ONLY` into automatic eligibility.

### A-04 · P1 policy-hardening: portable schema does not explicitly reject undeclared extension fields

**Evidence:** [portable normalization](../skills/container-lifecycle-management/scripts/maintenance.py#L61-L110) checks essential keys, service names and selected nested types, but does **not** apply a top-level or service-level unknown-field allowlist. [Portable validation](../skills/container-lifecycle-management/scripts/maintenance.py#L113-L171) inspects selected gates only. By contrast [native safety adapters](../skills/container-lifecycle-management/scripts/safety_adapter.py) explicitly fail on unregistered additional safety claims.

**Risk:** a consuming project might assume an extra portable-policy safety rule such as `safety_invariants` or a service-specific approval setting is enforced when the validator never interprets it. Existing read-only CLI does **not** use these fields to authorize mutation, so this is a semantic assurance issue, **not a demonstrated production bypass**.

**Disposition:** add a synthetic regression for unknown safety-critical portable fields, clarify which extension namespaces are allowed, and either reject unknown fields or require a reviewed adapter declaration. Preserve documented backward compatibility; do not silently delete project-owned extensions.

### A-05 · P1 trust / supply chain: sources and installations are not reproducibly pinned

**Evidence:** [unit CI](../.github/workflows/tests.yml) uses `ubuntu-latest` and GitHub Action major tags; [integration CI](../.github/workflows/integration.yml) installs `restic` from current Ubuntu APT state; [Python requirements](../skills/container-lifecycle-management/scripts/requirements.txt) use open minor-version ranges. Both [plugin manifests](../plugin.json) still report v0.2.0. [Roadmap D01](ROADMAP.md) calls for signed/hashed installed artifact provenance.

**Risk:** green CI on one day is not reproducible proof of identical dependencies, code-distributed artifacts or an installed agent skill on a server. This is not evidence that a dependency is compromised.

**Disposition:** for a future release, pin Actions by reviewed immutable commits, define reproducible test tool versions/digests and package/install attestation. Separate the experimental `cryptography` dependency from the minimal read-only CLI where practical, with tests for both install modes. Do not share local installed-skill hashes in a public report.

### A-06 · P1 structural complexity: proof subsystem is test-rich but not an application boundary

**Evidence:** eight+ adjacent modules model provider declarations, fault domains, read-only inspectors, signed witness receipts, replay prevention, continuity, source challenge and local monotonic publication; [PostgreSQL harness](../tests/integration/pg_group_harness.py) is a **large single test driver** containing H20–H31. [H31 aggregator](../tests/integration/ci_e2e_fault_chain.py) is explicitly a **test-only** module.

**Risk:** more contract layers increase the number of clocks, keys, identities, revisions and status enums that future code must reconcile. Unit/CI success does not test a real executor calling these components or a remote trust boundary. One long fixture makes failures and coverage attribution harder to maintain.

**Disposition:** freeze feature expansion; map each contract to an intended production caller or mark it test-only. Prefer a simple dependency graph and one canonical evidence/status vocabulary before adding the executor. Refactor fixture phases for readability only when needed for an actual failed test or pilot, not as another abstract framework.

### A-07 · P2 data minimization: portable live inspection requests more Docker data than it reports

**Evidence:** [portable CLI](../skills/container-lifecycle-management/scripts/maintenance.py#L174-L245) calls `docker inspect --format "{{json .}}"`, which materializes the full container inspect document in-process, then emits a limited projection. [Native CLI](../skills/container-lifecycle-management/scripts/native_runtime.py#L68-L84) already uses a targeted per-field projection that avoids environment and log content.

**Risk:** unnecessarily reading full inspect metadata into the agent's process increases exposure of environment-derived configuration or other sensitive operational metadata if debugging and error handling later change. This audit found **no evidence that the current normal report prints the full inspect document**.

**Disposition:** use a targeted projected Docker inspect format for portable mode too, retain strict type checks and synthetic regressions, and continue reporting fixed diagnostic identifiers for malformed metadata.

### A-08 · P2 input robustness: a few boundary types deserve adversarial tests

**Evidence:** [native policy revision](../skills/container-lifecycle-management/scripts/native_policy.py#L125-L128) compares with `!= 1` instead of strict integer type, so Python equality may accept boolean `True`. [Synthetic runtime JSON](../skills/container-lifecycle-management/scripts/maintenance.py#L387-L415) accepts a top-level mapping but does not explicitly validate that every selected per-service runtime value is a mapping before `assessment(...).get`.

**Risk:** malformed untrusted or test-provided data can be treated as valid structure or cause an avoidable exception rather than a fixed fail-closed result. There is no evidence this permits a Docker mutation.

**Disposition:** add precise negative tests (`policy_revision: true`, runtime evidence values that are strings/lists) and make invalid input return conservative structured errors without echoing raw payloads.

### A-09 · P2 evidence semantics: avoid overloading successful local statuses

**Evidence:** experimental result statuses include `CANDIDATE_ONLY`, `CRYPTO_VERIFIED_RECORDED`, `CRYPTO_MATCHED`, `SIGNED_SOURCE_CLAIM_MATCHED`, `PUBLISHED_LOCAL` and `LOCAL_EVIDENCE_CONSISTENT_ONLY`; each independently defaults operational authorization fields to false. Existing docs mostly explain the limits.

**Risk:** human operators or later adapter code could mistakenly treat a positive-sounding status as full remote proof.

**Disposition:** retain explicit `restore_authorized=False` and `off_host_proven=False` default guards. For a future executor, define a single typed action-eligibility decision that **cannot** be derived from these statuses without independent evidence and exact approval scope. Never silently equate signature with verified recoverability.

## Trust-boundary map

| Authority / data | Present and verified | Not established |
| --- | --- | --- |
| Project YAML policy | Parsed and assessed by read-only CLI; extra native safety rules need reviewed adapter API | Whether a declared backup or rollback is actually possible |
| Docker metadata | Synthetic tests and selective read-only runtime comparison | Data integrity, migration compatibility, application smoke or latest release |
| Restic repository | CI-owned encrypted local repository; exact snapshot and integrity checks | Off-host placement, independent keys, real app coverage or production access |
| Witness signatures | Ed25519 verification against a registered key in synthetic contracts | Independently operated witness or truthful physical-domain assertions |
| Replay/continuity journal | SQLite atomic uniqueness, revocations, hash chain, synthetic rollback refusals with supplied floor | Privileged rollback of SQLite **and** its trusted high-watermark together |
| Anchor-head source | Code-pinned synthetic reader, fresh challenge, signed reply | Remote durable high-watermark service, separate operator, protected signing key |
| Operation authorization | Safety classes and runbooks in skill; all experimental proof statuses non-authorizing | Durable scoped executor, locks, approved production restore or prune |
| Installed artifact | Public manifests v0.2.0 | Hash of a particular installed copy; verified update/rollback of the skill |

## Audit decision for the next PR and beyond

### PR #22: bounded remediation / documentation freeze, **not** a production release

- **Must:** fix/cover A-04 and A-08 with targeted read-only negative tests without changing the semantics of existing trusted project records.
- **Should:** implement A-07 projection/data minimization and confirm no regression in portable and native audit reports.
- **Should:** make capability and dependency/packaging boundaries explicit in English and Russian README, with reproducibility plan for A-05.
- **Should:** align the roadmap with proven synthetic work without marking E01–E04 or real backup provider support complete.
- **Must not:** add more witness/anchor layers merely to increase test counts, enable `prune`, publish a misleading ready-to-use executor, or access any real backup/server.
- **Exit:** reviewed PR diff, green unit CI, disposable integration when affected, accurate changelog and both README languages; decide release version only after checking actual user-facing functionality and installed-copy reproducibility.

### A separate operational implementation milestone remains

After PR #22, if actual automated service upkeep remains the product goal, plan an explicitly authorized pilot around a **disposable synthetic application**: operational adapter source, state inventory, approved immutable target, independent recoverable backups, failure-domain guarantees, one bounded executor, and truthful mutation/deployment records. Only after those gates pass can a separate, manually authorized limited live pilot be considered.

## Final audit statement

The synthetic tests are valuable and passed on the audited main commit, but the system is **not** independently proven recoverable or authorized to mutate real Docker state. Its strongest current deliverable is a conservative read-only Agent Skill plus a growing CI-tested experimental recovery/evidence toolkit. The responsible next step is bounded hardening and scope control, **not indefinite additional contract construction**.
