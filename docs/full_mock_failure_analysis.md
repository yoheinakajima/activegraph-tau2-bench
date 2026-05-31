# Full mock baseline detailed failure analysis

`python scripts/analyze_full_mock_failures.py --runtime-run-dir runs/20260531-184109-726391` performs an offline, read-only reconstruction of the two failed tasks in the committed full mock runtime-traced tau2 baseline.

## Scope and boundaries

The analyzer is intentionally artifact-only:

- It does **not** run tau2.
- It does **not** run another model-backed episode.
- It does **not** call LLM/API services.
- It does **not** require API keys.
- It does **not** mutate `vendor/tau2-bench`.

It inspects these existing artifacts from the runtime run directory:

- `runtime_events.jsonl`
- `tau2_output/results.json`
- `full_mock_analysis/task_outcomes.json`
- `full_mock_analysis/failure_analysis.json`
- `raw.log`

If the `full_mock_analysis/` inputs are not present yet, first generate the existing baseline-level analysis:

```bash
python scripts/analyze_full_mock_runtime_baseline.py \
  --runtime-run-dir runs/20260531-184109-726391
```

## Usage

```bash
python scripts/analyze_full_mock_failures.py \
  --runtime-run-dir runs/20260531-184109-726391
```

By default, outputs are written under:

```text
runs/20260531-184109-726391/full_mock_failure_analysis/
```

## Outputs

- `failure_analysis_detailed.json` — full per-task reconstruction, likely cause, and smallest next experiment.
- `failure_analysis_summary.md` — human-readable summary that directly answers the failure questions.
- `failed_task_timelines.json` — compact runtime event and message timeline by failed task.
- `failed_task_event_slices.jsonl` — event slices for the failed task spans, including task-less tool dispatch events that occur inside each span.
- `scoring_evidence.json` — reward, action, DB, communicate, env, NL, and outcome-classification evidence.
- `final_state.json` — analyzer status, input hashes, output list, and offline/no-API boundary metadata.
- `raw.log` — copied baseline raw log for colocated inspection.

## Failure conclusions encoded by the analyzer

### `update_task_with_initialization_data`

The detailed analyzer classifies this as a communication/scorer-detail failure, not a DB/write failure. The task reached normal `user_stop`, the DB matched, and the expected `update_task_status(task_2, completed)` write action matched. The reward nevertheless remained `0.0` because the task reward basis includes `COMMUNICATE`, and the serialized `communicate_checks` both have `met=false`:

- the agent did not satisfy the scorer's check for acknowledging the previous context;
- the agent did not satisfy the scorer's check for confirming the task status was updated successfully.

The artifact evidence makes wrong initial state unlikely because the runtime trace shows a state mutation for `task_2` and the final reward info reports `db_match=true`. It also makes missing user interaction unlikely because the episode stopped normally.

Smallest next experiment: rerun only this task with the same seed and an agent instruction that explicitly says it understands the previous `task_2` context and successfully updated `task_2` to completed, then compare only the communicate checks.

### `update_task_with_user_tools`

The detailed analyzer classifies this as a max-steps failure. The user simulator did call `check_notifications`, and the assistant eventually updated `task_1` and confirmed completion. However, the 10-step budget was exhausted before the user had another turn to call `dismiss_notification('notif_1')` and stop. Because tau2 terminated the episode with `max_steps`, the serialized reward info does not include DB/action/env/NL checks for this task.

The failure is therefore more likely an agent turn-path / task-complexity / tight-budget issue than an instrumentation failure. The current setup captured one user-side tool call (`check_notifications`), but the required post-confirmation user-side `dismiss_notification` behavior was not reached.

Smallest next experiment: rerun only this task with a slightly larger `max_steps` budget, or keep the budget fixed and prompt the agent to update `task_1` directly from the notification context without the extra user-ID clarification loop; then verify that the user calls `dismiss_notification` and the user env assertion passes.
