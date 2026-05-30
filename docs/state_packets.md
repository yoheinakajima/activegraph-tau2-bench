# Phase 4 ActiveGraph state-packet serialization

Phase 4 adds deterministic **state-packet artifacts** beside the existing
TraceEvent JSONL stream and ActiveGraph trace-only projection. State packets are
observational serialization units only: they are derived from `events.jsonl` and
`activegraph_trace.json`, written as explicit artifacts, and validated for later
replay/fork/diff experiments.

Phase 4 does **not** implement ActiveGraph reactive manager behavior, does not
let ActiveGraph control tau2 lifecycle or task state, does not mutate tau2-bench,
does not run model-backed tau2 episodes, and does not call paid LLM APIs.

## Smoke command

```bash
python scripts/run_state_packet_smoke.py
```

A successful run writes a timestamped artifact directory:

```text
runs/<timestamp>/
  events.jsonl
  activegraph_trace.json
  state_packets.jsonl
  state_packet_index.json
  summary.md
  final_state.json
  raw.log
```

Expected successful state:

```text
state_packet_smoke_passed
```

The command first validates the local `vendor/tau2-bench` tree and upstream
commit marker, then emits the same fixture-backed lifecycle TraceEvents used by
Phase 2/3. It preserves the Phase 3 `activegraph_trace.json` projection and adds
state packets derived from that ordered event/projection data.

## State packet schema

Each line in `state_packets.jsonl` is canonical JSON using schema version
`activegraph_state_packet.v1` and includes:

| Field | Meaning |
| --- | --- |
| `packet_id` | Stable run-local packet ID such as `pkt-000001`. |
| `packet_type` | One of `run_state`, `task_state`, `turn_state`, `tool_state`, `evaluation_state`, or `result_state`. |
| `run_id` | Trace run ID copied from the source event. |
| `created_at` | Source TraceEvent timestamp. |
| `source_event_id` | Event ID from `events.jsonl`; every packet references exactly one source event. |
| `source_event_type` | Event type from the referenced TraceEvent. |
| `sequence_index` | Zero-based packet order matching the TraceEvent order. |
| `state_scope` | Observed scope: run, task, turn, component, tool, and message-role identifiers. |
| `state_hash` | Canonical SHA-256 hash of the packet's scoped state material. |
| `packet_hash` | Canonical SHA-256 hash of the whole packet with `packet_hash` set to `null`. |
| `previous_packet_hash` | Previous packet hash, or `null` for the first packet. |
| `payload` | Observational lifecycle payload derived from the source event and projection counts. |
| `provenance` | tau2 upstream commit, wrapper commit, command, adapter mode, schema versions, and no-LLM status. |

Hashes use canonical JSON with sorted keys, compact separators, and SHA-256.
This makes packet hashes deterministic for equivalent packet content while still
allowing timestamps and git provenance to reflect the run that produced them.

## Packet types

Phase 4 emits packet types that summarize lifecycle state without owning runtime
state:

| Packet type | Purpose |
| --- | --- |
| `run_state` | Run-level lifecycle, CLI/config, batch setup, and completion observations. |
| `task_state` | Task start, orchestrator initialization, and state-snapshot observations. |
| `turn_state` | Turn and message observations for replay ordering. |
| `tool_state` | Tool dispatch request/completion observations. |
| `evaluation_state` | Fixture-backed evaluation observations. |
| `result_state` | Result/artifact persistence observations. |

## Event-to-packet mapping

| TraceEvent type | Packet type |
| --- | --- |
| `run.started` | `run_state` |
| `cli.config_inspected` | `run_state` |
| `batch.started` | `run_state` |
| `task.started` | `task_state` |
| `orchestrator.initialized` | `task_state` |
| `state.snapshot` | `task_state` |
| `turn.started` | `turn_state` |
| `message.observed` | `turn_state` |
| `tool.dispatch_requested` | `tool_state` |
| `tool.dispatch_completed` | `tool_state` |
| `evaluation.completed` | `evaluation_state` |
| `results.persisted` | `result_state` |
| `run.completed` | `run_state` |

For the current fixture trace, the smoke expects 18 TraceEvents and therefore 18
state packets.

## Hash-chain validation

`state_packet_index.json` records a compact packet lookup and validation result.
The validator checks that:

1. packet `sequence_index` values are monotonic and match source event order;
2. `previous_packet_hash` links every packet to its predecessor;
3. each `packet_hash` recomputes from canonical packet JSON;
4. every packet references an existing TraceEvent;
5. packet provenance includes the tau2 upstream commit and wrapper commit;
6. packets explicitly report that they do not control tau2 execution, lifecycle,
   or task state;
7. no paid LLM/API call was made according to no-LLM status flags;
8. the fixture packet count matches the expected count;
9. `activegraph_trace.json` remains a preserved projection artifact whose
   `event_log` matches `events.jsonl`.

## Safety and provenance

Packets are derived from the fixture-backed TraceEvent stream. They do not read
environment variables, API keys, external credentials, or provider config. The
secret-key validator rejects packet dictionaries containing secret-like key names
such as API keys, tokens, passwords, credentials, or authorization fields.

Each packet's provenance includes:

- `tau2_upstream_commit` from `vendor/tau2-bench.UPSTREAM_COMMIT`;
- wrapper repository commit from `git rev-parse --short=12 HEAD` when available;
- command used to generate the artifacts;
- TraceEvent and state-packet schema versions;
- ActiveGraph adapter mode and runtime availability;
- source-of-truth/projection artifact names;
- no-LLM/API-call status flags.

## What is intentionally not implemented

Phase 4 intentionally does not implement:

- ActiveGraph reactive manager behavior;
- ActiveGraph-owned tau2 task state or lifecycle control;
- replay execution, fork execution, or diff-driven control;
- mutation of tau2-bench behavior;
- monkeypatching or wrapping live tau2 runtime objects;
- real `tau2 run` executions;
- model-backed agents, user simulators, auto-review, or NL assertion judging;
- paid LLM/API calls;
- changes to `vendor/tau2-bench`.

## How this prepares Phase 5

Phase 4 creates deterministic serialized state material that future work can use
to compare replay/fork/diff plans without changing tau2 behavior. Phase 5 can
build on this by reading `events.jsonl`, `activegraph_trace.json`, and
`state_packets.jsonl` to prototype a reactive-manager or replay interface behind
a strict dry-run boundary. Any later manager must be explicitly scoped and must
prove that packet-derived decisions are separated from tau2 execution until a
future phase intentionally enables controlled behavior.
