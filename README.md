# activegraph-tau2-bench

This repository evaluates future **ActiveGraph.ai** integrations against the official **tau2-bench** benchmark while keeping the vendored benchmark source separate from local experiment code.

## Current phase boundary

- **Current phase:** Phase 1.5 local vendored source map and no-LLM smoke baseline.
- **Not implemented yet:** ActiveGraph integration, trace capture, state packets, reactive manager behavior, and Phase 2 observability hooks.
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
  scripts/run_smoke_baseline.py
  runs/                         # generated smoke output
  vendor/tau2-bench/            # vendored upstream benchmark source
```

## Install commands

For local repository smoke checks, no tau2 install or API key is required:

```bash
python scripts/run_smoke_baseline.py
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

The Phase 1.5 smoke harness is intentionally source/data inspection only. It:

- never requires API keys;
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

## Smoke output location

Each smoke run creates a timestamped directory:

```text
runs/<timestamp>/
  raw.log
  summary.md
  final_state.json
```

`raw.log` contains command/check details, `summary.md` is a human-readable summary, and `final_state.json` records the machine-readable final state and check results.

## Source map

See `docs/source_map.md` for exact local source paths and function/class names covering CLI entrypoints, run/batch flow, half-duplex interfaces, orchestrator turn loop, user simulator, environment/tool dispatch, domain data loading, task/evaluation models, artifacts, determinism controls, no-LLM smoke candidates, and future Phase 2 observability hook candidates.
