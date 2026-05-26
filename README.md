# activegraph-tau2-bench

This repository is for evaluating **ActiveGraph.ai** against the official **tau2-bench** benchmark.

## Scope

- Upstream benchmark source should live in `vendor/tau2-bench`.
- This repo keeps benchmark code separate from experiment code (`experiments/`, `scripts/`, `runs/`, `docs/`).
- Planned comparisons in later phases:
  - Baseline tau2-bench
  - ActiveGraph trace-only
  - ActiveGraph state-packet
  - ActiveGraph reactive manager
- **Current phase boundary:** no ActiveGraph integration yet.

## Repo layout

```text
activegraph-tau2-bench/
  README.md
  vendor/tau2-bench/
  experiments/
  scripts/
  runs/
  docs/
```

## Provenance (currently blocked in this environment)

Official upstream benchmark:
- https://github.com/sierra-research/tau2-bench

Vendoring attempts on **2026-05-26** failed in this environment due to outbound GitHub access restrictions (`CONNECT tunnel failed, response 403`):

```bash
git clone https://github.com/sierra-research/tau2-bench vendor/tau2-bench
git clone --depth 1 https://github.com/sierra-research/tau2-bench vendor/tau2-bench
curl -L https://github.com/sierra-research/tau2-bench/archive/refs/heads/main.tar.gz
```

Because vendoring is blocked, there is **no upstream commit hash recorded yet**.

When network access is available:

```bash
git clone https://github.com/sierra-research/tau2-bench vendor/tau2-bench
git -C vendor/tau2-bench rev-parse HEAD
```

Record that exact commit hash here and in `docs/source_map.md`.

## Install (once vendored)

Tau2 upstream docs indicate `uv`-based workflow and Python 3.12+.

```bash
cd vendor/tau2-bench
uv sync
uv run tau2 check-data
uv run tau2 intro
```

## Smoke test command

```bash
python scripts/run_smoke_baseline.py
```

## Smoke behavior and limits

The smoke harness:
- creates `runs/<timestamp>/`
- writes `raw.log`, `summary.md`, and `final_state.json`
- performs **no LLM/API calls**
- reports one of these states:
  - `upstream_missing`
  - `install_failed`
  - `import_failed`
  - `data_check_failed`
  - `source_inspection_only_passed`
  - `no_llm_smoke_passed`

What it validates today in this blocked environment:
- local repo structure and absence/presence of `vendor/tau2-bench`

What it does **not** validate until vendoring succeeds:
- tau2 install/runtime behavior
- data checks
- CLI behavior
- domain/task/policy/tool/evaluation loading from real upstream source

## Next phases (not implemented here)

After this Phase 1.5 vendoring/source-map/smoke step is complete with real upstream code:
1. baseline tau2 behavior
2. ActiveGraph trace-only
3. ActiveGraph state-packet
4. ActiveGraph reactive manager

## Latest blocker update (2026-05-26 UTC)

Re-attempted vendoring in this session and still blocked by outbound GitHub restrictions (HTTP 403 / CONNECT tunnel failure). See `docs/source_map.md` for exact commands and next steps.
