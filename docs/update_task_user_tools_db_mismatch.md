# update_task_with_user_tools DB mismatch analysis

## Purpose

`update_task_with_user_tools` has a committed runtime-traced tau2 artifact at
`runs/20260531-191847-173904`. The wrapper-level run passed and tau2 stopped
normally, but the task reward was `0.0`: the assistant write action matched, the
user-side notification assertion passed, and the final DB equality check failed.

`scripts/analyze_update_task_user_tools_db_mismatch.py` performs deterministic,
offline artifact analysis for that mismatch. It reads the committed runtime
trace, tau2 result JSON, and vendored mock-domain source/data. It does not rerun
tau2, does not call a model, does not require API keys, does not mutate
`vendor/tau2-bench`, and does not add ActiveGraph execution control.

## Command

```bash
python scripts/analyze_update_task_user_tools_db_mismatch.py \
  --runtime-run-dir runs/20260531-191847-173904
```

## Input artifacts

Runtime run artifacts:

- `runs/20260531-191847-173904/runtime_events.jsonl`
- `runs/20260531-191847-173904/runtime_trace_summary.md`
- `runs/20260531-191847-173904/runtime_trace_final_state.json`
- `runs/20260531-191847-173904/tau2_output/results.json`
- `runs/20260531-191847-173904/raw.log`

Vendored mock-domain source/data:

- `vendor/tau2-bench/data/tau2/domains/mock/tasks.json`
- `vendor/tau2-bench/data/tau2/domains/mock/db.json`
- `vendor/tau2-bench/data/tau2/domains/mock/user_db.json`
- `vendor/tau2-bench/src/tau2/domains/mock/tools.py`
- `vendor/tau2-bench/src/tau2/domains/mock/user_tools.py`
- `vendor/tau2-bench/src/tau2/environment/environment.py`
- `vendor/tau2-bench/src/tau2/evaluator/evaluator_env.py`
- `vendor/tau2-bench/src/tau2/environment/toolkit.py`

## Output artifacts

The analyzer writes under
`runs/20260531-191847-173904/db_mismatch_analysis/`:

- `db_mismatch_analysis.json` — full structured report.
- `db_mismatch_summary.md` — human-readable summary.
- `tool_call_timeline.json` — runtime tool calls with arguments, results, event IDs, and state hashes.
- `expected_vs_observed.json` — reconstructed expected gold DB/user DB versus observed predicted DB/user DB.
- `scoring_evidence.json` — reward, DB check, action check, env assertion, and evaluation replay evidence.
- `final_state.json` — analyzer status and boundary flags.
- `raw.log` — concise execution log.

## Likely cause

The likely cause is a scoring/evaluation ambiguity around user-side write tools,
not an assistant task/status mistake.

The task instructs the user to check notifications, tell the assistant that
`task_1` is complete, ask the assistant to mark it `completed`, and then dismiss
`notif_1`. The assistant did update `task_1` to `completed`. The user did dismiss
`notif_1`, changing the user DB notification status to `read`.

The DB equality check compares both the agent DB and user DB. The evaluator's gold
environment applies the expected assistant action from `evaluation_criteria.actions`,
which updates `task_1` to `completed`, but it does not replay the terminal
user-side `dismiss_notification` write into the gold user DB. The predicted
environment replays the full mutating runtime trajectory, including
`dismiss_notification`, so its user DB has `notif_1.status == "read"`. The env
assertion passes because it checks the predicted user DB and expects `read`, while
the DB check fails because gold user DB still has `unread`.

## Evidence fields

Key fields to inspect:

- `tool_call_timeline.json`:
  - `tool_call_requested_event.event_id`
  - `arguments`
  - `result`
  - `state_transition.toolkit_state_hash_before`
  - `state_transition.toolkit_state_hash_after`
- `expected_vs_observed.json`:
  - `component_matches.agent_db`
  - `component_matches.user_db`
  - `diffs.user_db`
  - `expected_notification_status`
  - `observed_notification_status`
  - `hashes.expected_user_db_hash`
  - `hashes.observed_user_db_hash`
- `scoring_evidence.json`:
  - `db_check`
  - `action_checks`
  - `env_assertions`
  - `evaluation_start_event`
  - `evaluation_end_event`
  - `evaluation_replay_events`

## Limitations

- The trace provides event-level tool arguments, results, and state hashes, but
  not complete live before/after DB snapshots for every dispatch.
- The expected/observed DB projection is intentionally offline and does not
  import or execute tau2. It is based on committed task data, tool semantics, the
  serialized trajectory, and evaluator source.
- The analysis explains this committed trajectory only. It does not claim that all
  user-tool tasks fail for the same reason.

## Boundaries

- No tau2 rerun.
- No model-backed episode.
- No LLM/API calls.
- No API keys required.
- No mutation of `vendor/tau2-bench`.
- No ActiveGraph execution control.
- No state packets fed back into tau2.

## Recommended next experiment

Create an offline scoring-only experiment against this committed trajectory that
compares two evaluator variants:

1. Exclude user DB equality from the DB reward when a task includes user-side
   write tools that are separately covered by env assertions.
2. Replay expected terminal user-side writes, such as `dismiss_notification`, into
   the gold user DB before DB equality.

Run that experiment only against existing artifacts first. Do not launch a new
model-backed tau2 episode until the intended DB semantics are explicit.
