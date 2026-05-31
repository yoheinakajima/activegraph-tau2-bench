# Airline task 8 baseline vs prompt-variant comparison

## Offline boundary

- tau2 rerun: **no**.
- Model-backed episode: **no**.
- LLM/API calls: **no**.
- API keys required: **no**.
- `vendor/tau2-bench` mutation: **no**.

## Result summary

- Baseline run: `runs/20260531-204930-608103`; reward `0.0`, DB match `False`, read score `3/3`, write score `0/1`.
- Prompt-variant run: `runs/20260531-222346-104165`; reward `0.0`, DB match `False`, read score `2/3`, write score `0/1`.
- Both runs terminated with `user_stop` but scored reward `0.0` because the required booking state/action did not match.

## Action score deltas

| Action | Type | Baseline | Variant | Delta | Regressed? |
|---|---:|---:|---:|---:|---|
| `book_reservation` | write | 0.0 | 0.0 | 0 | False |
| `get_reservation_details` | read | 1.0 | 1.0 | 0.0 | False |
| `get_user_details` | read | 1.0 | 1.0 | 0.0 | False |
| `search_direct_flight` | read | 1.0 | 0.0 | -1.0 | True |

## Tool argument deltas

- `search_direct_flight`: baseline arguments matched expected; variant made no `search_direct_flight` call, so read action matching regressed.
- `book_reservation`: baseline selected `['HAT271']` and paid `174`, but passengers were `['Sophia Silva']`.
- `book_reservation`: variant selected `['HAT271']` and passengers were `['Sophia Silva', 'Kevin Smith']`, but paid `320` instead of `348`.
- Kevin preserved in baseline write: `False`.
- Kevin preserved in variant write: `True`.
- HAT271 selected in baseline write: `True`.
- HAT271 selected in variant write: `True`.

## Message path deltas

- Conversation path changed: `True`.
- Baseline message count: `30`; variant message count: `26`.
- Baseline tool sequence: `get_user_details`, `get_reservation_details`, `get_reservation_details`, `get_reservation_details`, `get_reservation_details`, `get_reservation_details`, `search_direct_flight`, `book_reservation`
- Variant tool sequence: `get_user_details`, `get_reservation_details`, `get_reservation_details`, `get_reservation_details`, `get_reservation_details`, `get_reservation_details`, `book_reservation`
- The prompt variant batched reservation reads, skipped the flight search, and attempted the write earlier.

## Why matching regressed or remained failed

- `search_direct_flight` regressed because the prompt variant never called it. The scorer expected a read call with `origin=ORD`, `destination=PHL`, and `date=2024-05-26`.
- `book_reservation` still failed because the variant preserved Kevin and selected HAT271 but sent payment amount `320` while the tool reported the actual total was `348`.
- The baseline made the expected search and selected HAT271, but dropped Kevin and paid only `174`, producing a one-passenger booking.

## Failure class and generalization assessment

- Failure class: **multi-constraint write action argument construction after multi-step read evidence**.
- The current prompt variant is classified as **task-specific** and is **not recommended** for continued iteration.
- Reason: The variant targeted one observed symptom (dropping a named passenger) and changed the path enough to regress a read-action match while still failing the write. Iterating this task-specific prompt would optimize around airline task 8 artifacts rather than solve the broader write-argument construction problem.

### Task-specific prompt hacking vs general runtime support

Task-specific prompt hacking adds benchmark-specific prose and can move failures around. In this case it fixed the passenger-preservation symptom in the first write attempt but regressed the expected search action and still underpaid.

Generalizable ActiveGraph-style runtime support should instead externalize and check the constraints around any irreversible write:

- **pre-write constraint packet**: Before any write, assemble a compact packet of required entities, dates, route, flight, cabin, price, payment, insurance, and baggage constraints.
- **entity/constraint ledger from user request and tool results**: Maintain a ledger that separates user-stated constraints from tool-evidenced facts and highlights unresolved or contradictory fields.
- **write-intent vs tool-argument diff before dispatch**: Compare the intended booking state to the actual book_reservation arguments and block/flag missing passengers, missing search evidence, or payment mismatches.
- **policy/evidence checklist before irreversible booking**: Require explicit evidence for route/date/flight availability, passenger eligibility, payment coverage, and no-insurance/baggage choices before calling a write tool.
- **post-tool mutation verification against intended constraints**: After a write, compare the resulting reservation against the pre-write packet to identify silent drops or mismatched totals immediately.

No intervention is implemented by this comparison script; it only records offline analysis artifacts.
