# Phase 8 live-readiness audit

Phase 8 is a **review-only live-readiness audit extension** around the Phase 7
live opt-in artifacts. It adds deterministic audit-log integrity checks,
credential-vault interface stubs that accept handle-only references, and sandbox
policy validation simulations. It does not enable live reactive-manager control.

## Smoke command

```bash
python scripts/run_live_readiness_audit.py
```

A successful run prints:

```text
live_readiness_audit_passed
```

The command regenerates/preserves the fixture-backed Phase 7 artifact chain and
writes a timestamped artifact directory:

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
  summary.md
  final_state.json
  raw.log
```

## Purpose

The purpose is to make review evidence stronger before any future live-manager
phase is considered. Phase 8 proves that:

- Phase 7 proposals and readiness decisions can be represented in an append-only
  deterministic audit log;
- audit records link back to source proposal, decision, and report artifacts;
- the audit hash chain validates from a fixed genesis hash through the final
  record;
- only inert future-vault credential handles are accepted;
- raw API-key-like values are rejected and redacted from policy reports;
- credential vault runtime remains unavailable;
- sandbox policy checks reject unsafe network, model/API, live-tau2, vendor
  mutation, and write-boundary settings;
- `live_ready` remains `false` and live execution remains unavailable.

Phase 8 is still artifact-only. It never executes replay/fork/diff plans, never
lets ActiveGraph control tau2 lifecycle or task state, never feeds state packets
back into tau2, never mutates vendored tau2 source, never imports or runs tau2
benchmark episodes, never calls LLM/API services, and never handles real
credentials.

## Audit log schema

`audit_log.jsonl` contains one canonical JSON object per line. Records use schema
version `activegraph_live_readiness_audit_record.v1` and include:

| Field | Meaning |
| --- | --- |
| `schema_version` | Audit record schema version. |
| `audit_id` | Deterministic sequence ID, for example `audit-000001`. |
| `timestamp` | Run timestamp reused for every deterministic record in the run. |
| `run_id` | Phase 8 run ID. |
| `record_type` | Source type, such as `live_manager_proposal`, `live_readiness_decision`, `live_readiness_report`, or `phase_6_contract_report`. |
| `source_artifact` | Source artifact filename inside the run directory. |
| `source_record_id` | Source proposal/decision ID when the source artifact has row-level records; otherwise `null`. |
| `subject` | Proposal scenario, proposal ID, or report subject under review. |
| `action` | Review action represented by the record. |
| `result` | Review result/status. |
| `previous_audit_hash` | Previous record hash, or the fixed all-zero genesis hash for the first record. |
| `provenance` | Source hash and selected non-secret source facts. |
| `audit_hash` | SHA-256 hash of the canonical record without `audit_hash`. |

The current smoke creates records for every Phase 7 proposal, every Phase 7
readiness decision, the Phase 7 readiness report, and the Phase 6 contract
report.

## Audit hash-chain validation

`audit_integrity_report.json` uses schema version
`activegraph_live_readiness_audit_integrity_report.v1`. Validation recomputes the
canonical JSON hash for every audit record after removing `audit_hash`, checks
that each `previous_audit_hash` equals the prior record's hash, and confirms that
all source artifacts exist in the same run directory. Proposal records must link
to a proposal in `live_manager_proposal.json`; decision records must link to a
decision in `live_opt_in_decisions.jsonl`, and the decision provenance must link
to an existing proposal.

The report includes:

| Field | Meaning |
| --- | --- |
| `record_count` | Number of audit records. |
| `hash_chain_valid` | `true` only when every record hash and previous-hash link validates. |
| `source_links_valid` | `true` only when all source artifacts and row-level links resolve. |
| `genesis_hash` | Fixed all-zero genesis hash. |
| `final_audit_hash` | Last record hash. |
| `errors` | Integrity errors, empty on pass. |
| `source_artifacts` | Source artifacts referenced by the audit log. |
| `review_only` | Always `true`. |
| `live_execution_enabled` | Always `false`. |

## Credential handle schema

Phase 8 accepts only inert handles shaped like:

```text
credential://future-vault/<name>
```

`<name>` must begin with an ASCII letter or digit and may contain ASCII letters,
digits, `_`, `.`, or `-` for up to 64 characters total in the name. Examples:

```text
credential://future-vault/review-only-demo
credential://future-vault/operator_approval.001
```

Any other scheme, path traversal shape, API-key-like prefix, token-like text, or
secret label is rejected. Reports store only sanitized/redacted values for
rejected inputs.

## Credential-vault stub behavior

`experiments/reactive_manager/credential_vault.py` defines:

- `CredentialReference`, a handle-only reference model;
- `CredentialVault`, a future protocol stub;
- `UnavailableCredentialVault`, a fail-closed stub whose
  `vault_runtime_available` flag is `false` and whose `resolve()` method always
  raises.

Phase 8 does **not** implement real credential storage, does not read
environment variables, and does not resolve handles. Therefore
`credential_policy_report.json` always reports:

- `vault_runtime_available=false`;
- `credential_live_ready=false`;
- `raw_secret_storage_enabled=false`;
- `environment_secret_lookup_enabled=false`;
- `real_credential_resolution_enabled=false`.

## Sandbox policy schema

`sandbox_policy_report.json` uses schema version
`activegraph_sandbox_policy_report.v1`. Each simulated policy includes:

| Field | Meaning |
| --- | --- |
| `policy_id` | Deterministic policy scenario ID. |
| `output_dir` | Proposed output directory. |
| `output_dir_isolated` | Whether writes are declared isolated to `runs/<timestamp>`. |
| `vendor_tau2_bench_mutation_allowed` | Must be `false` in this phase. |
| `vendor_tau2_bench_modified` | Actual/simulated vendor modification status. |
| `network_access_declared` | Whether network access was declared. |
| `network_access_allowed` | Whether declared network access was allowed. |
| `model_api_call_requested` | Must be `false` in this phase. |
| `model_api_call_separately_gated` | Must be `false` in this phase because no model/API gate exists. |
| `live_tau2_execution_requested` | Must be `false`. |
| `artifact_only_read_paths` | Review-only read paths. |
| `artifact_only_write_paths` | Review-only write paths. |
| `future_live_requirements_present` | Always `false` in Phase 8. |

The smoke simulates one valid review-only policy and two invalid policies. The
invalid policies cover unsafe network/model/live-tau2 requests and unsafe vendor
or artifact-boundary settings.

## Readiness audit report schema

`live_readiness_audit_report.json` uses schema version
`activegraph_live_readiness_audit_report.v1` and summarizes:

| Field | Meaning |
| --- | --- |
| `status` | `live_readiness_audit_passed` or `live_readiness_audit_failed`. |
| `readiness_result` | Forced-false readiness summary for live, credential, and sandbox readiness. |
| `live_ready` | Always `false`. |
| `live_execution_available` | Always `false`. |
| `live_execution_unavailable_fail_closed` | Always `true`. |
| `audit_record_count` | Number of audit records. |
| `audit_hash_chain_valid` | Hash-chain validation result. |
| `audit_source_links_valid` | Source-link validation result. |
| `credential_policy` | Credential policy summary. |
| `sandbox_policy` | Sandbox policy summary. |
| `blocker_summary` | Remaining blockers and intentional disabled-by-construction notes. |
| `no_tau2_control_flow_executed` | Always `true`. |
| `no_state_packets_fed_back_into_tau2` | Always `true`. |
| `no_llm_api_calls_made` | Always `true`. |
| `no_tau2_benchmark_episodes_imported_or_run` | Always `true`. |
| `no_live_execution_code_path_added` | Always `true`. |

## Failure modes

The smoke returns `live_readiness_audit_inputs_missing` when required Phase 7
artifacts are not present after fixture-backed generation. It returns
`live_readiness_audit_failed` when any audit, credential, sandbox, vendor, or
forced-false readiness invariant fails. Representative blockers include:

- audit hash mismatch;
- broken audit previous-hash link;
- audit source artifact missing;
- audit decision/proposal source-record link missing;
- raw secret-like credential reference accepted;
- credential vault runtime unexpectedly available;
- network/model/live-tau2 unsafe policy accepted;
- writes outside the run artifact directory accepted;
- vendor/tau2-bench reported as modified;
- Phase 7 `live_ready` unexpectedly true.

## Why `live_ready` remains false

`live_ready` remains false because Phase 8 is not a live-manager phase. It adds
review evidence only. Credential runtime support is absent, future live sandbox
enforcement is absent, no live tau2 execution path exists, and Phase 7 already
forces live readiness false. The Phase 8 readiness audit preserves that behavior
and adds independent reports showing why live execution remains unavailable and
fail-closed.

## Requirements before a future live-manager phase

A future live-manager phase would need a separate, explicit design and review
that is outside Phase 8 scope. At minimum it would need:

- real credential-vault integration that resolves handles without exposing raw
  secrets;
- immutable audit-log storage outside the local review artifact directory;
- enforced sandbox isolation with reviewed network and filesystem controls;
- separate model/API gating, cost controls, and operator authorization;
- a tau2 ownership plan proving tau2 retains lifecycle, task state, tool
  dispatch, evaluation, and persistence authority;
- rollback/recovery design validated without hidden live control paths;
- explicit tests proving no state packet can be fed back into tau2 execution
  unless a future reviewed interface intentionally permits it;
- a security review that replaces disabled placeholders without adding hidden
  tau2 execution or credential-handling paths.

Until such a future phase is intentionally implemented and reviewed, live
reactive-manager execution remains unavailable and fail-closed.
