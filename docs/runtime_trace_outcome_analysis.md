# Runtime trace outcome analysis

`python scripts/analyze_runtime_trace_outcome.py` is an offline analyzer for already-produced runtime-traced tau2 baseline runs.  It generalizes the older successful-run-only report into a reusable outcome report for successful, failed, and partial-progress traces.

## Command

```bash
python scripts/analyze_runtime_trace_outcome.py \
  --runtime-run-dir runs/20260531-170618-525260 \
  --reference-success-run-dir runs/20260531-155904-128551 \
  --postrun-baseline-dir runs/20260531-042306-420109
```

The command writes to:

```text
<runtime-run-dir>/runtime_outcome_analysis/
```

## Outputs

- `runtime_outcome_analysis.json` — full machine-readable report titled `runtime-traced tau2 baseline analysis`.
- `runtime_outcome_summary.md` — human-readable outcome summary.
- `completion_or_failure_path.json` — ordered path events plus success/failure-path interpretation.
- `metric_classification.json` — explicit `task_outcome` classification, inputs, and rules.
- `final_state.json` — compact status, classification, metrics, evidence, and offline boundary flags.
- `raw.log` — plain-text execution summary.

## Task outcome classes

The analyzer emits exactly one `task_outcome` value:

| Outcome | Meaning |
| --- | --- |
| `success` | Reward is `1.0`, DB match is `true`, expected write actions matched, and the run stopped normally. |
| `failed_no_write` | An expected write action exists, but no live write dispatch was detected before evaluation; the run failed benchmark criteria despite a normal stop. |
| `failed_partial_progress` | Runtime evidence shows a mutation attempt or mutation result, but reward/DB/action/stop criteria did not pass.  A max-steps run with live mutation evidence is classified here and also records the premature max-steps reason. |
| `failed_max_steps` | The run terminated with `termination_reason=max_steps` and no more specific mutation/no-write failure class applied. |
| `failed_unknown` | Fallback for incomplete or conflicting artifacts that do not match the more specific rules. |

## Classification inputs

Classification is deterministic and uses only existing artifacts:

- tau2 reward from `tau2_output/results.json` or `tau2_artifacts/results.json`.
- DB match / DB reward when present.
- Expected and matched write action checks.
- Normal stop and termination reason.
- Live write tool dispatches before `evaluation_start`.
- Evaluation-phase write replay events, kept separate from live runtime writes.
- State hash before/after changes around live writes.
- Tool result payloads, such as returned task IDs and statuses.

## Partial progress vs success

Partial progress is not success.  For example, a run may call `create_task`, receive a `task_2` payload, and change the runtime state hash, but still fail because it reaches `max_steps`, never reaches a normal user stop, or lacks a passing DB/action check.  The analyzer preserves that evidence as `failed_partial_progress` instead of flattening the run to a generic reward-0 failure.

## Why reward alone is insufficient

Reward is the benchmark verdict, but it can hide useful runtime evidence:

- A no-write failure and a partial-progress write failure can both have reward `0.0`.
- A max-steps run can mutate state before termination.
- A normal-stop failure can show that the agent never dispatched the expected write tool.

The outcome analyzer keeps reward as an input while also reporting write detection, state-hash changes, and tool result payloads so reviewers can distinguish absent mutation from failed or incomplete mutation.

## No-rerun / no-API boundary

The analyzer is offline-only.  It does not run tau2, does not run another model-backed episode, does not call LLM/API services, does not require API keys, does not mutate `vendor/tau2-bench`, and does not add ActiveGraph control over tau2.

## Compatibility wrapper

`scripts/analyze_successful_runtime_trace.py` remains as an argument-compatible wrapper for older commands.  It delegates to the generalized outcome analyzer and writes outcome-neutral files under `runtime_outcome_analysis/`.

## Unit test coverage

Fixture-based unit tests in `tests/test_runtime_trace_outcome_classification.py` exercise the offline `classify_task_outcome()` rules and live-write evidence extraction without invoking tau2, model-backed episodes, LLM/API services, or API keys.  The tests cover all five emitted outcome classes (`success`, `failed_no_write`, `failed_partial_progress`, `failed_max_steps`, and `failed_unknown`) with minimal in-memory dictionaries/events, including checks that success requires reward, DB, action-match, and normal-stop evidence; no-write failures keep evaluation replay separate from live writes; partial-progress failures preserve live mutation evidence; max-steps failures remain distinct from generic unknowns; and ambiguous inputs fall back to `failed_unknown`.
