# activegraph-tau2-bench

This repository evaluates future **ActiveGraph.ai** integrations against the official **tau2-bench** benchmark while keeping the vendored benchmark source separate from local experiment code.

## Current phase boundary

- **Current phase:** Phase 3 ActiveGraph trace-only adapter smoke for the locally vendored tau2-bench baseline.
- **Not implemented yet:** ActiveGraph state packets, reactive manager behavior, and real tau2 runtime tracing. Phase 3 trace smoke is fixture-backed and no-LLM-safe; ActiveGraph is used only as a trace/log projection substrate.
- Local experiment code lives in `scripts/`, `docs/`, `runs/`, and future `experiments/` files. Upstream benchmark code lives under `vendor/tau2-bench/`.

## Vendored upstream provenance

- Upstream project: `sierra-research/tau2-bench`
- Vendored source path: `vendor/tau2-bench`
- Vendored upstream commit: `fcc9ed68df33c93ff0b8c946865f267d7c99fb06`
- Commit marker file: `vendor/tau2-bench.UPSTREAM_COMMIT`

The source map in `docs/source_map.md` is based only on the local vendored tree at that commit.

## Repo layout

```text
activegraph-tau2-bench/
  README.md
  docs/source_map.md
  docs/trace_only.md
  docs/activegraph_trace_only.md
  experiments/trace_only/
  experiments/activegraph_trace/
  scripts/run_smoke_baseline.py
  scripts/run_trace_smoke.py
  scripts/run_activegraph_trace_smoke.py
  runs/                         # generated smoke output
  vendor/tau2-bench/            # vendored upstream benchmark source
```

## Install commands

For local repository smoke checks, no tau2 install or API key is required:

```bash
python scripts/run_smoke_baseline.py
python scripts/run_trace_smoke.py
python scripts/run_activegraph_trace_smoke.py
```

For upstream tau2 development/runtime work, use the vendored upstream project environment:

```bash
cd vendor/tau2-bench
uv sync
uv run tau2 --help
uv run tau2 check-data
```

Running real tau2 benchmark simulations may require model/API credentials depending on the selected agent, user simulator, review, voice, or NL-assertion configuration.

## No-LLM/API-call boundary

The Phase 1.5 smoke harness is intentionally source/data inspection only. The Phase 2 trace smoke remains no-LLM-safe and fixture-backed while adding JSONL observability artifacts. The Phase 3 ActiveGraph trace smoke mirrors that JSONL stream into a trace-only adapter/mock projection. These smoke commands:

- never require API keys;
- never calls paid LLM APIs;
- does not run `tau2 run`;
- does not instantiate LLM agents or call user simulator generation;
- does not run auto-review or NL-assertion evaluators;
- uses Python standard-library checks over local files only.

## Smoke command

```bash
python scripts/run_smoke_baseline.py
```

Expected successful state when `vendor/tau2-bench` exists:

```text
no_llm_smoke_passed
```

The harness validates the local vendored source exists and will not report `upstream_missing` when `vendor/tau2-bench` is present.


## Phase 2 trace-only smoke command

```bash
python scripts/run_trace_smoke.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit:

```text
trace_smoke_passed
```

This command writes trace-only artifacts under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  events.jsonl
  raw.log
  summary.md
  final_state.json
```

The trace smoke is fixture-backed. It inspects real local tau2 source paths with the Python standard library and emits baseline lifecycle events, but it does not import `tau2`, run `tau2 run`, call model-backed agents, integrate ActiveGraph, create state packets, or implement reactive manager behavior. See `docs/trace_only.md` for the event schema, hook boundaries, and Phase 3 handoff notes.

## Phase 3 ActiveGraph trace-only smoke command

```bash
python scripts/run_activegraph_trace_smoke.py
```

Expected successful state when the local vendor tree exists at the recorded upstream commit and no real ActiveGraph runtime is importable:

```text
activegraph_trace_mock_passed
```

If an ActiveGraph runtime module is importable, the successful state is:

```text
activegraph_trace_runtime_passed
```

This command writes Phase 2-compatible trace events and an ActiveGraph projection under `runs/<timestamp>/`:

```text
runs/<timestamp>/
  events.jsonl
  activegraph_trace.json
  raw.log
  summary.md
  final_state.json
```

The ActiveGraph path is trace-only. It does not create state packets, implement reactive manager behavior, mutate tau2 behavior, run `tau2 run`, call model-backed agents, or require real LLM/API keys. When no ActiveGraph dependency is available, it uses the deterministic local adapter seam in `experiments/activegraph_trace/` and records `activegraph_unavailable` as availability metadata. See `docs/activegraph_trace_only.md` for mapping details and Phase 4 handoff notes.

## Smoke output location

Each smoke run creates a timestamped directory:

```text
runs/<timestamp>/
  raw.log
  summary.md
  final_state.json
```

`raw.log` contains command/check details, `summary.md` is a human-readable summary, and `final_state.json` records the machine-readable final state and check results. Phase 2 and Phase 3 trace smokes also write `events.jsonl`; Phase 3 additionally writes `activegraph_trace.json`.

## Source map

See `docs/source_map.md` for exact local source paths and function/class names covering CLI entrypoints, run/batch flow, half-duplex interfaces, orchestrator turn loop, user simulator, environment/tool dispatch, domain data loading, task/evaluation models, artifacts, determinism controls, no-LLM smoke candidates, and observability hook candidates. See `docs/trace_only.md` for the Phase 2 event schema and fixture-backed trace smoke details. See `docs/activegraph_trace_only.md` for the Phase 3 ActiveGraph trace-only adapter boundary.
