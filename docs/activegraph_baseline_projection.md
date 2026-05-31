# ActiveGraph projection from a real tau2 baseline trace

## Purpose

`scripts/project_baseline_trace_to_activegraph.py` converts an already-extracted, real tau2 model-baseline `TraceEvent` stream into offline ActiveGraph-style graph and state-packet artifacts. The projection is for inspection, provenance, and future comparison work only. It does **not** rerun tau2, call LLM/API services, require API keys, mutate `vendor/tau2-bench`, or implement ActiveGraph execution control.

The first canonical baseline run for this workflow is:

```bash
python scripts/project_baseline_trace_to_activegraph.py \
  --baseline-run-dir runs/20260531-042306-420109
```

The expected status for that run is `activegraph_baseline_projection_completed_with_gaps` because the extracted tau2 baseline trace lacks tick-level and effect-timeline details.

## Input artifacts

The command reads these required files from `<baseline-run-dir>/extracted_trace/`:

- `baseline_trace.jsonl` — normalized `trace_event.v1` events extracted from a completed real tau2 baseline run.
- `baseline_trace_final_state.json` — extraction summary, event counts, source metadata, and extraction limitations.
- `baseline_artifact_index.json` — source-run artifact provenance, parsers, hashes, and contribution counts.

If present, the command also reads `<baseline-run-dir>/trace_comparison/trace_comparison_report.json` as optional context. Missing comparison output is recorded as a coverage gap, but it does not block projection when the extracted baseline trace exists.

## Output artifacts

The command writes all projection outputs under `<baseline-run-dir>/activegraph_projection/`:

- `activegraph_baseline_projection.json` — full graph projection, copied source event log, metadata, counts, and validation details.
- `activegraph_baseline_events.jsonl` — canonical JSONL copy of the real baseline `TraceEvent` stream used as projection input.
- `activegraph_baseline_state_packets.jsonl` — one observational state packet per baseline event.
- `activegraph_baseline_state_packet_index.json` — packet lookup table, packet hashes, and validation summary.
- `activegraph_projection_summary.md` — human-readable run summary and known coverage gaps.
- `activegraph_projection_final_state.json` — compact machine-readable final state.
- `raw.log` — command boundary, counts, status, and validation notes.

Generated outputs live under ignored `runs/` directories and are not required to be committed.

## Projection schema

The projection schema is `activegraph_baseline_projection.v1`. It preserves the baseline run ID, source event IDs, original `event_type` values, task IDs, tool names, message roles, artifact references, tau2 upstream commit, wrapper repository commit, provider/model metadata, and extraction limitations where available.

The graph contains these node families when observed:

- `run` — the extracted baseline run.
- `task` — task IDs from the trace or run-start payload.
- `event` — one node per source `TraceEvent`.
- `component` — trace components such as `baseline.wrapper`, `baseline.message`, and `baseline.tool`.
- `message_role` — roles such as `assistant`, `user`, and `tool` when present.
- `tool` — tool names from tool request/completion events when present.
- `evaluation_result` — evaluation and result observations.
- `artifact` — extracted-trace files and source-run artifacts from `baseline_artifact_index.json`.
- `state_packet` — derived observational state packets.

The graph emits edge families for:

- `run_contains_event`
- `event_follows_previous_event`
- `run_has_task`
- `event_belongs_to_task`
- `event_has_component`
- `event_has_message_role`
- `event_uses_tool`
- `event_observes_evaluation_result`
- `run_references_artifact`
- `event_references_source_artifact`
- `packet_derives_from_event`

## State packet derivation

State packets use schema `activegraph_baseline_state_packet.v1` and are derived after the tau2 baseline run has completed. Each packet contains:

- `packet_id`
- `packet_type`
- `run_id`
- `created_at`
- `source_event_id`
- `source_event_type`
- `sequence_index`
- `state_scope`
- `state_hash`
- `packet_hash`
- `previous_packet_hash`
- `payload`
- `provenance`

Packet hashes use canonical JSON and SHA-256. Validation checks that packet ordering is monotonic, each `previous_packet_hash` links to the prior packet, every packet references an existing baseline `TraceEvent`, packet count matches event count, and every control-boundary flag is false. Packets explicitly state that they do not control tau2 execution, task state, lifecycle, tools, or replay.

## Status values

The projection command reports one of:

- `activegraph_baseline_projection_passed`
- `activegraph_baseline_projection_completed_with_gaps`
- `activegraph_baseline_projection_failed`
- `activegraph_baseline_projection_inputs_missing`

`activegraph_baseline_projection_inputs_missing` is used when required extracted-trace files are absent. The workflow should not continue if `baseline_trace.jsonl` is missing.

## Known limitations

The real extracted baseline trace is post-run observational data. Current known gaps include:

- No tick-level tau2 execution timeline is serialized in the baseline artifacts.
- No effect/state-transition timeline is serialized in the baseline artifacts.
- No speech/audio environment artifact is present for the canonical mock run.
- Some evaluation internals may be `null`, including database checks, action checks, and natural-language assertion details.
- Wrapper `raw.log` and `summary.md` are provenance inputs, not full structured turn timelines.
- Optional fixture-vs-baseline comparison artifacts may be unavailable locally and are not required for projection.

## No-rerun/no-API boundary

This workflow only reads local files. It does not run `tau2`, does not run another model-backed episode, does not call OpenAI or other LLM/API providers, does not require API keys, and does not mutate `vendor/tau2-bench`.

## Comparison with fixture-backed ActiveGraph projection

The fixture-backed ActiveGraph projection in the smoke suite is generated from deterministic no-LLM fixture events. It includes synthetic lifecycle details useful for contract testing and CI-lite validation.

The real baseline projection instead starts from extracted model-backed tau2 artifacts. It preserves real baseline message/tool/evaluation observations but cannot invent missing tick/effect details that tau2 did not serialize. This makes the output suitable for apples-to-apples comparison at the `TraceEvent`, graph-node/edge, and state-packet levels while keeping expected coverage gaps explicit.

## Preparing for baseline-vs-ActiveGraph state comparison

The projection produces a graph and a hash-chained packet stream keyed by source event IDs. A follow-up comparator can align fixture-backed ActiveGraph packets with real-baseline ActiveGraph packets by event family, component, task, message role, tool name, packet type, state scope, and provenance. The comparator should treat missing tick/effect timelines as expected coverage gaps rather than failures unless a future baseline extraction includes those artifacts.
