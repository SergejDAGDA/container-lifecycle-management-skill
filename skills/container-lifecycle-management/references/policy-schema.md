# Portable project policy v1

The **public skill** is universal. Each project owns its own `maintenance/services.yaml` (or JSON) and adapters. This v1 schema is deliberately small and the validation tool does not silently translate a project-specific policy.

Top level: `schema_version: "1"` and `services` as a sequence or mapping keyed by name.

Minimum declared update candidate:

```yaml
schema_version: "1"
services:
  - name: demo-web
    policy: AUTO_SAFE
    ownership: sandbox
    deployment:
      compose_file: ./compose.yaml
      project: demo
      service: web
    image:
      current: example.invalid/web:1.0.0
    target:
      image: example.invalid/web:1.0.1
    state:
      complete: true
      binds: []
      volumes: []
      databases: []
      user_files: []
      secret_refs: []
    backup:
      required: false
    rollback:
      class: image_only
    health:
      container: healthy
    smoke:
      profile: http
```

`AUTO_GATED` must have `backup.required: true` plus a defined restore/migration runbook before an agent may act. Other rollback classes are `state_restore_required` and `unknown`. Neither is equivalent to a verified automated rollback.

For `PIN_ONLY` the target image must be the same immutable image content, not simply a tag that looks similar. For `MANUAL` or `NO_TOUCH` a minimal record needs `name`, `policy` and `ownership`.

`ownership` is one of `sandbox`, `application_project`, `external_admin` or `unknown`. `application_project` means the project has maintenance authority for the application. Deployment authority must still be confirmed from repo instructions. `external_admin` and `unknown` are blocked from automation.

The bundled validator checks syntax, required fields and some logical contradictions. It does not access upstream release APIs, run data restores, execute smoke probes or run upgrades.

### Runtime evidence

`--live` performs Docker metadata reads and checks one uniquely matched Compose project/service. It does not prove equality of bind contents, target compatibility, or source/Compose render. `--runtime-json` exists for synthetic fixture testing, not as trusted proof of a live server. Never treat a `GATED` result as execution authorization.

### Extending the schema

**Portable v1 is now strict.** Its root contains only `schema_version` and
`services`. Each service may declare only `name`, `policy`, `ownership`,
`reason`, `deployment`, `image`, `target`, `state`, `backup`,
`rollback`, `health`, `smoke`, and the validated optional
`release_management`. Inside the documented portable sections, unknown keys
also fail validation. Unrecognized keys or payloads are not copied into public
diagnostic output. Existing documented portable examples remain valid.

Project-specific provenance, extended release ranges, dependency groups,
additional security invariants, adapter references, and advanced backup gates
must be expressed in a **separately validated versioned project/native policy**
or explicitly normalized by reviewed consuming-project code. They cannot be
silently attached to portable v1 and assumed enforced. The
`<project>-maintenance/v1` adapter supports defined additional structures and
code-registered safety adapters; a YAML-provided path never loads Python code.
A consuming project with extra legacy fields must explicitly migrate/map
them and review each rule rather than drop unknown safety constraints.
A project-specific deployment owner must still verify additional dynamic
security/restore/approval gates; the read-only CLI cannot authorize mutations.

A project with a pre-existing differently shaped `services.yaml` must map it to the portable contract or provide a validated adapter. File naming alone does not establish compatibility.

## Extended, namespaced project policies

The CLI also accepts an extended family of policies identified by `schema: <project>-maintenance/v1` and `policy_revision: 1`. This is a generic structural adapter, not a service-specific driver. Typical extended entries use `policy_class`, `identity.compose_project`, `identity.compose_services`, `deployment.server_source`, `state_contract.completeness`, `backup`, `migration`, `smoke`, `rollback`, and `dependencies`. A top-level `service_groups` mapping may describe composite stacks and subcomponents.

The adapter validates safety invariants, mutation-reporting dimensions and actionable service declarations: explicit state boundaries, strict boolean reproducibility/backup gates, migration and rollback semantics, topology, health, and smoke expectations. For `AUTO_SAFE`, image/source-only rollback must be declared unambiguously. `validate` now returns errors for unresolved safety-critical declarations even when the YAML parses. This is deliberately fail-closed: a consuming project may need to clarify legacy `complete` state contracts whose individual fields still say `unknown`. It never mutates that project's policy. It leaves unknown migration gates unresolved. A group may refer to a subcomponent with a different policy logical name. Such aliases are reported for review, never invented or silently considered safe. `NO_TOUCH` records are excluded without Docker inspection. `MANUAL` records remain manual. For evidence-bearing scalar fields, `[]` is **not** a valid recovery method, rollback identity, smoke profile or instance identity; empty lists remain valid only where the state schema expressly permits an empty inventory. Unknown security invariants are validation errors. In both supported schemas, a malformed policy stops `--live` before Docker inspection but still reports service inventory as blocked, manual or excluded.

A service with a declared `complete` contract is still **not** automatically ready for update: current upstream release, recovery evidence, precise target, topology, and smoke must be independently proved.

The adapter is intentionally read-only. It does not translate the rich policy back into the simplified portable format or write to the original file. See `examples/native-policy.yaml` for synthetic data.


### Explicit component aliases

Extended policies may declare logical group member names that differ from their
actual Docker Compose service identities. Declare each mismatch **in the
consuming project's policy**, not in the portable skill:

```yaml
service_groups:
  demo-stack:
    services: [demo-web, demo-background]
    component_aliases:
      demo-background:
        policy_service: demo-worker
        compose_service: worker
    update_as_group: true
    manual_member_forces_group_manual: true
```

Here `demo-background` names a group component, `demo-worker` names its
existing policy record, and `worker` must exactly match one of that record's
`identity.compose_services` values. The record must declare
`dependencies.update_group: demo-stack`. Normalization of hyphens, prefixes,
container names or image tags is **never guessed**.

For `update_as_group: true`, an unresolved, incorrect or conflicting alias
makes structural validation **FAIL** rather than merely warning. A group
containing a `MANUAL` or `NO_TOUCH` policy member remains blocked for
automatic updates. Aliases do not grant new ownership or change the policies of
the underlying service records.


## Release-management strategy (optional)

A project that builds its own application releases can declare a **release strategy**
independent of the safety class. This is not an update executor or a required
migration of existing policies:

```yaml
name: local-editor
policy_class: MANUAL
ownership: application_project
release_management:
  strategy: project_managed
  release_authority: application_project
  version_monitoring: false
  automatic_updates: false
```

`release_management` accepts only the four documented fields. Unknown fields invalidate the policy, and no arbitrary field/value is emitted in JSON reports. Use separate project-owned configuration for additional metadata and secrets.

Extended policies require declared dependency-group references and a valid Compose project identity for automatic candidates. An undeclared or mismatched dependency group fails validation; it is not silently treated as a standalone service. Unknown **global** `safety_invariants` also fail closed unless each extra rule is explicitly claimed and validated by a version/digest-matched, trusted in-process adapter supplied by the consuming project. The default CLI does not load plugins from policy paths. See [safety-adapter.md](safety-adapter.md); no generic whitelist or optional adapter can override the core rules.

The same `release_management` fields are understood by portable and extended
policies. Accepted strategies: `upstream_managed`, `project_managed`, and
`externally_managed`. Accepted release authorities: `upstream_project`, `application_project`,
`deployment_project`, and `external_admin`.

A `project_managed` service requires `MANUAL` or `NO_TOUCH`, must set
`version_monitoring: false` and `automatic_updates: false`, and is never
included in `update-auto`. A targeted `deploy-project` may use a
project-approved release of a `MANUAL` service only after its normal safety,
ownership, backup and rollback gates pass. `NO_TOUCH` requires a separate
expressly authorized workstream before any mutation. External administration
cannot be silently overridden.

This setting is optional. When absent, the agent must establish release
authority from the project and runtime rather than assuming that public
GitHub releases, private Git `HEAD`, or a Docker tag are authoritative.

See [project-deployment.md](project-deployment.md) for the full agent-level
workflow and the boundary between application release records, deployment
records, project documentation and project memory. The bundled CLI **validates
these fields but does not execute `deploy-project`**.
