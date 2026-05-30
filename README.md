# activegraph-tau2-bench

This repository evaluates future **ActiveGraph.ai** integrations against the official **tau2-bench** benchmark while keeping the vendored benchmark source separate from local experiment code.

## Current phase boundary

- **Current phase:** Phase 5 dry-run reactive-manager replay/fork/diff planning for the locally vendored tau2-bench baseline.
- **Not implemented yet:** live ActiveGraph reactive manager behavior and real tau2 runtime tracing. Phase 5 adds dry-run-only replay/fork/diff planning over fixture artifacts; ActiveGraph is still not used to control tau2 lifecycle or task state.
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

The Phase 1.5 smoke harness is intentionally source/data inspection only. The Phase 2 trace smoke remains no-LLM-safe and fixture-backed while adding JSONL observability artifacts. The Phase 3 ActiveGraph trace smoke mirrors that JSONL stream into a trace-only adapter/mock projection. The Phase 4 state-packet smoke serializes deterministic packet artifacts derived from the same event stream and projection. The Phase 5 reactive-manager dry run computes replay/fork/diff plans from those artifacts without executing them. These smoke commands:

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

See `docs/source_map.md` for exact local source paths and function/class names covering CLI entrypoints, run/batch flow, half-duplex interfaces, orchestrator turn loop, user simulator, environment/tool dispatch, domain data loading, task/evaluation models, artifacts, determinism controls, no-LLM smoke candidates, and observability hook candidates. See `docs/trace_only.md` for the Phase 2 event schema and fixture-backed trace smoke details. See `docs/activegraph_trace_only.md` for the Phase 3 ActiveGraph trace-only adapter boundary. See `docs/state_packets.md` for the Phase 4 state-packet schema and validation boundary. See `docs/reactive_manager_dry_run.md` for the Phase 5 dry-run replay/fork/diff planning boundary.
