# activegraph-tau2-bench

A local, no-LLM readiness harness for evaluating future **ActiveGraph.ai** integrations around the official **tau2-bench** source while keeping upstream benchmark code isolated under `vendor/tau2-bench/`.

## Current status

- **Current milestone:** Phase 13 consolidation, milestone report, and CI-lite validation.
- **Fast unit validation:** `python -m unittest discover -s tests`.
- **Preferred smoke validation:** `python scripts/run_all_smokes.py` → `aggregate_status=all_smokes_passed`.
- **Live execution:** unavailable and fail-closed; `live_ready=false` remains intentional.
- **LLM/API calls in smokes:** none. The local smoke commands do not require API keys and do not call paid model services.
- **tau2 control:** ActiveGraph does not control tau2 lifecycle or task state, and state packets are not fed back into tau2 execution.
- **Vendor posture:** tau2-bench is vendored as local source and must remain unmodified by this harness.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python scripts/check_repo_health.py
python -m unittest discover -s tests
python scripts/run_all_smokes.py
```

For the health check plus full smoke aggregate:

```bash
python scripts/check_repo_health.py --run-smokes
```

## Review docs

- [Phase matrix](docs/phase_matrix.md) — phase-by-phase command/status/artifact table.
- [Milestone report](docs/milestone_report.md) — consolidated Phase 1.5 through Phase 13 report.
- [Operations guide](docs/operations.md) — setup, validation, artifact inspection, cleanup, and safety boundaries.
- [Source map](docs/source_map.md) — local map of the vendored tau2-bench source.

## Vendored tau2 provenance

- Upstream project: `sierra-research/tau2-bench`
- Vendored source path: `vendor/tau2-bench/`
- Recorded upstream commit: `fcc9ed68df33c93ff0b8c946865f267d7c99fb06`
- Commit marker: `vendor/tau2-bench.UPSTREAM_COMMIT`

Verify vendor cleanliness with:

```bash
cat vendor/tau2-bench.UPSTREAM_COMMIT
git status --short -- vendor/tau2-bench vendor/tau2-bench.UPSTREAM_COMMIT
```


## Real tau2 local smoke

Run the first non-fixture tau2 operational check with:

```bash
python scripts/run_tau2_real_smoke.py
```

This command avoids LLM/API calls and does not require API keys. It checks the local vendored tau2-bench install/import/CLI/data/test behavior where available, including safe commands such as `tau2 --help`, `tau2 run --help`, `tau2 check-data`, and `tau2 intro`, plus a small no-LLM mock-domain test subset when dependencies are installed. It does not run model-backed tau2 benchmark episodes. Outputs are written to ignored `runs/<timestamp>/` directories with `raw.log`, `summary.md`, `final_state.json`, and `domain_probe.json`. See [Real tau2 local smoke](docs/tau2_real_smoke.md) for details.

## Explicit opt-in tau2 model baseline

A real model-backed tau2 baseline is available as an explicit, paid-API opt-in command. It is **not** included in `python scripts/run_all_smokes.py` and does not integrate ActiveGraph into tau2 execution.

```bash
python scripts/run_tau2_model_baseline.py \
  --provider <provider> \
  --model <model> \
  --domain mock \
  --task-id <task_id_or_index> \
  --max-steps 2 \
  --yes-i-understand-this-may-call-paid-apis
```

The wrapper refuses to run without provider/model configuration and the paid-API acknowledgement flag, reports only API-key presence booleans, and writes artifacts under ignored `runs/<timestamp>/` directories. See [Explicit opt-in tau2 model baseline](docs/tau2_model_baseline.md) for setup, outputs, and troubleshooting.



## Airline task 8 prompt/control variant

An explicit opt-in prompt/control variant runner is available for investigating the airline task 8 passenger-preservation failure mode. It is **not** included in `python scripts/run_all_smokes.py`, keeps concurrency at 1, records the exact prompt variant under `runs/<timestamp>/`, and refuses unless provider/model and the paid-API acknowledgement are supplied.

```bash
python scripts/run_airline_task8_prompt_variant.py \
  --provider openai \
  --model gpt-4.1-mini \
  --max-steps 30 \
  --yes-i-understand-this-may-call-paid-apis
```

See [Airline task 8 prompt/control variant](docs/airline_task8_prompt_variant.md) for boundaries, refusal checks, and artifact details.

### Airline task 8 prompt-variant comparison

Compare the committed airline task 8 baseline and prompt-variant failures offline, without rerunning tau2 or calling LLM/API services:

```bash
python scripts/compare_airline_task8_prompt_variant.py \
  --baseline-run-dir runs/20260531-204930-608103 \
  --variant-run-dir runs/20260531-222346-104165
```

The comparator writes `prompt_variant_comparison.json`, `prompt_variant_comparison_summary.md`, action/tool/message deltas, `generalization_assessment.json`, `final_state.json`, and `raw.log` under `runs/20260531-222346-104165/prompt_variant_comparison/`. It marks the prompt variant as task-specific, identifies the general failure class as multi-constraint write action argument construction after multi-step read evidence, and records general ActiveGraph-style intervention hypotheses without implementing them. See [Airline task 8 prompt-variant comparison](docs/airline_task8_prompt_variant_comparison.md).

### Failed trace write-intent gap scan

Scan existing failed or partial runtime artifacts for task-agnostic write-intent gaps without rerunning tau2 or calling LLM/API services:

```bash
python scripts/scan_failed_traces_for_write_intent_gaps.py
```

The scanner writes `write_intent_gap_scan.json`, `write_intent_gap_scan_summary.md`, `failure_taxonomy.json`, `trace_case_index.json`, `candidate_intervention_matrix.json`, `final_state.json`, and `raw.log` under `runs/write_intent_gap_scan_<timestamp>/`. It reports whether each case is detectable offline today, requires runtime observation, or would require future ActiveGraph control for prevention. See [Failed trace write-intent gap scan](docs/write_intent_gap_scan.md).

### Airline task 8 write-intent constraint analysis

Build an offline pre-write constraint ledger and compare baseline/prompt-variant `book_reservation` arguments against the required task 8 write intent, without rerunning tau2 or calling LLM/API services:

```bash
python scripts/analyze_airline_task8_write_intent.py \
  --baseline-run-dir runs/20260531-204930-608103 \
  --variant-run-dir runs/20260531-222346-104165
```

The analyzer writes `write_intent_analysis.json`, `write_intent_summary.md`, `constraint_ledger.json`, `write_argument_diff.json`, `evidence_timeline.json`, `general_intervention_hypotheses.json`, `final_state.json`, and `raw.log` under `runs/20260531-222346-104165/write_intent_analysis/`. It identifies the baseline dropped-entity/payment mismatch, the prompt variant's missing search evidence/payment mismatch, and general pre-write constraint/check hypotheses rather than recommending more task-specific prompt tuning. See [Airline task 8 write-intent constraint analysis](docs/airline_task8_write_intent_analysis.md).

### Runtime trace-only tau2 instrumentation

A no-LLM runtime trace smoke validates the trace writer, hook schema, and non-invasive monkeypatch installation without requiring API keys or paid services:

```bash
python scripts/run_tau2_runtime_trace_smoke.py
```

An explicit opt-in model-backed traced baseline is available, but is not included in aggregate smokes and must be acknowledged as paid/API-backed:

```bash
python scripts/run_tau2_runtime_traced_baseline.py \
  --provider <provider> \
  --model <model> \
  --domain mock \
  --task-id create_task_1 \
  --max-steps 2 \
  --yes-i-understand-this-may-call-paid-apis
```

See [tau2 runtime trace-only instrumentation](docs/tau2_runtime_trace.md) for hook coverage, artifacts, status values, and no-control/no-vendor-mutation boundaries.


### Runtime trace outcome analysis

Analyze any already-produced runtime-traced tau2 baseline outcome against a reference success run and the post-run extracted baseline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_runtime_trace_outcome.py \
  --runtime-run-dir runs/20260531-170618-525260 \
  --reference-success-run-dir runs/20260531-155904-128551 \
  --postrun-baseline-dir runs/20260531-042306-420109
```

The analyzer writes `runtime_outcome_analysis.json`, `runtime_outcome_summary.md`, `completion_or_failure_path.json`, `metric_classification.json`, `final_state.json`, and `raw.log` under `<runtime-run-dir>/runtime_outcome_analysis/`. It classifies `success`, `failed_no_write`, `failed_partial_progress`, `failed_max_steps`, and `failed_unknown` using reward, DB checks, write-action checks, stop reason, live write dispatches, state-hash changes, and tool result payloads. It is offline-only: no tau2 rerun, no model-backed episode, no LLM/API calls, no API keys, no vendored tau2 mutation, and no ActiveGraph control. The legacy `scripts/analyze_successful_runtime_trace.py` command remains as a compatibility wrapper. See [Runtime trace outcome analysis](docs/runtime_trace_outcome_analysis.md) for details.

### Full mock runtime baseline analysis

Analyze the committed 10-task full mock runtime-traced baseline offline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_full_mock_runtime_baseline.py \
  --runtime-run-dir runs/20260531-184109-726391
```

The analyzer writes `full_mock_baseline_analysis.json`, `full_mock_baseline_summary.md`, `task_outcomes.json`, `failure_analysis.json`, `runtime_event_coverage.json`, `mutation_summary.json`, `final_state.json`, and `raw.log` under `<runtime-run-dir>/full_mock_analysis/`. It reports benchmark pass rate, average reward, per-task outcomes, DB/action/write checks, termination reasons, costs where available, runtime event coverage, mutation evidence, and inferable failure causes. See [Full mock runtime baseline analysis](docs/full_mock_runtime_baseline_analysis.md) for details.


### Airline runtime baseline analysis

Analyze the committed first successful airline runtime-traced baseline offline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_airline_runtime_baseline.py \
  --runtime-run-dir runs/20260531-193831-340466
```

The analyzer writes `airline_baseline_analysis.json`, `airline_baseline_summary.md`, `airline_task_timeline.json`, `airline_tool_timeline.json`, `airline_scoring_evidence.json`, `final_state.json`, and `raw.log` under `<runtime-run-dir>/airline_analysis/`. It reports task instructions, reward/DB evidence, agent/user turn path, read/write tool timeline, runtime event coverage, cost/token usage, runtime-trace advantages over post-run results, and remaining airline instrumentation gaps. See [Airline runtime-traced baseline analysis](docs/airline_runtime_baseline_analysis.md) for details.

### Full mock detailed failure analysis

Analyze the failed cases from the committed full mock runtime-traced tau2 baseline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_full_mock_failures.py \
  --runtime-run-dir runs/20260531-184109-726391
```

The analyzer writes `failure_analysis_detailed.json`, `failure_analysis_summary.md`, `failed_task_timelines.json`, `failed_task_event_slices.jsonl`, `scoring_evidence.json`, `final_state.json`, and `raw.log` under `runs/20260531-184109-726391/full_mock_failure_analysis/`. It explains why `update_task_with_initialization_data` received reward `0.0` despite DB/write success and why `update_task_with_user_tools` hit `max_steps`. See [Full mock baseline detailed failure analysis](docs/full_mock_failure_analysis.md).


### Update task user-tools DB mismatch analysis

Analyze the committed `update_task_with_user_tools` runtime-traced failure artifact offline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_update_task_user_tools_db_mismatch.py --runtime-run-dir runs/20260531-191847-173904
```

The analyzer writes `db_mismatch_analysis.json`, `db_mismatch_summary.md`, `tool_call_timeline.json`, `expected_vs_observed.json`, `scoring_evidence.json`, `final_state.json`, and `raw.log` under `runs/20260531-191847-173904/db_mismatch_analysis/`. It identifies whether the assistant updated the wrong task/status, whether notification dismissal succeeded, how user DB state differs from gold DB replay, and why the env assertion can pass while the combined DB check fails. See [update_task_with_user_tools DB mismatch analysis](docs/update_task_user_tools_db_mismatch.md).


### Airline task 8 failure analysis

Analyze the committed airline task 8 runtime-traced failure artifact offline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_airline_task8_failure.py \
  --runtime-run-dir runs/20260531-204930-608103
```

The analyzer writes `airline_task8_failure_analysis.json`, `airline_task8_failure_summary.md`, `action_expectation_analysis.json`, `tool_call_timeline.json`, `expected_vs_observed.json`, `scoring_evidence.json`, `final_state.json`, and `raw.log` under `runs/20260531-204930-608103/airline_task8_failure_analysis/`. It compares the expected two-passenger HAT271 booking against the observed one-passenger booking and remains offline-only: no tau2 rerun, no model-backed episode, no LLM/API calls, no API keys, and no vendored tau2 mutation. See [Airline task 8 failure analysis](docs/airline_task8_failure_analysis.md).

### Runtime DB mutation analysis

Project the available DB mutation evidence from the successful runtime-traced tau2 baseline without rerunning tau2 or calling APIs:

```bash
python scripts/analyze_runtime_db_mutation.py \
  --runtime-run-dir runs/20260531-155904-128551
```

The analyzer writes `db_mutation_summary.json`, `db_mutation_summary.md`, `mutation_events.jsonl`, `mutation_evidence_index.json`, `final_state.json`, and `raw.log` under `runs/20260531-155904-128551/db_mutation_analysis/`. It reports the detected `create_task` write, tool arguments/result payload, state-hash transition, inferred `task_2` creation, reward/DB/action confirmation, confidence, and the limitation that no full before/after DB snapshot is available. See [Runtime DB mutation analysis](docs/runtime_db_mutation_analysis.md) for details.

### Runtime vs post-run trace comparison

Compare the paid runtime-traced tau2 baseline against the earlier post-run extracted baseline trace without rerunning tau2 or calling APIs:

```bash
python scripts/compare_runtime_trace_vs_postrun_trace.py \
  --runtime-run-dir runs/20260531-153843-240865 \
  --postrun-baseline-dir runs/20260531-042306-420109
```

The comparator writes `runtime_vs_postrun_comparison.json`, `runtime_vs_postrun_summary.md`, `runtime_coverage_gaps.json`, `event_type_alignment.json`, `final_state.json`, and `raw.log` under `<runtime-run-dir>/runtime_vs_postrun_comparison/`. The expected canonical status is `runtime_vs_postrun_comparison_completed_with_remaining_gaps`. See [Runtime trace vs post-run extracted trace comparison](docs/runtime_vs_postrun_trace_comparison.md) for closed gaps, remaining hook coverage gaps, and no-rerun/no-API boundaries.

### Post-run baseline trace extraction

Extract a normalized trace from an already-completed tau2 model baseline run without rerunning tau2 or calling LLM/API services:

```bash
python scripts/extract_tau2_baseline_trace.py --run-dir <runs/...>
```

The extractor writes `baseline_trace.jsonl`, `baseline_trace_summary.md`, `baseline_trace_final_state.json`, and `baseline_artifact_index.json` under `<runs/...>/extracted_trace/`. See [Post-run tau2 baseline trace extraction](docs/tau2_baseline_trace_extraction.md) for schema details and no-LLM/no-rerun boundaries.


### Offline ActiveGraph projection from a real baseline trace

Project an already-extracted real tau2 baseline trace into offline ActiveGraph-style graph and state-packet artifacts without rerunning tau2 or calling LLM/API services:

```bash
python scripts/project_baseline_trace_to_activegraph.py \
  --baseline-run-dir runs/20260531-042306-420109
```

The projector writes `activegraph_baseline_projection.json`, `activegraph_baseline_events.jsonl`, `activegraph_baseline_state_packets.jsonl`, `activegraph_baseline_state_packet_index.json`, `activegraph_projection_summary.md`, `activegraph_projection_final_state.json`, and `raw.log` under `<baseline-run-dir>/activegraph_projection/`. The expected canonical-run status is `activegraph_baseline_projection_completed_with_gaps` because the real baseline artifacts do not serialize tick-level or effect-timeline details. See [ActiveGraph projection from a real tau2 baseline trace](docs/activegraph_baseline_projection.md) for schema, packet validation, and boundary details.

### Fixture vs real ActiveGraph projection comparison

Compare a fixture-backed ActiveGraph smoke projection against the offline real-baseline ActiveGraph projection without rerunning tau2 or calling APIs:

```bash
python scripts/run_activegraph_trace_smoke.py
python scripts/run_state_packet_smoke.py
python scripts/compare_activegraph_projection_vs_baseline.py \
  --fixture-run-dir <runs/state-packet-smoke-dir> \
  --baseline-run-dir runs/20260531-042306-420109
```

Use the `run_state_packet_smoke.py` output directory as the fixture run because it contains `events.jsonl`, `activegraph_trace.json`, `state_packets.jsonl`, and `state_packet_index.json`. The comparator writes `activegraph_projection_comparison_report.json`, `activegraph_projection_comparison_summary.md`, `graph_alignment.json`, `packet_alignment.json`, `provenance_alignment.json`, `coverage_gaps.json`, `final_state.json`, and `raw.log` under `<baseline-run-dir>/activegraph_projection_comparison/`. The expected canonical status is `activegraph_projection_comparison_completed_with_expected_gaps`. See [Fixture vs real ActiveGraph projection comparison](docs/activegraph_projection_comparison.md) for comparison dimensions, expected fixture-vs-real differences, known gaps, and no-rerun/no-API boundaries.

### Fixture vs real baseline trace comparison

Compare a no-LLM fixture trace smoke run against an already-extracted real tau2 baseline trace without rerunning tau2 or calling APIs:

```bash
python scripts/run_trace_smoke.py
python scripts/compare_fixture_vs_baseline_trace.py \
  --fixture-run-dir <runs/...> \
  --baseline-run-dir runs/20260531-042306-420109
```

The comparator writes `trace_comparison_report.json`, `trace_comparison_summary.md`, `event_type_alignment.json`, `schema_field_alignment.json`, `coverage_gaps.json`, `final_state.json`, and `raw.log` under `<baseline-run-dir>/trace_comparison/` by default. See [Fixture vs real baseline trace comparison](docs/fixture_vs_baseline_trace_comparison.md) for comparison dimensions, expected gaps, and no-LLM/no-rerun boundaries.

## Validation commands

Use standard-library test discovery for the fastest unit-level check, including runtime trace outcome classification coverage:

```bash
python -m unittest discover -s tests
```

Use the aggregate command for the completed no-LLM smoke suite:

```bash
python scripts/run_all_smokes.py
```

Individual smoke scripts remain available in `scripts/` for targeted review, but the aggregate command is the compact full-harness validation path.

## Artifact locations

Generated outputs are written to ignored `runs/<timestamp>/` directories. Aggregate runs include:

- `aggregate_final_state.json`
- `aggregate_summary.md`
- `aggregate_raw.log`

See the [operations guide](docs/operations.md) for inspection and cleanup commands.

## Explicit non-goals for this milestone

This repository does not implement or enable:

- live reactive-manager execution;
- ActiveGraph control over tau2 lifecycle or task state;
- state-packet feedback into tau2 execution;
- vendored tau2-bench behavior changes;
- model-backed tau2 benchmark episodes;
- paid LLM/API calls;
- real credential handling, vault integration, or raw secret storage.

### Passive write-intent observer

Run the deterministic no-LLM passive observer smoke without rerunning tau2 or
calling model/API services:

```bash
python scripts/run_write_intent_observer_smoke.py
```

The smoke writes `observer_events.jsonl`, `constraint_ledger_snapshots.jsonl`,
`write_intent_diffs.jsonl`, `observer_summary.md`, `observer_final_state.json`,
and `raw.log` under `runs/<timestamp>/`. It validates fixture coverage for the
airline task 8 write gaps, a successful `create_task_1`, a no-write case, and a
DB mismatch/scoring ambiguity case. An explicit paid/API-backed runtime traced
baseline can optionally add passive emission with `--enable-write-intent-observer`,
but the observer remains no-control and does not block or rewrite tau2 tool
calls. See [Passive write-intent observer](docs/write_intent_passive_observer.md).
