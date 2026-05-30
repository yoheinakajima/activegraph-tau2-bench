# Phase 9 external audit-store and vault readiness

Phase 9 is a **design-only, mock-contract readiness specification** for two
future live-manager prerequisites:

1. an external append-only audit store; and
2. a credential-vault resolver that accepts only inert handle references.

It does not enable live reactive-manager execution. It does not let ActiveGraph
control tau2 lifecycle or task state, does not feed state packets back into tau2,
does not mutate tau2-bench behavior, does not mutate vendored tau2 source, does
not import or run tau2 benchmark episodes, does not call LLM/API services, does
not require API keys, and does not handle real credentials.

## Smoke command

```bash
python scripts/run_external_readiness_contracts.py
```

A successful run prints:

```text
external_readiness_contracts_passed
```

The command regenerates/preserves the Phase 8 artifact chain and writes a
timestamped artifact directory:

```text
runs/<timestamp>/
  events.jsonl
  activegraph_trace.json
  state_packets.jsonl
  state_packet_index.json
  manager_plan.json
  manager_decisions.jsonl
  replay_plan.json
  fork_plan.json
  diff_report.json
  contract_decisions.jsonl
  contract_report.json
  live_opt_in_decisions.jsonl
  live_readiness_report.json
  live_manager_proposal.json
  audit_log.jsonl
  audit_integrity_report.json
  credential_policy_report.json
  sandbox_policy_report.json
  live_readiness_audit_report.json
  external_audit_store_contracts.json
  external_audit_store_decisions.jsonl
  vault_integration_contracts.json
  vault_integration_decisions.jsonl
  external_readiness_report.json
  summary.md
  final_state.json
  raw.log
```

## External audit-store purpose

The external audit-store contract describes what a future live-manager phase
would need before audit evidence could leave the local review artifact directory:
append-only writes, deterministic read-back verification, external immutability,
hash-chain anchoring, and source artifact anchoring. Phase 9 deliberately uses
only an in-memory deterministic mock store. There is no network client, database
client, cloud service, or production storage backend.

## Audit-store interface contract

`experiments/reactive_manager/external_audit_store.py` defines an
`ExternalAuditStore` protocol with:

| Interface member | Requirement |
| --- | --- |
| `store_available` | Future implementation must report availability before writes are accepted. |
| `externally_immutable` | Future implementation must prove records are immutable outside the local run directory. |
| `append(record)` | Appends exactly one canonical audit record and returns an acknowledgement. |
| `read_back(audit_id)` | Reads back the stored record by deterministic audit ID for verification. |

The deterministic mock accepts only records that preserve the existing Phase 8
audit hash chain and source artifact links.

## Append-only and hash-chain anchoring rules

A future external store must satisfy all of these rules before it could become
live-ready:

- records are append-only;
- duplicate `audit_id` values are rejected;
- the first record anchors to the fixed all-zero genesis hash;
- each subsequent `previous_audit_hash` equals the prior accepted record hash;
- each `audit_hash` is recomputed from canonical JSON with `audit_hash` removed;
- every record includes a non-empty `source_artifact` link;
- every source artifact link resolves to a generated local review artifact.

## Read-back verification

Every accepted append must be followed by read-back verification. The read-back
record must match the appended canonical record exactly. Any mismatch is treated
as a failing contract and keeps `external_audit_store_live_ready=false`.

## Failure modes

The Phase 9 smoke covers these external audit-store failure modes with mock
contract decisions:

- `store_unavailable`;
- `write_rejected`;
- `read_back_mismatch`;
- `hash_chain_mismatch`;
- `duplicate_audit_id`;
- `missing_source_artifact_link`.

These are contract scenarios only. They do not contact a real external service.

## Vault resolver interface

`experiments/reactive_manager/vault_integration.py` defines a
`VaultCredentialResolver` protocol with:

| Interface member | Requirement |
| --- | --- |
| `vault_runtime_available` | Always `false` in Phase 9. |
| `validate_handle(reference)` | Validates only a future-vault handle string. |
| `resolve(handle)` | Future placeholder; the Phase 9 mock always fails closed. |

The deterministic mock validates shape only and never resolves secret material.

## Credential handle schema

The only accepted reference form is:

```text
credential://future-vault/<name>
```

`<name>` must begin with an ASCII letter or digit and may contain ASCII letters,
digits, `_`, `.`, or `-` for up to 64 characters total in the name.

## Rejected secret patterns

Phase 9 rejects and redacts these patterns from artifacts:

- raw API-key-like or token-like values;
- `api_key`, `secret`, `token`, or bearer-style raw material;
- environment-variable lookup forms such as `env:NAME`, `${NAME}`, and
  `environment://...`;
- filesystem secret reads such as `file://...`, `/run/secrets/...`, or relative
  secret paths;
- wrong schemes such as `vault://...`;
- invalid handle names such as path traversal under `credential://future-vault/`.

Reports store sanitized references only. Raw credential material is not written
to artifacts.

## Readiness report schema

`external_readiness_report.json` uses schema version
`activegraph_external_readiness_report.v1` and summarizes:

| Field | Meaning |
| --- | --- |
| `status` | `external_readiness_contracts_passed` or `external_readiness_contracts_failed`. |
| `live_ready` | Always `false`. |
| `live_execution_available` | Always `false`. |
| `live_execution_unavailable_fail_closed` | Always `true`. |
| `external_audit_store_live_ready` | Always `false`. |
| `vault_integration_live_ready` | Always `false`. |
| `readiness_result` | Forced-false design-only readiness summary. |
| `external_audit_store` | Append-only, read-back, immutability, hash-chain, source-link, and failure-mode coverage. |
| `vault_integration` | Handle schema, unavailable runtime, rejected raw/env/file patterns, and no raw material in artifacts. |
| `blocker_summary` | Remaining blockers and disabled-by-construction notes. |
| `no_tau2_control_flow_executed` | Always `true`. |
| `no_state_packets_fed_back_into_tau2` | Always `true`. |
| `no_llm_api_calls_made` | Always `true`. |
| `no_tau2_benchmark_episodes_imported_or_run` | Always `true`. |
| `no_live_execution_code_path_added` | Always `true`. |

## Compact aggregate smoke command

Phase 9 also adds a compact smoke aggregator:

```bash
python scripts/run_all_smokes.py
```

It runs all local smoke commands in order, prints a compact status table by
default, writes full combined logs to `aggregate_raw.log`, and writes
`aggregate_summary.md` plus `aggregate_final_state.json`. Use `--verbose` to
print full child-script output while retaining the same artifacts.

A successful aggregate run reports:

```text
all_smokes_passed
```

## Why `live_ready` remains false

`live_ready` remains false because Phase 9 is not a live-manager phase. It only
specifies and tests deterministic mock contracts for future external audit-store
and vault-integration requirements. There is no real immutable external store,
no real vault runtime, no secret resolution, no live sandbox enforcement, no
operator-approved live execution path, and no tau2 ownership handoff.

## Requirements before a future live-manager phase

A future live-manager phase would require a separate explicit design and review.
At minimum it would need:

- a real external immutable audit store with reviewed availability, append-only,
  read-back, retention, and tamper-evidence properties;
- hash-chain and source-artifact anchoring that survives process and host
  failure;
- a real vault integration that resolves only scoped handles without exposing raw
  secret material in logs or artifacts;
- reviewed vault access policy, audit logging, rotation metadata, handle scopes,
  and revocation behavior;
- enforced sandbox isolation with reviewed network and filesystem controls;
- separate model/API gating, cost controls, and operator authorization;
- a tau2 ownership plan proving tau2 retains lifecycle, task state, tool
  dispatch, evaluation, and persistence authority;
- explicit tests proving no state packet can be fed back into tau2 execution
  unless a future reviewed interface intentionally permits it;
- security review replacing all disabled placeholders without adding hidden live
  tau2 execution, LLM/API, or credential-handling paths.

Until such a future phase is intentionally implemented and reviewed, live
reactive-manager execution remains unavailable and fail-closed.
