# tau2 runtime trace

- status: `tau2_runtime_traced_baseline_passed`
- run_id: `20260601-033543-612139`
- runtime events: `/Users/yoheinakajima/activegraph-tau2-bench/runs/20260601-033543-612139/runtime_events.jsonl`
- event count: `526`
- paid LLM/API calls made: `True`
- ActiveGraph control of tau2: `false`
- command: `python experiments/tau2_runtime_trace/traced_tau2_cli.py run --domain airline --agent llm_agent --agent-llm openai/gpt-4.1-mini --user user_simulator --user-llm openai/gpt-4.1-mini --num-trials 1 --max-steps 30 --max-concurrency 1 --save-to /Users/yoheinakajima/activegraph-tau2-bench/runs/20260601-033543-612139/tau2_output --log-level INFO --num-tasks 5`

## Event counts

- `agent_response`: `43`
- `batch_end`: `1`
- `batch_start`: `1`
- `evaluation_end`: `5`
- `evaluation_start`: `5`
- `message_observed`: `23`
- `orchestrator_run_end`: `5`
- `orchestrator_run_start`: `5`
- `result_persistence_end`: `1`
- `result_persistence_start`: `1`
- `simulation_end`: `5`
- `simulation_execution_end`: `5`
- `simulation_execution_start`: `5`
- `simulation_start`: `5`
- `tool_call_requested`: `27`
- `tool_dispatch_end`: `29`
- `tool_dispatch_start`: `29`
- `toolkit_dispatch_end`: `36`
- `toolkit_dispatch_start`: `36`
- `trace_bootstrap_end`: `1`
- `trace_bootstrap_start`: `1`
- `turn_end`: `91`
- `turn_start`: `91`
- `user_generate_end`: `25`
- `user_generate_start`: `25`
- `user_response`: `25`

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

