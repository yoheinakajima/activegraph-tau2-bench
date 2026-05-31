# Post-run tau2 baseline trace extraction

## Purpose

`python scripts/extract_tau2_baseline_trace.py` converts an already-completed, model-backed tau2 baseline run into a repository-owned JSONL trace. The extractor is intentionally post-run only: it reads the wrapper artifacts and tau2 `results.json` that already exist under a run directory, then writes normalized trace files beside those artifacts.

This phase is for preparing real baseline observations for later baseline-vs-ActiveGraph comparison without changing tau2 execution behavior.

## Command

```bash
python scripts/extract_tau2_baseline_trace.py --run-dir runs/20260531-042306-420109
```

For failed or partial runs, the extractor refuses by default. Use `--allow-failed` only when intentionally inspecting an incomplete run:

```bash
python scripts/extract_tau2_baseline_trace.py --run-dir <runs/...> --allow-failed
```

## Expected inputs

The input must be an existing tau2 model baseline wrapper run directory with:

- `final_state.json` from `scripts/run_tau2_model_baseline.py`
- `summary.md` from the wrapper
- `raw.log` from the wrapper and tau2 stdout/stderr capture
- `tau2_output/results.json` produced by tau2
- optionally, copied artifacts under `tau2_artifacts/`

Without `--allow-failed`, `final_state.json` must contain `"status": "tau2_model_baseline_passed"`.

## Output files

Outputs are written under the run directory in `extracted_trace/`:

- `baseline_trace.jsonl` — normalized trace events, one JSON object per line
- `baseline_trace_summary.md` — human-readable extraction summary
- `baseline_trace_final_state.json` — machine-readable extraction final state
- `baseline_artifact_index.json` — inspected artifact inventory with sizes, hashes, parsers, and contribution flags

## Trace schema

The extractor reuses the repository trace event envelope where practical:

- `event_id`
- `timestamp`
- `run_id`
- `phase`
- `component`
- `event_type`
- `task_id`
- `turn_index`
- `tool_name`
- `message_role`
- `state_hash`
- `payload`
- `parent_event_id`

Every extracted event uses:

- `phase: real_tau2_model_baseline_extracted`
- `payload.trace_mode: post_run_extraction`
- `payload.fixture_backed: false`
- `payload.tau2_rerun: false`
- `payload.llm_api_calls_made_by_extractor: false`

## What is extracted from real tau2 artifacts

From wrapper `final_state.json`, the extractor emits run/config events containing the source run status, provider/model metadata, tau2 command metadata, task ID, domain, max steps, and output paths.

From tau2 `tau2_output/results.json`, the extractor emits only event categories directly supported by the observed artifact structure:

- run/task metadata from `tasks[]` and `simulations[]`
- message observations from `simulations[].messages[]`
- tool requests from message-level `tool_calls[]`
- tool completions from messages whose role is `tool`
- evaluation observations from `simulations[].reward_info`
- result persistence metadata from the results artifact and copied artifact list

The extractor indexes `tau2_artifacts/results.json` when present, but treats it as a copy of `tau2_output/results.json` and does not emit duplicate events from it.

## What is unavailable

The baseline artifact format does not provide every internal tau2 runtime transition. The extractor does not fabricate unavailable categories. Depending on the run, unavailable details can include:

- internal orchestrator state transitions that were not serialized to `results.json`
- database state snapshots when tau2 did not persist them in the result object
- tool implementation internals beyond serialized tool call/result messages
- evaluator sub-check detail when `reward_info` contains only summary/null fields
- token-level or streaming chunks when only final messages are serialized

These limitations are recorded in `baseline_trace_summary.md`, `baseline_trace_final_state.json`, and `baseline_artifact_index.json`.

## No-LLM/no-rerun boundary

The extractor does not:

- launch tau2
- import tau2 runtime code
- instantiate model-backed agents or users
- call LLM/API services
- require API keys
- mutate `vendor/tau2-bench`
- change tau2 execution behavior
- integrate ActiveGraph control into tau2

Any LLM/API calls represented in the source artifacts happened during the original explicit opt-in baseline run, not during extraction.

## Difference from fixture-backed trace smoke

The fixture-backed trace smoke (`scripts/run_trace_smoke.py`) proves the local trace schema and artifact-writing pipeline with deterministic, no-LLM fixture data. It does not inspect a real tau2 model-backed run.

Post-run baseline trace extraction reads a real completed tau2 result artifact and preserves observed model-run metadata, messages, tool calls, tool results, and reward information. It is still no-LLM at extraction time because it only parses files.

## Preparing baseline-vs-ActiveGraph comparison

The extracted trace gives later comparison work a real baseline event stream with the same high-level envelope used by fixture traces. A future comparison step can align fixture-backed and real baseline traces by task ID, turn index, message role, tool name, event type, reward metadata, and artifact provenance before any ActiveGraph execution-control integration is considered.
