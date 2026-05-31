# tau2 runtime trace

- status: `tau2_runtime_traced_baseline_passed`
- run_id: `20260531-184109-726391`
- runtime events: `/Users/yoheinakajima/activegraph-tau2-bench/runs/20260531-184109-726391/runtime_events.jsonl`
- event count: `446`
- paid LLM/API calls made: `True`
- ActiveGraph control of tau2: `false`
- command: `python experiments/tau2_runtime_trace/traced_tau2_cli.py run --domain mock --agent llm_agent --agent-llm openai/gpt-4.1-mini --user user_simulator --user-llm openai/gpt-4.1-mini --num-trials 1 --max-steps 10 --max-concurrency 1 --save-to /Users/yoheinakajima/activegraph-tau2-bench/runs/20260531-184109-726391/tau2_output --log-level INFO --num-tasks 10`

## Event counts

- `agent_response`: `25`
- `batch_end`: `1`
- `batch_start`: `1`
- `evaluation_end`: `10`
- `evaluation_start`: `10`
- `message_observed`: `13`
- `orchestrator_run_end`: `10`
- `orchestrator_run_start`: `10`
- `result_persistence_end`: `1`
- `result_persistence_start`: `1`
- `simulation_end`: `10`
- `simulation_execution_end`: `10`
- `simulation_execution_start`: `10`
- `simulation_start`: `10`
- `tool_call_requested`: `13`
- `tool_dispatch_end`: `26`
- `tool_dispatch_start`: `26`
- `toolkit_dispatch_end`: `33`
- `toolkit_dispatch_start`: `33`
- `trace_bootstrap_end`: `1`
- `trace_bootstrap_start`: `1`
- `turn_end`: `61`
- `turn_start`: `61`
- `user_generate_end`: `23`
- `user_generate_start`: `23`
- `user_response`: `23`

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

