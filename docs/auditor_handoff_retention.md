# Phase 12 external-auditor handoff and retention manifest

Phase 12 is a **design-only, advisory external-auditor handoff package** for the
Phase 11 human-review artifacts. It creates deterministic artifacts for an
external auditor or internal review board to inspect, retain, hash, and compare
against a future live-manager proposal. It does not approve, authorize, enable,
or execute live reactive-manager behavior.

## Smoke command

```bash
python scripts/run_auditor_handoff_package.py
```

A successful run prints:

```text
auditor_handoff_package_passed
```

The preferred compact validation command is:

```bash
python scripts/run_all_smokes.py
```

## Purpose of the external auditor handoff

The handoff package preserves a retention-ready view of the local artifact chain:

- Phase 1.5 tau2 provenance;
- Phase 2 trace events;
- Phase 3 ActiveGraph trace-only projection;
- Phase 4 state packets and hash-chain index;
- Phase 5 dry-run replay/fork/diff plans;
- Phase 6 guarded execution contracts;
- Phase 7 live opt-in readiness contracts;
- Phase 8 live-readiness audit, credential policy, sandbox policy, and audit log;
- Phase 9 external audit-store and vault-integration readiness contracts;
- Phase 10 operator authorization and incident-response readiness contracts;
- Phase 11 human-review package, packet, checklist, evidence index, and blocker matrix;
- Phase 12 auditor handoff, retention, hash, evidence bundle, question, and summary artifacts.

This phase is reporting only. It reads or regenerates the Phase 11 artifact chain
through the existing local smoke command, copies those artifacts into the Phase
12 run directory, and writes deterministic references for review. It never
imports tau2, executes tau2 control flow, runs model-backed tau2 benchmark
episodes, calls LLM/API services, requires API keys, handles real credentials,
stores raw secrets, mutates `vendor/tau2-bench`, feeds state packets back into
tau2, or lets ActiveGraph control tau2 lifecycle/task state.

## Generated artifacts

A successful run writes:

```text
runs/<timestamp>/
  auditor_handoff_package.json
  auditor_handoff_packet.md
  retention_manifest.json
  artifact_hash_manifest.json
  evidence_bundle_index.json
  auditor_questions.md
  handoff_summary.md
  summary.md
  final_state.json
  raw.log
```

The same directory also preserves the Phase 11 input chain, including:

```text
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
vault_integration_contracts.json
external_readiness_report.json
operator_authorization_requests.json
operator_authorization_decisions.jsonl
incident_response_plans.json
incident_response_decisions.jsonl
operator_incident_readiness_report.json
human_review_package.json
human_review_packet.md
reviewer_checklist.md
source_evidence_index.json
blocker_matrix.json
```

## Handoff package schema

`auditor_handoff_package.json` uses schema version
`activegraph_auditor_handoff_package.v1` and includes:

| Field | Meaning |
| --- | --- |
| `schema_version` | Machine-readable package schema version. |
| `run_id` | Deterministic run identifier derived from the local timestamp. |
| `generated_at` | UTC timestamp string used by the local run directory. |
| `phase` | `phase_12_design_only_external_auditor_handoff_and_retention_manifest`. |
| `status` | `auditor_handoff_package_passed`, `auditor_handoff_package_failed`, or `auditor_handoff_inputs_missing`. |
| `live_ready` | Always `false`. |
| `live_execution_available` | Always `false`. |
| `tau2_control_flow_executed` | Always `false`. |
| `llm_api_calls_made` | Always `false`. |
| `vendor_tau2_bench_modified` | Must remain `false` for a passing smoke. |
| `source_human_review_package` | Source Phase 11 run directory, package artifact, status, readiness state, and non-approval statement. |
| `evidence_bundle_index` | Reference to `evidence_bundle_index.json`. |
| `retention_manifest` | Reference to `retention_manifest.json`. |
| `artifact_hash_manifest` | Reference to `artifact_hash_manifest.json`. |
| `blocker_summary` | Non-empty summary derived from `blocker_matrix.json` and source reports. |
| `unresolved_prerequisites` | Flattened blocker/prerequisite list for future live-manager review. |
| `auditor_question_set` | Non-empty question list mapped to evidence groups and source artifacts. |
| `non_approval_statement` | Explicit statement that the package does not approve execution. |
| `provenance` | Command, output directory, source Phase 11 run, required artifacts, emitted sections, and design-only boundaries. |

## Markdown handoff packet structure

`auditor_handoff_packet.md` includes these sections:

- Executive summary
- Scope and non-goals
- Current readiness status
- Evidence bundle overview
- Artifact integrity summary
- Retention categories
- Blocker summary
- Auditor question set
- Required future approvals
- Explicit non-approval statement

## Retention manifest schema

`retention_manifest.json` uses schema version `activegraph_retention_manifest.v1`.
It classifies artifacts into these required groups:

- `source_provenance`
- `trace_events`
- `activegraph_projection`
- `state_packets`
- `manager_plans`
- `safety_contracts`
- `live_readiness`
- `audit_logs`
- `credential_and_sandbox`
- `external_readiness`
- `operator_incident`
- `human_review`
- `auditor_handoff`

Each entry includes:

| Field | Meaning |
| --- | --- |
| `artifact` | Artifact path relative to the Phase 12 run directory, except `vendor/tau2-bench.UPSTREAM_COMMIT` which is repo-relative provenance. |
| `group` | One required retention group. |
| `retention_reason` | Deterministic reason to retain the artifact. |
| `contains_secrets` | Always `false`. |
| `generated_by_phase` | Source phase that generated or owns the artifact. |
| `required_for_future_live_review` | Whether a future live-manager review should compare this artifact. |
| `hash_reference` | Pointer into `artifact_hash_manifest.json`. |

The manifest is advisory. Retaining artifacts does not approve live execution.

## Artifact hash manifest schema

`artifact_hash_manifest.json` uses schema version
`activegraph_artifact_hash_manifest.v1` and records deterministic integrity
metadata for referenced artifacts:

| Field | Meaning |
| --- | --- |
| `artifact` | Artifact path. |
| `sha256` | Stable SHA-256 hash of file bytes, except the manifest's own self-entry. |
| `byte_size` | File size in bytes at manifest generation time. |
| `exists` | Whether the artifact existed when the manifest was generated. |
| `group` | Retention group. |
| `source_phase` | Source phase. |

`artifact_hash_manifest.json` lists itself with `self_hash_excluded=true` because
a file cannot contain its final own cryptographic hash without recursive
non-determinism. All other existing entries receive stable SHA-256 hashes.

## Evidence bundle index schema

`evidence_bundle_index.json` uses schema version
`activegraph_evidence_bundle_index.v1` and groups artifacts by review area:

- tau2 provenance
- trace and projection
- state packets and hash chain
- manager dry-run planning
- execution contracts
- live opt-in readiness
- audit / credential / sandbox readiness
- external audit/vault readiness
- operator authorization and incident response
- human review
- auditor handoff

Each entry records the artifact name, retention group, source phase, and
retention reason. A passing smoke requires every review area to be populated and
all referenced artifacts to exist.

## Auditor question set

`auditor_questions.md` lists review questions mapped to evidence groups and
source artifacts, including:

- What evidence proves `live_ready=false`?
- What evidence proves live execution is unavailable/fail-closed?
- What evidence proves no tau2 control flow executed?
- What evidence proves no LLM/API calls were made?
- What evidence proves no raw secrets were stored?
- What evidence proves `vendor/tau2-bench` was unchanged?
- What blockers prevent live readiness?
- What future approvals would be required before live execution?
- Which artifacts should be retained for later comparison?
- Which evidence would an external auditor need to inspect first?

The question set is inspection guidance only. Answering it does not approve or
enable execution.

## Non-approval statement

Every package includes this explicit boundary:

> This Phase 12 external-auditor handoff and retention-manifest package is
> advisory/reporting only. It does not approve, authorize, enable, or execute
> live reactive-manager behavior; live_ready remains false and live execution
> remains unavailable/fail-closed.

## Why `live_ready` remains false

`live_ready` remains false because Phase 12 only packages and hashes existing
advisory evidence. It does not add a live manager, operator approval runtime,
credential vault runtime, external immutable audit service, live sandbox
enforcement, rollback executor, tau2 lifecycle ownership transfer, or any code
path that could execute tau2 control flow.

## Requirements before a future live-manager phase

A future live-manager phase would require a separate prompt, design, code review,
and approval process that resolves at least:

- explicit operator authorization runtime with revocation and expiration;
- real external immutable audit-store integration;
- real handle-only credential vault integration without raw secret storage;
- enforceable sandbox, network, model, and tool boundaries;
- tau2 ownership and ActiveGraph control-flow boundaries;
- rollback/recovery execution design and verification;
- audit and evidence retention guarantees;
- no-regression proof that state packets are not fed back into tau2 execution;
- a new human approval process separate from this advisory auditor handoff.
