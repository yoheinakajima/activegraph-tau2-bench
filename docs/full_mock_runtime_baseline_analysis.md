# Full mock runtime baseline analysis

`scripts/analyze_full_mock_runtime_baseline.py` performs an offline analysis of an already-produced full mock runtime-traced tau2 baseline run. It is intended for the committed run at `runs/20260531-184109-726391`, which used OpenAI `gpt-4.1-mini` on the `mock` domain with 10 tasks, `max_steps=10`, and concurrency 1.

## Command

```bash
python scripts/analyze_full_mock_runtime_baseline.py \
  --runtime-run-dir runs/20260531-184109-726391
```

The analyzer writes reports under:

```text
runs/20260531-184109-726391/full_mock_analysis/
```

## Inputs inspected

The command reads these existing artifacts only:

- `runtime_events.jsonl`
- `runtime_trace_final_state.json`
- `runtime_trace_summary.md`
- `tau2_output/results.json`
- `raw.log`

It does not run tau2, does not run another model-backed episode, does not call LLM/API services, does not require API keys, does not mutate `vendor/tau2-bench`, and does not add ActiveGraph control.

## Outputs

- `full_mock_baseline_analysis.json` — complete machine-readable report.
- `full_mock_baseline_summary.md` — human-readable benchmark, task, failure, and coverage summary.
- `task_outcomes.json` — per-task metrics, event counts, tool calls, mutation evidence, and classification.
- `failure_analysis.json` — failed task IDs, failure kinds, and inferable reasons.
- `runtime_event_coverage.json` — event-family and event-type coverage.
- `mutation_summary.json` — expected writes, live write detections, state-hash changes, and result IDs.
- `final_state.json` — compact final status and benchmark summary.
- `raw.log` — analysis command log and offline-boundary assertions.

## Classification

The analyzer reuses the existing runtime outcome classification rules where practical and emits one of:

- `success`
- `failed_no_write`
- `failed_partial_progress`
- `failed_max_steps`
- `failed_unknown`

For full mock benchmark summaries, pass/fail follows tau2 reward semantics: a task with reward `1.0`, normal stop, and matched expected write actions is treated as a benchmark success. DB match, action checks, write action success, termination reason, cost, event counts, tool calls, and mutation evidence remain visible so cases such as DB mismatch with aggregate reward success are not hidden.

## Current committed run summary

For `runs/20260531-184109-726391`, the generated analysis reports:

- Total tasks: 10
- Average reward: 0.8000
- Pass rate: 0.800
- Write actions: 6/6
- DB match: 8/9
- Normal stop: 9
- Max steps: 1
- Runtime events: 446
- ActiveGraph controlled tau2: false
- State packets fed back to tau2: false

The two failed tasks are classified as partial progress/non-communication reward loss and max-steps failure respectively in the generated failure analysis.
