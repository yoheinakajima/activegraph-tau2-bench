# Airline runtime-traced baseline analysis

This document describes the offline analyzer for the first committed successful airline runtime-traced tau2 baseline:

- Run directory: `runs/20260531-193831-340466`
- Domain: `airline`
- Provider/model: `openai/gpt-4.1-mini` for both agent and user simulator
- Tasks/trials: one task, task `0`, one trial
- Max steps/concurrency: `20` / `1`
- Observed outcome: reward `1.0`, DB check `1.0`, normal user stop, and 70 runtime events

## Command

```bash
python scripts/analyze_airline_runtime_baseline.py \
  --runtime-run-dir runs/20260531-193831-340466
```

The command is offline-only. It reads committed artifacts and static airline task/domain data. It does **not** rerun tau2, run another model-backed episode, call LLM/API services, require API keys, mutate `vendor/tau2-bench`, add ActiveGraph control, or feed state packets back into tau2.

## Inputs inspected

The analyzer requires these run artifacts:

- `runtime_events.jsonl`
- `runtime_trace_final_state.json`
- `runtime_trace_summary.md`
- `tau2_output/results.json` (or `tau2_artifacts/results.json` as a fallback)
- `raw.log`

It also reads relevant static airline assets:

- `vendor/tau2-bench/data/tau2/domains/airline/tasks.json`
- `vendor/tau2-bench/data/tau2/domains/airline/db.json`
- `vendor/tau2-bench/data/tau2/domains/airline/policy.md`
- `vendor/tau2-bench/src/tau2/domains/airline/tools.py`

## Outputs

Outputs are written under `runs/20260531-193831-340466/airline_analysis/`:

- `airline_baseline_analysis.json` — full structured report with inputs, hashes, run configuration, task/reward summary, static domain evidence, turn/tool summaries, coverage, costs/tokens, and scoring evidence.
- `airline_baseline_summary.md` — human-readable summary of the inspected run.
- `airline_task_timeline.json` — message timeline plus selected runtime events for simulation, turn, tool, and evaluation flow.
- `airline_tool_timeline.json` — tool-call request/dispatch/result timeline, read/write classification, and state-hash-change evidence.
- `airline_scoring_evidence.json` — reward, DB check, task evaluation criteria, initial reservation evidence, and evaluation runtime events.
- `final_state.json` — compact analyzer status and boundary flags.
- `raw.log` — copied source run log for local inspection alongside the generated analysis artifacts.

## What the analyzer reports

For the committed baseline, the generated report highlights:

- Task `0` asks the simulated user, Emma Kim (`emma_kim_9957`), to attempt cancellation of reservation `EHGLP3` and avoid cancellation if no refund is available.
- The airline task purpose is to test that the agent refuses to proceed with a disallowed cancellation even after the user says she was told insurance was unnecessary.
- The run passed with reward `1.0`, DB match `true`, DB reward `1.0`, and termination reason `user_stop`.
- The conversation contains 14 persisted messages: seven assistant messages (including the greeting), six user messages, and one tool message.
- The only tool call was `get_reservation_details` with reservation `EHGLP3`; it returned the reservation details as a read-only result.
- No write tool call was observed, no runtime tool state hash changed, and the static DB evidence shows the initial reservation had `insurance: "no"` and `cabin: "basic_economy"`.
- Runtime event coverage includes batch, persistence, simulation, orchestrator, turn, user generation, user/agent response, tool dispatch, message observation, and evaluation events.
- The report preserves the distinction between the original paid/API-backed run and this offline analysis: the original run made paid LLM calls, while the analyzer makes none.

## Runtime trace value beyond post-run results

The runtime trace adds evidence that is difficult to reconstruct from final `results.json` alone:

- Ordered event IDs and timestamps across lifecycle, turn, tool, and evaluation phases.
- Tool-call request, environment dispatch, toolkit dispatch, response payload, and state-hash before/after boundaries.
- Message flow between agent, user simulator, and environment while the episode was live.
- Evidence that the successful airline outcome was a no-write success rather than a write/mutation success.

## Remaining gaps for airline instrumentation

The analyzer also records remaining instrumentation gaps:

- Some environment/toolkit tool dispatch events do not carry `task_id`, so they are associated by ordering and surrounding context.
- The trace stores state hashes, but not a structured before/after DB diff for no-write airline cases.
- The reward output for this task has no detailed communicate judge payload because `communicate_info` is empty.
- Policy-rule reasoning is inferred from messages and tool evidence; there is no explicit runtime event for refund-rule rationale.

## Validation

Recommended checks after changing the analyzer or docs:

```bash
python scripts/check_repo_health.py
python scripts/run_all_smokes.py
python scripts/analyze_airline_runtime_baseline.py --runtime-run-dir runs/20260531-193831-340466
python -m compileall scripts experiments
git diff --check
git status --short
git status --short -- vendor/tau2-bench
```
