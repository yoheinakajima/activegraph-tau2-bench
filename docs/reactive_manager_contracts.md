# Phase 6 guarded reactive-manager execution contracts

Phase 6 adds a **guarded, opt-in execution contract layer** for a future
reactive manager. It defines request/decision schemas, safety policy gates,
executor interfaces, and fail-closed behavior over the fixture-backed Phase 5
artifacts. It does **not** implement live reactive-manager control.

## Smoke command

```bash
python scripts/run_reactive_manager_contracts.py
```

A successful run prints:

```text
reactive_manager_contracts_passed
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
  summary.md
  final_state.json
  raw.log
```

## Execution contract scope

The contract layer is a design and validation boundary only. It can:

- regenerate the fixture-backed Phase 5 artifacts;
- build representative `ReactiveManagerExecutionRequest` records;
- validate requests against a `ReactiveManagerSafetyPolicy`;
- emit deterministic, source-linked `ReactiveManagerExecutionDecision` records;
- accept exactly a valid dry-run request as `accepted_plan_only`;
- reject live-control, missing-provenance, invalid-packet-chain, and
  secret-bearing requests as `rejected_fail_closed`.

The contract layer cannot:

- run `tau2 run` or any model-backed tau2 benchmark episode;
- control tau2 lifecycle, task state, tool dispatch, evaluation, or persistence;
- feed state packets back into tau2 execution;
- execute replay, fork, or diff plans;
- mutate `vendor/tau2-bench` or wrapper behavior;
- call LLM/API services or require API keys.

## Safety gates

Every execution-like request must pass all gates before it can be accepted even
as a plan-only dry run:

1. execution mode is allowlisted (`plan_only` in Phase 6);
2. live execution remains unavailable;
3. explicit opt-in flag is present;
4. `dry_run` is `true`;
5. operator acknowledgment is `phase6_plan_only_no_live_execution`;
6. provenance includes `events.jsonl`;
7. provenance includes `activegraph_trace.json`;
8. provenance includes `state_packets.jsonl` and `state_packet_index.json`;
9. required Phase 5 artifacts are present;
10. state-packet hash-chain validation is valid;
11. replay/fork/diff manager validation is valid;
12. no pending validation errors exist;
13. request metadata and payload contain no API-key-like or secret-like values;
14. `vendor/tau2-bench` is unchanged;
15. no model-backed tau2 episode execution is requested or reported;
16. no tau2 control-flow ownership is requested.

Any failed gate produces a structured refusal and `executed: false`.

## Request schema

`ReactiveManagerExecutionRequest` is defined in
`experiments/reactive_manager/contracts.py` and includes:

| Field | Meaning |
| --- | --- |
| `schema_version` | Contract schema version. |
| `request_id` | Deterministic run-local request ID. |
| `scenario` | Contract-test scenario name. |
| `run_id` | Artifact run ID. |
| `execution_mode` | Requested mode such as `plan_only` or rejected `live_control`. |
| `dry_run` | Must be `true` in Phase 6. |
| `explicit_opt_in` | Must be `true` for execution-like boundaries. |
| `operator_acknowledgment` | Must acknowledge Phase 6 plan-only/no-live scope. |
| `requested_action` | Human-readable requested boundary. |
| `artifact_paths` | Source artifact paths for events, graph, packets, plans, and diffs. |
| `provenance` | Source counts, validations, and no-LLM/no-tau2-execution status. |
| `validation` | Combined Phase 5 validation result. |
| `payload` | Bounded request metadata checked for control claims and secrets. |

## Decision schema

`ReactiveManagerExecutionDecision` records:

| Field | Meaning |
| --- | --- |
| `schema_version` | Decision schema version. |
| `decision_id` | Deterministic run-local decision ID. |
| `request_id` | Source request ID. |
| `scenario` | Scenario evaluated. |
| `run_id` | Artifact run ID. |
| `accepted` | `true` only for the valid dry-run plan-only request. |
| `status` | `accepted_plan_only` or `rejected_fail_closed`. |
| `dry_run` | Always `true` on emitted decisions. |
| `executed` | Always `false`. |
| `execution_mode` | Requested mode. |
| `executor` | `DryRunExecutor` or `DisabledLiveExecutor`. |
| `reason` | Human-readable decision reason. |
| `refusal_reasons` | Failed safety gates for rejected requests. |
| `validation` | Aggregate guard results and errors. |
| `source_links` | Artifact paths supporting the decision. |

## Fail-closed behavior

Phase 6 hard-codes live execution as unavailable. The `DisabledLiveExecutor`
(alias `FailClosedExecutor`) always returns a refusal with `executed: false`.
The `DryRunExecutor` accepts only requests that pass every safety gate and still
returns a plan-only decision. No executor has a code path that launches tau2,
changes tau2 state, calls tools, or calls external services.

## Contract test scenarios

The smoke builds five representative requests:

| Scenario | Expected result |
| --- | --- |
| `valid_dry_run_request` | Accepted as `accepted_plan_only`; no execution. |
| `invalid_live_control_request` | Rejected because live control, `dry_run=false`, and tau2 control are unavailable. |
| `invalid_missing_provenance` | Rejected because events, graph, and packet provenance are missing. |
| `invalid_packet_hash_chain` | Rejected with a simulated packet hash-chain validation failure. |
| `invalid_secret_payload` | Rejected because the payload contains an API-key-like secret. |

A passing smoke reports one accepted decision, four rejected decisions, zero
executed decisions, live execution unavailable, no tau2 control flow, and no
LLM/API calls.

## What is intentionally not implemented

Phase 6 intentionally does not implement:

- a live ActiveGraph reactive manager;
- opt-in live tau2 execution;
- replay execution;
- fork execution;
- diff-driven task control;
- ActiveGraph-owned tau2 lifecycle or task-state management;
- state-packet feedback into tau2 execution;
- model-backed benchmark episodes;
- paid LLM/API calls;
- vendored tau2 source changes.

## Future live-manager preparation

This phase gives a future opt-in live-manager phase a concrete contract surface:
request/decision records, named safety gates, source-linked provenance, and
structured failure modes. A future phase would need to deliberately expand the
allowlist, replace the disabled live executor, and add additional operator,
credential, and tau2 integration controls. Until that future phase is explicitly
implemented, every execution-like path remains plan-only or fail-closed.
