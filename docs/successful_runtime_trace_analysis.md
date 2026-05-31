# Successful runtime-traced tau2 baseline analysis

This document describes the offline analyzer for the successful real runtime-traced tau2 baseline at `runs/20260531-155904-128551`.

## Purpose

The analyzer compares three already-produced artifacts without rerunning tau2 or calling model/API services:

1. Successful runtime-traced baseline: `runs/20260531-155904-128551`
2. Prior short max_steps=2 runtime-traced run: `runs/20260531-153843-240865`
3. Post-run extracted baseline: `runs/20260531-042306-420109`

The canonical successful run used:

- provider: `openai`
- model: `gpt-4.1-mini`
- domain: `mock`
- task_id: `create_task_1`
- max_steps: `6`

## Command

```bash
python scripts/analyze_successful_runtime_trace.py \
  --successful-runtime-run-dir runs/20260531-155904-128551 \
  --short-runtime-run-dir runs/20260531-153843-240865 \
  --postrun-baseline-dir runs/20260531-042306-420109
```

The command writes to:

```text
runs/20260531-155904-128551/runtime_success_analysis/
```

## Outputs

- `successful_runtime_trace_analysis.json` — full machine-readable report.
- `successful_runtime_trace_summary.md` — human-readable summary.
- `runtime_event_coverage.json` — event family/type coverage, hook coverage, and remaining gaps.
- `completion_path.json` — ordered completion-path events from user/agent/tool/evaluation flow.
- `comparison_to_short_run.json` — max_steps=6 runtime trace vs prior max_steps=2 runtime trace.
- `comparison_to_postrun_trace.json` — successful runtime trace vs post-run extracted trace.
- `final_state.json` — compact status, metric, and boundary state.
- `raw.log` — plain-text execution summary.

## Findings from the committed canonical run

### Event counts

| Artifact | Event count |
| --- | ---: |
| Successful max_steps=6 runtime trace | 44 |
| Prior max_steps=2 runtime trace | 30 |
| Post-run extracted baseline trace | 12 |

The successful runtime run adds 14 events over the short runtime run and 32 events over the post-run extracted trace.

### Additional successful-runtime events over the short run

The max_steps=6 run includes additional:

- turn lifecycle events (`turn_start`, `turn_end`)
- user generation and response events (`user_generate_start`, `user_generate_end`, `user_response`)
- assistant response events (`agent_response`)
- tool dispatch and toolkit dispatch events (`tool_dispatch_*`, `toolkit_dispatch_*`)

These additional events correspond to the run continuing past the short run's early tool path and reaching the write mutation, assistant confirmation, user stop, and successful evaluation.

### Completion path

The successful run follows this path:

1. Assistant greets the user.
2. User asks to create a task titled `Important Meeting` for `user_1`.
3. Assistant requests the `create_task` tool with `user_id=user_1` and `title=Important Meeting`.
4. The environment/toolkit returns `task_2` and records a state-hash change.
5. The assistant confirms that the task was created.
6. The user emits `###STOP###` and the orchestrator stops normally.
7. Evaluation records `reward=1.0`, `db_match=true`, and a matched write action.

### Metrics

The successful run records:

- termination reason: `user_stop`
- reward: `1.0`
- DB match: `true`
- DB reward: `1.0`
- write actions: `1/1`
- normal stop: `true`
- agent errors: `0`
- user errors: `0`

The short max_steps=2 run terminated with `max_steps`, reward `0.0`, and no available DB/action success checks.

### Runtime coverage improvement over post-run extraction

Compared with post-run extraction, runtime tracing improves coverage by recording:

- bootstrap, batch, simulation, orchestrator, and per-turn lifecycle boundaries
- user generation start/end boundaries
- distinct user, assistant, and tool-message observations
- live tool dispatch and low-level toolkit dispatch
- state hashes before and after tool execution
- evaluation-time reward, DB check, and action-check observations

The post-run extractor remains useful as an offline fallback, but it cannot reconstruct all live runtime boundaries from serialized tau2 results alone.

## Reporting inconsistencies flagged

The analyzer flags reporting-only issues in the source artifacts rather than mutating historical run outputs:

- `runtime_trace_summary.md` embeds absolute local paths from the source machine.
- `runtime_trace_summary.md` renders one boolean as Python-style `True` while newer generated JSON/Markdown normalizes booleans.
- `runtime_hook_map.json` records the source machine's absolute `repo_root`.

Generated analysis artifacts use repository-relative paths where applicable and JSON booleans in machine-readable outputs.

## Remaining instrumentation gaps

The analysis confirms these gaps remain:

- Runtime tracing is observation-only; ActiveGraph still does not control tau2.
- State packets are not fed back into tau2.
- The trace does not include a full serialized DB diff; DB success is inferred from tool result content, state hashes, and reward DB checks.
- Evaluation can replay/check tools, so downstream analysis must distinguish task-time mutation from evaluator activity.
- Fixture-backed trace/projection artifacts remain offline comparison aids, not part of the live tau2 control path.

## Boundary

The analyzer is offline-only. It does not:

- run tau2
- run a model-backed episode
- call LLM/API services
- require API keys
- mutate `vendor/tau2-bench`
- add ActiveGraph control
