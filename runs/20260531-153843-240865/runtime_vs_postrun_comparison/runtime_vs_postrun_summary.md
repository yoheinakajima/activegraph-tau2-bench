# Runtime trace vs post-run extracted trace comparison

- status: `runtime_vs_postrun_comparison_completed_with_remaining_gaps`
- generated_at_utc: `2026-05-31T15:50:12.598109Z`
- runtime_run_dir: `runs/20260531-153843-240865`
- postrun_baseline_dir: `runs/20260531-042306-420109`
- runtime_event_count: `30`
- postrun_event_count: `12`
- schema_compatible_envelope: `True`
- runtime_paid_llm_api_calls_made: `True`
- activegraph_controlled_tau2: `False`
- state_packets_fed_back_to_tau2: `False`
- tau2_rerun_performed_by_comparison: `False`
- llm_api_calls_made_by_comparison: `False`
- requires_api_keys: `False`

## Event-type alignment

- exact common event types: `0`
- common semantic event families: `evaluation_observed, message_observed, results_persisted, run_completed, run_started, task_started, tool_completed, tool_requested`
- runtime-only event types: `agent_response, batch_end, batch_start, evaluation_end, evaluation_start, message_observed, orchestrator_run_end, orchestrator_run_start, result_persistence_end, result_persistence_start, simulation_end, simulation_execution_end, simulation_execution_start, simulation_start, tool_call_requested, tool_dispatch_end, tool_dispatch_start, toolkit_dispatch_end, toolkit_dispatch_start, trace_bootstrap_end, trace_bootstrap_start, turn_end, turn_start, user_generate_end, user_generate_start, user_response`
- postrun-only event types: `baseline.config.loaded, baseline.evaluation.observed, baseline.message.observed, baseline.result.persisted, baseline.run.completed, baseline.run.started, baseline.task.started, baseline.tool.completed, baseline.tool.requested`

## Coverage summary

- runtime task ids: `['create_task_1']`
- post-run task ids: `['create_task_1']`
- runtime turn indexes: `[0, 1, 2]`
- post-run turn indexes: `[0, 1, 2, 3]`
- runtime message roles: `['assistant', 'tool', 'user']`
- post-run message roles: `['assistant', 'tool', 'user']`
- runtime tool names: `['get_users']`
- post-run tool names: `['get_users']`
- runtime state-hash events: `15`
- post-run state-hash events: `1`

## Previous post-run extraction gaps now closed

- Runtime trace closes the turn-level boundary gap with turn_start and turn_end events.
- Runtime trace closes the tool dispatch gap with request, environment dispatch, and toolkit dispatch events.
- Runtime trace adds explicit agent_response and user_response boundaries in addition to serialized messages.
- Runtime trace adds evaluation start/end boundaries instead of only post-run reward observation.
- Runtime trace adds result persistence start/end boundaries around tau2 result saving.
- Runtime trace improves state snapshot coverage with repeated environment/toolkit state hashes around turns and tools.
- Runtime run artifacts retain provider/model token and cost metadata in copied tau2 results.

## Remaining runtime hook coverage gaps

- detailed DB assertion checks remain missing because reward_info.db_check is null.
- detailed action assertion checks remain missing because reward_info.action_checks is null.
- detailed natural-language assertion checks remain missing because reward_info.nl_assertions is null.
- effect timeline transitions are still missing; tau2 results serialize effect_timeline as null and runtime hooks do not reconstruct it.
- tick-level internals are still missing; tau2 results serialize ticks as null and runtime hooks do not emit tick events.

## Missed message/tool/evaluator fields

- runtime events do not emit a config_observed equivalent; config remains available in tau2 results artifacts.
- turn indexes do not align exactly: post-run extraction uses serialized message turn_idx values while runtime hooks use orchestrator step_count boundaries.

## Optional comparison inputs

- trace_comparison: available=`False` path=`runs/20260531-042306-420109/trace_comparison`
- activegraph_projection: available=`False` path=`runs/20260531-042306-420109/activegraph_projection`

## Boundary

This comparison reads existing runtime-trace and post-run extraction artifacts only. It does not run tau2, does not run a model-backed episode, does not call LLM/API services, does not require API keys, does not feed state packets back to tau2, and does not mutate `vendor/tau2-bench`.
