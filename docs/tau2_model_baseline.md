# Explicit opt-in tau2 model baseline

## Purpose

`scripts/run_tau2_model_baseline.py` is the first wrapper for running a real, model-backed tau2 baseline episode from this repo. It is intentionally narrow:

- It runs tau2 through the vendored project with `cd vendor/tau2-bench && uv run tau2 ...`.
- It targets one text-mode tau2 task by default.
- It writes wrapper artifacts under this repo's ignored `runs/<timestamp>/` directories.
- It does **not** integrate ActiveGraph into tau2 execution.
- It does **not** replace `scripts/run_tau2_real_smoke.py`, which remains the default no-LLM operational validation path.

The local tau2 CLI exposes text model selection with `--agent-llm` and `--user-llm`, not with separate provider flags. The wrapper therefore accepts `--provider` and `--model`, then passes the combined LiteLLM-style model name `<provider>/<model>` to both tau2 flags.

## Explicit cost/API warning

This command can call paid model provider APIs. It refuses to run tau2 unless all of the following are true:

1. `--provider` is supplied.
2. `--model` is supplied.
3. `--yes-i-understand-this-may-call-paid-apis` is supplied.
4. The domain is `mock`, unless `--allow-non-mock-domain` is also supplied.
5. Required provider API-key-like environment variables are present.

The wrapper reports only whether API-key-like environment variables are present. It does not print or store secret values.

## Command shape

```bash
python scripts/run_tau2_model_baseline.py \
  --provider <provider> \
  --model <model> \
  --domain mock \
  --task-id <task_id_or_index> \
  --max-steps <small_number> \
  --yes-i-understand-this-may-call-paid-apis
```

Internally, for text-mode tau2 runs, the wrapper builds a command equivalent to:

```bash
cd vendor/tau2-bench && uv run tau2 run \
  --domain mock \
  --agent llm_agent \
  --agent-llm <provider>/<model> \
  --user user_simulator \
  --user-llm <provider>/<model> \
  --num-trials 1 \
  --max-steps <small_number> \
  --max-concurrency 1 \
  --save-to /absolute/path/to/runs/<timestamp>/tau2_output \
  --log-level INFO \
  --task-ids <task_id_or_index>
```

If `--task-id` is omitted, it uses `--num-tasks 1` instead.

## Required env vars by provider

Set the provider credentials in your shell before running the wrapper. Examples of provider environment variables are:

| Provider | Environment variable presence checked |
| --- | --- |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` or `claude` | `ANTHROPIC_API_KEY` |
| `google` or `gemini` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `azure` or `azure_openai` | `AZURE_OPENAI_API_KEY` |
| `xai` | `XAI_API_KEY` |
| `mistral` | `MISTRAL_API_KEY` |
| `cohere` | `COHERE_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `together` or `together_ai` | `TOGETHER_API_KEY` |
| `fireworks` or `fireworks_ai` | `FIREWORKS_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `bedrock` | `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` presence is reported; at least one mapped variable must be present for the wrapper guard |

For unknown provider names, the wrapper requires at least one known API-key-like environment variable to be present and then lets tau2/LiteLLM perform final provider validation.

## Why this is not part of `run_all_smokes.py`

`python scripts/run_all_smokes.py` is the compact no-LLM validation path. It must stay safe for routine local and CI-like use, with no paid API calls and no model-backed tau2 episodes. The model baseline wrapper is deliberately separate because a successful run may spend money, depend on provider credentials, and vary with external model/provider availability.

## One-task mock-domain baseline

Example for OpenAI:

```bash
export OPENAI_API_KEY='...'
python scripts/run_tau2_model_baseline.py \
  --provider openai \
  --model gpt-4.1-mini \
  --domain mock \
  --task-id 0 \
  --max-steps 2 \
  --yes-i-understand-this-may-call-paid-apis
```

## Output artifacts

Every invocation creates a new ignored `runs/<timestamp>/` wrapper directory containing:

- `raw.log` — wrapper log and, for real executions, tau2 stdout/stderr.
- `summary.md` — human-readable status, command, key-presence booleans, and artifact list.
- `final_state.json` — machine-readable status, parameters, exact tau2 command, key-presence booleans, tau2 output path, and copied artifact metadata.
- `tau2_output/` — tau2 `--save-to` output location when a model-backed episode runs.
- `tau2_artifacts/` — copied tau2 result/trajectory/log files when tau2 generates them.

Possible statuses are:

- `tau2_model_baseline_ready_not_run`
- `tau2_model_baseline_refused_missing_ack`
- `tau2_model_baseline_refused_missing_model`
- `tau2_model_baseline_refused_non_mock_domain`
- `tau2_model_baseline_env_missing`
- `tau2_model_baseline_passed`
- `tau2_model_baseline_failed`

## Troubleshooting tau2/LiteLLM/provider errors

- Confirm the no-LLM path first:

  ```bash
  python scripts/run_tau2_real_smoke.py
  ```

- Confirm the aggregate no-LLM suite still passes:

  ```bash
  python scripts/run_all_smokes.py
  ```

- If the wrapper reports `tau2_model_baseline_refused_missing_ack`, add `--yes-i-understand-this-may-call-paid-apis` only when you intend to make paid calls.
- If it reports `tau2_model_baseline_refused_missing_model`, pass both `--provider` and `--model`.
- If it reports `tau2_model_baseline_refused_non_mock_domain`, use `--domain mock` for the first baseline, or explicitly add `--allow-non-mock-domain` after reviewing cost and task scope.
- If it reports `tau2_model_baseline_env_missing`, export the relevant provider environment variable without echoing the secret value.
- If tau2 runs and then fails, inspect `runs/<timestamp>/raw.log` for tau2/LiteLLM/provider diagnostics and `runs/<timestamp>/final_state.json` for the exact command and output path.

## Later baseline vs ActiveGraph comparisons

This wrapper establishes the first explicit paid/API opt-in baseline only. Future work can compare the same provider/model/domain/task/max-step tuple against:

1. Baseline tau2 with no ActiveGraph involvement.
2. ActiveGraph trace-only observation around tau2 execution.
3. ActiveGraph state-packet capture for post-run analysis.
4. Reactive-manager modes after they are proven safe outside tau2 control.

Those later modes should preserve this baseline command as the control condition and should not mutate vendored tau2 source.
