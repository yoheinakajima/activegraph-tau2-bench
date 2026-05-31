# Airline task 8 write-intent constraint analysis

## Offline boundary

- tau2 rerun: **no**.
- Model-backed episode: **no**.
- LLM/API calls: **no**.
- API keys required: **no**.
- `vendor/tau2-bench` mutation: **no**.
- ActiveGraph control added: **no**.

## Constraint ledger summary

- Required passengers: `[{'first_name': 'Sophia', 'last_name': 'Silva', 'dob': '1957-10-05'}, {'first_name': 'Kevin', 'last_name': 'Smith', 'dob': '2001-04-12'}]`.
- Route/date/flight: `ORD` → `PHL`, `2024-05-26`, selected flight `HAT271`.
- Cabin/baggage/insurance: `economy`, total baggage `0`, nonfree baggage `0`, insurance `no`.
- Price/payment: HAT271 economy unit price `$174` × `2` passengers = `$348`, payable with `certificate_8045380` whose balance is `$500`.
- Conditional passenger drop triggered: `False`; therefore Kevin should remain in the write intent.

## Baseline write-argument diff

- Verdict: `violates_ledger`.
- Dropped entities: `[{'first_name': 'Kevin', 'last_name': 'Smith', 'dob': '2001-04-12'}]`.
- Payment total: `174` vs expected `348`.
- Prior search evidence present: `True`; selected flight supported by search result: `True`.
- Write before sufficient evidence: `False`.
- Unsupported argument aspects: `['payment amount equals computed total', 'complete passenger set from task constraints']`.

## Prompt-variant write-argument diff

- Verdict: `violates_ledger`.
- Dropped entities: `[]`.
- Payment total: `320` vs expected `348`.
- Prior search evidence present: `False`; selected flight supported by search result: `False`.
- Write before sufficient evidence: `True`.
- Unsupported argument aspects: `['flight availability', 'current selected-flight price', 'seat availability on requested date', 'payment amount equals computed total']`.

## Evidence timeline summary

- Baseline gathered user details, read WUNA5K, searched ORD→PHL for 2024-05-26, then wrote a one-passenger HAT271 booking for `$174`.
- Prompt variant gathered user details and WUNA5K, preserved Sophia + Kevin, but attempted `book_reservation` without prior `search_direct_flight` evidence and paid `$320` for a `$348` write.
- Static task data and airline DB confirm the expected two-passenger total is `$348` and below the `$500` certificate threshold.

## General intervention hypotheses

- **pre-write constraint packet**: Construct a structured packet of required entities, route/date, selected flight, class, baggage, insurance, price, payment method, and prerequisite evidence before any irreversible booking write. Classifications: `offline-detectable now, runtime-observable next, requires future control/manager behavior`.
- **entity/constraint ledger from user request and tool results**: Maintain a durable ledger that merges user constraints with reservation, search, policy, and tool outputs so later write construction cannot silently drop entities or overwrite constraints. Classifications: `offline-detectable now, runtime-observable next, requires future control/manager behavior`.
- **write-intent vs tool-argument diff before dispatch**: Diff intended constraints against concrete tool arguments before the tool call, flagging missing passengers, unsupported flight selection, or payment totals that do not equal known prices. Classifications: `offline-detectable now, runtime-observable next, requires future control/manager behavior`.
- **policy/evidence checklist before irreversible booking**: Require evidence for user identity, source reservation, selected flight availability, current price, passenger count, payment coverage, and no-insurance/no-baggage policy before booking. Classifications: `offline-detectable now, runtime-observable next, requires future control/manager behavior`.
- **post-tool mutation verification against intended constraints**: After a write, compare the resulting reservation or error against the pre-write packet to detect silent drops, mismatched totals, or failed mutations immediately. Classifications: `offline-detectable now, runtime-observable next, requires future control/manager behavior`.

## Why not more task-specific prompt tuning

Further task-specific prompt tuning is not recommended because the prompt variant fixed one symptom (preserving Kevin) while regressing prerequisite read evidence and still constructing an invalid payment amount. The general failure class is multi-constraint write action argument construction after multi-step read evidence; the next ActiveGraph-aligned direction is a general pre-write constraint/check mechanism, not more benchmark-specific prompt prose.
