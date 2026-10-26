# Changelog

## 0.6.0

- Rename the installed Agent Skill ID and package path to `container-lifecycle-management` and update its invocation, repository documentation, plugin manifests and test/import paths.
- Retire the obsolete active `release-v0.3.0.yml` publishing workflow; preserve the already published v0.3.0 tag, release notes and immutable historical commit `de1708213dbaf2895719120023d5bddfe42715e3` without trying to republish it.
- Keep the existing wire-level trusted safety adapter API `maintain-server-containers/safety-adapter/v1` unchanged for compatibility with consuming projects.
- This is a breaking Skill ID migration, not a production Docker feature release. Existing installations and project-level Skill ID references require separately authorized updates after a published release and verified acceptance.
- GitHub rename, code merge, published Release, local installation, and SandBox-Server adoption remain independently verifiable stages.

## 0.5.1

- Require application-scoped consistent checkpoints for targeted updates and deployments; do not invoke host-wide stop-all backup scripts without separate explicit authorization.
- Route verified pet-project deployment receipts to project-memory and impacted-documentation owners, preserving their independent write policies and pending-sync status.
- Clarify portable Docker application lifecycle scope, optional companion-skill dependencies and read-only inspection of local pet-project revisions.

## 0.5.0 - 2026-10-16

- Stabilization of the reviewed v0.5.0-rc.1 capability set; no additional Docker mutation executor or host administration responsibility introduced.
- Independent synthetic Linux Docker end-to-end exercise covered install, clean rebuild, pinned update, consistent backup/isolated restore, failure injection, source+runtime rollback and bounded cleanup on commit `4168a775b2ad0cb53d659aefb9d891a260a0dc3a` (CONDITIONAL PASS).
- Native Codex Skill discovery/invocation remained NOT VERIFIED due to local Responses transport socket error 10013; no confirmed code blocker. Do not claim real-server recovery or production backup monitoring from synthetic evidence.
- Server physical storage, disk/filesystem integrity and host-level backup placement or synchronization remain consuming-site administrator responsibilities, not portable Agent Skill release requirements.
- The final `v0.5.0` package version and publication records are separately checked before release; merge, tag, Release and installed-skill upgrade remain explicit operations.

## 0.5.0-rc.1 - release candidate (not published)

- Add first-class read-only `backup-audit [service]` and owner-authorized isolated `backup-verify <service>` workflows: event-based backup baselines, inventory of existing scheduled jobs, per-service data+source coverage, exact snapshot/restore proof, off-host independence, historical retention/milestone protection, job failures and alert evidence. No new scheduler, backup engine or destructive retention CLI.
- Add `rebuild <service>` agent workflow for clean replacement of existing Compose applications, with per-resource PROTECT / REPLACE / UNKNOWN state rules. Explicitly disposable models and caches do not require restoration rehearsal; protected personal files still require verification.
- Introduce environment-aware Linux Compose layouts (single-host system service, SSH-managed remote host, user/rootless), preserving existing site conventions and distinguishing immutable OCI images from pinned Git-built source.
- Require full canonical Compose/build source and active-server parity, genuine functional smoke, owner access, state preservation and source+runtime rollback as deployment acceptance gates. Stop incremental patches after two failed attempts.
- Extend the existing read-only Compose source preflight with opt-in `--render --check-build-sources` to test local build context and Dockerfile presence without disclosing interpolation data. Remote/additional build contexts remain separately gated.
- Add offline regression tests and a Docker Compose CLI fixture in CI.
- Fix B-01 from independent RC review: quiet Compose render and local build-file presence no longer set `source_reproducible=true`; expose separate `compose_render_verified` evidence and cover missing Dockerfile under plain render.
- This RC is an agent-operated workflow improvement **not** a production mutation CLI. Existing consuming-project validation or trusted-adapter blockers still fail closed. No server changes, merge, release publication or installed-skill update are implied.


## 0.4.0 - 2026-10-14

- Ensure CI-only PostgreSQL/Restic harness closes synthetic SQLite handles before sandbox cleanup, with offline lifecycle regressions.
- Run the full offline suite on a Windows GitHub Actions runner in addition to Linux checks.
- Reconcile YAML dependency guidance and the CLI error with noninstalling read-only preflight.
- Clarify doctor/Compose machine status and exit-code semantics, and require an agent-level runtime-to-policy coverage summary without an extra scanner.
- Fix synthetic SQLite handle lifetime, portable Restic fixture paths, and UTF-8 reads so offline Windows tests expose genuine regressions rather than cleanup/encoding failures.
- PR #26 baseline independently accepted on Windows and Linux at 393/393 offline tests each and disposable recovery CI. The v0.4.0 release package is verified separately before manual publication.
- Add a stdlib-only, noninstalling `doctor.py` to verify the exact
  interpreter can run the YAML validator; require a local reviewed venv
  rather than installing PyYAML on the inspected server.
- Add a read-only Compose source preflight for explicit ordered file sets,
  with opt-in quiet render and redacted failures. Distinguish local source
  reproducibility from remote runtime identity and change authorization.
- Require agent audits to reconcile unmanaged/unlabelled containers, whole
  dependency-group image identities, cross-project coupling and missing
  source/env; keep external-admin systems NO_TOUCH with feedback only.
- Add offline regression tests for the preflight and SQLite lifecycle.
  No automatic Docker update or server change is authorized by this release.

## 0.3.0 - 2026-10-13

- **Portable policy hardening:** undeclared portable v1 root/service/section keys now fail closed rather than silently implying support for project-specific safety or approval rules. Verify and explicitly map custom policy extensions before upgrading the installed skill.
- **Strict runtime evidence:** reject malformed synthetic runtime payloads and boolean native policy revisions; portable read-only Docker inspect now requests selected identity, image, health and mount attributes rather than full inspect metadata.
- **Experimental recovery-contract research:** provider-neutral recovery descriptors, exact Restic snapshot IDs, source-pinned read-only inspectors, signature verification, persisted replay/revocation guards, pinned ledger continuity and local atomic CAS. All are non-authorizing research contracts, **not independent off-host proof**.
- **Disposable recovery validation:** SQLite + attachment restore and PostgreSQL two-service restoration with fault-injection gates H20–H31; no production system access and no destructive retention actions.
- **Security and architecture audit:** documented actionable readiness blockers and the absence of a bundled deterministic production mutation executor.
- **Installable release marker:** `skills/maintain-server-containers/VERSION` records the skill package version; both plugin manifests are synchronized.
- **Publishing:** `v0.3.0` is a source/skill release. It neither updates existing installations nor authorizes real Docker changes.

## 0.2.0 - 2026-10-12

- Withhold unsupported service security-invariant values from all read-only CLI diagnostics; cover text and JSON reports for malformed untrusted values.

- Require exact claim coverage for every phase-specific service adapter result; omitted checks and unrelated passing checks fail closed.

- Add `deploy-project <project> [release-id]` as an agent-operated,
  explicitly authorized project-owned release deployment workflow.
- Support local/private application release authority independent of
  public upstream version monitoring.
- Add optional validated `release_management` routing in both policy formats.
- Coordinate post-deploy operational records, `maintain-project-memory`
  Checkpoint and targeted `project-documentation` update without new handoffs.
- Enforce existing MANUAL, NO_TOUCH and external ownership restrictions.
- Synthetic policy fixture and regression tests.
- Add opt-in `safety-adapter/v1` claim-validation API for trusted, pre-registered consuming-project adapters; exact version/digest pins and fail-closed PASS/BLOCK/UNRESOLVED/ERROR results. No policy-controlled code loading or default CLI adapter installation.
- Permit explicit null dependency-group references and missing manual/excluded Compose identities; reject nontext Docker ps output in both schemas, and sanitize unknown global invariant identifiers.
- Add strict named-service field validation, dependency-group references and exact membership, Compose project identity validation, and sanitized allowlisted `release_management` report fields; reject unknown release extensions rather than echo their values.
- Treat non-text native Docker metadata as unverified instead of throwing; add synthetic fourth-review regressions.
- Harden invalid external inputs: malformed group identities/dependencies and Docker inspect metadata now return explicit errors/unverified rather than crashing; unknown top-level global safety invariants fail validation.
- Prevent malformed optional release-management values from triggering type errors in either policy schema.
- Fix fail-closed regressions: forbid empty collections as backup/rollback/smoke identity evidence, while allowing explicitly empty state inventories; reject unsupported security invariants before live checks; stop all portable-policy live inspection if validation fails.
- Validate selective Docker metadata types, reject unapproved host/container networking and spoofed Docker socket sources; cover both with synthetic regression tests.
- Enforce per-service extended-policy safety semantics (state, migration, rollback, backup, topology and health), and compare only selected read-only Docker metadata. Distinguish metadata parity from proof of a safe deployment.
- Define a portable deployment record discovery/reconciliation contract and local project integration checklist.
- This is an agent workflow, **not a bundled Docker mutation executor**.
- Add bounded `deploy-repository` agent workflow for first-time installation of external Git repositories, including trust, privileges, network exposure, persistent state, secrets, dependency validation and policy adoption.
- Clarify that core deployment and operational records are standalone; `maintain-project-memory` and `project-documentation` integrations are optional, never required.

## 0.1.0 - 2026-10-12

- First public preview of the portable `maintain-server-containers` Agent Skill.
- Codex/Claude compatible packaging with a single canonical skill body.
- English and Russian user documentation.
- Versioned portable policy v1 and read-only validator, audit, status and plan CLI.
- Read-only adapter for richer namespaced project maintenance v1 policies, including policy classes, composite Compose identities and dependency groups. The original project policy is never rewritten.
- Explicit logical-to-Compose `component_aliases` for composite update groups, with fail-closed validation of unresolved or contradictory members.
- Agent-operated bounded maintenance and rollback runbooks.
- Synthetic regression tests and GitHub Actions checks.
- Explicit distinction between the read-only helper and an unimplemented deterministic update executor.

### Current limitations

- No production mutation executor is bundled in this version.
- Project-specific policy adapters, verified backup/restore and application-level smoke tests remain the responsibility of each consuming project.
- Upstream latest-version discovery is an agent workflow, not a live feature of the read-only CLI.
