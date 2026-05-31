# activegraph-tau2-bench

This repository evaluates future **ActiveGraph.ai** integrations against the official **tau2-bench** benchmark while keeping the vendored benchmark source separate from local experiment code.

## Current phase boundary

- **Current phase:** Phase 10 design-only operator authorization and incident-response readiness for the locally vendored tau2-bench baseline.
- **Not implemented yet:** live ActiveGraph reactive manager behavior and real tau2 runtime tracing. Phase 10 adds mock-contract operator approval, revocation, incident rollback/recovery planning, and incident audit anchoring while preserving `live_ready=false`; ActiveGraph is still not used to control tau2 lifecycle or task state.
- Local experiment code lives in `scripts/`, `docs/`, `runs/`, and future `experiments/` files. Upstream benchmark code lives under `vendor/tau2-bench/`.

## Vendored upstream provenance

- Upstream project: `sierra-research/tau2-bench`
- Vendored source path: `vendor/tau2-bench`
- Vendored upstream commit: `fcc9ed68df33c93ff0b8c946865f267d7c99fb06`
- Commit marker file: `vendor/tau2-bench.UPSTREAM_COMMIT`

The source map in `docs/source_map.md` is based only on the local vendored tree at that commit.

## Repo layout

```text
activegraph-tau2-bench/
  README.md
  docs/source_map.md
  docs/trace_only.md
  docs/activegraph_trace_only.md
  docs/state_packets.md
  docs/reactive_manager_dry_run.md
  experiments/trace_only/
  experiments/activegraph_trace/
  experiments/state_packets/
  experiments/reactive_manager/
  scripts/run_smoke_baseline.py
  scripts/run_trace_smoke.py
  scripts/run_activegraph_trace_smoke.py
  scripts/run_state_packet_smoke.py
  scripts/run_reactive_manager_dry_run.py
  runs/                         # generated smoke output
  vendor/tau2-bench/            # vendored upstream benchmark source
```

## Install commands

For local repository smoke checks, no tau2 install or API key is required:

```bash
python scripts/run_smoke_baseline.py
python scripts/run_trace_smoke.py
python scripts/run_activegraph_trace_smoke.py
python scripts/run_state_packet_smoke.py
python scripts/run_reactive_manager_dry_run.py
python scripts/run_operator_incident_readiness.py
python scripts/run_human_review_package.py
python scripts/run_all_smokes.py  # preferred compact validation command
```

For upstream tau2 development/runtime work, use the vendored upstream project environment:

```bash
cd vendor/tau2-bench
uv sync
uv run tau2 --help
uv run tau2 check-data
```

Running real tau2 benchmark simulations may require model/API credentials depending on the selected agent, user simulator, review, voice, or NL-assertion configuration.

## No-LLM/API-call boundary

The Phase 1.5 smoke harness is intentionally source/data inspection only. The Phase 2 trace smoke remains no-LLM-safe and fixture-backed while adding JSONL observability artifacts. The Phase 3 ActiveGraph trace smoke mirrors that JSONL stream into a trace-only adapter/mock projection. The Phase 4 state-packet smoke serializes deterministic packet artifacts derived from the same event stream and projection. The Phase 5 reactive-manager dry run computes replay/fork/diff plans from those artifacts without executing them. Later readiness phases through Phase 11 add design-only contracts for live opt-in, audit readiness, external audit/vault readiness, operator/incident readiness, and advisory human-review packaging while preserving fail-closed live execution. These smoke commands:

- never require API keys;
- never call paid LLM APIs;
- does not run `tau2 run`;
- does not instantiate LLM agents or call user simulator generation;
- does not run auto-review or NL-assertion evaluators;
- uses Python standard-library checks over local files only.

## Smoke command

```bash
python scripts/run_smoke_baseline.py
```

Expected successful state when `vendor/tau2-bench` exists:

```text
no_llm_smoke_passed
```

The harness validates the local vendored source exists and will not report `upstream_missing` when `vendor/tau2-bench` is present.


## Phase 2 trace-only smoke command

```bash
python scripts/run_trace_smoke.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
trace_smoke_passed
```

This command writes trace-only artifacts under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  events.jsonl
  raw.log
  summary.md
  final_state.json
```

The trace smoke is fixture-backed. It inspects real local tau2 source paths with the Python standard library and emits baseline lifecycle events, but it does not import `tau2`, run `tau2 run`, call model-backed agents, integrate ActiveGraph, create state packets, or implement reactive manager behavior. See `docs/trace_only.md` for the event schema, hook boundaries, and Phase 3 handoff notes.

## Phase 3 ActiveGraph trace-only smoke command

```bash
python scripts/run_activegraph_trace_smoke.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit and no real ActiveGraph runtime is importable:

```text
activegraph_trace_mock_passed
```

If an ActiveGraph runtime module is importable, the successful state is:

```text
activegraph_trace_runtime_passed
```

This command writes Phase 2-compatible trace events and an ActiveGraph projection under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  events.jsonl
  activegraph_trace.json
  raw.log
  summary.md
  final_state.json
```

The ActiveGraph path is trace-only. It does not create state packets, implement reactive manager behavior, mutate tau2 behavior, run `tau2 run`, call model-backed agents, or require real LLM/API keys. When no ActiveGraph dependency is available, it uses the deterministic local adapter seam in `experiments/activegraph_trace/` and records `activegraph_unavailable` as availability metadata. See `docs/activegraph_trace_only.md` for mapping details and Phase 4 handoff notes.


## Phase 4 ActiveGraph state-packet smoke command

```bash
python scripts/run_state_packet_smoke.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
state_packet_smoke_passed
```

This command writes Phase 2-compatible trace events, preserves the Phase 3 ActiveGraph projection, and adds deterministic state-packet artifacts under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  events.jsonl
  activegraph_trace.json
  state_packets.jsonl
  state_packet_index.json
  raw.log
  summary.md
  final_state.json
```

The state-packet path is still observational only. Packets are derived from `events.jsonl` and `activegraph_trace.json`; they do not implement reactive manager behavior, do not let ActiveGraph control tau2 lifecycle or task state, do not mutate tau2 behavior, do not run `tau2 run`, call model-backed agents, or require LLM/API keys. See `docs/state_packets.md` for schema, mapping, hash-chain validation, and Phase 5 handoff notes.


## Phase 5 reactive-manager dry-run planning command

```bash
python scripts/run_reactive_manager_dry_run.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
reactive_manager_dry_run_passed
```

This command writes Phase 2-compatible trace events, preserves the Phase 3 ActiveGraph projection, preserves the Phase 4 state-packet hash chain, and adds dry-run manager planning artifacts under `runs/<timestamp>/`:

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
  raw.log
  summary.md
  final_state.json
```

The reactive-manager dry run is still not live reactive control. It only reads fixture-backed artifacts and writes deterministic replay/fork/diff plans. It does not execute replay or fork steps, does not let ActiveGraph control tau2 lifecycle or task state, does not feed state packets back into tau2, does not mutate tau2 behavior, does not run `tau2 run`, and does not call model-backed agents or LLM/API services. See `docs/reactive_manager_dry_run.md` for schemas, validation rules, boundaries, and future-phase handoff notes.

## Phase 6 reactive-manager execution contract smoke command

```bash
python scripts/run_reactive_manager_contracts.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
reactive_manager_contracts_passed
```

This command regenerates/preserves the Phase 5 fixture-backed artifacts and adds guarded execution-contract artifacts under `runs/<timestamp>/`:

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
  raw.log
  summary.md
  final_state.json
```

The contract smoke defines a future execution request/decision boundary, validates safety gates, and hard-codes live execution as unavailable. A valid dry-run request is accepted as plan-only; live-control, missing-provenance, invalid-packet-chain, and secret-bearing requests are rejected fail-closed. It does not execute tau2 control flow, does not feed state packets back into tau2, does not mutate tau2 behavior, does not run `tau2 run`, and does not call model-backed agents or LLM/API services. See `docs/reactive_manager_contracts.md` for contract schemas, safety gates, failure modes, and future-phase handoff notes.

## Smoke output location

Each smoke run creates a timestamped directory:

```text
runs/<timestamp>/
  raw.log
  summary.md
  final_state.json
```

`raw.log` contains command/check details, `summary.md` is a human-readable summary, and `final_state.json` records the machine-readable final state and check results. Phase 2, Phase 3, Phase 4, Phase 5, and Phase 6 smokes also write `events.jsonl`; Phase 3, Phase 4, Phase 5, and Phase 6 write `activegraph_trace.json`; Phase 4, Phase 5, and Phase 6 write `state_packets.jsonl` and `state_packet_index.json`; Phase 5 and Phase 6 additionally write `manager_plan.json`, `manager_decisions.jsonl`, `replay_plan.json`, `fork_plan.json`, and `diff_report.json`; Phase 6 additionally writes `contract_decisions.jsonl` and `contract_report.json`.

## Source map

See `docs/source_map.md` for exact local source paths and function/class names covering CLI entrypoints, run/batch flow, half-duplex interfaces, orchestrator turn loop, user simulator, environment/tool dispatch, domain data loading, task/evaluation models, artifacts, determinism controls, no-LLM smoke candidates, and observability hook candidates. See `docs/trace_only.md` for the Phase 2 event schema and fixture-backed trace smoke details. See `docs/activegraph_trace_only.md` for the Phase 3 ActiveGraph trace-only adapter boundary. See `docs/state_packets.md` for the Phase 4 state-packet schema and validation boundary. See `docs/reactive_manager_dry_run.md` for the Phase 5 dry-run replay/fork/diff planning boundary. See `docs/reactive_manager_contracts.md` for the Phase 6 guarded execution-contract boundary and `docs/live_reactive_manager_opt_in.md` for the Phase 7 live opt-in readiness boundary.

## Phase 7 live reactive-manager opt-in contract smoke command

```bash
python scripts/run_live_manager_opt_in_contracts.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
live_manager_opt_in_contracts_passed
```

This command regenerates/preserves the Phase 6 fixture-backed artifacts and adds live opt-in proposal/readiness artifacts under `runs/<timestamp>/`:

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
  raw.log
  summary.md
  final_state.json
```

The live opt-in smoke is a proposal/readiness contract layer only. It models operator authorization, credential isolation, tau2/ActiveGraph ownership, sandboxing, rollback/recovery, audit logging, failure modes, and readiness scoring for a future live manager, while intentionally keeping `live_ready=false` and live execution unavailable/fail-closed. It does not execute tau2 control flow, does not feed state packets back into tau2, does not mutate tau2 behavior or vendored tau2 source, does not run `tau2 run`, and does not call model-backed agents or LLM/API services. See `docs/live_reactive_manager_opt_in.md` for schemas, gate details, failure modes, and future-phase handoff notes.

## Phase 8 live-readiness audit smoke command

```bash
python scripts/run_live_readiness_audit.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
live_readiness_audit_passed
```

This command regenerates/preserves the Phase 7 fixture-backed artifacts and adds review-only audit/readiness artifacts under `runs/<timestamp>/`:

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
  raw.log
  summary.md
  final_state.json
```

The live-readiness audit is review-only. It validates deterministic audit-log hash-chain integrity, handle-only credential references, unavailable credential-vault runtime behavior, sandbox policy rejection of unsafe network/model/live-tau2 settings, and vendor immutability while intentionally preserving `live_ready=false` and live execution unavailable/fail-closed. It does not execute tau2 control flow, does not feed state packets back into tau2, does not mutate tau2 behavior or vendored tau2 source, does not run `tau2 run`, does not call model-backed agents or LLM/API services, and does not read or store real credentials. See `docs/live_readiness_audit.md` for schemas, integrity validation, policy checks, failure modes, and future-phase handoff notes.

## Phase 9 external audit-store and vault readiness smoke command

```bash
python scripts/run_external_readiness_contracts.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
external_readiness_contracts_passed
```

This command regenerates/preserves the Phase 8 fixture-backed artifacts and adds design-only external audit-store and vault-integration readiness artifacts under `runs/<timestamp>/`:

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
  raw.log
  summary.md
  final_state.json
```

The external readiness smoke is design-only. It defines future external audit-store and vault resolver interfaces, validates deterministic mock contracts for append-only/read-back/hash-chain/source-artifact audit anchoring, rejects unsafe vault references including raw secrets and environment/file lookups, and intentionally preserves `live_ready=false`, `external_audit_store_live_ready=false`, `vault_integration_live_ready=false`, and live execution unavailable/fail-closed. It does not implement a real external service or vault, execute tau2 control flow, feed state packets back into tau2, mutate tau2 behavior or vendored tau2 source, run `tau2 run`, call model-backed agents or LLM/API services, or read/store real credentials. See `docs/external_audit_vault_readiness.md` for schemas, contracts, failure modes, and future-phase requirements.

## Phase 10 operator authorization and incident-response readiness smoke command

```bash
python scripts/run_operator_incident_readiness.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
operator_incident_readiness_passed
```

This command regenerates/preserves the Phase 9 fixture-backed artifacts and adds design-only operator authorization and incident-response readiness artifacts under `runs/<timestamp>/`:

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
  raw.log
  summary.md
  final_state.json
```

The operator/incident readiness smoke is design-only. It validates future operator authorization, revocation, expiration, incident declaration, rollback/recovery planning, and incident audit/source anchoring shapes while intentionally preserving `live_ready=false`, `operator_authorization_live_ready=false`, `incident_response_live_ready=false`, rollback execution unavailable, and live execution unavailable/fail-closed. It does not execute tau2 control flow, feed state packets back into tau2, mutate tau2 behavior or vendored tau2 source, run `tau2 run`, call model-backed agents or LLM/API services, or read/store real credentials. See `docs/operator_incident_readiness.md` for schemas, validation rules, failure modes, and future-phase requirements.

## Phase 11 human-review package smoke command

```bash
python scripts/run_human_review_package.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
human_review_package_passed
```

This command regenerates/preserves the Phase 10 fixture-backed artifact chain and adds deterministic human-review artifacts under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  human_review_package.json
  human_review_packet.md
  reviewer_checklist.md
  source_evidence_index.json
  blocker_matrix.json
  raw.log
  summary.md
  final_state.json
```

The human-review package is advisory/reporting only. It summarizes readiness state, blockers, evidence links, operator authorization decisions, incident-response decisions, audit/vault/sandbox readiness, and future live-manager prerequisites while intentionally preserving `live_ready=false` and live execution unavailable/fail-closed. It does not approve execution, execute tau2 control flow, feed state packets back into tau2, mutate tau2 behavior or vendored tau2 source, run `tau2 run`, call model-backed agents or LLM/API services, or read/store real credentials. See `docs/human_review_package.md` for the package schema, Markdown packet structure, checklist, evidence index, blocker matrix, non-approval statement, and future-phase requirements.

## Compact aggregate smoke command

Preferred compact validation command:

```bash
python scripts/run_all_smokes.py
```

Expected successful aggregate state:

```text
all_smokes_passed
```

The aggregate command runs all local smoke scripts in order, prints a compact status table by default, and writes combined artifacts under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  aggregate_raw.log
  aggregate_summary.md
  aggregate_final_state.json
```

Use `python scripts/run_all_smokes.py --verbose` to print full child-script output. The aggregator does not change any existing smoke behavior; it only captures each child output directory and final status and fails if any smoke fails or expected status is missing.
