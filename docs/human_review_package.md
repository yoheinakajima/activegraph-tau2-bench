# Phase 11 human-review package

Phase 11 is a **design-only, advisory human-review package generator** for the
Phase 10 operator authorization and incident-response readiness artifacts. It
creates deterministic review packets for humans to inspect; it does not approve,
authorize, enable, or execute live reactive-manager behavior.

## Smoke command

```bash
python scripts/run_human_review_package.py
```

A successful run prints:

```text
human_review_package_passed
```

The preferred compact validation command remains:

```bash
python scripts/run_all_smokes.py
```

## Purpose

The package summarizes the current readiness state for a future human reviewer:

- `live_ready=false` and live execution remains unavailable/fail-closed;
- tau2 control flow was not executed and state packets were not fed back into
  tau2;
- no LLM/API calls were made and no API keys are required;
- `vendor/tau2-bench` remains immutable;
- operator authorization decisions remain structural-only and disabled;
- incident-response decisions remain plan-only with rollback unavailable;
- audit hash-chain, state-packet hash-chain, credential/vault, sandbox, and
  external-readiness evidence is source-linked;
- blockers and future live-manager prerequisites remain unresolved.

## Generated artifacts

The command regenerates/preserves the Phase 10 artifact chain, then writes:

```text
runs/<timestamp>/
  human_review_package.json
  human_review_packet.md
  reviewer_checklist.md
  source_evidence_index.json
  blocker_matrix.json
  summary.md
  final_state.json
  raw.log
```

The same run directory also contains the Phase 10 input chain, including trace,
state-packet, manager-plan, contract, audit, vault, sandbox, external-readiness,
operator-authorization, and incident-response artifacts.

## Review package schema

`human_review_package.json` uses schema version
`activegraph_human_review_package.v1` and includes:

| Field | Meaning |
| --- | --- |
| `schema_version` | Machine-readable package schema version. |
| `run_id` | Deterministic run identifier derived from the timestamp. |
| `generated_at` | UTC timestamp string used by the local run directory. |
| `phase` | `phase_11_design_only_human_review_package`. |
| `status` | `human_review_package_passed`, `human_review_package_failed`, or `human_review_package_inputs_missing`. |
| `live_ready` | Always `false`. |
| `live_execution_available` | Always `false`. |
| `tau2_control_flow_executed` | Always `false`. |
| `llm_api_calls_made` | Always `false`. |
| `vendor_tau2_bench_modified` | Must remain `false` for a passing smoke. |
| `artifact_chain` | Required Phase 10 artifacts and Phase 11 outputs. |
| `readiness_reports` | Compact summaries of live-readiness, audit, external, and operator/incident reports. |
| `operator_authorization_summary` | Decision counts, accepted count, status counts, blockers, and source artifacts. |
| `incident_response_summary` | Decision counts, accepted count, rollback status, blockers, and source artifacts. |
| `audit_summary` | Audit and state-packet hash-chain validation state. |
| `credential_summary` | Handle-only/mock-only credential and vault readiness state. |
| `sandbox_summary` | Sandbox review policy and vendor immutability state. |
| `external_readiness_summary` | External audit-store and vault integration readiness state. |
| `blocker_matrix` | Non-empty category matrix of unresolved live-readiness blockers and evidence reports. |
| `evidence_index` | Source-linked artifact index grouped by phase. |
| `reviewer_checklist` | Required human checklist prompts. |
| `non_approval_statement` | Explicit statement that the package does not approve execution. |
| `provenance` | Command, source Phase 10 run, output directory, boundaries, and emitted sections. |

## Markdown packet structure

`human_review_packet.md` contains these sections:

- Executive summary
- Current readiness status
- Live execution status
- tau2 control-flow status
- LLM/API-call status
- Vendor immutability status
- Trace/state/manager artifact chain
- Operator authorization decisions
- Incident-response decisions
- Audit-log integrity
- Credential/vault readiness
- Sandbox readiness
- External audit/vault readiness
- Open blockers
- Evidence artifacts
- Future live-manager prerequisites
- Explicit non-approval statement

## Reviewer checklist

`reviewer_checklist.md` includes checklist prompts for confirming:

- `live_ready=false`;
- live execution is unavailable/fail-closed;
- no tau2 control flow executed;
- no LLM/API calls were made;
- no vendor mutation occurred;
- no secrets are in artifacts;
- the credential vault is handle-only/mock-only;
- audit hash-chain validation;
- state-packet hash-chain validation;
- operator authorization is structural only;
- incident response is plan-only;
- future live-manager blockers remain unresolved;
- the package does not approve execution.

Checking these boxes is a human review action only; it does not authorize or
enable live execution.

## Evidence index

`source_evidence_index.json` lists required artifacts, records whether each one
exists, stores compact file sizes, and groups evidence by phase:

- trace/state/manager;
- execution contracts and live opt-in;
- audit credential sandbox;
- external audit vault;
- operator incident.

The index is source-linked to existing generated artifacts only. It does not
fetch remote evidence, call APIs, or inspect secrets.

## Blocker matrix

`blocker_matrix.json` groups blockers by:

- operator authorization;
- incident response;
- credential/vault readiness;
- sandbox readiness;
- external audit-store readiness;
- live execution gate;
- tau2 ownership/control boundary;
- rollback/recovery;
- audit/evidence;
- unresolved future implementation prerequisites.

The matrix is intentionally non-empty. Passing Phase 11 means the review package
was generated correctly, not that the blockers were resolved.

## Non-approval statement

Every package includes this explicit boundary:

> This Phase 11 human-review package is advisory/reporting only. It does not
> approve, authorize, enable, or execute live reactive-manager behavior;
> live_ready remains false and live execution remains unavailable/fail-closed.

## Why `live_ready` remains false

`live_ready` remains false because Phase 11 only summarizes and packages Phase
10 readiness evidence. It does not add a live-manager implementation, operator
approval runtime, credential vault runtime, external immutable audit service,
live sandbox enforcement, rollback executor, tau2 lifecycle ownership transfer,
or any path that could execute tau2 control flow.

## Requirements before a future live-manager phase

A future live-manager phase would require a separate design and review that
resolves, at minimum:

- explicit operator authorization runtime and revocation semantics;
- real external immutable audit-store integration;
- real handle-only credential vault integration without raw secret storage;
- enforceable sandbox/network/model/tool boundaries;
- tau2 ownership and ActiveGraph control-flow boundaries;
- rollback/recovery execution design and verification;
- audit and evidence retention guarantees;
- no-regression proof that state packets are not fed back into tau2 execution;
- a new human approval process that is separate from this advisory package.
