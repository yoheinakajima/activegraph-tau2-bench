# Airline task 8 prompt/control variant

This runner is an explicit opt-in experiment for the airline task 8 passenger-dropping failure observed in `runs/20260531-204930-608103`.

## Purpose

The failed run called `book_reservation`, but booked only Sophia on HAT271 for `$174` instead of Sophia and Kevin on HAT271 for `$348`. The likely cause was model behavior plus policy confusion: the assistant treated a new booking request like a passenger-count modification and dropped Kevin.

`scripts/run_airline_task8_prompt_variant.py` reruns only airline task `8` with a small agent prompt/control variant to test whether the instruction fixes this failure mode.

## Prompt/control variant

The exact prompt variant appended to the agent system prompt is:

> Treat this as a new booking request unless the user explicitly says they are modifying an existing booking. Preserve all named passengers unless the user explicitly removes one. If booking a reservation for multiple passengers, include every eligible named passenger in the booking.

The runner records this text in each output directory as:

- `prompt_variant.json`
- `prompt_variant.txt`
- `wrapper_summary.md`
- `runtime_trace_final_state.json` when tracing initializes

## Implementation boundary

The wrapper does **not** edit `vendor/tau2-bench`. Source inspection found no tau2 CLI option for appending an agent instruction directly. The least-invasive path is a repo-owned adapter at `experiments/tau2_prompt_variant/prompt_variant_tau2_cli.py` that applies a process-local wrapper around `tau2.agent.llm_agent.LLMAgent.system_prompt` before tau2 constructs the agent.

The experiment also keeps these boundaries:

- Hard-coded domain: `airline`.
- Hard-coded task id: `8`.
- Concurrency: `1`.
- Not included in `scripts/run_all_smokes.py`.
- No ActiveGraph control is added.
- API key values are never printed or stored; only presence booleans are recorded.
- Refuses without `--provider`, `--model`, and `--yes-i-understand-this-may-call-paid-apis`.

## Manual command

Do not run this during local/no-API smoke validation. To intentionally run the paid/API-backed experiment, use:

```bash
python scripts/run_airline_task8_prompt_variant.py \
  --provider openai \
  --model gpt-4.1-mini \
  --max-steps 30 \
  --yes-i-understand-this-may-call-paid-apis
```

The wrapper writes artifacts under `runs/<timestamp>/`, including runtime trace files when the paid run actually starts.

## Refusal/no-API validation

Safe no-API checks include:

```bash
python scripts/run_airline_task8_prompt_variant.py
python scripts/run_airline_task8_prompt_variant.py --provider dummy --model dummy --max-steps 30
```

The first command refuses because provider/model/acknowledgement are missing. The second command refuses because the paid API acknowledgement is missing. Both paths write refusal artifacts and do not execute tau2.
