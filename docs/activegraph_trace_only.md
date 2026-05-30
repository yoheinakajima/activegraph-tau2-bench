# Phase 3 ActiveGraph trace-only integration

Phase 3 adds an **ActiveGraph trace-only** path for the repository-owned tau2-bench
smoke harness. It mirrors the Phase 2 append-only `TraceEvent` JSONL stream into
an ActiveGraph-style trace store and writes a graph/log projection artifact.

The integration is deliberately narrow: ActiveGraph is a trace/log substrate
only. It is **not** the source of task state, control flow, orchestration, tool
selection, evaluation, or lifecycle management.

## Smoke command

```bash
python scripts/run_activegraph_trace_smoke.py
```

A successful run writes a timestamped artifact directory:

```text
runs/<timestamp>/
  events.jsonl
  activegraph_trace.json
  summary.md
  final_state.json
  raw.log
```

Expected statuses:

| Status | Meaning |
| --- | --- |
| `activegraph_trace_mock_passed` | No importable ActiveGraph runtime was found, so the deterministic local adapter/mock projected the trace successfully. |
| `activegraph_trace_runtime_passed` | An ActiveGraph runtime module was importable and the trace projection completed through the runtime-aware adapter seam. |
| `activegraph_unavailable` | Recorded as availability metadata when no runtime is importable; this does not fail the smoke because the mock adapter is the intended fallback. |

The command first verifies that `vendor/tau2-bench` exists and that
`vendor/tau2-bench.UPSTREAM_COMMIT` matches
`fcc9ed68df33c93ff0b8c946865f267d7c99fb06`. It then inspects selected upstream
source files with Python `ast`, emits fixture-backed lifecycle events, writes
normal Phase 2-compatible JSONL, and ingests the same events into the
ActiveGraph trace adapter.

## What “ActiveGraph trace-only” means

ActiveGraph trace-only means every emitted Phase 2 `TraceEvent` is also appended
to a graph-style trace store. The JSONL event stream remains the source of truth
for event order and semantics. The ActiveGraph projection is an additional view
over that stream, not a replacement for it.

Trace-only does **not** mean:

- ActiveGraph state packets;
- ActiveGraph-owned task state;
- reactive manager behavior;
- tau2 lifecycle control;
- mutation of tau2-bench behavior;
- model-backed tau2 benchmark episodes;
- paid LLM/API calls.

## What is real vs adapter/mock-backed

Real in Phase 3:

- the Phase 2 `TraceEvent` schema is reused unchanged;
- `events.jsonl` remains append-only and ordered by emission;
- every event is ingested by an `ActiveGraphTraceStore` interface;
- `activegraph_trace.json` exports an event log plus graph projection;
- provenance includes the tau2 upstream commit, wrapper repository commit when
  available, adapter mode, runtime availability, command, trace mode, and
  no-LLM/API-call status;
- the smoke remains fixture-backed and requires no API keys.

Adapter/mock-backed when ActiveGraph is not installed:

- `experiments/activegraph_trace/store.py` provides a thin local
  `ActiveGraphTraceStore` protocol;
- `InMemoryActiveGraphTraceStore` deterministically models append-only ingest
  plus graph projection;
- the smoke reports `activegraph_trace_mock_passed` and records
  `activegraph_unavailable` in metadata;
- this is an adapter seam for future runtime integration, not a real
  ActiveGraph runtime execution.

Runtime-aware when ActiveGraph is importable:

- the script detects conservative module names (`activegraph` or
  `active_graph`) without executing runtime behavior;
- the current Phase 3 implementation still preserves the same trace-only
  semantics and export shape;
- no state packets or reactive manager calls are made.

## TraceEvent to ActiveGraph-style mapping

Phase 3 preserves these Phase 2 fields exactly in both `events.jsonl` and the
`activegraph_trace.json` `event_log` entries:

| TraceEvent field | ActiveGraph-style use |
| --- | --- |
| `event_id` | Event node ID (`event:<event_id>`) and append-only event-log identity. |
| `timestamp` | Event node timestamp attribute. |
| `run_id` | Run node ID (`run:<run_id>`) and event containment scope. |
| `phase` | Event phase attribute for comparing Phase 2/3 streams. |
| `component` | Component node ID and `emitted_by` edge target. |
| `event_type` | Event node type attribute. |
| `task_id` | Optional task node and task-scope edges. |
| `turn_index` | Preserved in the event log for turn-scoped events. |
| `tool_name` | Optional tool node and `references_tool` edge. |
| `message_role` | Optional message-role node and `has_message_role` edge. |
| `state_hash` | Optional observed-state node and `observed_state` edge. |
| `payload` | Preserved structured metadata; ActiveGraph metadata is namespaced under `payload.activegraph` only on `run.started`. |
| `parent_event_id` | Parent-event edge for lifecycle nesting. |

The exported graph contains nodes for runs, events, components, tasks, states,
tools, and message roles. Edges capture event containment, emitter components,
parent event nesting, task scope, observed state, referenced tools, and message
roles. These graph edges are derived from the append-only event log; they do not
change event ordering or semantics.

## Intentionally not implemented

Phase 3 intentionally does not implement:

- ActiveGraph state packets;
- ActiveGraph as source of task state or control flow;
- reactive manager behavior;
- monkeypatching or wrapping live tau2 runtime objects;
- real `tau2 run` executions;
- model-backed agents, user simulators, auto-review, or NL assertion judging;
- paid LLM/API calls;
- changes to `vendor/tau2-bench`.

## How this prepares Phase 4

Phase 3 creates the adapter boundary that Phase 4 can extend with explicit
state-packet artifacts. The next phase can add packet construction and validation
beside the existing trace ingest path while preserving:

1. Phase 2-compatible `events.jsonl` as the ordered event source of truth;
2. trace-only provenance and no-LLM safety metadata;
3. a clear separation between observation/projection and tau2 control flow;
4. generated comparison artifacts under `runs/<timestamp>/`.

Phase 4 should add state-packet serialization and validation as a separate layer
without enabling reactive manager behavior or letting ActiveGraph control tau2
until that behavior is intentionally scoped in a later phase.
