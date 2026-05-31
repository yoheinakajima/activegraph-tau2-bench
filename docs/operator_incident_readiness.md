# Phase 10 operator authorization and incident-response readiness

Phase 10 is a **design-only, mock-contract readiness specification** for future
operator authorization, authorization revocation, incident declaration,
rollback/recovery planning, and incident audit/source anchoring workflows.

It does not enable live reactive-manager execution. It does not let ActiveGraph
control tau2 lifecycle or task state, does not feed state packets back into tau2,
does not mutate tau2-bench behavior, does not mutate vendored tau2 source, does
not import or run tau2 benchmark episodes, does not call LLM/API services, does
not require API keys, does not handle real credentials, does not store raw
secrets, and does not execute rollback.

## Smoke command

```bash
python scripts/run_operator_incident_readiness.py
```

A successful run prints:

```text
operator_incident_readiness_passed
```

The command regenerates/preserves the Phase 9 artifact chain and writes a
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
  vault_integration_contracts.json
  external_readiness_report.json
  operator_authorization_requests.json
  operator_authorization_decisions.jsonl
  incident_response_plans.json
  incident_response_decisions.jsonl
  operator_incident_readiness_report.json
  summary.md
  final_state.json
  raw.log
```

## Operator authorization request schema

`experiments/reactive_manager/operator_authorization.py` defines
`OperatorAuthorizationRequest` with schema version
`activegraph_operator_authorization_request.v1`.

Required fields:

| Field | Meaning |
| --- | --- |
| `operator_id` | Future operator identity for the approval request. Empty values are rejected. |
| `request_id` | Stable request identifier. Empty values are rejected. |
| `experiment_id` | Experiment or readiness phase being requested. |
| `run_scope` | Scope string; Phase 10 uses mock-contract validation only. |
| `requested_mode` | Must be `design_only_review` or `plan_only`; live modes are rejected. |
| `acknowledgement_text` | Operator acknowledgement text; missing text is rejected. |
| `rollback_acknowledged` | Must be `true`. |
| `audit_acknowledged` | Must be `true`. |
| `credential_policy_acknowledged` | Must be `true`. |
| `sandbox_policy_acknowledged` | Must be `true`. |
| `expires_at` | UTC timestamp; expired or invalid timestamps are rejected. |
| `source_artifact_links` | Non-empty links to generated local artifacts. |

The request also records `revoked`, `requested_live_execution`,
`requested_model_api_call`, and `request_payload` contract fields so the smoke
can validate revocation, unsafe live execution requests, model/API call requests,
and secret-like payload rejection.

## Authorization decision schema

`OperatorAuthorizationDecision` uses schema version
`activegraph_operator_authorization_decision.v1` and includes:

| Field | Meaning |
| --- | --- |
| `decision_id` | Deterministic decision identifier. |
| `request_id` | Request being evaluated. |
| `scenario` | Deterministic scenario name. |
| `structurally_complete` | True only when all shape checks pass. |
| `accepted` | Always `false` in Phase 10. |
| `disabled` | Always `true`; complete requests are disabled by construction. |
| `revoked` | Mirrors request revocation state. |
| `expired` | True when `expires_at` is not in the future. |
| `status` | `disabled_design_only` or `rejected`. |
| `reason` | Human-readable fail-closed/disabled reason. |
| `blockers` | Explicit blocker codes. |
| `source_links` | Source artifact links used for audit anchoring. |
| `operator_authorization_live_ready` | Always `false`. |

A valid complete operator authorization is recognized as structurally complete,
but the decision remains disabled and not accepted. No authorization can turn on
live execution.

## Revocation and expiration behavior

Phase 10 validates revocation and expiration semantics as contract data only:

- any request with `revoked=true` is rejected with `revoked_authorization`;
- any request with an invalid or past `expires_at` is rejected;
- revocation and expiration are fail-closed and cannot be overridden by other
  acknowledgements;
- structurally complete, non-expired, non-revoked requests still remain disabled
  because `operator_authorization_live_ready=false`.

## Incident declaration schema

`experiments/reactive_manager/incident_response.py` defines
`IncidentDeclaration` with schema version `activegraph_incident_declaration.v1`.

Required fields:

| Field | Meaning |
| --- | --- |
| `incident_id` | Stable incident identifier. Empty values are rejected in the plan validation. |
| `severity` | Severity label. Empty values are rejected. |
| `declared_by` | Mock operator or process declaring the incident. |
| `related_run_id` | Generated run ID under review. |
| `affected_artifacts` | Non-empty links to local artifacts affected by the incident. |

Declaration records can also mark unsafe requests to execute rollback, mutate
tau2, or call model/API services. Those requests are rejected.

## Incident response plan schema

`IncidentResponsePlan` uses schema version
`activegraph_incident_response_plan.v1` and requires:

| Field | Meaning |
| --- | --- |
| `incident_id` | Stable incident identifier. |
| `severity` | Severity label. |
| `declared_by` | Mock operator or process declaring the incident. |
| `related_run_id` | Generated run ID under review. |
| `affected_artifacts` | Non-empty source artifact links. |
| `rollback_plan_ref` | Reference to the inert manager rollback/planning artifact. |
| `replay_plan_ref` | Reference to `replay_plan.json`. |
| `fork_plan_ref` | Reference to `fork_plan.json`. |
| `audit_log_ref` | Reference to `audit_log.jsonl`. |
| `state_packet_index_ref` | Reference to `state_packet_index.json`. |
| `containment_steps` | Non-empty containment checklist. |
| `recovery_steps` | Non-empty recovery checklist. |
| `verification_steps` | Non-empty verification checklist. |

Plans also record `execute_rollback_requested`, `mutate_tau2_requested`, and
`model_api_call_requested`. Any true value is rejected.

## Incident decision schema

`IncidentResponseDecision` uses schema version
`activegraph_incident_response_decision.v1` and includes:

| Field | Meaning |
| --- | --- |
| `decision_id` | Deterministic decision identifier. |
| `incident_id` | Incident being evaluated. |
| `scenario` | Deterministic scenario name. |
| `structurally_complete` | True only when all plan-shape checks pass. |
| `accepted` | Always `false` in Phase 10. |
| `plan_only` | Always `true`. |
| `rollback_executed` | Always `false`. |
| `status` | `plan_only_disabled` or `rejected`. |
| `reason` | Human-readable fail-closed/plan-only reason. |
| `blockers` | Explicit blocker codes. |
| `source_links` | Rollback/replay/fork/audit/state-packet/source artifact anchors. |
| `incident_response_live_ready` | Always `false`. |

A valid complete incident response plan is recognized as structurally complete,
but it remains plan-only and cannot execute rollback.

## Validation rules

The Phase 10 smoke validates that:

- existing Phase 9 artifacts are preserved/regenerated;
- `live_ready=false`;
- `operator_authorization_live_ready=false`;
- `incident_response_live_ready=false`;
- live execution remains unavailable and fail-closed;
- rollback execution remains unavailable and `rollback_executed=false`;
- valid complete operator authorization is structurally complete but disabled;
- invalid operator authorizations are rejected with explicit blockers;
- expired and revoked authorizations are rejected;
- valid incident response planning is structurally complete but plan-only;
- invalid incident plans are rejected with explicit blockers;
- no request executes tau2, imports tau2 benchmark episodes, calls LLM/API
  services, stores raw secrets, or mutates `vendor/tau2-bench`.

## Failure modes covered

Operator authorization scenarios include:

- complete-but-disabled authorization;
- missing operator ID;
- missing request ID;
- missing acknowledgement flags;
- expired authorization;
- revoked authorization;
- requested live execution;
- requested model/API call;
- missing source artifact links;
- secret-like payload.

Incident response scenarios include:

- complete plan-only incident response;
- missing incident ID;
- missing severity;
- missing rollback/replay/fork references;
- missing audit reference;
- missing state-packet chain reference;
- requested rollback execution;
- requested tau2 mutation;
- requested model/API call.

## Why `live_ready` remains false

`live_ready` remains false because Phase 10 is not a live-manager phase. It only
specifies and tests deterministic mock contracts for future operator approval,
revocation, incident planning, and incident audit anchoring. There is no live
executor, no rollback executor, no real operator identity provider, no real
credential handling, no model/API capability, no tau2 lifecycle handoff, and no
reviewed path that can feed ActiveGraph state back into tau2.

## Requirements before a future live-manager phase

A future live-manager phase would require a separate explicit design and review.
At minimum it would need:

- reviewed operator identity, authorization, revocation, expiration, and audit
  semantics backed by a real identity/approval system;
- tamper-evident, externally durable authorization and incident audit storage;
- reviewed rollback and recovery execution design with dry-run proofs and manual
  approval gates;
- enforced sandbox, network, filesystem, credential-vault, and cost controls;
- explicit model/API gating and no hidden paid-API paths;
- a tau2 ownership plan proving tau2 retains lifecycle, task state, tool
  dispatch, evaluation, and persistence authority;
- tests proving no state packet can affect tau2 execution unless a future
  reviewed interface intentionally permits it;
- security review replacing all disabled placeholders without adding hidden live
  tau2 execution, LLM/API, or credential-handling paths.

Until such a future phase is intentionally implemented and reviewed, live
reactive-manager execution and rollback execution remain unavailable and
fail-closed.
