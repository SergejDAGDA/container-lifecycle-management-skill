# Experimental recovery-set evidence contract

**Status:** draft and automated CI contract only. Not a deployed backup manager, Docker executor, stable API, or new v0.2.0 policy schema. See [roadmap](ROADMAP.md), [lifecycle design](LIFECYCLE-RECOVERY-DESIGN.md), and [Restic fixture ADR](ADR-001-DISPOSABLE-RESTIC.md).

Source: `skills/container-lifecycle-management/scripts/recovery_contract.py`. It uses only Python's standard library; no connection to Docker, Restic, storage backends, SSH, secrets or cloud APIs.

## What this contract distinguishes

1. **Recovery-set declaration:** precisely identified application, Compose source digest, immutable image digests, typed assets (database, volumes, filesystem, object store and external key-recovery reference), documented consistency method. `validate_recovery_set` generates a canonical SHA-256 fingerprint for a valid declaration. A hash proves **declaration identity**, not the integrity of underlying data.
2. **Checkpoint evidence:** immutable provider snapshot ID tied to that fingerprint, event class, full capture flag, repository check flag, isolated restore check flag and successful application smoke. `RESTORE_TESTED` requires all actual checks; a syntactically complete declaration is insufficient.
3. **Retention dry-run:** no deletion occurs. `plan_retention_dry_run` rejects unknown/malformed IDs, mismatched recovery fingerprints, missing recovery tests and incomplete inventory. Independently verified snapshots, pre-migration/pre-decommission checkpoints, active rollback references and legal/manual holds are protected.

Strictly separating **declared**, **captured**, **repository checked** and **restore tested** avoids making 'backup exists' interchangeable with 'application can recover'.

## Example (invented values only)

```python
from recovery_contract import validate_recovery_set, validate_checkpoint, plan_retention_dry_run

declared = {
    "schema": "recovery-set/v1",
    "application": "artificial-demo",
    "compose": {
        "project": "isolated-fixture",
        "source_digest": "sha256:" + "a" * 64,
    },
    "images": {"app": "sha256:" + "b" * 64},
    "assets": [
        {"id": "sqlite", "kind": "database", "backend": "sqlite",
         "consistency": "sqlite_backup_api",
         "reference": "logical-test-database", "recovery_required": True},
        {"id": "uploads", "kind": "user_files", "backend": "filesystem",
         "consistency": "snapshot_quiesced",
         "reference": "artificial-attachments", "recovery_required": True},
        {"id": "key-authority", "kind": "secret_reference",
         "backend": "external_reference", "consistency": "immutable_reference",
         "reference": "approved-key-source", "recovery_required": True},
    ],
}
result = validate_recovery_set(declared)
assert result.valid
```

**This sample is not runnable backup execution.** Checkpoints are evaluated only after a separate provider has produced and independently verified real proof. Never set the booleans to `True` merely to satisfy validation. An attacker-controlled checkpoint document cannot self-attest a restore test: a future trusted executor must bind those fields to independently captured evidence and approved verification authority.

## Supported failure handling

- Invalid asset type, duplicate identity, unknown consistency method, unproven required state or absent external key-recovery responsibility -> invalid recovery-set declaration.
- Missing/restored-without-check/negative smoke/foreign recovery fingerprint -> not restore-tested; contradictory proof -> invalid checkpoint.
- Any unknown retention target, invalid checkpoint inventory, missing restore-tested reference or unauthorized class -> no automatic candidate deletion.
- All successfully restore-tested points are conservatively protected because the experimental contract has **no trusted timestamp, replacement-proof or independent removal authorization yet**.
- `permitted_candidates` are advisory candidates for a *future* separately approved deletion plan; they are **not permission to delete**. There is no deletion function.

## Currently tested with Restic

The GitHub-hosted disposable integration runner uses a synthetic SQLite application with three artificial attachments. It prepares a consistent checkpoint using SQLite's backup API, captures it into an encrypted local Restic repository, validates the exact snapshot ID and repository contents, restores into a fresh project and runs application smoke. The harness then produces a provider-neutral checkpoint evidence declaration and confirms that retention does **not** consider the only verified working checkpoint deletable.

See `tests/integration/harness.py` and `tests/test_recovery_contract.py`. This proves a synthetic CI recovery set, **not** a live or remote Docker recovery guarantee.

## Important future gates

- A production implementation must independently verify evidence, record timestamps/freshness, failure domains, storage ownership, secrets authority and application-consistent DB capture.
- Support off-host/immutable backup destinations, repository access controls and emergency key recovery.
- Define retention holds and legal constraints with an independently authorized deletion workflow (with dry-run and restored replacement), never blindly call `restic forget --prune`.
- Determine coherent capture of databases + user files under concurrent writes, grouped Compose services, external object stores, PostgreSQL, and restore compatibility across migrations.
- Version the resulting stable contract and plugin manifests together at release time. Merely landing source on `main` does not automatically update installed skills.

The current shipped `maintenance.py` remains read-only.

## Experimental migration-sensitive rollback refusal (H06)

The separate pure module `migration_contract.py` evaluates a proposed
**image-only rollback** following an observed incompatible schema change and a
bounded interruption *after the schema transaction commits*. Its only outcomes
are `BLOCKED` and `RECOVERY_REQUIRED`. Both set
`image_only_allowed=False`. Neither executes a restore or authorizes an
image change.

`RECOVERY_REQUIRED` requires a matching `recovery-set/v1` fingerprint,
complete isolated-restore + application-smoke proof for a held
`PRE_MIGRATION` checkpoint, exact image and Compose identities, fresh
expected/observed runtime identity parity, a complete database migration scope
and an observed changed schema. The response identifies only the checkpoint ID
and a **separately authorized** state-aware recovery planning task. Any
incomplete evidence, stale identity, unresolved scope, missing protection,
unknown schema or unproven failure becomes `BLOCKED`, without an executable
rollback path.

The disposable GitHub Actions harness now exercises a **synthetic-only** SQLite
v1 to v2 table/column rename, commits it, injects a later simulated upgrade
failure and confirms that the old v1 reader rejects it. It verifies that the
previous Restic checkpoint remains independently checked, restored into an
isolated v1 Compose project and smoke-tested. It never runs a Docker image
update, downgrade, production restore or backup deletion. H06 tests the
migration **refusal** contract, not H04's full update executor or recovery
authorization. Caller-provided evidence is not independent attestation. A
future trusted executor must establish and bind runtime observations and proof
before acting.

## Synthetic PostgreSQL two-service recovery fixture (F2, experimental)

`tests/integration/pg_group_harness.py` is a **separate** GitHub-hosted
CI-only exercise. It provisions an ephemeral internal-network Compose
`db + worker` group with an immutable PostgreSQL image reference and
throws away its database cluster in tmpfs after the test. Synthetic
identifiers and three related binary attachments are generated fresh.

The test uses PostgreSQL's `pg_dump -Fc`, which reads from a consistent
database snapshot, while the fixture has no attachment writers. It captures
a group checkpoint with the exact two required members, Compose source
digest, pinned image identity, dump checksum, and per-file checksums. It
rejects any damaged dump, missing file, partial group membership, foreign
source identity or mismatching recovery metadata **before** restoring.

An independent Compose project initializes a fresh database, receives
`pg_restore`, and runs SQL/attachment verification both inside the DB
container and through the independent worker. The source group is checked
again, and only fixture-owned containers, an internal network, ephemeral
tmpfs and synthetic directories are cleaned. The fixture has no published
ports, production credentials or real server access.

**Scope limits:** This is a coherent capture only for a quiescent artificial
file set, not a guarantee of atomic capture under concurrent DB/file writes.
The local package is not an independently stored or Restic-protected
off-host checkpoint. It has checksums and an isolated restore smoke, not
proof of production-grade durable backup, replacement retention, automatic
failover or a production multi-service restore executor. Provider integration,
multi-service state contract trust, interruption, cancellation and
state-aware migration remain separate future steps.

## F2 PostgreSQL encrypted Restic recovery set (H20/H21, synthetic CI)

The CI-only `pg_restic_fixture.py` extends the strictly bounded local
`ResticFixture` runner. After PostgreSQL `pg_dump -Fc`, quiesced
attachments, and manifest validation, it archives the **whole two-service
recovery package** into a fresh encrypted Restic repository on the ephemeral
GitHub runner. It validates an exact 64-character immutable snapshot ID,
source path and fixture-only tag, and runs `restic check --read-data`. No
`latest`, ambiguous prefix, remote store, `forget`, `prune`, or destructive
command is accepted.

A separate staging tree is restored **from the encrypted repository**. Its
manifest, dump and three attachment checksums are validated before starting
the separate PostgreSQL + worker Compose group, which receives `pg_restore`
and then independently checks SQL records, worker access, and attachment
digests. The original group and checkpoint remain unchanged. Incorrect
password, incomplete or corrupted packages, foreign snapshot identities,
missing proof, and pre-existing restore destinations fail closed. A
provider-neutral `recovery-set/v1` evidence record is initially
`REPOSITORY_CHECKED`; only after separate application smoke does the
test mark it `RESTORE_TESTED`, and retention dry-run must protect the
verified checkpoint.

Passing H20/H21 demonstrates a **local, encrypted, fully synthetic** snapshot
and isolated multi-service recovery. It is NOT off-host disaster recovery,
atomic live database-plus-file capture with concurrent writes, a trusted
attestation engine, a production provider or an authorized Docker executor.
Production migration, rollback, backup scheduling and deletion remain
separately gated.

## Failure-domain declaration and source-loss fault injection (H22/H23)

`failure_domain_contract.py` is an experimental, strictly pure/read-only
**declaration gate**. It compares the exact recovery-set fingerprint,
restore-tested checkpoint and immutable snapshot ID with declared source,
repository and independent key-authority fault domains. Unresolved identities,
shared failure domains, on-host repositories, missing key or snapshot access,
repository outages, stale evidence, and incomplete restore tests are
`BLOCKED`. Even a fully populated off-host topology declaration returns only
`CANDIDATE_ONLY`, never independent proof or permission to restore. Untrusted
booleans or source-controlled assertions cannot establish a real off-host
recovery guarantee.

H22 in the disposable F2 test shuts down the **synthetic** primary Compose
project, destroys its tmpfs PostgreSQL database and removes its artificial
three-file source plus original staging checkpoint. The pre-existing encrypted
local Restic repository is then used to recreate the full two-service group
and verify database/file application smoke. H23 temporarily removes access to
the synthetic Restic key and repository, verifying refusal and subsequent
availability of the *same* immutable snapshot. The loss simulation is bounded
to unique GitHub-hosted CI test directories and fixture-owned containers.
No production or user backup is involved.

**Important:** The local Restic repository and temporary key still share
the original GitHub runner fault domain. Accordingly, the new contract
**must report off-host disaster recovery as BLOCKED** even though the
synthetic application successfully reconstitutes on the same runner.
Actual independent fault-domain delivery, key escrow, disaster-region
availability and independently witnessed restore remain unimplemented.

## Provider-neutral Backup Storage API proposal (PR #13, experimental)

`storage_provider_contract.py` defines a **pure, read-only** interface for
future reviewed storage inspectors. It does not implement Restic, Kopia, Borg,
SSH, object-store APIs, capture, transfer, restore, remote access or deletion.
Policy documents must never select executable adapter code.

- `backup-storage-provider/v1`: declares logical provider/repository identity,
  backup engine, independently pinned adapter source digest, expected source,
  storage and key fault domains, and fixed observational capabilities.
  `validate_storage_provider` rejects unknown fields, unsafe identifiers,
  unreviewed capabilities and unknown adapter pins. It returns a canonical
  fingerprint of the **declaration only**, not verified storage placement.
- `backup-storage-observation/v1`: binds a claimed observation to the
  canonical provider fingerprint, exact checkpoint ID, recovery-set fingerprint,
  Compose source digest, repository identity, reviewer-selected issuer ID and
  a bounded observation timestamp. Missing key, unavailable repository,
  unreadable snapshot, changed source, stale clocks and mismatched issuers
  fail closed.
- `BackupStorageInspector` is a **typing Protocol only**, exposing hypothetical
  read-only repository inventory and data-integrity inspection. Real adapters
  must be reviewed and registered by trusted code, not selected from a policy.
- `assess_storage_evidence` requires source/repository/key domain separation
  and independently recoverable keys for disaster-recovery candidates.
  Explicit local storage may be inventoried but never qualifies for off-host
  disaster recovery. No structure or self-reported boolean authenticates its
  own provenance. Even matching observations return `CANDIDATE_ONLY` with
  `restore_authorized=False`, `off_host_proven=False` and
  `eligible_for_prune=False`.

H24 applies the same contract to the existing *local* encrypted Restic
PostgreSQL fixture after actual CI restore and application smoke. The result
**must be BLOCKED for off-host readiness**, despite exact snapshot, content
checks and successful local restoration.

**Out of scope:** trusted adapter registration, signed attestations or
independent witnesses, remote backend provisioning, key custody, production
credentials, retention mutation, production backup lifecycle, or treating the
caller-supplied clock, expected fingerprint and issuer as independently trusted.
The current `maintenance.py` CLI and v0.2.0 policy parser are untouched.

## Code-registered read-only inspector and one-use observations (H25)

`trusted_inspector_registry.py` is an **experimental in-process gate**.
The calling program explicitly constructs an inspector object and supplies
a `ReviewedInspector` binding. No policy string, YAML adapter path,
dynamic import or observation JSON selects executable code. The registry
re-hashes the **class source file** under an explicitly designated reviewed
repository root and checks the SHA-256 against the provider declaration
before each observation. An unknown or changed source/adapter pin fails closed.

A scope-bound observation ticket includes the exact provider fingerprint,
recovery-set fingerprint, snapshot ID and Compose digest. It is consumed
on **first use**, including failures, and cannot be replayed in that registry
instance. A short freshness bound rejects late or future uses. The registry
itself dispatches only the code-registered inspector's three read-side
methods and constructs the observation from their structured replies,
instead of accepting an arbitrary observation document. Invalid responses
or thrown exceptions are converted into constant diagnostic identifiers.

H25 exercises this with a **directly instantiated, synthetic-only, read-side**
PostgreSQL Restic inspector on the ephemeral GitHub runner. The real local
Restic snapshot is checked again, the one-use ticket is consumed, a replay
is rejected, and off-host readiness remains `BLOCKED`. No new production
observer, remote backend, backup capture/restore authority or prune API is
exposed.

**Trust limitations:** Source hashing detects changed bytes in an identified
local file. It is **not** a code-signing system, protected bootstrap, sandbox,
remote evidence signature or defense against a compromised Python process,
monkey-patched methods, forged trusted-root registration or malicious
reviewed code. The registration site, source pins, trusted clock and runtime
remain the responsibility of an independently reviewed caller.
Tickets are only replay-protected in one process and are not a durable
distributed anti-replay store. Every result remains non-authorizing even
when it says `CANDIDATE_ONLY`. The shipped v0.2.0 skill and CLI are unchanged.

## Independently pinned signed witness evidence and durable replay (H26)

`witness_attestation_contract.py` experimentally separates **cryptographic
authenticity** from backup and disaster recovery readiness. A
`TrustedWitness` registers a raw Ed25519 verification public key, key ID
and declared fault domain through reviewed code, never through a
source-controlled attestation document. A canonical
`independent-witness-attestation/v1` signed statement binds the witness,
key and domain, exact provider/recovery-set fingerprints, immutable Restic
snapshot ID, Compose digest, repository identity, random nonce, and bounded
issue/expiry times. Signature verification uses maintained OSS
`cryptography`; it does not implement homegrown cryptography.

A `DurableWitnessLedger` is constructed using an explicit SQLite connection
opened by the trusted caller. It requires a filesystem-backed database and
records verified attestation IDs with transactionally enforced uniqueness.
Reopening that same database rejects reused evidence after a process restart.
Append-only revocations may invalidate an attestation ID, a witness or its
key, including evidence recorded **before** the revocation. The ledger cannot
create a DB from an arbitrary policy path, issue signing keys, restore
applications, mutate Docker or prune backups.

A syntactically and cryptographically valid independent-domain declaration
only produces `CRYPTO_VERIFIED_RECORDED`, with
`restore_authorized=False`, `off_host_proven=False` and
`eligible_for_prune=False`. Missing or stale signature, scope mismatch,
same declared failure domain, invalid restore proof, revocation, duplicate
receipt and unavailable journal block acceptance.

H26 in the disposable CI PostgreSQL fixture generates an ephemeral
synthetic Ed25519 key, signs a fully artificial witness claim after the
actual isolated Restic restore smoke, commits it into a runner-owned SQLite
file, reopens that file to test replay refusal, and revokes the key.
**The synthetic signing key resides on the same CI runner and does not
represent an independently operated witness**. H24/H25 continue to
classify the actual local Restic repository as `BLOCKED` for off-host
disaster recovery.

Threat-model limitations: public-key pin provenance, independent witness
operation and truthfulness, trusted clock, SQLite file ownership, durable
replication, tamper resistance, backup of the journal, distributed replay
protection, secure signing-key custody and revocation dissemination are not
implemented. Ledger files can be rolled back or replaced by a privileged
host adversary. A successful signature cannot establish physical domain
independence or automatically permit any real-world change. Adding the
`cryptography` verification dependency to source requirements is not
a v0.2.0 release or installed-skill update.

## SQLite rollback-detection using externally pinned signed state (H27)

`ledger_continuity_contract.py` is a read-only verifier for the logical
contents of the already-existing `witness_used` and `witness_revoked`
tables. It validates the filesystem-backed SQLite connection supplied by
reviewed code, checks the schema, reads a consistent snapshot of both tables
and produces a deterministic domain-separated SHA-256 digest plus row counts.
It does not write to the journal or expose table contents in diagnostics.
Unknown rows, missing tables, concurrent caller transactions or corrupt
databases fail closed.

A `witness-ledger-anchor/v1` statement binds a logical ledger ID, digest,
counts, revision (total recorded event count), nonce, signer/key identities,
and bounded validity times. Verification requires **both** a valid Ed25519
signature from a pre-registered public key and an exact
`expected_current_anchor_id` provided separately by trusted calling code.
A previously valid signature cannot pass when an actually current,
independently secured anchor ID is supplied and the SQLite file is rolled
back to older state. A different journal or altered rows likewise mismatch.
This is a read-only comparison, not a ledger updater or anchor publisher.

H27 stores a copy of a **synthetic** SQLite journal before witness-key
revocation, signs its subsequent state after revocation, and confirms the
current state matches while the older SQLite copy and an old signed statement
are refused against the new anchor ID. It runs entirely inside the ephemeral
GitHub runner, after H26, without real server or user files.

**Critical limitation:** This code has no independent high-watermark
service, protected publication path, monotonic counter, remote witness or
authenticated clock. H27 **simulates** an independent anchor by passing a
pin from its test code. If an adversary can replace the journal AND the
latest expected ID, it can replay a matching old signed anchor. Signatures
are not proof of physical independence, and SQLite contents can be modified
by privileged host access. The caller must obtain the genuinely latest
anchor ID from a separately protected and freshness-verified authority
before any reliable rollback decision. In the absence of such an authority,
this verification is not production rollback protection. No status
authorizes restore, deploy, update, deletion or off-host recovery claims.

## Code-registered signed current-anchor source (H28, experimental)

`current_anchor_source_contract.py` adds a reviewed, read-only source interface
for the current anchor ID expected by the preceding
`ledger_continuity_contract.py`. The trusted calling code constructs and
registers an actual reader object, its Ed25519 verification key, source ID
and SHA-256 pin for the implementation source file inside a reviewed root.
Untrusted policy files, response documents and URLs cannot select or import
an adapter.

Each verification makes a new random challenge and calls the registered
source's read-only `read_current_head(ledger_id, challenge)` method. The
response is a strict Ed25519 signed `current-anchor-head-response/v1`
statement binding source/key/ledger identities, exact immutable anchor ID,
revision, challenge and short issue/expiration window. An unavailable source,
unknown fields, invalid signature, replayed challenge, stale response,
incorrect head ID or revision and source-code pin mismatch fail closed.

The verifier then requires the claimed head to match a separately signed
ledger anchor and the **actual current SQLite witness ledger contents**.
A `trusted_min_revision` must be supplied by reviewed calling code to
prevent acceptance of a freshly signed older head when a higher revision
is already known. A missing/invalid minimum blocks the request. Successful
verification returns only `SIGNED_SOURCE_CLAIM_MATCHED`, which never
authorizes restore, pruning, migration or a claim of off-host proof.

H28 exercises a same-runner synthetic head responder in GitHub CI using
ephemeral Ed25519 keys. It checks matching state, forced source outage,
replay of a previously signed response under a new random challenge and
rollback to a pre-revocation synthetic SQLite file. These are **contract
checks**, not operational independent-anchor service tests.

**Unimplemented trust dependencies:** physical separation or operation of
the source, true monotonic publication, externally protected high-water
revision, clock integrity, durable challenge tracking, network transport,
TLS or hardware key custody. A compromised or dishonest registered source
can newly sign an old anchor, especially when the independently trusted
minimum revision is stale or fabricated. Source-code hashing is not
sandboxing or a defense against process-level compromise. The fake CI
source and signing key are on the same runner, so the tests **do not prove
actual independence or rollback safety under a simultaneous compromise**.
The current published v0.2.0 skill remains unchanged.

## Separate synthetic signing process via bounded stdio (H29)

PR #18 adds a test-only process boundary instead of relying solely on an
in-process signing object. A fixed, source-pinned `ci_forked_head.py`
adapter launches exactly `ci_head_child.py` using an isolated Python
interpreter, with bounded JSON stdin/stdout, a short deadline, checked
exit status and explicit child cleanup. The worker has no network endpoint,
listening socket, server credentials, backup or mutation capability.
No configuration document selects its command or an arbitrary subprocess.

The subprocess receives a synthetic Ed25519 seed through a private test
pipe, signs a response bound to the original challenge and immutable
anchor ID, and exits. Separate requests result in different process IDs.
Concurrent synthetic readers use independent SQLite connections and
validate the same signed high-watermark. Fault injection exercises early
process death, timeout, malformed/truncated response, unexpected signing
key, old revision, changed head, replay of a previous response and
rollback to an earlier synthetic SQLite journal. Every failed condition
is interpreted conservatively and never authorizes restore or deletion.

H29 in the disposable PostgreSQL/Restic fixture verifies two concurrent
real child-interpreter responses, different child PIDs, rejection of a
crashed signer and refusal of another signing key after H28. Everything
runs on the same ephemeral GitHub CI host and is cleaned there.

**This is process isolation for testing, not an independent trust domain.**
The parent deliberately holds the signing seed and sends it to each child.
A shared host compromise, a hostile reviewed adapter, a malicious Python
runtime or stale trusted revision can defeat this test model. No
long-lived separate operator, durable signing service, protected transport,
remote monotonic store, hardware-backed key or inter-host availability is
implemented. No production backup executor or v0.2.0 release is enabled.

## Local synthetic monotonic anchor publication with atomic CAS (H30)

`monotonic_head_contract.py` defines a narrowly scoped, **experimental
local** compare-and-swap head journal. It requires an already-created
filesystem-backed SQLite store, a caller-pinned store ID and a caller-pinned
genesis anchor. No policy path, arbitrary SQL execution, general restore,
deployment or backup mutation API exists. The implementation never
bootstraps a missing database. Only `tests/integration/ci_monotonic_fixture.py`
may create an empty **synthetic** test store.

A complete bounded history is checked in a consistent transaction: exact
revision sequence, previous-anchor linkage, deterministic SHA-256 chain,
unchanged pinned genesis and store identity, and current-head agreement.
CAS uses SQLite `BEGIN IMMEDIATE` and exact expected
revision/previous-anchor match. It atomically appends one revision and
updates the head, or returns `CONFLICT` without changing storage.
Duplicate IDs, history gaps, foreign/changed store IDs and malformed rows
block access. Read and write operations require a `trusted_min_revision`
from separately reviewed calling code. The returned statuses
`OBSERVED_LOCAL` and `PUBLISHED_LOCAL` never authorize production work.

The new H30 CI scenario starts **two independent Python interpreters**,
each attempting to publish a different head for revision 1 of the same
disposable SQLite file. Exactly one succeeds; the other conflicts.
A new child publishes revision 2 only from the committed revision 1.
Tests also restore a snapshot of the old synthetic store and simulate
complete store loss. Both fail closed against the caller-supplied
higher revision floor. After each run the entire fixture is removed.

**Critical limitation:** SQLite atomicity prevents forks only for writers
on the **same writable database file**. A separately cloned file, privileged
storage rollback, changed genesis registration, fabricated revision floor,
corrupt host, or remote split-brain is not prevented. Neither this local
CAS journal nor the two CI child processes constitute an independently
operated monotonic authority. No actual remote publication, immutable
external high-watermark, multi-host quorum, signature release, protected
key custody or production executor is implemented. A deliberate synthetic
bootstrap is not a safe recovery procedure after real state loss.

## H31 integrated local recovery evidence fault matrix (synthetic CI only)

H31 unifies the existing disposable PostgreSQL/Restic recovery evidence
into one non-authorizing test-only evaluation
(`tests/integration/ci_e2e_fault_chain.py`). It checks the exact immutable
snapshot through the reviewed Restic fixture, the registered signed current
anchor source, the actual SQLite witness-ledger digest and revocations,
and a caller-pinned monotonic publication head. A problem at **any** stage
blocks the whole local assessment, with fixed, non-secret diagnostic codes.

The H31 sequence runs only after the F2 isolated PostgreSQL restore and
application smoke, H20–H30. The original synthetic source is already lost,
and the synthetic application must still be healthy in its separate restored
Compose project. The chain then exercises a temporary missing Restic key,
unavailable local repository, crashed child signer, substituted signing key,
replayed signed response, pre-revocation witness SQLite rollback, stale
head after CAS publication, rolled-back CAS store, and total publication
store loss. Tests restore only their own temporarily parked key/repository,
start new disposable child readers, and confirm local evidence consistency
returns with the correct latest signed anchor and CAS state. Previously
revoked witness receipts must remain revoked.

The only successful status is `LOCAL_EVIDENCE_CONSISTENT_ONLY`, carrying
`chain:independent_off_host_not_proven`. All results retain
`restore_authorized=False`, `off_host_proven=False`, and
`eligible_for_prune=False`. It is **never** a production-recovery or
disaster-readiness approval. Missing trusted inputs, unavailable snapshots,
incorrect signatures, altered journals and missing/stale publication
state fail closed.

This is a synthetic acceptance test of already existing contracts, **not**
an independent production service, real off-host repository, restored
tenant data, live infrastructure or external monotonic authority. Its
revision floors, key placement, process trust and filesystem state all
remain controlled by a single ephemeral GitHub runner. The test does not
implement production backup capture, failover, deletion, automatic
recovery or a deploy executor. No installed v0.2.0 skill is modified.
