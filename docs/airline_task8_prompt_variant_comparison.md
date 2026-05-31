# Airline task 8 prompt-variant comparison

This document describes the offline comparator for the airline task 8 baseline failure and the subsequent prompt-variant failure.

## Purpose

The comparator is intentionally **not** a new prompt-tuning loop. It compares two already-produced runtime-traced runs to understand the failure class:

- Baseline failure: `runs/20260531-204930-608103`
- Prompt-variant failure: `runs/20260531-222346-104165`

The prompt variant attempted to preserve all named passengers, but the resulting run still failed and also regressed one read-action match. The comparison therefore focuses on whether this is a general runtime-support problem rather than another task-specific prompt problem.

## Offline-only boundary

`scripts/compare_airline_task8_prompt_variant.py` only reads existing artifacts. It does not:

- rerun tau2;
- start another model-backed episode;
- call LLM/API services;
- require API keys;
- mutate `vendor/tau2-bench`;
- implement ActiveGraph interventions.

## Command

```bash
python scripts/compare_airline_task8_prompt_variant.py \
  --baseline-run-dir runs/20260531-204930-608103 \
  --variant-run-dir runs/20260531-222346-104165
```

By default, outputs are written under:

```text
runs/20260531-222346-104165/prompt_variant_comparison/
```

## Inputs inspected

The script validates and reads:

- both `runtime_events.jsonl` files;
- both `tau2_output/results.json` files, falling back to `tau2_artifacts/results.json` if needed;
- both `raw.log` files;
- the baseline `airline_task8_failure_analysis/expected_vs_observed.json` artifact when present;
- `prompt_variant.json` and `prompt_variant.txt` from the prompt-variant run;
- airline task static data from `vendor/tau2-bench/data/tau2/domains/airline/tasks.json`.

## Outputs

The comparator writes:

- `prompt_variant_comparison.json` — consolidated comparison, input hashes, answers, evidence, and offline boundaries;
- `prompt_variant_comparison_summary.md` — human-readable summary;
- `action_score_delta.json` — baseline vs variant action matching/reward deltas;
- `tool_argument_delta.json` — expected vs observed arguments for `search_direct_flight` and `book_reservation`;
- `message_path_delta.json` — message-count, tool-sequence, and conversation-path deltas;
- `generalization_assessment.json` — task-specific prompt-hack assessment and general ActiveGraph intervention hypotheses;
- `final_state.json` — script status and artifact list;
- `raw.log` — comparator execution log.

## Current findings

The generated comparison reports:

- Baseline reward `0.0`, DB match `false`, read actions `3/3`, write actions `0/1`.
- Prompt-variant reward `0.0`, DB match `false`, read actions `2/3`, write actions `0/1`.
- The prompt variant changed the conversation path.
- The prompt variant did not call `search_direct_flight`, causing the expected read action to regress.
- The prompt variant did preserve Kevin in its first `book_reservation` call.
- Both runs selected HAT271 for the write attempt.
- The baseline write failed because it booked only Sophia and paid `$174`.
- The prompt-variant write failed because it booked Sophia and Kevin but paid `$320`; the tool reported the total was `$348`.

## Generalization assessment

The current prompt variant is marked as **task-specific** and is **not recommended** for continued iteration. It repaired one symptom in the first write attempt, but it changed the path enough to skip the expected search action and still produced an invalid write argument set.

The generalizable failure class is:

> multi-constraint write action argument construction after multi-step read evidence

This class occurs when the assistant must carry forward user-stated entities, dates, route, cabin, flight identity, tool-observed prices, payment rules, baggage, insurance, and policy constraints into one irreversible write call.

## ActiveGraph-style intervention hypotheses

The comparison proposes, but does not implement, these general mechanisms:

1. **Pre-write constraint packet** — assemble required entities, route/date/flight, cabin, price, payment, baggage, and insurance constraints before a write.
2. **Entity/constraint ledger from user request and tool results** — track user-stated constraints separately from tool-evidenced facts and unresolved fields.
3. **Write-intent vs tool-argument diff before dispatch** — compare intended mutation state with actual write arguments before calling `book_reservation`.
4. **Policy/evidence checklist before irreversible booking** — require route/date/availability, passenger, payment, insurance, and baggage evidence before dispatch.
5. **Post-tool mutation verification against intended constraints** — compare the created reservation against the pre-write constraint packet immediately after the write.
