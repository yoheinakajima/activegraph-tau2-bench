# Runtime DB mutation analysis

This document describes the offline deterministic DB-diff / mutation-summary projection for runtime-traced tau2 baselines, including successful runs, no-write failures, and partial-progress failures.

## Purpose

The analyzer inspects already-produced artifacts from a runtime-traced baseline and projects the DB mutation evidence that is available without fabricating a complete database diff.

The canonical successful run reports:

- 44 runtime events
- reward `1.0`
- DB match `true`
- write actions `1/1`
- normal stop `true`
- agent errors `0`
- user errors `0`
- completion path: user request → `create_task` write tool → `task_2` result/state-hash change → assistant confirmation → normal user stop → reward/DB/action success

## Command

```bash
python scripts/analyze_runtime_db_mutation.py \
  --runtime-run-dir runs/20260531-155904-128551
```

The command writes to:

```text
runs/20260531-155904-128551/db_mutation_analysis/
```

## Inputs inspected

The analyzer requires and inspects these existing source artifacts:

- `runtime_events.jsonl`
- `tau2_output/results.json`

When present, it also uses generalized outcome-analysis artifacts as confirmation context, with legacy successful-runtime artifacts as a fallback:

- `runtime_outcome_analysis/completion_or_failure_path.json`
- `runtime_outcome_analysis/runtime_outcome_analysis.json`
- `runtime_outcome_analysis/final_state.json`
- `runtime_success_analysis/completion_path.json` (legacy fallback)
- `runtime_success_analysis/successful_runtime_trace_analysis.json` (legacy fallback)
- `runtime_success_analysis/final_state.json` (legacy fallback)

It performs artifact analysis only. It does not run tau2, run a model-backed episode, call LLM/API services, require API keys, mutate `vendor/tau2-bench`, or add ActiveGraph control over tau2.

## Outputs

- `db_mutation_summary.json` — full machine-readable mutation projection.
- `db_mutation_summary.md` — human-readable summary with detected write tools, inferred mutation, confirmation fields, confidence, and limitations.
- `mutation_events.jsonl` — compact evidence events for live runtime write execution plus evaluation replay evidence.
- `mutation_evidence_index.json` — source artifact index, event IDs, confirmation sources, and field paths used.
- `final_state.json` — compact status and boundary state.
- `raw.log` — plain-text execution summary.

## Evidence model

The projection uses only evidence that exists in the committed run artifacts:

1. Runtime tool dispatch evidence (`tool_call_requested`, `tool_dispatch_start`, `tool_dispatch_end`).
2. Low-level toolkit dispatch evidence (`toolkit_dispatch_start`, `toolkit_dispatch_end`).
3. Tool arguments from runtime dispatch payloads.
4. Tool result payloads from toolkit result fields and tool-message content.
5. State hash before/after fields around the write tool.
6. tau2 reward, DB check, and action check fields from `tau2_output/results.json`.
7. Existing runtime outcome-analysis final metrics for normal stop and error counts, with legacy successful-runtime metrics as a fallback.

## Compatibility findings

The analyzer supports three important evidence shapes:

- Success write with reward success: a live write is detected, DB match is true, and reward/action checks pass.
- No-write failure: expected write action checks exist, but no live write dispatch is detected before evaluation.
- Partial-progress write with reward failure: a live write/result/state-hash change is detected, but reward/DB/action/termination criteria do not pass.

The canonical successful run has one detected live runtime write:

| Tool | Arguments | Result | State hash changed | Inferred mutation |
| --- | --- | --- | --- | --- |
| `create_task` | `user_id=user_1`, `title=Important Meeting` | `task_id=task_2`, `status=pending` | `107f83a70b7bf4f616e283b0b0b8451346fe7681173398d4498a1ec15c5fdfc6` → `3b82583d5c026d816c5a32430fb3ab8d42b72ec2b91cd5cafaab817e0e05b00c` | task created (`task_2`) |

The analyzer retains evaluation-phase `create_task` replay/toolkit events as confirmation evidence, but it does not count them as additional live runtime writes.

## Confirmation fields

For the canonical run, the projection records:

- reward: `1.0`
- DB match: `true`
- DB reward: `1.0`
- write actions matched: `1/1`
- termination reason: `user_stop`
- normal stop: `true`
- agent errors: `0`
- user errors: `0`

## Confidence and limitations

The canonical projection is high confidence because tool-call evidence, tool-result evidence, a state-hash change, and tau2 reward/DB/action checks all agree.

The analyzer intentionally does not fabricate missing DB state. The current source artifacts do not include a full before/after DB snapshot or a serialized row-level DB diff, so the report states that limitation and uses the available tool, result, state-hash, and reward/DB/action evidence instead.

## Boundary

This analyzer is offline-only. It does not:

- run tau2
- run another model-backed episode
- call LLM/API services
- require API keys
- mutate `vendor/tau2-bench`
- add ActiveGraph control over tau2
- feed state packets or mutation projections back into tau2
