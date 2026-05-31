# tau2 baseline trace extraction

- source run directory: `runs/20260531-042306-420109`
- source status: `tau2_model_baseline_passed`
- phase: `real_tau2_model_baseline_extracted`
- trace mode: `post_run_extraction`
- fixture backed: `False`
- tau2 rerun: `False`
- LLM/API calls made by extractor: `False`
- task_id: `create_task_1`
- provider: `openai`
- model: `gpt-4.1-mini`
- artifacts inspected: `5`
- trace events extracted: `12`

## Output files

- `runs/20260531-042306-420109/extracted_trace/baseline_trace.jsonl`
- `runs/20260531-042306-420109/extracted_trace/baseline_trace_summary.md`
- `runs/20260531-042306-420109/extracted_trace/baseline_trace_final_state.json`
- `runs/20260531-042306-420109/extracted_trace/baseline_artifact_index.json`

## Event types emitted

- `baseline.config.loaded`
- `baseline.evaluation.observed`
- `baseline.message.observed`
- `baseline.result.persisted`
- `baseline.run.completed`
- `baseline.run.started`
- `baseline.task.started`
- `baseline.tool.completed`
- `baseline.tool.requested`

## Limitations

- wrapper raw.log and summary.md were inspected for provenance but do not contain structured turn data beyond fields already represented in final_state.json/results.json.
- simulation 119def6a-5e46-4609-8c5b-11bca149b307 did not serialize tick-level events; no tick events were emitted.
- simulation 119def6a-5e46-4609-8c5b-11bca149b307 did not serialize an effect_timeline; no state transition timeline was emitted.
- simulation 119def6a-5e46-4609-8c5b-11bca149b307 has no speech_environment artifact; no audio events were emitted.
- simulation 119def6a-5e46-4609-8c5b-11bca149b307 reward_info.db_check is null; no database assertion detail was emitted.
- simulation 119def6a-5e46-4609-8c5b-11bca149b307 reward_info.action_checks is null; no action check detail was emitted.
- simulation 119def6a-5e46-4609-8c5b-11bca149b307 reward_info.nl_assertions is null; no natural-language assertion detail was emitted.

## Boundary

This extractor reads completed run artifacts only. It does not import tau2, launch tau2, call LLM/API services, require API keys, or mutate `vendor/tau2-bench`.
