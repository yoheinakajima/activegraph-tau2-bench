# Airline task 8 failure analysis

`scripts/analyze_airline_task8_failure.py` performs a detailed offline analysis of the committed airline task 8 runtime-traced artifact at `runs/20260531-204930-608103`.

The analyzer is intentionally read-only with respect to tau2 execution:

- It does **not** run tau2.
- It does **not** run another model-backed episode.
- It does **not** call LLM/API services.
- It does **not** require API keys.
- It does **not** mutate `vendor/tau2-bench`.
- It does **not** add ActiveGraph control or feed state packets back into tau2.

## Usage

```bash
python scripts/analyze_airline_task8_failure.py \
  --runtime-run-dir runs/20260531-204930-608103
```

By default, outputs are written under:

```text
runs/20260531-204930-608103/airline_task8_failure_analysis/
```

## Inputs inspected

Runtime artifacts:

- `runtime_events.jsonl`
- `runtime_trace_summary.md`
- `runtime_trace_final_state.json`
- `tau2_output/results.json` (or `tau2_artifacts/results.json` fallback)
- `raw.log`

Static airline artifacts:

- `vendor/tau2-bench/data/tau2/domains/airline/tasks.json`
- `vendor/tau2-bench/data/tau2/domains/airline/db.json`
- `vendor/tau2-bench/data/tau2/domains/airline/policy.md`
- `vendor/tau2-bench/src/tau2/domains/airline/tools.py`
- `vendor/tau2-bench/src/tau2/evaluator/evaluator_env.py`
- `vendor/tau2-bench/src/tau2/evaluator/evaluator_action.py`

## Outputs

The analyzer writes:

- `airline_task8_failure_analysis.json` — complete structured report.
- `airline_task8_failure_summary.md` — human-readable summary.
- `action_expectation_analysis.json` — expected action checks versus observed tool calls.
- `tool_call_timeline.json` — runtime tool call event timeline with arguments, results, and state-hash changes.
- `expected_vs_observed.json` — expected successful path and DB mutation compared to observed behavior.
- `scoring_evidence.json` — reward, DB check, action checks, and terminal evidence.
- `final_state.json` — compact machine-readable status.
- `raw.log` — copied source run log with appended analyzer boundary/status lines.

## Findings encoded by the analyzer

The committed artifact ended with `USER_STOP`, reward `0.0`, DB check `0.0`, communicate score `1.0`, all read action checks passing, and the write action check failing.

The key finding is that the observed failure is an argument/DB mismatch rather than a missing write dispatch:

- `book_reservation` was called in the runtime trace.
- The tool-level booking succeeded and changed state.
- The observed booking included only Sophia Silva and paid `$174`.
- The expected booking included Sophia Silva plus Kevin Smith and paid `$348`.
- The searched HAT271 economy candidate had enough seats and the two-passenger total was under the user's `$500` cap.

The likely cause is model behavior plus policy confusion: the assistant applied the airline policy's modify-reservation passenger-count rule to a new booking request, persuaded the user simulator to continue with only Sophia, and then completed the conversation normally.

## Recommended next experiment

After this offline analysis, the next useful experiment is to rerun only task 8 with a prompt/control variant that explicitly distinguishes new bookings from modifying an existing reservation. The comparison should check whether the assistant retains Kevin Smith when the target flight has enough seats and the two-passenger total remains below `$500`.
