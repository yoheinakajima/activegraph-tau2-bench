# tau2 runtime trace

- status: `tau2_runtime_traced_baseline_passed`
- run_id: `20260531-193831-340466`
- runtime events: `/Users/yoheinakajima/activegraph-tau2-bench/runs/20260531-193831-340466/runtime_events.jsonl`
- event count: `70`
- paid LLM/API calls made: `True`
- ActiveGraph control of tau2: `false`
- command: `python experiments/tau2_runtime_trace/traced_tau2_cli.py run --domain airline --agent llm_agent --agent-llm openai/gpt-4.1-mini --user user_simulator --user-llm openai/gpt-4.1-mini --num-trials 1 --max-steps 20 --max-concurrency 1 --save-to /Users/yoheinakajima/activegraph-tau2-bench/runs/20260531-193831-340466/tau2_output --log-level INFO --num-tasks 1`

## Event counts

- `agent_response`: `6`
- `batch_end`: `1`
- `batch_start`: `1`
- `evaluation_end`: `1`
- `evaluation_start`: `1`
- `message_observed`: `1`
- `orchestrator_run_end`: `1`
- `orchestrator_run_start`: `1`
- `result_persistence_end`: `1`
- `result_persistence_start`: `1`
- `simulation_end`: `1`
- `simulation_execution_end`: `1`
- `simulation_execution_start`: `1`
- `simulation_start`: `1`
- `tool_call_requested`: `1`
- `tool_dispatch_end`: `1`
- `tool_dispatch_start`: `1`
- `toolkit_dispatch_end`: `1`
- `toolkit_dispatch_start`: `1`
- `trace_bootstrap_end`: `1`
- `trace_bootstrap_start`: `1`
- `turn_end`: `13`
- `turn_start`: `13`
- `user_generate_end`: `6`
- `user_generate_start`: `6`
- `user_response`: `6`

## Structurally validated hooks

- `agent_base_generate_contract`
- `batch_run_simulation_alias`
- `batch_run_single_task`
- `batch_run_tasks`
- `environment_get_response`
- `evaluator_evaluate_simulation`
- `layer1_run_simulation`
- `orchestrator_run`
- `orchestrator_step`
- `simulation_evaluate_alias`
- `simulation_model_dump`
- `toolkit_use_tool`
- `user_simulator_generate_contract`

## Deferred/live-only hooks

