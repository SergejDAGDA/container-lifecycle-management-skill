# Clean rebuild of an existing Compose application

Agent workflow: `rebuild <service>`. This is an **explicit, targeted replacement** of an existing application's installation, not `deploy-repository` (first install) or `update-auto` (policy-eligible upgrades). The bundled Python helper remains read-only. Use this workflow only with an agent that has separately authorized deployment tools.

## Scope and authority

- One explicit owner request may authorize a bounded set of named applications and normal stop/remove/build/pull/recreate steps within their exclusively owned resources. Do not demand approval for each routine step. Preserve the order of the named workstream, and do not enroll `MANUAL` services in `update-auto`. A `MANUAL` entry **can** be rebuilt under a separately authorized, target-specific manual workstream after all applicable project gates are satisfied.
- `NO_TOUCH`, `external_admin`, unknown ownership, protected dependency groups, shared storage, and project-enforced invariants do **not** become writable simply because the user said "reinstall". Require separate authority from the relevant owner and a safe project-specific procedure. A missing/unverified trusted safety adapter or invalid policy is not silently waived by a manual rebuild.
- Rebuilding an application never authorizes host-wide prune, indiscriminate `docker compose down -v`, permission changes outside its verified boundary, deletion of unrelated images, service discovery/ingress changes, or external account and credential operations.

## 1. Freeze the intended data outcome

Before mutation classify **each existing state path and logical data class**, including databases, media, jobs, app accounts, credentials, keys, uploaded/generated files, models and caches:

| Classification | Rule |
| --- | --- |
| `PROTECT` | Personal documents, original media, databases or metadata the owner wants, unique user-created output and keys needed to preserve it. Verify isolated backup/export and restoration or a proven non-destructive handover **before** replacing its store. |
| `REPLACE` | Explicitly owner-approved disposable, app-owned state such as re-downloadable models, caches, temporary jobs and unused account history. Record the exact owned resources. No restore test is required for data the owner has deliberately agreed to discard. |
| `UNKNOWN` | Not deletion-authorized. Inspect only what is needed to determine ownership/value; otherwise **skip this target**, preserving existing data. |

Approval to discard models/caches does not imply approval to discard user files colocated with them. Account recreation may be acceptable if authorized, but an encryption key cannot be discarded while protected encrypted data still depends on it. Determine shared mounts, named volume contents, dependent services and credentials before deciding a resource is exclusively app-owned.

Use the smallest reliable backup method for `PROTECT`. If there is no protected state and all actual state is explicitly `REPLACE`, do **not** force a 25 GB full-host archive restore or database recovery rehearsal as a condition of clean installation. Keep a bounded pre-change source and image rollback reference when possible, and document what cannot be rolled back.

## 2. Prove deployment-source readiness before stopping anything

Apply the layout selection order and host-specific deployment receipt in [deployment-layouts.md](deployment-layouts.md). For an existing installation, **retain its already authoritative paths and persistent data names**, even when they differ from the suggested profiles. A rebuild is not permission for cosmetic filesystem migration.

Identify the deployment owner, established canonical non-secret Compose/build source, **complete ordered Compose/override file list**, project directory and source-to-server synchronization convention. Neither the newest chat notes nor a working live container is the authoritative deployment source.

Confirm all inputs needed to **recreate the candidate later**, not just boot it once: upstream release/OCI digest or pinned source commit, Dockerfile and complete build context, required packages and build arguments, external secrets referenced but not copied, interpolation environment, architecture/runtime dependencies, fixed ports, and precise bind/named-volume identities. Avoid unnecessary custom wrappers when a supported upstream image works.

Prepare candidate files under the deployment owner's approved source convention without replacing the authoritative **last-known-good deployment definition** until candidate approval. Capture immutable old image identity and source files. For remote hosts, independently compare the authoritative source with the actual server-side ordered Compose files and rendered configuration **on that host**; a local-only `docker compose config --quiet` is not proof of parity.

**Block mutation** on missing Compose overrides, missing build inputs, unresolved source ownership, shared-storage collisions, missing required secrets, or unexplained runtime/source drift. Never silently reconstruct the missing source or declare `SOURCE_READY` from a passing HTTP healthcheck.

## 3. Bounded replacement

1. Show a short pre-mutation receipt: target identities, expected new release/artifact, candidate source location, precise `PROTECT`/`REPLACE` resources, dependency and network scope, recovery/rollback boundary, and intended smoke test. One explicit authorization covers the ordinary operations inside this frozen receipt.
2. Preserve `PROTECT` state before any destructive action. Keep retained old state and images outside the disposal set until the new deployment passes.
3. Stop/recreate only the target Compose service(s) and necessary target-owned dependencies. Use a unique temporary project when safely feasible; do not attach replacement builds to unrelated live services.
4. Recreate disposable state as **new, clearly isolated** storage rather than guessing whether old named volumes are empty. Ensure target app UID/GID and directory modes permit needed writes; do not solve permissions with `chmod 777`, privileged mode or a broad recursive `chown`.
5. Install a reviewed, immutable or pinned compatible release. Do not pull `latest` implicitly or install arbitrary host packages.
6. Re-render the **effective production** Compose on the server, inspect actual new image/containers/mounts/ports/network and compare them with the approved candidate and frozen scope.

## 4. Acceptance is more than a healthy container

Require all applicable results **before** calling the rebuild complete:

- `RUNTIME_PASS`: exact image IDs and complete dependency identities, stable health, expected ports/mounts/security and no unrelated changes.
- `FUNCTIONAL_PASS`: a real, synthetic application operation with verified result (convert a test document, execute a harmless workflow, generate a test output). Accept the **actual application/UI contract**; do not invent ZIP endpoints or other expected features without evidence. Remove only synthetic fixtures.
- `STATE_PASS`: protected user files/database/metadata and required identity or permissions survive; explicitly approved replaced state is newly initialized. Never substitute container health or Restic metadata for a restore test of protected state.
- `SOURCE_READY`: the **approved last-known-good** canonical deployment source and the installed server sources correspond, including ordered Compose overrides, full build context or verifiable pinned upstream images and immutable artifact identity. Demonstrate that another operator could reproduce the installation without inferring missing files or values.
- `OWNER_ACCESS_READY`: an actual owner can initialize or access the application. Do **not** create a disposable synthetic owner account and then discard its only password while reporting completion. When secure browser setup is necessary, report `OWNER_SETUP_REQUIRED` and leave that aspect unaccepted until the owner confirms access.
- `INTEGRATION_PASS`: required project-owned dashboard/service discovery entries and dependency connectivity are present once, functional and managed by the correct owner. A separate external-admin dashboard is not automatically in scope.
- `RECORD_READY`: update the existing project-owned maintenance and deployment records only with the **verified running** identities, source authority, protected/disposable state, recovery boundary and functional smoke. Preserve conservative safety classes; a manual rebuild does not prove `AUTO_SAFE` or make invalid global policy valid.

Report `REBUILT` only when all applicable axes pass and owner setup is complete. Otherwise use `REBUILT_OWNER_SETUP_REQUIRED`, `DEPLOYED_RECORD_SYNC_PENDING`, `FAILED_AND_ROLLED_BACK`, `SKIPPED` or `PARTIAL_UNSAFE_STOP` with the exact missing evidence. Never say `MAINTENANCE_READY` unless the next bounded update can be planned from the canonical deployment source and the governing policy/safety gates are satisfied. A green smoke test alone does not confer update readiness.

## 5. Failed attempts and cleanup

Allow **one focused correction** for a demonstrated install defect. After two failed acceptance attempts, **stop that application**: diagnose the common cause, reconsider the custom wrapper versus supported upstream solution, and propose a narrower verified next plan; do not run a third incremental patch. Preserve failed candidate files in a clearly non-authoritative location for analysis. If returning to the old runtime, also restore/check the **active canonical source and project maintenance record** to the old running release. A container-only rollback with candidate Dockerfiles still active is `SOURCE_DRIFT`, not a completed rollback.

If the rollback is unsafe, incomplete, or risks protected data, stop the affected dependency workstream and report `PARTIAL_UNSAFE_STOP`; do not proceed with shared dependencies. Independent targets in an expressly authorized wave may continue only when their scopes are demonstrably disjoint.

Delete only identified temporary resources and specifically approved `REPLACE` objects. Keep protected rollback material until its retention/release is expressly resolved. Do not prune Docker globally or delete Restic backups.

## Next maintenance action

For a future `update <service>`, re-open this application's canonical source, state decision and latest runtime before applying [maintenance-protocol.md](maintenance-protocol.md). Updating the installed image without reproducible deployment source, stable persistent boundaries, applicable policy gates, owner access and application smoke is **not** a completed maintenance cycle.
