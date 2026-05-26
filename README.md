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
- **Phase 1 (this phase):** local install + baseline no-LLM smoke checks only.

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

## Provenance

Official upstream benchmark:
- https://github.com/sierra-research/tau2-bench

> Note: In this environment, outbound GitHub access is blocked (HTTP 403 tunnel error), so the vendor checkout cannot be fetched automatically here.

When network access is available:

```bash
git clone https://github.com/sierra-research/tau2-bench vendor/tau2-bench
cd vendor/tau2-bench
git rev-parse HEAD
```

Record the printed commit hash in your run notes.

## Install (baseline)

After vendoring tau2-bench:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
# then install tau2-bench per upstream docs, e.g. one of:
# pip install -e vendor/tau2-bench
# or: uv pip install -e vendor/tau2-bench
```

## Smoke test (no LLM/API calls)

Run:

```bash
python scripts/run_smoke_baseline.py
```

This writes artifacts to `runs/<timestamp>/`:
- `final_state.json`
- `summary.md`
- `raw.log`

The script is designed to avoid LLM/API calls; it only performs local structural checks and optional `pytest --collect-only` when vendor code exists.

## What remains once vendor code is present

- Inspect and document tau2-bench runtime/entrypoints/domains/tools/policies/state/evaluation details.
- Run the smallest local upstream smoke target that does not hit paid model APIs.
