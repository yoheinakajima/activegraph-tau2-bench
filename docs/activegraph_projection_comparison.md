# Fixture vs real ActiveGraph projection comparison

## Purpose

`compare_activegraph_projection_vs_baseline.py` compares a deterministic, fixture-backed ActiveGraph smoke projection with an offline ActiveGraph-style projection generated from an already-completed real tau2 baseline run.

The comparison is intended to answer: "Do the fixture contracts cover the same graph, state-packet, provenance, and boundary dimensions that appear in a real baseline projection, and which differences are expected because one side is synthetic and the other is post-run extracted data?"

This is an artifact-only review workflow. It does not run tau2, does not start a model-backed episode, does not call LLM/API services, does not require API keys, does not mutate `vendor/tau2-bench`, and does not implement ActiveGraph execution control.

## Command

Generate fresh fixture-backed artifacts first:

```bash
python scripts/run_activegraph_trace_smoke.py
python scripts/run_state_packet_smoke.py
```

Use the state-packet smoke output directory as the fixture run directory because it contains the full set of fixture comparison inputs:

- `events.jsonl`
- `activegraph_trace.json`
- `state_packets.jsonl`
- `state_packet_index.json`

Then compare against the canonical real baseline projection:

```bash
python scripts/compare_activegraph_projection_vs_baseline.py \
  --fixture-run-dir <runs/state-packet-smoke-dir> \
  --baseline-run-dir runs/20260531-042306-420109
```

The comparator writes outputs under:

```text
runs/20260531-042306-420109/activegraph_projection_comparison/
```

## Inputs

### Fixture-backed ActiveGraph projection

The fixture side reads:

- `events.jsonl` — deterministic no-LLM `TraceEvent` stream.
- `activegraph_trace.json` — fixture-backed ActiveGraph trace projection.
- `state_packets.jsonl` — serialized fixture state packets.
- `state_packet_index.json` — fixture packet index and hash-chain validation summary.

### Real baseline ActiveGraph projection

The real baseline side reads:

- `activegraph_projection/activegraph_baseline_events.jsonl`
- `activegraph_projection/activegraph_baseline_projection.json`
- `activegraph_projection/activegraph_baseline_state_packets.jsonl`
- `activegraph_projection/activegraph_baseline_state_packet_index.json`
- `activegraph_projection/activegraph_projection_final_state.json`

The comparison should not continue when the real baseline ActiveGraph projection inputs are absent. Generate the real projection from an already-extracted trace only with `scripts/project_baseline_trace_to_activegraph.py`; do not rerun tau2 for this workflow.

## Outputs

The comparator writes:

- `activegraph_projection_comparison_report.json` — complete machine-readable comparison report.
- `activegraph_projection_comparison_summary.md` — human-readable summary.
- `graph_alignment.json` — graph schema, count, node-kind, edge-type, task, component, role, tool, event-family, and artifact/provenance alignment.
- `packet_alignment.json` — packet count/type, source-event reference, ordering, and hash-chain alignment.
- `provenance_alignment.json` — provider/model/task/max-steps and control-boundary alignment.
- `coverage_gaps.json` — expected differences and known fixture-vs-real coverage gaps.
- `final_state.json` — compact comparison status and output list.
- `raw.log` — command boundary, status, input paths, and validation notes.

Generated outputs live under ignored `runs/` directories and are not intended to be committed.

## Comparison dimensions

The report compares:

- graph schema versions and trace-event schema versions;
- event counts, node counts, and edge counts;
- node kinds/types and edge types;
- event semantic families;
- task IDs;
- component coverage;
- message-role coverage;
- tool coverage;
- evaluation/result coverage;
- artifact/provenance nodes;
- packet counts and packet types;
- packet hash-chain validation;
- packet source-event references;
- control-boundary flags;
- no-rerun/no-API flags;
- known coverage gaps.

## Status values

The comparison reports one of:

- `activegraph_projection_comparison_passed`
- `activegraph_projection_comparison_completed_with_expected_gaps`
- `activegraph_projection_comparison_failed`
- `activegraph_projection_comparison_inputs_missing`

The expected status for the canonical fixture-vs-real comparison is:

```text
activegraph_projection_comparison_completed_with_expected_gaps
```

Fixture-vs-real differences are not failures by default. The comparator fails only when required validation boundaries are violated, such as broken packet ordering, missing source-event references, hash-chain issues, or control-boundary flags implying the comparison reran tau2 or called APIs.

## Expected fixture-vs-real differences

Expected differences include:

- The fixture uses a synthetic task ID, while the real baseline uses `create_task_1`.
- The fixture emits 18 events and 18 packets, while the real baseline projection emits 12 events and 12 packets.
- The fixture graph contains synthetic lifecycle coverage for smoke-contract testing.
- The real graph contains extracted baseline artifacts and richer real-run provenance.
- The real baseline carries provider/model/task/max-steps provenance from the source model-backed run.
- The real baseline lacks tick/effect timeline details because tau2 did not serialize them in the source artifacts.

## Known coverage gaps

Known gaps are carried through from the baseline projection and supplemented by comparison-derived gaps. Typical gaps are:

- no serialized tick-level tau2 execution timeline;
- no serialized effect/state-transition timeline;
- no speech/audio environment artifact for the canonical mock run;
- nullable evaluation internals such as DB checks, action checks, or natural-language assertion details;
- wrapper logs and summaries being provenance inputs rather than complete structured turn timelines;
- fixture-only synthetic lifecycle coverage that does not exist in the extracted real baseline.

## No-rerun/no-API boundary

This comparison is offline-only. It reads local JSON/JSONL/Markdown artifacts and writes comparison artifacts. It does not:

- run `tau2`;
- run another model-backed episode;
- instantiate model-backed agents;
- call OpenAI or other LLM/API providers;
- require API keys;
- mutate `vendor/tau2-bench`;
- feed state packets back into tau2;
- implement ActiveGraph execution control.

## Preparing future real ActiveGraph runtime adapter work

The comparison establishes a shared review surface across deterministic fixture contracts and real baseline observations. It identifies which schema fields, graph families, packet families, provenance fields, and boundary flags are already represented on both sides and which gaps belong to upstream tau2 serialization rather than ActiveGraph runtime behavior.

That makes future runtime-adapter work safer: the adapter can target concrete graph/packet/provenance contracts, preserve no-rerun/no-API boundaries during offline review, and avoid mistaking expected fixture-vs-real differences for execution-control requirements.
