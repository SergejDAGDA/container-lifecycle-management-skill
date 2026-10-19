# Deploying application-project releases

This is the **agent-run** workflow for `deploy-project <project>`. The bundled Python CLI remains read-only and does **not** implement a production deployment executor. It is intended for local, private, self-hosted or otherwise project-managed applications whose approved release may be outside a public registry.

## Separate ownership and authority

- **Application project** owns source, approved release/build, application migration and verification contracts, and maintained product documentation.
- **Deployment project** owns Compose topology, runtime configuration, backup/recovery boundaries and an operational deployment record.
- **Project memory** indexes verified project state and decisions, but is not the authoritative build artifact or runtime record.
- **Documentation** tracks implementation and release-related behavior, not operational handoff or project-memory history.

`project_managed` is a release strategy, **not another update-safety class**. It cannot turn `NO_TOUCH`, `MANUAL` or externally owned projects into `AUTO_SAFE`. A project with `MANUAL` requires a targeted, explicitly approved application deployment workstream; it remains excluded from `update-auto`. An ordinary `deploy-project` request does **not** override `NO_TOUCH`, which requires its own distinct expressly authorized workstream before any mutation. External/unknown ownership requires appropriate external authority.

## Invocation and authorization

`$container-lifecycle-management deploy-project <project> [release-id]`

Select an existing **approved deployable** release, never merely the highest Git commit, latest local working tree or newest image tag. The project may publish source outside the server, use a private Git repository, CI build, local package or other accessible release source. If multiple releases fit, ask for the release identity once.

One user request for a named project and release authorizes the bounded expected deployment sequence and records synchronization for that project, subject to its project policies and host permission prompts. Do not ask per-step confirmations for normal backup/pull/build/recreate/health/smoke/safe rollback actions inside the approved scope. Stop at an expanded scope, changed network exposure, uncertain release identity, unapproved migration, destructive recovery or denied project ownership.

## Evidence contract — not a new mandatory handoff file

For a separately developed pet project, the **development workstream** prepares the release before requesting deployment: approve the exact build/source revision; use the application's documentation workflow (e.g. `$project-documentation release/update`) for relevant maintained technical/release documents; use its project-memory **Handoff** workflow when transferring an unfinished cross-project workstream; and give the operator a bounded deployment prompt pointing to the existing project source and release evidence. Reuse the pet project's established files and handoff convention; do not invent a duplicate record. Preparation is not a claim that deployment already happened.

The **deployment workstream** follows that prompt to discover and independently verify the prepared release, scope, source/build inputs and safety requirements. It must not choose a later Git HEAD or treat handoff text as stronger evidence than the approved release or runtime.

Discover existing authoritative records before creating anything:

1. Application root and deployment root, established from project instructions, not guessed from container names.
2. Approved release identity, source revision and immutable artifact digest or reproducible build provenance.
3. Validated **authoritative non-secret deployment source** including the complete ordered Compose/override stack, project directory, every required Dockerfile/build-context input and pinned upstream source; verify effective server-side source parity, not just existence of a local Compose example.
4. Exact service/group scope, dependency compatibility, topology contract and environment secret **references** (never values).
5. Data/schema migration plan, backup freshness and **restoration evidence** appropriate to the persistent state.
6. Application-specific read-only smoke and state-identity tests.
7. Deployed runtime identity and previous immutable rollback identity.

Accept verified release records, CI attestations, immutable tags/digests, project-owned deployment manifests or equivalent existing evidence. No new `HANDOFF.md` or duplicate release metadata file is required. A release descriptor is optional, although useful for projects without an established deployment interface.

A memory file stating "ready" cannot replace a build/CI acceptance record. A Git `HEAD` may be ahead of the released revision because documentation and other work continued. A Compose image tag is not immutable proof of the running build.

**Optional local pet-project version inspection:** When the developer's working checkout is already available and its owner permits read-only inspection, offer a focused comparison of the prepared/approved source commit, local Git HEAD and working-tree status, and the currently deployed release/image identity from the deployment record (recheck actual runtime when accuracy requires it). This is a **read-only version and drift check**, not an instruction to deploy the latest working tree, modify local source or overwrite project memory. Its absence does not block deployment if authoritative approved release evidence is available through other channels.

## Deployment phases

Choose the established site/project layout according to [deployment-layouts.md](deployment-layouts.md) before staging release sources. Never move existing state or create a competing source of truth merely to match a default profile.

**A. Discover and freeze:** Read both projects' instructions, project memory as context, actual release/build records, active Compose source stack and runtime identities. Validate installed supporting skill freshness before planning any of its writes. If a runtime-labeled Compose override is missing, do not deploy until a reproducible active source is established. Do not overwrite unrelated application code or read raw environment secrets.

**B. Validate:** Confirm the targeted project has authorized deployment ownership. Keep `MANUAL` out of generic update waves; refuse `NO_TOUCH` without a separate explicitly scoped workstream. Verify complete persistent-state contract, current compatible backup, isolated restoration evidence, migration and rollback limitations, and Compose topology parity. Do not accept a restic archive integrity check as proof of a database-consistent restore.

**C. Apply:** Stage the exact approved release, preserve the previous immutable runtime/source and a durable copy of the effective deployment inputs, then apply only the approved Compose group. Any generated release override must be durable and reproducible, not an ephemeral temporary file. Treat each stop/start/recreate/restart as a runtime mutation.

**D. Verify:** Observe health/stability; run application-owned **functional** smoke and state checks; compare mounted volumes, account state, uploads, configuration/instance identity and runtime IDs. Verify the final approved canonical source/complete build inputs reproduce the active server deployment; unresolved source drift blocks full release acceptance. Verify owner access/onboarding if the project requires it; when secure interactive setup is outstanding report `OWNER_SETUP_REQUIRED`, not full acceptance. Only perform automatic rollback when image/source rollback is proven safe for the actual migrated state. If state-aware restoration would be required, stop with `RECOVERY_REQUIRED` instead of forcing old code onto new data.

**E. Record only what happened:** Once runtime verification passes, write or update the deployment owner's existing authoritative deployment record with approved release identity, source revision, artifact/image digest, Compose source identity, actual runtime identities, timestamp, smoke checks and recovery references. Do not create a competing ledger when the project already has one.

Read [deployment-record.md](deployment-record.md) for the optional adapter interface, durable operational identity and a precise revalidation-based recovery path for `DEPLOYED_RECORD_SYNC_PENDING`. Its record example is not a required new file or replacement for the project's existing schema.

## Project memory and documentation synchronization

Successful deployment is a meaningful **Checkpoint**, not a new active Handoff:

- **Deployment skill's responsibility is verified evidence, not independent authorship of pet-project documentation.** After runtime acceptance, produce a compact deployment receipt containing environment/endpoint, exact approved release/source commit, installed image/digest, effective Compose/build fingerprint, verification time and outcome, recovery reference, and pending owner actions. Update the deployment project's own authoritative operational record.
- **Route pet-project writes to their owners.** When the separately developed pet-project root is accessible and the project's approved write policy permits it, use the pet project's `$maintain-project-memory Checkpoint` for `STATUS`, `SESSION_LOG`, handoff closure or other coordination state. Invoke `$project-documentation update` only when maintained technical/deployment documentation is actually affected or the user has requested documentation work; a routine status receipt by itself must not trigger a broad documentation rewrite. Each workflow must read/revalidate its own target files and preserve its own ownership protocol. Do not directly rewrite pet-project docs or project memory as an improvised deployment-helper side effect. Do not rewrite README merely because the deployment timestamp changed.
- **Make the feedback loop explicit.** The deployment chat orchestrates the applicable post-deploy project-memory workflow and, when warranted, the documentation workflow using the verified receipt; the development chat must read those shared updated project files before continuing work. A chat message or deployment report alone does not synchronize another chat. No automatic commit, push, GitHub publication or release approval follows from runtime deployment.
- **Prove synchronization or report pending.** Verify each authorized update and report pet-project documentation and memory separately as `UPDATED`, `UNCHANGED`, `PENDING` or `BLOCKED`. If the checkout, skill or required write authorization is unavailable, report `DEPLOYED_RECORD_SYNC_PENDING` with exact destination files/owner and evidence needed for later reconciliation; never say the development chat already knows. Do not roll back a healthy deployment solely because optional cross-project file synchronization is blocked.
- **Keep boundaries distinct.** Server-side project memory may use its own authorized `$maintain-project-memory Checkpoint` for operational facts. Application documentation owns product/development knowledge; application project memory owns coordination artifacts such as `STATUS`, `HANDOFF` and `SESSION_LOG`. Follow any `notify`, `approve-decisions` or `strict` policy and optimistic concurrency checks. A newly approved technical or business decision is not implied by a deployment.
- **Companion skills are optional integrations, not deployment prerequisites.** If absent or blocked, finish and verify the authorized Docker deployment using this skill's own operational record, then report `DEPLOYED_RECORD_SYNC_PENDING` and the exact owner-scoped documentation or memory updates still needed. Do not fabricate unavailable skills, write their files outside their contracts, or call an uncompleted cross-project sync a deployment failure.
- **Third-party repository installations are different.** `deploy-repository` normally records upstream revision, deployment source/runtime, state, recovery and version monitoring only in the deployment project's existing operational registry/policy. No separate pet-project development folder, handoff or cross-project documentation synchronization is required merely because the source came from GitHub.

## Partial failures

Deployment and cross-project documentation are **not atomic**. If runtime is verified healthy but record synchronization fails, report `DEPLOYED_RECORD_SYNC_PENDING` and the exact pending updates. Do not roll back a good runtime solely because a documentation or project-memory write failed. If deployment fails, distinguish `BLOCKED_BEFORE_MUTATION`, `FAILED_SAFE_ROLLBACK` and `RECOVERY_REQUIRED` and do not report success. A safe rollback must restore/check the **active authoritative and server deployment sources** as well as the previous runtime identity; do not leave candidate build files as the active release. After two failed acceptance attempts for the same goal, stop incremental patching and reassess the custom build/upstream alternative before another mutation.

Report six operational mutation dimensions independently: application version, runtime/container, persistent user state, deployment source, network/access and database schema. Separately report application documentation, application memory and server memory as `UPDATED`, `UNCHANGED`, `PENDING` or `BLOCKED`. Label all evidence as independently verified, declared or not verified; never conflate historical receipts with current observation.

## Practical limits

This workflow does not autonomously execute upgrades via the bundled CLI, deploy all project-managed services during `update-auto`, override security boundaries, or install/update other Agent Skills. Without authorized access to the application source or proven release/restore evidence, stop before mutation and report the precise blocker. The same workflow is usable even if the agent starts in a new chat and has no memory of the application's development conversation.
