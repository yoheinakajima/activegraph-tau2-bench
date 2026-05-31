# Runtime DB mutation analysis

Status: `runtime_db_mutation_analysis_completed_with_gaps`

Runtime run inspected: `runs/20260531-170523-841701`

This report is an offline deterministic projection from existing runtime-trace and tau2 result artifacts. It did not rerun tau2, did not run a model-backed episode, did not call LLM/API services, did not require API keys, did not mutate `vendor/tau2-bench`, and did not add ActiveGraph control over tau2.

## Detected write tools

| # | Tool | Status | State hash before | State hash after | Inferred target | Resulting object ID |
| ---: | --- | --- | --- | --- | --- | --- |
| _none_ | _none_ | _none_ | _none_ | _none_ | _none_ | _none_ |

## Reward / DB / action confirmation

- Reward: `0.0`
- DB match: `False`
- DB reward: `0.0`
- Write actions matched: `0/1`
- Normal stop: `True`
- Agent errors: `0`
- User errors: `0`

## Evidence fields used

- Runtime tool dispatch start/end events.
- Toolkit dispatch result payloads.
- Tool message response content.
- State hash before/after fields.
- tau2 reward, DB check, and write action checks from `tau2_output/results.json`.
- Existing successful runtime-trace analysis final metrics.

## Confidence and limitations

Confidence: `medium`

- No full before/after DB snapshot artifact is available; the projection uses tool-call evidence, tool-result payloads, state-hash transition evidence, and tau2 reward/DB/action checks.
- Evaluation-phase tool replay events are retained as confirmation evidence but are not counted as additional live runtime writes.
- No live runtime write tool dispatch was detected before evaluation_start.
