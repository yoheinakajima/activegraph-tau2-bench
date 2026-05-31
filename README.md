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
