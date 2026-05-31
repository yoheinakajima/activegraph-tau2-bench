# Real tau2 local smoke

## Purpose

`python scripts/run_tau2_real_smoke.py` is the first non-fixture operational tau2 check in this repository. It validates the local vendored `vendor/tau2-bench` package surface without requiring API keys, paid LLM calls, external services, voice providers, or model-backed benchmark episodes.

The smoke is intentionally focused on real tau2 install/import/CLI/data/test behavior. It does not add another readiness, auditor, review, safety, or consolidation layer.

## Install strategy

The script reads `vendor/tau2-bench/pyproject.toml` and expects Python `>=3.12,<3.14`. If `uv` is available, it runs from `vendor/tau2-bench` with:

```bash
uv sync
```

When that succeeds, CLI and import probes prefer `uv run`. Child processes receive `TAU2_DATA_DIR=vendor/tau2-bench/data` and API-key environment variables are removed. `LITELLM_LOCAL_MODEL_COST_MAP=True` is set so importing tau2 uses LiteLLM's bundled local model-cost map instead of attempting a remote metadata fetch.

For pytest, the script runs the repository Python with `PYTHONPATH` pointing at `vendor/tau2-bench/src` and, when available, the `vendor/tau2-bench/.venv` site-packages directory. This lets the local harness pytest execute a small no-LLM tau2 subset against the installed vendored dependencies without installing tau2 into the harness environment.

## Command

```bash
python scripts/run_tau2_real_smoke.py
```

Outputs are written to an ignored `runs/<timestamp>/` directory.

## Tiers of checks

### Tier 0: local source checks

Verifies that the vendored source exists, the recorded upstream commit matches, and key mock-domain files are present:

- `vendor/tau2-bench/`
- `vendor/tau2-bench.UPSTREAM_COMMIT`
- `vendor/tau2-bench/pyproject.toml`
- `vendor/tau2-bench/src/tau2/cli.py`
- `vendor/tau2-bench/data/tau2/domains/mock/`
- `tasks.json`
- `policy.md`
- `src/tau2/domains/mock/tools.py`

### Tier 1: Python/package checks

Detects Python version, parses `pyproject.toml`, checks whether the current Python satisfies tau2's requirement, detects `uv`, runs dependency sync when possible, and checks `tau2` import behavior.

### Tier 2: safe CLI checks

Runs only no-LLM tau2 commands:

```bash
tau2 --help
tau2 run --help
tau2 check-data
tau2 intro
```

These commands exercise the real CLI and data-dir wiring, but do not start model-backed episodes.

### Tier 3: safe tests

Runs a small no-LLM subset from the official vendored tests:

- `tests/test_domains/test_mock/test_tools_mock.py`
- `tests/test_tasks.py`
- `tests/test_environment.py`

The subset covers mock tools, task loading/data format, and environment/toolkit behavior. It avoids API-key, model-backed, voice-provider, external-service, and network tests.

### Tier 4: optional no-LLM tau2 run

The script inspects the local source posture and currently skips `tau2 run` episodes. The vendored registry provides LLM-backed agent factories and a `dummy_user`, but no dummy/non-LLM agent factory that can complete a benchmark episode through `tau2 run` without a model. The script reports `real_tau2_episode_not_available_without_llm` rather than forcing an unsafe command.

## Domain/data probe

The smoke writes `domain_probe.json`. The file-level probe reads the mock-domain files, counts tasks, confirms `policy.md` is non-empty, checks `db.json` and `user_db.json`, and records the mock tools source path. If tau2 imports, the script also probes the actual tau2 registry/domain loader and records domains, agents, users, mock task count, first task id, and mock tool count.

## What counts as pass

The strongest status is:

- `tau2_real_smoke_passed`

This is only reported when at least one real tau2 command or real tau2 test ran against the installed vendored package. In the normal full local path, CLI commands and the no-LLM pytest subset run.

If only source/path checks pass because dependencies cannot be installed or imported, the script reports:

- `tau2_real_smoke_source_only_passed`

The aggregate smoke treats that status as a warning-level minimum so dependency/network limitations are visible without hiding unexpected failures.

## Status interpretation

- `tau2_real_smoke_source_only_passed`: source and mock-domain file checks passed, but import/CLI/tests did not run successfully.
- `tau2_real_smoke_import_passed`: vendored tau2 import worked.
- `tau2_real_smoke_cli_passed`: safe CLI help commands worked.
- `tau2_real_smoke_data_check_passed`: `tau2 check-data` worked against local vendored data.
- `tau2_real_smoke_tests_passed`: safe no-LLM vendored tests worked.
- `tau2_real_smoke_passed`: full local no-LLM operational smoke passed.
- `tau2_real_smoke_failed`: an unexpected required check failed.
- `tau2_real_smoke_env_missing`: required local source/vendor files are missing.
- `tau2_real_smoke_install_failed`: reserved for dependency installation failures that cannot safely degrade to source-only reporting.

## Manual uv commands

If `uv` is available, these are the corresponding manual checks:

```bash
cd vendor/tau2-bench
uv sync
uv run tau2 --help
uv run tau2 run --help
uv run tau2 check-data
```

For a no-LLM test subset after `uv sync`, run from `vendor/tau2-bench`:

```bash
PYTHONPATH="$PWD/src:$PWD/.venv/lib/python3.12/site-packages" \
TAU2_DATA_DIR="$PWD/data" \
LITELLM_LOCAL_MODEL_COST_MAP=True \
python -m pytest -q \
  tests/test_domains/test_mock/test_tools_mock.py \
  tests/test_tasks.py \
  tests/test_environment.py
```

## Future model-backed baseline

A future model-backed baseline should be implemented as a separate explicit opt-in task. It should require credentials, document cost controls, choose a single mock or small domain task, set low concurrency and max steps, write artifacts under `runs/<timestamp>/`, and preserve the current no-LLM smoke as the default local validation path. This session intentionally does not implement model-backed baseline execution.
