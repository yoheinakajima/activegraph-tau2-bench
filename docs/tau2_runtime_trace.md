# tau2 runtime trace-only instrumentation spike

## Purpose

The runtime trace spike observes a real tau2 run while tau2 remains fully in control of execution. It fills gaps left by post-run artifact extraction by emitting tick/turn-adjacent events, tool dispatch boundaries, state hashes before and after tools, evaluator boundaries, and result-persistence events as they happen.

This is an observation layer only. It does **not** let ActiveGraph control tau2 lifecycle, task state, tool routing, or simulation state, and it never feeds state packets back into tau2 execution.

## Hook map

The hook map is written to each run as `runtime_hook_map.json`. The current non-invasive hook targets are:

| Hook | Vendored source target | Runtime event coverage |
| --- | --- | --- |
| `batch_run_tasks` | `vendor/tau2-bench/src/tau2/runner/batch.py::run_tasks` | batch start/end and persistence intent |
| `batch_run_single_task` | `vendor/tau2-bench/src/tau2/runner/batch.py::run_single_task` | per-task simulation start/end |
| `layer1_run_simulation` | `vendor/tau2-bench/src/tau2/runner/simulation.py::run_simulation` | simulation execution and evaluation envelope |
| `batch_run_simulation_alias` | `vendor/tau2-bench/src/tau2/runner/batch.py::run_simulation` | batch module alias so `run_single_task` emits Layer 1 simulation envelope events |
| `simulation_evaluate_alias` | `vendor/tau2-bench/src/tau2/runner/simulation.py::evaluate_simulation` | simulation module alias so `run_simulation` emits evaluation events |
| `orchestrator_run` | `vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py::Orchestrator.run` | orchestrator run start/end |
| `orchestrator_step` | `vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py::Orchestrator.step` | turn start/end, message observation, agent/user responses, tool-call requests |
| `environment_get_response` | `vendor/tau2-bench/src/tau2/environment/environment.py::Environment.get_response` | tool dispatch start/end and environment state hashes |
| `toolkit_use_tool` | `vendor/tau2-bench/src/tau2/environment/toolkit.py::ToolKitBase.use_tool` | low-level toolkit dispatch start/end |
| `evaluator_evaluate_simulation` | `vendor/tau2-bench/src/tau2/evaluator/evaluator.py::evaluate_simulation` | evaluation start/end, reward/check summaries |
| `simulation_model_dump` | `vendor/tau2-bench/src/tau2/data_model/simulation.py::Results.save` | result persistence start/end |
| `agent_base_generate_contract` | `vendor/tau2-bench/src/tau2/agent/base_agent.py::HalfDuplexAgent.generate_next_message` | base contract import/signature; concrete responses are observed via `orchestrator_step` |
| `user_simulator_generate_contract` | `vendor/tau2-bench/src/tau2/user/user_simulator.py::UserSimulator.generate_next_message` | user response generation where the concrete class method is patchable |

## No-LLM dry smoke

```bash
python scripts/run_tau2_runtime_trace_smoke.py
```

The smoke command does not require API keys and must not call paid LLM/API services. It imports/inspects local vendored tau2 targets where safe, installs monkeypatches in a dry context, writes sample runtime events, and reports which hooks are structurally validated versus deferred to a live traced run.

Expected status values are:

- `tau2_runtime_trace_smoke_passed`
- `tau2_runtime_trace_smoke_completed_with_skipped_live_hooks`
- `tau2_runtime_trace_smoke_failed`

## Explicit paid traced baseline

```bash
python scripts/run_tau2_runtime_traced_baseline.py \
  --provider <provider> \
  --model <model> \
  --domain mock \
  --task-id create_task_1 \
  --max-steps 2 \
  --yes-i-understand-this-may-call-paid-apis
```

This command is intentionally opt-in and is **not** included in `python scripts/run_all_smokes.py`. It refuses to run without provider/model configuration and the explicit paid-API acknowledgement flag. It also keeps the mock domain as the default and limits the first traced baseline to one task and concurrency one.

Refusal/success status values are:

- `tau2_runtime_traced_baseline_refused_missing_ack`
- `tau2_runtime_traced_baseline_refused_missing_model`
- `tau2_runtime_traced_baseline_passed`
- `tau2_runtime_traced_baseline_failed`

## Output artifacts

No-LLM runtime trace smoke writes:

- `runs/<timestamp>/runtime_events.jsonl`
- `runs/<timestamp>/runtime_trace_summary.md`
- `runs/<timestamp>/runtime_trace_final_state.json`
- `runs/<timestamp>/runtime_hook_map.json`
- `runs/<timestamp>/raw.log`

A model-backed traced baseline writes the same runtime trace artifacts plus:

- `runs/<timestamp>/tau2_output/results.json` when tau2 persists results
- `runs/<timestamp>/wrapper_summary.md`
- `runs/<timestamp>/tau2_artifacts/...` copied from tau2 output when present

## Event schema

Runtime events follow the existing trace-event style:

- `event_id`
- `timestamp`
- `run_id`
- `phase`
- `component`
- `event_type`
- `task_id`
- `turn_index`
- `tool_name`
- `message_role`
- `state_hash`
- `payload`
- `parent_event_id`

Runtime-specific details live under `payload.runtime_trace` only.

## Dry-validated versus live-only hooks

The dry smoke validates that hook targets can be found/imported, monkeypatches can be installed, the JSONL writer emits schema-shaped events, and hook metadata can be serialized. Some semantic events, such as real agent responses, real user responses, actual tool state transitions, evaluator checks, and tau2 persistence, are only proven during an explicit live traced baseline because the dry smoke must not call paid models or run model-backed tau2.

## Boundaries

- No vendored tau2 source files are modified.
- ActiveGraph does not control tau2 lifecycle or task state.
- Runtime events are not fed back into tau2 execution.
- The spike does not implement reactive-manager control.
- Model-backed traced baseline execution is explicit opt-in only.
- The traced baseline is not added to aggregate smokes.
- API key values are never printed or stored by the wrapper.

## Improvement over post-run extraction

Post-run extraction can only normalize what tau2 serialized after completion. The runtime trace layer observes turn boundaries, tool-call requests, dispatch start/end, state hashes around tool calls, and evaluator/persistence boundaries while they occur. That creates a richer evidence stream for later trace comparison and projection work without changing tau2 behavior.

## Preparation for ActiveGraph observation

The event stream gives ActiveGraph-style projection code more precise runtime facts to consume later: parent/child event relationships, state-hash transitions, tool timelines, and evaluator summaries. This prepares ActiveGraph runtime observation while preserving the no-control boundary.
