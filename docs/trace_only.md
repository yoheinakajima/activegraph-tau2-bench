# Phase 2 trace-only tau2 observability

Phase 2 adds repository-owned, trace-only observability scaffolding for the
locally vendored `tau2-bench` tree. It is intentionally a baseline logging layer
only: it does **not** integrate ActiveGraph, create state packets, implement
reactive manager behavior, mutate tau2 behavior, call paid LLM APIs, or run real
model-backed tau2 benchmark episodes.

## Smoke command

```bash
python scripts/run_trace_smoke.py
```

A successful run writes a timestamped artifact directory:

```text
runs/<timestamp>/
  events.jsonl
  summary.md
  final_state.json
  raw.log
```

The command first verifies that `vendor/tau2-bench` exists and that
`vendor/tau2-bench.UPSTREAM_COMMIT` matches
`fcc9ed68df33c93ff0b8c946865f267d7c99fb06`. It then inspects selected upstream
source files with Python `ast` and emits fixture-backed lifecycle events.

## Event schema

The JSONL envelope is defined outside the vendor tree in
`experiments/trace_only/schema.py`. Each line in `events.jsonl` contains these
fields:

| Field | Meaning |
| --- | --- |
| `event_id` | Monotonic run-local ID such as `evt-000001`. |
| `timestamp` | UTC ISO-8601 emission timestamp. |
| `run_id` | Run identifier for correlating all events in one smoke run. |
| `phase` | Phase label; currently `phase_2_trace_only_baseline`. |
| `component` | Lifecycle component such as `runner`, `orchestrator`, or `environment`. |
| `event_type` | Event name such as `run.started` or `tool.dispatch_completed`. |
| `task_id` | Task identifier when the event is task-scoped. |
| `turn_index` | Turn index when the event is turn-scoped. |
| `tool_name` | Tool name when the event describes a tool dispatch. |
| `message_role` | Message role when a message/turn is observed. |
| `state_hash` | Stable SHA-256 hash for state snapshots when available. |
| `payload` | Event-specific structured metadata. |
| `parent_event_id` | Optional parent event for reconstructing lifecycle nesting. |

Events are append-only. Event IDs are deterministic and monotonic within the
run. State hashes are computed from canonical JSON. Wall-clock timestamps and
git commit provenance naturally vary by run.

## Provenance and safety fields

The initial `run.started` event and `final_state.json` include:

- tau2 upstream commit from `vendor/tau2-bench.UPSTREAM_COMMIT`;
- wrapper repository commit from `git rev-parse --short=12 HEAD` when available;
- smoke command (`python scripts/run_trace_smoke.py`);
- no-LLM/API-call status flags;
- trace mode (`fixture_backed_baseline_trace_only`).

The smoke never records environment variables, API keys, or full external
runtime configuration.

## Hook boundaries represented

The smoke covers the hook boundaries identified in `docs/source_map.md` without
patching or importing tau2:

- CLI/config boundary: `cli.config_inspected` from `vendor/tau2-bench/src/tau2/cli.py`.
- Runner batch lifecycle: `batch.started` and `task.started` from runner source paths.
- Half-duplex turn boundaries: `orchestrator.initialized`, `turn.started`, and `message.observed`.
- Environment/tool dispatch boundaries: `tool.dispatch_requested`, `tool.dispatch_completed`, and `state.snapshot`.
- Evaluator boundary: `evaluation.completed`.
- Result persistence boundary: `results.persisted`.
- Run lifecycle: `run.started` and `run.completed`.

## What is real vs fixture-backed

Real in Phase 2:

- the local tau2 vendor directory and upstream commit marker are checked;
- actual tau2 source paths are parsed with `ast` for expected classes/functions;
- real JSONL, summary, final-state, and raw-log artifacts are written under
  `runs/<timestamp>/`;
- the event schema, writer, state hashing, provenance fields, and no-LLM safety
  metadata are implemented in repository-owned code.

Fixture-backed in Phase 2:

- the task ID, transcript, tool call, tool result, reward, and state snapshots;
- lifecycle sequencing around the source-inspected boundaries;
- the baseline trace mode, which models where future hooks will emit events.

## Intentionally not implemented

Phase 2 intentionally does not implement:

- ActiveGraph integration;
- state packets;
- reactive manager behavior;
- monkeypatching or wrapping live tau2 runtime objects;
- real `tau2 run` executions;
- model-backed agents, user simulators, auto-review, or NL assertion judging;
- paid LLM/API calls;
- changes to `vendor/tau2-bench`.

## How this prepares Phase 3

The trace smoke establishes a stable event envelope and artifact layout for
later comparisons between:

1. baseline tau2;
2. ActiveGraph trace-only;
3. ActiveGraph state-packet;
4. ActiveGraph reactive manager.

Phase 3 can replace fixture emissions with safe wrappers or monkeypatch context
managers around the source-mapped tau2 lifecycle functions while preserving the
same `events.jsonl` schema. Keeping Phase 2 fixture-backed makes it possible to
validate downstream replay and analysis tooling before any runtime integration or
behavioral changes are introduced.
