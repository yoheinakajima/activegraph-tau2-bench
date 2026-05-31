# Airline runtime-traced baseline analysis

- Status: `airline_runtime_baseline_analysis_passed`
- Runtime run inspected: `runs/20260531-193831-340466`
- Task: `0` — Testing that agent refuses to proceed with a cancellation that is not allowed even if User mentions that she had been told she didn't need insurance.
- Reward: `1.0`; DB match: `True`; DB reward: `1.0`; termination: `user_stop`.
- Runtime events: `70` across `26` event types.
- Tool path: `1` call(s), `1` read, `0` write, `0` state-hash changes.
- Cost: agent `$0.004940`, user `$0.001812`, total `$0.006753`.
- Tokens from messages: `26230` total (`25762` prompt, `468` completion).

## Task goal and outcome

- Reason for call: You want to cancel reservation EHGLP3.

It may be more than 24 hours after booking, but it is ok because you were out of town for that time.
- Known info: You are Emma Kim.
Your user id is emma_kim_9957.
- Task instructions: If Agent tells you that cancellation is not possible,
mention that you were told that you didn't need to get insurance because your previous trip was booked with the same agency with insurance.

You don't want to cancel if you don't get a refund.
- The agent used `get_reservation_details` to verify reservation EHGLP3, explained that the current reservation had no insurance and basic-economy/change-of-plan cancellation did not qualify for a refund, and did not call a cancellation/write tool.
- The user declined to cancel without a refund and ended with `###STOP###`, matching the expected refusal/no-write behavior.

## Runtime trace coverage

- `agent_response`: 6
- `batch_end`: 1
- `batch_start`: 1
- `evaluation_end`: 1
- `evaluation_start`: 1
- `message_observed`: 1
- `orchestrator_run_end`: 1
- `orchestrator_run_start`: 1
- `result_persistence_end`: 1
- `result_persistence_start`: 1
- `simulation_end`: 1
- `simulation_execution_end`: 1
- `simulation_execution_start`: 1
- `simulation_start`: 1
- `tool_call_requested`: 1
- `tool_dispatch_end`: 1
- `tool_dispatch_start`: 1
- `toolkit_dispatch_end`: 1
- `toolkit_dispatch_start`: 1
- `trace_bootstrap_end`: 1
- `trace_bootstrap_start`: 1
- `turn_end`: 13
- `turn_start`: 13
- `user_generate_end`: 6
- `user_generate_start`: 6
- `user_response`: 6

## What runtime trace captures beyond post-run results

- Per-event ordering and timestamps across turn, tool, and evaluation phases.
- Tool dispatch boundaries, arguments, result payloads, and state hashes before/after dispatch.
- Agent/user generation events and role-to-role message flow, not just final messages.
- Evidence that the only tool call was read-only and no state hash changed before evaluation.

## Remaining airline instrumentation gaps

- Tool events do not carry task_id on environment/toolkit dispatch events in this run, so they must be associated by order/context.
- The trace records state hashes but not a structured DB diff for unchanged/no-write airline cases.
- Post-run reward output does not include detailed LLM-judge text for the communicate assertion when communicate_info is empty.
- Policy-rule decisions are inferred from dialogue/tool data; there is no explicit runtime event for refund-rule rationale.

## Offline boundary

- This analysis did not rerun tau2, did not run another model-backed episode, did not call LLM/API services, did not require API keys, and did not mutate `vendor/tau2-bench`.
