# activegraph-tau2-bench

A local, no-LLM readiness harness for evaluating future **ActiveGraph.ai** integrations around the official **tau2-bench** source while keeping upstream benchmark code isolated under `vendor/tau2-bench/`.

## Current status

- **Current milestone:** Phase 13 consolidation, milestone report, and CI-lite validation.
- **Preferred validation:** `python scripts/run_all_smokes.py` → `aggregate_status=all_smokes_passed`.
- **Live execution:** unavailable and fail-closed; `live_ready=false` remains intentional.
- **LLM/API calls in smokes:** none. The local smoke commands do not require API keys and do not call paid model services.
- **tau2 control:** ActiveGraph does not control tau2 lifecycle or task state, and state packets are not fed back into tau2 execution.
- **Vendor posture:** tau2-bench is vendored as local source and must remain unmodified by this harness.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python scripts/check_repo_health.py
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

## Smoke commands

The aggregate command runs the completed no-LLM smoke suite:

```bash
python scripts/run_all_smokes.py
```

Individual smoke scripts remain available in `scripts/` for targeted review, but the aggregate command is the compact validation path.

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
