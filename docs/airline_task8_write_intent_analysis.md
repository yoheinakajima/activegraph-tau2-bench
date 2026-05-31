# Airline task 8 write-intent constraint analysis

This document describes the offline pre-write constraint ledger and write-intent analysis for the committed airline task 8 baseline and prompt-variant failure artifacts.

## Purpose

The analysis targets the general failure class identified by the prior artifacts: **multi-constraint write action argument construction after multi-step read evidence**. It does not recommend additional task-specific prompt tuning. Instead, it frames the next ActiveGraph-aligned direction as a general pre-write constraint/check mechanism that can preserve entities, reconcile read evidence, and validate concrete write arguments before irreversible tool dispatch.

## Offline boundary

The analyzer is artifact-only:

- It does **not** rerun tau2.
- It does **not** start another model-backed episode.
- It does **not** call LLM/API services.
- It does **not** require API keys.
- It does **not** mutate `vendor/tau2-bench`.
- It does **not** add ActiveGraph control over tau2.

## Command

```bash
python scripts/analyze_airline_task8_write_intent.py \
  --baseline-run-dir runs/20260531-204930-608103 \
  --variant-run-dir runs/20260531-222346-104165
```

Outputs are written under:

```text
runs/20260531-222346-104165/write_intent_analysis/
```

## Inputs inspected

The analyzer reads:

- Baseline runtime trace and result artifacts:
  - `runs/20260531-204930-608103/runtime_events.jsonl`
  - `runs/20260531-204930-608103/tau2_output/results.json`
- Baseline prior analysis outputs when present:
  - `runs/20260531-204930-608103/airline_task8_failure_analysis/`
- Prompt-variant runtime trace and result artifacts:
  - `runs/20260531-222346-104165/runtime_events.jsonl`
  - `runs/20260531-222346-104165/tau2_output/results.json`
- Prompt-variant comparison outputs when present:
  - `runs/20260531-222346-104165/prompt_variant_comparison/`
- Static airline task and DB data:
  - `vendor/tau2-bench/data/tau2/domains/airline/tasks.json`
  - `vendor/tau2-bench/data/tau2/domains/airline/db.json`
- Airline tool source for policy/tool semantics:
  - `vendor/tau2-bench/src/tau2/domains/airline/tools.py`

## Outputs

The analyzer writes the required output bundle:

- `write_intent_analysis.json` — complete combined report.
- `write_intent_summary.md` — human-readable summary.
- `constraint_ledger.json` — structured ledger of task, user, reservation, search, price, payment, policy, baggage, insurance, and seat constraints.
- `write_argument_diff.json` — baseline and prompt-variant `book_reservation` arguments compared against the ledger.
- `evidence_timeline.json` — message/tool evidence timeline plus runtime tool event slices.
- `general_intervention_hypotheses.json` — general pre-write/check hypotheses classified by detectability/control requirements.
- `final_state.json` — status, source artifact hashes, scoring summaries, and offline boundary.
- `raw.log` — compact run log.

## Constraint ledger summary

The ledger reconstructs the required write intent from task data, DB state, tool results, and source semantics:

- Required passengers/entities: Sophia Silva and Kevin Smith, DOB `2001-04-12`, must be preserved unless the total price exceeds `$500`.
- Origin/destination: `ORD` to `PHL`.
- Travel date: `2024-05-26`.
- Selected flight: `HAT271`, derived from the May 10 `WUNA5K` reservation and confirmed available for May 26 in static DB/search evidence.
- Cabin/class: `economy`.
- Baggage: `total_baggages=0`, `nonfree_baggages=0`.
- Seat preference: aisle and middle together requested, but `book_reservation` has no seat-selection argument.
- Payment/price: HAT271 economy price `$174` × 2 passengers = `$348`, payable by `certificate_8045380` with `$500` balance.
- Policy/tool constraints: `book_reservation` requires payment totals to equal computed price; `search_direct_flight` supplies current availability and price evidence before booking.

## Baseline diff

The baseline gathered `search_direct_flight` evidence for `ORD` → `PHL` on `2024-05-26` and selected HAT271, but its write arguments violated the ledger:

- Dropped Kevin Smith from `passengers`.
- Paid `$174`, the one-passenger HAT271 economy price, instead of `$348` for Sophia + Kevin.
- Had prior search evidence for HAT271 availability and unit price, so the failure is primarily entity preservation and payment-total construction.

## Prompt-variant diff

The prompt variant preserved Sophia + Kevin and selected HAT271, but still violated the ledger:

- Skipped/failed the prerequisite `search_direct_flight` read evidence before the write.
- Paid `$320` instead of the expected `$348`.
- Attempted the write before sufficient evidence was gathered for current price, seat availability, and flight availability on the requested date.

## General intervention hypotheses

The analysis records five general hypotheses and explicitly classifies each as:

- `offline-detectable now`
- `runtime-observable next`
- `requires future control/manager behavior`

The hypotheses are:

1. Pre-write constraint packet.
2. Entity/constraint ledger from user request and tool results.
3. Write-intent vs tool-argument diff before dispatch.
4. Policy/evidence checklist before irreversible booking.
5. Post-tool mutation verification against intended constraints.

## Why not more task-specific prompt tuning

The prompt variant fixed one visible symptom by preserving Kevin, but it regressed read-action evidence and still built an invalid payment amount. That makes further task-specific prompt tuning a poor next step. The more generalizable direction is a pre-write constraint/check mechanism that can compare intended constraints and available evidence against concrete tool arguments before dispatch, and later verify the resulting mutation or tool error.
