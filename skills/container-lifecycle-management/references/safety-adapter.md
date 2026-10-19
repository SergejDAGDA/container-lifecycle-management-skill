# Trusted safety adapters — API v1

A consuming project may have stricter or differently named global safety
invariants. The portable skill must never ignore those rules or guess their
meaning. A versioned, **pre-registered trusted adapter** is the only supported
extension boundary. The adapter is not downloaded or imported from policy YAML.

## What is implemented

The read-only Python API offers:

- `native_policy.structure(policy, trusted_adapters=registry)`
- `safety_adapter.TrustedSafetyAdapter`
- `safety_adapter.validate_adapter_claims(...)`
- `safety_adapter.validate_adapter_service(...)`

The **bundled CLI currently has no adapter registration mechanism**. It still
rejects all unknown global rules on its own; the consuming project's reviewed
integration can supply a registry programmatically after establishing the
adapter code's integrity and provenance. This is a protocol and testable policy
boundary, not an installed project adapter or production mutation executor.

## Manifest and trusted registration

A consuming project may declare the following *data-only* manifest alongside
extended policy fields:

```yaml
safety_adapter:
  api: maintain-server-containers/safety-adapter/v1
  id: example.project-safety
  version: 1.0.0
  digest: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  required: true

safety_invariants:
  no_proven_state_contract: no_update
  image_rollback_is_not_state_rollback: true
  external_or_unknown_ownership: never_automatic
  security_release_gate_bypass: prohibited
  example_extra_gate: enforce_in_consumer
```

The manifest may only contain `api`, `id`, `version`, `digest`,
`required`. It must not contain a module path, URL, shell command,
installation instruction, Python expression, or secret. The format ID is
stable and the version must match exactly.

The **host integration**, not the policy file, imports or instantiates
audited adapter code. That integration separately verifies the distributed
adapter artifact's digest, then registers its metadata and functions.
This API compares the registered identity to the manifest; **comparing
digest strings does not itself verify binary/code integrity**.

The exact set of custom invariant IDs must match the registered adapter's
claims. IDs obey a conservative identifier grammar. All known core rules are
checked independently and cannot be relaxed by the adapter.

## Checks and statuses

`check_global(policy)` must return exactly one result per extra global
invariant, with status `PASS`, `BLOCK`, `UNRESOLVED` or `ERROR`.

`PASS` means the adapter recognized and validated its declared static
contract; it is **not** proof of backup recovery, successful database
migration, a live state comparison, or mutation eligibility.

All other statuses, missing results, extra results, invalid status types,
missing adapter, wrong digest/version, unclaimed rules, or adapter exceptions
fail policy validation. Error reports omit arbitrary policy keys, values and
exception messages. No values from `Env`, secrets, volumes or logs belong
in adapter reports.

The optional `check_service(service, evidence, phase)` protocol must return **exactly one result per registered invariant claim for each service and phase**, without missing or extra checks. It uses the same statuses and additive restrictions for `plan`, `pre_mutation`,
`post_deploy` and `restore` phases. The bundled read-only CLI does not
invoke this phase-level callback; a future tested executor must verify every
required project gate as well as the core safety policy.

## Dependency normalization belongs to the consuming project

An adapter that claims global rules **does not automatically normalize**
unrelated policy fields. The consuming project is responsible for a
separately reviewed, versioned normalization mapping, if its descriptive
dependency metadata differs from the strict public model.

Core rules remain:

- `dependencies.update_group: null` is an explicit ungrouped record.
- Non-null update groups must resolve to declared groups and exact members.
- A group alias must resolve to a real policy owner with the same update group.
- `MANUAL` or `NO_TOUCH` records may lack a Compose project identity;
  automatic candidates must have an exact reproducible Compose identity.
- A group cannot silently acquire invented companion services or be treated
  as eligible because its label happens to match a service name.
- Unknown state, an invalid state contract, or unproven recovery remains
  `UNRESOLVED` / blocked even when an adapter validates other invariants.

## Limits and next stage

The portable skill has no knowledge of any particular host's extra rules.
Creating a project-specific adapter, checking exact host-local semantics and
wiring the trusted registration into a consuming project's read-only CLI
wrapper are **separate project tasks**. The public bundled CLI deliberately
does not accept a policy-controlled adapter path or execute arbitrary code.

A full usable extension eventually needs: reviewed adapter distribution and
digest attestation, service-level dynamic evidence contracts, independent
adapter conformance tests, and a consuming-project smoke test with actual
policy data. No production privileges or container mutation should be
authorized merely because structural adapter tests pass.
