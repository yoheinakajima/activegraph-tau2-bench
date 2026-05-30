# Phase 5 reactive-manager dry-run replay planning

Phase 5 adds a **dry-run-only reactive-manager planning prototype**. It reads the
same fixture-backed trace, ActiveGraph projection, and state-packet artifacts
created for Phase 4, then writes deterministic replay, fork, diff, and manager
decision artifacts. The prototype is intentionally observational and plan-only.
It does **not** implement a live reactive manager and does **not** let
ActiveGraph control tau2 lifecycle, task state, tool dispatch, evaluation, or
result persistence.

## Smoke command

```bash
python scripts/run_reactive_manager_dry_run.py
```

A successful run prints:

```text
reactive_manager_dry_run_passed
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
  summary.md
  final_state.json
  raw.log
```

## Dry-run manager scope

The dry-run manager is an artifact planner. It can:

- generate the fixture-backed TraceEvent stream used by Phase 4;
- preserve the ActiveGraph trace projection and state-packet hash chain;
- read `events.jsonl`, `activegraph_trace.json`, `state_packets.jsonl`, and
  `state_packet_index.json` back from disk;
- validate event, graph, packet, replay, fork, diff, and decision references;
- write replay/fork/diff plans and manager decisions that are all marked
  `dry_run: true` and `executed: false`.

The dry-run manager cannot:

- run `tau2 run` or any model-backed tau2 benchmark episode;
- import or mutate the vendored tau2 source tree;
- control tau2 lifecycle, task state, tool dispatch, or evaluation;
- feed state packets back into tau2 execution;
- call LLM/API services or require API keys.

## Input artifacts

The manager reads these artifacts from the same run directory after generating
or loading the fixture-backed Phase 4-equivalent stream:

| Artifact | Purpose |
| --- | --- |
| `events.jsonl` | Append-only TraceEvent stream and replay ordering source of truth. |
| `activegraph_trace.json` | Trace-only ActiveGraph-style graph/log projection. |
| `state_packets.jsonl` | One hash-chained state packet per TraceEvent. |
| `state_packet_index.json` | Packet lookup, first/last packet hashes, and packet validation summary. |

## Output artifacts

| Artifact | Purpose |
| --- | --- |
| `manager_plan.json` | Top-level dry-run manager plan, counts, source artifacts, boundaries, and validation. |
| `manager_decisions.jsonl` | Append-only manager decisions emitted by the planner. |
| `replay_plan.json` | Deterministic event/packet replay ordering plan. |
| `fork_plan.json` | Safe fixture fork-point plan. |
| `diff_report.json` | Deterministic packet/projection comparisons across fork points. |
| `summary.md` | Human-readable run summary. |
| `final_state.json` | Machine-readable final status, validations, summaries, and limitations. |
| `raw.log` | Command boundary, source checks, emitted event log lines, and final status. |

## Manager decision schema

Each line of `manager_decisions.jsonl` contains one decision:

| Field | Meaning |
| --- | --- |
| `schema_version` | Manager decision schema version. |
| `decision_id` | Monotonic run-local ID such as `decision-000001`. |
| `timestamp` | UTC timestamp for the dry-run decision emission. |
| `run_id` | Run ID shared by all Phase 5 artifacts. |
| `decision_type` | Decision class, such as `build_replay_plan`, `select_fixture_fork_point`, or `build_diff_report`. |
| `source_event_id` | Source TraceEvent ID when the decision is tied to one event; otherwise `null`. |
| `source_packet_id` | Source state-packet ID when the decision is tied to one packet; otherwise `null`. |
| `proposed_action` | Plan-only action description. |
| `dry_run` | Always `true`. |
| `executed` | Always `false`. |
| `reason` | Human-readable reason for the plan-only decision. |
| `provenance` | Source artifact counts, fork point IDs, or deterministic diff hash references. |

Validation rejects decisions that are not dry-run/unexecuted or that reference
missing source events/packets.

## Replay plan schema

`replay_plan.json` records:

- `schema_version`;
- `run_id`;
- `plan_type: deterministic_trace_packet_replay_plan`;
- `dry_run: true`;
- `executed: false`;
- `source_artifacts`;
- `step_count`;
- `steps`.

Each replay step includes a deterministic `step_id`, `sequence_index`,
`event_id`, `event_type`, `packet_id`, `packet_hash`, and plan-only operation.
The replay plan lists all 18 fixture TraceEvents and all 18 state packets in
source order without executing them.

## Fork plan schema

`fork_plan.json` records safe fixture fork points only. The current prototype
selects:

1. after `run.started`;
2. after `task.started`;
3. before `tool.dispatch_requested`;
4. after `evaluation.completed`.

Each fork point includes the source event ID/type, source packet ID/hash,
position, safety reason, `dry_run: true`, and `executed: false`. Fork points are
planning anchors only; no forked tau2 execution is launched.

## Diff report schema

`diff_report.json` compares selected serialized packets and graph projection
summaries across adjacent fork points. It records:

- source artifacts;
- graph projection counts and node-kind counts;
- adjacent fork-point packet comparisons;
- event windows between compared packet sequence indices;
- whether packet state hashes changed;
- `dry_run: true` and `executed: false`;
- `deterministic_report_hash` computed from canonical JSON.

The report is deterministic for equivalent artifact content. It compares
serialized artifacts only and does not update tau2 task state.

## Validation rules

The Phase 5 smoke validates that:

1. the event count matches the expected 18-event fixture trace;
2. TraceEvent IDs are monotonic and parent references exist;
3. `activegraph_trace.json` preserves the event log and count;
4. state packet count matches the event count and expected fixture count;
5. state packet IDs, sequence indices, packet hashes, and
   `previous_packet_hash` links are valid;
6. every replay step references an existing event and packet;
7. every fork point references an existing event and packet;
8. the diff report deterministic hash recomputes successfully;
9. all manager decisions have `dry_run: true` and `executed: false`;
10. no decision claims to execute tau2 control flow;
11. no LLM/API calls or paid LLM APIs were made;
12. no live tau2 benchmark episode was run;
13. `vendor/tau2-bench` remains unmodified.

## What is intentionally not implemented

Phase 5 intentionally does not implement:

- a live ActiveGraph reactive manager;
- replay execution;
- fork execution;
- diff-driven task control;
- ActiveGraph-owned tau2 state or lifecycle management;
- packet feedback into tau2 execution;
- monkeypatching or wrapping live tau2 runtime objects;
- real `tau2 run` executions;
- model-backed agents, user simulators, auto-review, or NL assertion judging;
- paid LLM/API calls;
- changes to `vendor/tau2-bench`.

## How this prepares a future live reactive-manager phase

Phase 5 establishes source-linked planning artifacts and validation gates before
any runtime control is considered. A future phase can use these artifacts to
specify which replay/fork/diff operations would need an explicit execution
boundary, additional safety controls, and opt-in tau2 integration. Until such a
phase is explicitly implemented, manager outputs are plans only and tau2 remains
the sole lifecycle/task-state owner.
