# Operations guide

This guide covers local review and CI-lite operation for the no-LLM tau2-bench/ActiveGraph readiness repo.

## Setup

Use Python 3.12 from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
```

The local smoke and health scripts use the Python standard library. They do not require API keys and do not require installing the vendored tau2 package.

## Validation commands

Use the lightweight standard-library unit test discovery command when changing runtime trace outcome classification logic or when you need the fastest check of the `tests/` suite:

```bash
python -m unittest discover -s tests
```

Use the aggregate no-LLM smoke command when you need the full local harness validation and can tolerate generated artifacts under `runs/<timestamp>/`:

```bash
python scripts/run_all_smokes.py
```

Expected aggregate status:

```text
aggregate_status=all_smokes_passed
```

Neither command requires API keys, calls paid model services, or runs model-backed tau2 benchmark episodes.

## CI-lite health checks

Fast repository health check:

```bash
python scripts/check_repo_health.py
```

Health check plus the full smoke aggregate:

```bash
python scripts/check_repo_health.py --run-smokes
```

The default health check is intentionally cheap: it checks that the runtime outcome unit test file is present, but it does not execute the full smoke suite. The `--run-smokes` flag delegates to `python scripts/run_all_smokes.py`.

## Inspect the latest aggregate run

Aggregate outputs are written below `runs/<timestamp>/`. To inspect the latest aggregate run:

```bash
latest=$(find runs -maxdepth 2 -name aggregate_final_state.json -print | sort | tail -1)
echo "$latest"
python -m json.tool "$latest"
```

The sibling `aggregate_summary.md` contains a compact table of child smoke statuses.

## Artifact locations

- Per-smoke artifacts: `runs/<timestamp>/`
- Aggregate smoke artifacts: `runs/<timestamp>/aggregate_final_state.json`, `runs/<timestamp>/aggregate_summary.md`, and `runs/<timestamp>/aggregate_raw.log`
- Documentation: `docs/`
- Local experiment code: `experiments/`
- Smoke and health scripts: `scripts/`
- Vendored upstream tau2 source: `vendor/tau2-bench/`
- Vendored upstream commit marker: `vendor/tau2-bench.UPSTREAM_COMMIT`

## Clean ignored runs safely

Generated run directories are ignored by git. To preview cleanup:

```bash
git clean -ndX runs
```

To remove ignored generated run artifacts after reviewing the preview:

```bash
git clean -fdX runs
```

Do not remove `runs/.gitkeep`.

## Troubleshoot Python version issues

The health check requires Python 3.12 or newer. If it fails:

```bash
python --version
which python
python3.12 --version
```

If `python` is not Python 3.12+, recreate and activate the local environment:

```bash
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python --version
```

## Verify the vendored tau2 tree is unchanged

Check the recorded upstream commit:

```bash
cat vendor/tau2-bench.UPSTREAM_COMMIT
```

Check for local vendor modifications:

```bash
git status --short -- vendor/tau2-bench vendor/tau2-bench.UPSTREAM_COMMIT
```

A clean result means no tracked vendor changes are pending. The health check also verifies key vendor paths and the expected commit marker.

## What not to run without explicit future gating

Do not run any of the following without a future, explicit gate and review plan:

- Live reactive-manager execution.
- Any ActiveGraph path that controls tau2 lifecycle or task state.
- State-packet feedback into tau2 execution.
- Model-backed tau2 benchmark episodes.
- `tau2 run` configurations that require LLM/API credentials.
- Auto-review, NL-assertion, voice, user-simulator, or agent configurations that call paid APIs.
- Real credential/vault integrations or external audit-store writes.

## GitHub Actions

The repository includes a CI-lite workflow at `.github/workflows/ci.yml`. It runs the fast health check, standard-library unit tests, and Python compile checks:

```bash
python scripts/check_repo_health.py
python -m unittest discover -s tests
python -m compileall scripts experiments
```

It intentionally does not run `python scripts/run_all_smokes.py` by default to avoid heavier artifact generation in CI.
