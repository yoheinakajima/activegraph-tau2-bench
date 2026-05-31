# Runtime trace vs post-run extracted trace comparison

`python scripts/compare_runtime_trace_vs_postrun_trace.py` compares the first paid, runtime-traced tau2 baseline against the earlier post-run extracted baseline trace. The comparison is strictly offline: it reads existing artifacts, writes derived reports, does not rerun tau2, does not start a model-backed episode, does not call LLM/API services, does not require API keys, and does not mutate `vendor/tau2-bench`.

Canonical command:

```bash
python scripts/compare_runtime_trace_vs_postrun_trace.py \
  --runtime-run-dir runs/20260531-153843-240865 \
  --postrun-baseline-dir runs/20260531-042306-420109
```

The expected canonical status is:

- `runtime_vs_postrun_comparison_completed_with_remaining_gaps`

Other status values are:

- `runtime_vs_postrun_comparison_passed`
- `runtime_vs_postrun_comparison_failed`
- `runtime_vs_postrun_inputs_missing`

## Inputs inspected

The runtime side inspects:

- `runtime_events.jsonl`
- `runtime_trace_summary.md`
- `runtime_trace_final_state.json`
- `runtime_hook_map.json`
- `tau2_output/results.json`, when present
- `tau2_artifacts/results.json`, when present

The post-run side inspects:

- `extracted_trace/baseline_trace.jsonl`
- `extracted_trace/baseline_trace_final_state.json`
- `extracted_trace/baseline_trace_summary.md`, when present
- `extracted_trace/baseline_artifact_index.json`
- `tau2_output/results.json`, when present
- optional `trace_comparison/` and `activegraph_projection/` directories, when present

## Outputs

The comparator writes under the runtime run directory:

```text
runs/20260531-153843-240865/runtime_vs_postrun_comparison/
```

Files:

- `runtime_vs_postrun_comparison.json` — full machine-readable comparison report.
- `runtime_vs_postrun_summary.md` — human-readable summary of counts, alignment, closed gaps, remaining gaps, and boundaries.
- `runtime_coverage_gaps.json` — gap inventory focused on runtime hook coverage.
- `event_type_alignment.json` — exact and semantic event-type alignment.
- `final_state.json` — compact status and safety flags.
- `raw.log` — command-style status log.

## How runtime tracing improves over post-run extraction

Post-run extraction can only normalize information tau2 serialized after completion. Runtime tracing observes selected tau2 calls while they happen and therefore adds evidence that the extracted baseline could not recover reliably after the fact:

- turn boundaries via `turn_start` and `turn_end`;
- tool-call request and dispatch boundaries via `tool_call_requested`, `tool_dispatch_start`, `tool_dispatch_end`, `toolkit_dispatch_start`, and `toolkit_dispatch_end`;
- agent/user response boundaries via `agent_response`, `user_response`, and user generation start/end events;
- evaluation boundaries via `evaluation_start` and `evaluation_end`;
- result persistence boundaries via `result_persistence_start` and `result_persistence_end`;
- repeated state hashes around turns, environment dispatch, and toolkit dispatch;
- provider/model token and cost metadata retained in copied tau2 result artifacts.

The comparator treats exact event names as source-specific. Runtime events use hook-oriented names, while post-run extraction emits normalized `baseline.*` names. The comparison therefore reports both exact event-type sets and semantic families such as message observation, tool request/completion, evaluation, and result persistence.

## Remaining gaps

Runtime tracing does not yet close every post-run extraction limitation. Remaining expected gaps include:

- tick-level internals, because the canonical tau2 results serialize `ticks` as `null` and runtime hooks do not emit tick events;
- effect timeline transitions, because `effect_timeline` is `null` and runtime hooks do not reconstruct state-transition timelines;
- detailed DB assertion checks, because `reward_info.db_check` is `null`;
- detailed action assertion checks, because `reward_info.action_checks` is `null`;
- detailed natural-language assertion checks, because `reward_info.nl_assertions` is `null`;
- first-class usage/token/cost fields on runtime events, because those details are currently retained in tau2 results rather than promoted onto each runtime event;
- exact turn-index alignment, because post-run extraction uses serialized message `turn_idx` values while runtime tracing uses orchestrator `step_count` boundaries.

## Safety boundary

The comparison does not add ActiveGraph control over tau2. It does not feed state packets back to tau2 and does not change tau2 inputs, task state, lifecycle, or vendored source. It is an artifact-only analysis step intended to show which runtime hooks improve observability and which lower-level hooks would be needed next.
