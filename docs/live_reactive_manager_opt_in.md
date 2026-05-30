# Phase 7 live reactive-manager opt-in contracts

Phase 7 adds a **proposal and live-readiness contract layer** for a future live
reactive manager. The layer enumerates the requirements that would have to be
satisfied before live control could ever be considered, then deliberately keeps
live execution disabled. It produces source-linked reports and decisions only;
it does not execute replay/fork/diff plans, control tau2, feed state packets back
into tau2, run model-backed benchmark episodes, call LLM/API services, or handle
real credentials.

## Smoke command

```bash
python scripts/run_live_manager_opt_in_contracts.py
```

A successful run prints:

```text
live_manager_opt_in_contracts_passed
```

The command writes a timestamped artifact directory:

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
  summary.md
  final_state.json
  raw.log
```

## Purpose of the opt-in proposal phase

The purpose is to make the future live-manager authorization surface explicit
without enabling it. Phase 7 models the proposal schema, safety-gate decisions,
readiness report, and representative failure modes for a future live manager.
The output is useful for review because every blocker maps back to a named
requirement category, but all decisions remain non-executable and fail-closed.

## Live readiness requirements

Phase 7 validates these requirement groups:

1. **Operator authorization**: explicit operator acknowledgement, experiment ID,
   run scope, rollback acknowledgement, and audit-log acknowledgement.
2. **Credential and secret policy**: no secrets in request payloads, no API keys
   in artifacts, no environment-variable leakage, handle-only future credential
   references, and credential vault support before any live readiness.
3. **tau2 lifecycle ownership**: explicit ownership boundary, explicit tau2
   ownership statement, explicit ActiveGraph ownership statement, no ambiguous
   control ownership, and a validated ownership plan.
4. **Sandbox and isolation**: required sandbox mode, isolated output directory,
   unchanged `vendor/tau2-bench`, declared/allowed network access, and separate
   gating for model-backed runs.
5. **Rollback and recovery**: rollback plan, recovery point, replay plan, fork
   plan, state-packet chain, and dry-run-only rollback simulation in this phase.
6. **Audit logging**: immutable decision-log plan, provenance, operator/request
   IDs, safety-gate results, and hash-chain references.
7. **Failure-mode gates**: dirty vendor tree, invalid packet chain, live
   execution requested before enablement, tau2 control request, and model/API
   request without a separate future gate.
8. **Readiness scoring**: `live_ready` is always `false` in Phase 7.

## Proposal schema

`LiveManagerOptInProposal` is defined in
`experiments/reactive_manager/live_opt_in.py`. Each proposal contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Proposal schema version. |
| `phase` | Phase 7 proposal/readiness scope. |
| `proposal_id` | Deterministic run-local proposal ID. |
| `scenario` | Representative proposal scenario. |
| `run_id` | Source run ID. |
| `operator_authorization` | Operator acknowledgement, experiment, scope, rollback, and audit acknowledgement fields. |
| `credential_policy` | Secret-free request/artifact policy and handle-only future credential-reference policy. |
| `ownership_boundary` | tau2-owned responsibilities, ActiveGraph-owned responsibilities, and no-control assertions. |
| `sandbox_isolation` | Sandbox, output isolation, vendor immutability, network, and model-run gates. |
| `rollback_recovery` | Rollback, recovery, replay, fork, packet-chain, and dry-run simulation requirements. |
| `audit_logging` | Immutable log, provenance, operator/request ID, safety-gate, and hash-chain requirements. |
| `requested_capabilities` | Live execution, tau2 control, packet feedback, and model/API request flags. |
| `artifact_paths` | Source artifact paths for events, graph, packets, plans, and diffs. |
| `provenance` | Fixture-backed source counts and no-LLM/no-live-run status. |
| `validation` | Phase 5/6 validation inputs, including packet-chain validation. |
| `simulation_overrides` | Deterministic simulated dirty-vendor and invalid-packet scenarios. |
| `source_links` | Artifact links supporting proposal evaluation. |

The smoke emits a bundle in `live_manager_proposal.json` containing all nine
representative proposals.

## Decision schema

`LiveReadinessDecision` is defined in
`experiments/reactive_manager/live_readiness.py` and is emitted one JSON object
per line in `live_opt_in_decisions.jsonl`:

| Field | Meaning |
| --- | --- |
| `schema_version` | Decision schema version. |
| `decision_id` | Deterministic run-local decision ID. |
| `proposal_id` | Source proposal ID. |
| `scenario` | Scenario evaluated. |
| `run_id` | Source run ID. |
| `structurally_complete` | `true` only when all structural gates pass, excluding intentionally missing future vault support and forced disabled readiness. |
| `accepted` | Always `false` in Phase 7; no live proposal is accepted for execution. |
| `status` | `structurally_complete_disabled` or `rejected_fail_closed`. |
| `live_ready` | Always `false`. |
| `live_execution_available` | Always `false`. |
| `executed` | Always `false`. |
| `reason` | Human-readable decision summary. |
| `blockers` | Failed gates mapped to requirement groups. |
| `gate_results` | Complete pass/fail gate results. |
| `source_links` | Supporting artifact paths. |

## Readiness report schema

`live_readiness_report.json` contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Report schema version. |
| `run_id` | Source run ID. |
| `phase` | Phase 7 scope. |
| `live_ready` | Always `false`. |
| `live_execution_available` | Always `false`. |
| `proposal_count` / `decision_count` | Number of proposals and decisions. |
| `accepted_decision_count` / `rejected_decision_count` | Execution acceptance counts; accepted remains zero in this phase. |
| `structurally_complete_disabled_count` | Count of proposals complete enough for future review but disabled by construction. |
| `executed_decision_count` | Always zero. |
| `requirements` | Requirement-key to label mapping. |
| `blocker_counts_by_requirement` | Blocker totals grouped by requirement. |
| `scenario_results` | Per-scenario status, readiness, and blockers. |
| `disabled_by_construction` | Always `true`. |
| `no_tau2_control_flow_executed` | Always `true`. |
| `no_state_packets_fed_back_into_tau2` | Always `true`. |
| `no_llm_api_calls_made` | Always `true`. |

## Operator acknowledgement requirements

A proposal must include a proposal-only/no-live acknowledgement, explicit
operator ID, request ID, experiment ID, run scope, rollback acknowledgement, and
audit-log acknowledgement. Missing acknowledgement produces the
`operator_authorization.operator_acknowledgement_present` blocker.

## Credential isolation requirements

A proposal must assert that request payloads and artifacts contain no secrets,
that environment variables are not leaked, and that future credential references
are handles rather than raw values. Phase 7 intentionally does **not** implement
credential vault support; therefore `credential_secret_policy.credential_vault_supported`
is a blocker even for the structurally complete proposal, and `live_ready` stays
`false`.

## tau2/ActiveGraph ownership requirements

The proposal must state that tau2 owns benchmark lifecycle, task state, tool
dispatch, evaluation, and persistence. ActiveGraph may own trace observation,
state-packet serialization, and readiness reporting only. Any ambiguous ownership
or ActiveGraph tau2-control claim is rejected fail-closed.

## Sandbox requirements

Future live execution would require declared sandbox mode, output-directory
isolation, an unchanged `vendor/tau2-bench`, no network access unless explicitly
declared and allowed, and a separate gate for model-backed runs. Phase 7 only
validates those declarations and simulated failures; it does not create a live
sandboxed execution path.

## Rollback/recovery requirements

A future live manager would require a rollback plan, recovery point, replay plan,
fork plan, and state-packet chain. Phase 7 allows rollback simulation only as
`dry_run_only` metadata and never executes rollback, replay, fork, or diff steps.

## Audit logging requirements

A future live manager would need immutable decision logs, provenance,
operator/request IDs, safety-gate results, and hash-chain references. Phase 7
emits deterministic decision/report artifacts so reviewers can verify those
requirements without enabling live control.

## Failure modes covered

The smoke builds these representative proposals:

| Scenario | Expected result |
| --- | --- |
| `complete_but_disabled_proposal` | Structurally complete, but disabled because Phase 7 forces `live_ready=false` and credential vault support is absent. |
| `missing_operator_acknowledgement` | Rejected with operator-authorization blockers. |
| `missing_credential_isolation` | Rejected with credential-isolation blockers. |
| `ambiguous_tau2_ownership` | Rejected with tau2 ownership blockers. |
| `missing_rollback_plan` | Rejected with rollback/recovery blockers. |
| `missing_audit_log_plan` | Rejected with audit-log blockers. |
| `dirty_vendor_tree_simulated` | Rejected with vendor immutability blocker. |
| `invalid_packet_chain_simulated` | Rejected with packet-chain blocker. |
| `unsafe_model_api_request` | Rejected because live execution and model/API calls are requested before future gates exist. |

## Why `live_ready` is intentionally false

`live_ready` is intentionally false because Phase 7 is a design and validation
phase, not an enablement phase. Credential vault support is absent, live
execution is unavailable, and a forced disabled-by-construction gate is applied
to every proposal. This preserves Phase 6 fail-closed behavior and prevents any
proposal from becoming executable by accident.

## What a future live-manager phase would need

A future phase would need a deliberate design that is outside Phase 7 scope:

- real credential vault integration using handles only;
- explicit operator workflow and immutable audit log implementation;
- independently reviewed sandbox and network policy enforcement;
- validated tau2/ActiveGraph ownership plan that keeps tau2 lifecycle and task
  state under tau2 control;
- separate model/API gating and cost controls;
- validated rollback/recovery simulation before any live action;
- explicit code review that replaces disabled placeholders without adding hidden
  tau2 execution paths.

Until such a phase is intentionally implemented and reviewed, live reactive
manager execution remains unavailable and fail-closed.
