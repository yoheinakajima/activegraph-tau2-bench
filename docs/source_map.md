# tau2-bench local source map (Phase 1.5)

- Date (UTC): 2026-05-30
- Vendored upstream path: `vendor/tau2-bench`
- Vendored upstream commit: `fcc9ed68df33c93ff0b8c946865f267d7c99fb06`
- Inspection boundary: local vendored files only; no GitHub source pages were used.
- Phase boundary: this is a source map and no-LLM smoke baseline only. It does **not** add ActiveGraph integration or Phase 2 observability hooks.

## CLI / run entrypoint

- `vendor/tau2-bench/src/tau2/cli.py`
  - `main()` builds the `argparse` CLI and subcommands.
  - `add_run_args(parser)` attaches the `tau2 run` options.
  - Nested `run_command(args)` creates either `TextRunConfig` or `VoiceRunConfig`, then calls `run_domain(config)`.
  - Utility subcommands include `run_intro()`, `run_check_data()`, `run_view_simulations(args)`, `run_show_domain(args)`, and leaderboard/submission helpers.
- `vendor/tau2-bench/src/tau2/run.py`
  - Facade module that re-exports runner APIs.
  - Deprecated compatibility shims: `run_task(...)` and `run_tasks(...)`.
  - Main imported execution symbols: `run_domain`, `run_single_task`, `run_simulation`, `build_orchestrator`, `get_tasks`, `get_options`.

## Run / batch execution flow

- `vendor/tau2-bench/src/tau2/runner/batch.py`
  - `run_domain(config)` is the CLI/API entrypoint after config construction. It validates config, loads tasks, filters tasks by registered agent task filters, derives `data/simulations/<run_name>/results.json`, delegates to `run_tasks(...)`, then computes metrics.
  - `run_tasks(config, tasks, ...)` handles seed generation, voice/persona setup, checkpoint/resume, concurrency, progress display, retries, hallucination retries, and persistence format selection.
  - `run_single_task(config, task, ...)` creates a simulation UUID, opens `_TaskLogContext`, calls `build_orchestrator(...)`, calls `run_simulation(...)`, and optionally runs review/audio side effects.
  - `_TaskLogContext` owns per-task logs and LLM debug log routing when verbose logs are enabled.
  - `run_auto_review(...)` is an optional post-run LLM review path and is not part of the no-LLM smoke boundary.
  - `save_simulation_audio(...)` is an optional voice artifact path.
- `vendor/tau2-bench/src/tau2/runner/simulation.py`
  - `run_simulation(orchestrator, ...)` is the lowest execution layer: run the orchestrator, attach policy, choose half/full-duplex mode, evaluate, attach `reward_info`, and return `SimulationRun`.
- `vendor/tau2-bench/src/tau2/runner/build.py`
  - `build_environment(...)`, `build_agent(...)`, `build_user(...)`, `build_voice_user(...)`, `build_text_orchestrator(...)`, `build_voice_orchestrator(...)`, and `build_orchestrator(...)` translate names/config into live objects via the registry.

## Half-duplex agent interface

- `vendor/tau2-bench/src/tau2/agent/base/participant.py`
  - `HalfDuplexParticipant.generate_next_message(message, state)` is the turn-based interface.
  - `HalfDuplexParticipant.get_init_state(message_history=None)` initializes participant state.
  - `HalfDuplexParticipant.stop(...)`, `HalfDuplexParticipant.is_stop(...)`, and `HalfDuplexParticipant.set_seed(seed)` are lifecycle/determinism hooks.
- `vendor/tau2-bench/src/tau2/agent/base_agent.py`
  - `HalfDuplexAgent` receives `UserMessage`, `ToolMessage`, or `MultiToolMessage` and produces `AssistantMessage`.
  - `is_valid_agent_history_message(message)` filters history for agent state initialization.
  - `validate_message_format_default(...)` and `validate_message_format_solo(...)` enforce the no-empty/no-mixed-message protocol checks.
- `vendor/tau2-bench/src/tau2/user/user_simulator_base.py`
  - `HalfDuplexUser` mirrors the participant interface for user simulators, receiving assistant/tool messages and producing `UserMessage`.

## Orchestrator / turn loop

- `vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py`
  - `BaseOrchestrator.run()` is the lifecycle template: initialize, loop `step()` until `done`, check termination, finalize, and emergency-cleanup on exception.
  - `BaseOrchestrator._initialize_environment(...)` calls `Environment.set_state(...)` with task initial state and prior message history.
  - `BaseOrchestrator._execute_tool_calls(tool_calls)` dispatches each `ToolCall` through `Environment.get_response(...)` and increments error count for tool errors.
  - `Orchestrator.initialize()` prepares initial environment state, seeds agent/user, initializes participant states, validates/replays any task message history, sends the default first assistant message when needed, and syncs tools.
  - `Orchestrator.step()` is the half-duplex turn loop. It routes agent/user messages to the other participant or to `Role.ENV`, executes tool calls, appends trajectory messages, advances roles, checks stops/errors, increments step count, and calls `environment.sync_tools()`.
  - `Orchestrator.get_trajectory()` returns the sorted message trajectory with turn indexes.
  - `Orchestrator._finalize()` stops participants and returns a `SimulationRun` with messages, costs, timing, seed, mode, termination reason, and optional voice metadata.

## User simulator

- `vendor/tau2-bench/src/tau2/user/user_simulator.py`
  - `get_global_user_sim_guidelines(...)` and `get_global_user_sim_guidelines_voice(...)` load simulator guideline markdown from `data/tau2/user_simulator/`.
  - `UserSimulator` is the half-duplex LLM user simulator.
  - `UserSimulator.system_prompt` combines global guidelines, task instructions, and runtime persona config.
  - `UserSimulator.get_init_state(...)` builds `UserState` from system messages and valid message history.
  - `UserSimulator.generate_next_message(...)` updates state with `_generate_next_message(...)`; `_generate_next_message(...)` calls `generate(...)`, converts assistant-style tool calls into user-requested tool calls, and returns a `UserMessage`.
  - `UserSimulator.is_stop(...)` detects `###STOP###`, `###TRANSFER###`, and `###OUT-OF-SCOPE###` markers.
  - `DummyUser` supports solo-agent mode without making LLM calls.
- `vendor/tau2-bench/src/tau2/user/user_simulator_base.py`
  - `UserState.flip_roles()` adapts conversation history for the user simulator by flipping user/assistant roles.

## Environment state

- `vendor/tau2-bench/src/tau2/environment/environment.py`
  - `Environment` owns `domain_name`, `policy`, assistant `tools`, optional `user_tools`, and `solo_mode`.
  - `Environment.set_state(initialization_data, initialization_actions, message_history)` applies task-provided DB updates, initialization actions, and mutating tool-call replay from prior history, then syncs tools.
  - `Environment.run_env_function_call(...)`, `run_env_assertion(...)`, and `run_env_function_calls(...)` execute task/evaluation setup and checks.
  - `Environment.get_db_hash()` and `Environment.get_user_db_hash()` expose state hashes for evaluation.
  - `Environment.sync_tools()` is the domain override point for keeping assistant/user toolkits in sync.

## Tool definitions / dispatch

- `vendor/tau2-bench/src/tau2/environment/tool.py`
  - `Tool` wraps callable metadata and rendering/description behavior.
- `vendor/tau2-bench/src/tau2/environment/toolkit.py`
  - `ToolKitBase.use_tool(tool_name, **kwargs)` invokes registered tool methods.
  - `ToolKitBase.get_tools(include=None)` converts toolkit methods to `Tool` objects.
  - `ToolKitBase.has_tool(...)`, `tool_type(...)`, `tool_mutates_state(...)`, and `get_statistics()` expose tool metadata.
  - `ToolSignature` and `get_tool_signatures(tools)` produce serializable tool definitions.
- `vendor/tau2-bench/src/tau2/environment/environment.py`
  - `Environment.make_tool_call(...)` chooses assistant vs user toolkit by `ToolCall.requestor`.
  - `Environment.get_response(tool_call)` catches tool exceptions, syncs tools after success, JSON-serializes output, and returns `ToolMessage(error=...)`.
- Domain tool implementations live under `vendor/tau2-bench/src/tau2/domains/*/tools.py` and optional `user_tools.py`.

## Domain data loading

- `vendor/tau2-bench/src/tau2/utils/utils.py`
  - `DATA_DIR` is resolved from `TAU2_DATA_DIR` or defaults to vendored `data/`.
- `vendor/tau2-bench/src/tau2/domains/<domain>/utils.py`
  - Domain constants point to policy, DB, task, split, and optional voice difficulty files under `data/tau2/domains/<domain>/`.
- `vendor/tau2-bench/src/tau2/domains/<domain>/environment.py`
  - `get_environment(...)` loads DB/policy files and constructs an `Environment` with domain toolkits.
  - `get_tasks(task_split_name="base")` loads task JSON and applies splits.
  - `get_tasks_split()` loads split JSON.
- `vendor/tau2-bench/src/tau2/registry.py`
  - The global `registry` registers default users, agent factories, domain constructors, and task loaders for `mock`, `airline`, `retail`, `telecom`, `telecom-workflow`, and `banking_knowledge`.

## Policies

- Policy text is loaded from domain policy files in `vendor/tau2-bench/data/tau2/domains/*/`.
- Environment constructors pass policy text into `Environment(domain_name=..., policy=..., tools=...)`.
- `Environment.get_policy()` exposes the active policy to agents, metadata, and evaluation/run records.
- `runner.helpers.get_info(...)` records `EnvironmentInfo.policy` in run metadata.

## Task data

- `vendor/tau2-bench/src/tau2/data_model/tasks.py`
  - `Task` contains `id`, `description`, `user_scenario`, optional `ticket`, `initial_state`, `evaluation_criteria`, issues, required documents, and per-task user tool allowlists.
  - `UserScenario` and `StructuredUserInstructions` define what the simulator sees.
  - `InitialState`, `InitializationData`, `EnvFunctionCall`, and `EnvAssertion` define setup and state assertions.
  - `EvaluationCriteria` contains reference actions, environment assertions, communicate checks, NL assertions, and `reward_basis`.
  - `RewardType` defines DB, environment assertion, communicate, NL assertion, and action reward components.
- Domain task JSON files live under `vendor/tau2-bench/data/tau2/domains/*/tasks*.json` with split files such as `split_tasks.json`.

## Evaluation / scoring

- `vendor/tau2-bench/src/tau2/evaluator/evaluator.py`
  - `EvaluationType` selects environment, communication, action, NL assertion, all, or all-with-NL checks.
  - `evaluate_simulation(simulation, task, evaluation_type, solo_mode, domain, mode, env_kwargs)` returns zero for premature termination, one when no criteria exist, selects half/full-duplex evaluator classes, gathers tool types, runs relevant evaluators, multiplies reward components selected by `task.evaluation_criteria.reward_basis`, and returns `RewardInfo`.
- Component evaluators:
  - `vendor/tau2-bench/src/tau2/evaluator/evaluator_env.py` (`EnvironmentEvaluator`, `FullDuplexEnvironmentEvaluator`)
  - `vendor/tau2-bench/src/tau2/evaluator/evaluator_action.py` (`ActionEvaluator`, `FullDuplexActionEvaluator`)
  - `vendor/tau2-bench/src/tau2/evaluator/evaluator_communicate.py` (`CommunicateEvaluator`, `FullDuplexCommunicateEvaluator`)
  - `vendor/tau2-bench/src/tau2/evaluator/evaluator_nl_assertions.py` (`NLAssertionsEvaluator`, `FullDuplexNLAssertionsEvaluator`; LLM-judged path, outside no-LLM smoke)
- `vendor/tau2-bench/src/tau2/data_model/simulation.py`
  - `RewardInfo` stores final reward and component check details.

## Output artifacts

- `vendor/tau2-bench/src/tau2/runner/batch.py`
  - `run_domain(config)` writes benchmark results under `DATA_DIR / "simulations" / run_name / "results.json"`.
  - Text runs default to monolithic JSON; voice runs default to directory format.
  - Verbose per-task logs and audio artifacts live under the run `save_dir` when enabled.
- `vendor/tau2-bench/src/tau2/data_model/simulation.py`
  - `SimulationRun` stores task ID, timing, termination reason, reward info, costs, messages or ticks, seed, mode, and optional artifact metadata.
  - `Results.save(path, format="json")` writes one JSON file.
  - `Results.save(path, format="dir")` writes metadata to `results.json` and individual simulation files under `simulations/`.
  - `Results.load(...)`, `Results.save_metadata(...)`, and `Results.iter_simulations(...)` handle monolithic and directory formats.
- `vendor/tau2-bench/src/tau2/runner/checkpoint.py`
  - Checkpoint helpers maintain resumable result files and per-simulation directory-format updates.

## Seed / determinism controls

- `vendor/tau2-bench/src/tau2/config.py`
  - `DEFAULT_SEED = 300`, `DEFAULT_NUM_TRIALS = 1`, `DEFAULT_MAX_CONCURRENCY = 3`, `DEFAULT_MAX_STEPS = 200`, and `DEFAULT_MAX_ERRORS = 10`.
- `vendor/tau2-bench/src/tau2/data_model/simulation.py`
  - `BaseRunConfig.seed`, `num_trials`, `max_concurrency`, retry, timeout, and resume fields capture runtime controls.
  - `TextRunConfig.max_steps` controls half-duplex turn limits.
- `vendor/tau2-bench/src/tau2/runner/batch.py`
  - `run_tasks(...)` seeds Python `random` with `config.seed` and derives one trial seed per trial.
  - `run_single_task(...)` passes each trial seed into `build_orchestrator(...)`.
- `vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py`
  - `Orchestrator.initialize()` calls `agent.set_seed(seed)` and `user.set_seed(seed)` when a seed is provided.
  - `_finalize()` stores the seed in `SimulationRun`.

## No-LLM smoke candidates

Safe Phase 1.5 smoke checks that do not require API keys or paid LLM calls:

1. Verify `vendor/tau2-bench`, `vendor/tau2-bench.UPSTREAM_COMMIT`, `pyproject.toml`, and key source/data files exist.
2. Verify the upstream commit marker equals `fcc9ed68df33c93ff0b8c946865f267d7c99fb06`.
3. Parse selected Python source files with `ast.parse` rather than importing `tau2`, avoiding dependency setup and runtime side effects.
4. Inspect the local registry source text for expected domain registrations.
5. Validate representative domain data JSON files (`mock`, `airline`, `retail`, `banking_knowledge`) and TOML files (`telecom`) can be loaded with the Python standard library.
6. Count task records and confirm policy files are non-empty.
7. Compile repository-owned helper scripts with `python -m compileall scripts experiments`.

The Phase 1.5 smoke must not run `tau2 run`, instantiate LLM agents, invoke `UserSimulator.generate_next_message(...)`, execute auto-review/NL assertion evaluators, or call any external API.

## Future Phase 2 observability hook candidates (not implemented)

- `BaseOrchestrator.run()` for run lifecycle spans.
- `Orchestrator.initialize()` for initial state, task, policy, and seed snapshots.
- `Orchestrator.step()` for turn-level message/role transitions.
- `BaseOrchestrator._execute_tool_calls(...)` and `Environment.get_response(...)` for tool-call spans and error capture.
- `Environment.set_state(...)`, `run_env_function_call(...)`, and `sync_tools()` for state mutation/replay events.
- `run_single_task(...)` and `_TaskLogContext` for per-simulation artifact wiring.
- `run_tasks(...)` for batch/trial/concurrency/retry/checkpoint events.
- `run_simulation(...)` and `evaluate_simulation(...)` for evaluation spans and reward component summaries.
- `Results.save(...)` / checkpoint functions for artifact manifest and output indexing.
