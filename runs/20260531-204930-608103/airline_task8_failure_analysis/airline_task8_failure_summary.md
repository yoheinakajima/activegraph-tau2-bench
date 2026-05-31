# Airline task 8 failure analysis

- Status: `airline_task8_failure_analysis_passed`
- Runtime run inspected: `runs/20260531-204930-608103`
- Generated: `2026-05-31T21:08:27.437303Z`
- Analysis boundary: offline artifacts only; no tau2 rerun, no model-backed episode, no LLM/API calls, no API keys, no vendor mutation.

## Conclusion

The assistant applied the modify-flight passenger-count rule to a new booking request, told the user Kevin could not be added, and then booked only Sophia. The booking tool itself supports up to five passengers and HAT271 had enough economy seats at a two-passenger total of $348.

The important correction is that `book_reservation` was **not absent** in this artifact. It was called, succeeded at the tool level, and changed the DB, but it booked only Sophia for `$174`; the expected action and DB target required Sophia plus Kevin for `$348`.

## Task goal and expected mutation

Purpose: Booking with extra passenger.

Expected successful path:
1. Obtain user details for sophia_silva_7557.
2. Identify the May 10 ORD→PHL reservation WUNA5K and its flight number HAT271.
3. Search ORD→PHL direct flights on 2024-05-26 and select HAT271.
4. Because HAT271 economy has 3 seats and costs $174 per passenger, book Sophia plus Kevin for $348, below the $500 cap.
5. Use one travel certificate, no baggage, and no travel insurance after explicit user confirmation.

Expected `book_reservation` arguments:

```json
{
  "cabin": "economy",
  "destination": "PHL",
  "flight_type": "one_way",
  "flights": [
    {
      "date": "2024-05-26",
      "flight_number": "HAT271"
    }
  ],
  "insurance": "no",
  "nonfree_baggages": 0,
  "origin": "ORD",
  "passengers": [
    {
      "dob": "1957-10-05",
      "first_name": "Sophia",
      "last_name": "Silva"
    },
    {
      "dob": "2001-04-12",
      "first_name": "Kevin",
      "last_name": "Smith"
    }
  ],
  "payment_methods": [
    {
      "amount": 348,
      "payment_id": "certificate_8045380"
    }
  ],
  "total_baggages": 0,
  "user_id": "sophia_silva_7557"
}
```

## Observed path

- Termination reason: `user_stop`.
- Reward: `0.0`; DB check: `{"db_match": false, "db_reward": 0.0}`.
- `book_reservation` called: `True`; absent: `False`.
- Book event IDs: `['rt-000134-411e1a12']`.
- Passenger count expected vs observed: `2` vs `1`.
- Payment total expected vs observed: `$348` vs `$174`.

Observed `book_reservation` arguments:

```json
{
  "cabin": "economy",
  "destination": "PHL",
  "flight_type": "one_way",
  "flights": [
    {
      "date": "2024-05-26",
      "flight_number": "HAT271"
    }
  ],
  "insurance": "no",
  "nonfree_baggages": 0,
  "origin": "ORD",
  "passengers": [
    {
      "dob": "1957-10-05",
      "first_name": "Sophia",
      "last_name": "Silva"
    }
  ],
  "payment_methods": [
    {
      "amount": 174,
      "payment_id": "certificate_8045380"
    }
  ],
  "total_baggages": 0,
  "user_id": "sophia_silva_7557"
}
```

## Prerequisite evidence

- user_id: `True`
- prior_reservation_WUNA5K: `True`
- target_flight_HAT271_found: `True`
- two_economy_seats_available: `True`
- two_passenger_total_under_500: `True`
- certificate_8045380_available: `True`
- explicit_confirmation_before_write: `True`

Event IDs:
- `get_user_details`: `['rt-000025-57183b67']`
- `get_reservation_details`: `['rt-000036-08eacd05', 'rt-000047-5f72cfb2', 'rt-000058-981d60e4', 'rt-000069-3ccc0e7a', 'rt-000080-4a47f2e3']`
- `search_direct_flight`: `['rt-000107-9f97a55c']`
- `book_reservation`: `['rt-000134-411e1a12']`

HAT271 search candidate:

```json
{
  "available_seats": {
    "basic_economy": 20,
    "business": 14,
    "economy": 3
  },
  "date": null,
  "destination": "PHL",
  "flight_number": "HAT271",
  "origin": "ORD",
  "prices": {
    "basic_economy": 83,
    "business": 338,
    "economy": 174
  },
  "scheduled_arrival_time_est": "21:00:00",
  "scheduled_departure_time_est": "19:00:00",
  "status": "available"
}
```

## Tool/action timeline summary

| # | Event | Tool | Turn | Status | State changed | Argument/result excerpt |
|---:|---|---|---:|---|---|---|
| 1 | `rt-000025-57183b67` | `get_user_details` | `4` | `ok` | `False` | {"address": {"address1": "141 Cedar Avenue", "address2": "Suite 436", "city": "Columbus", "country": "USA", "state": "OH", "zip": "43282"}, "dob": "1957-10-05", "email": "sophia.si |
| 2 | `rt-000036-08eacd05` | `get_reservation_details` | `6` | `ok` | `False` | {"cabin": "basic_economy", "created_at": "2024-05-03T08:46:43", "destination": "EWR", "flight_type": "round_trip", "flights": [{"date": "2024-05-25", "destination": "EWR", "flight_ |
| 3 | `rt-000047-5f72cfb2` | `get_reservation_details` | `8` | `ok` | `False` | {"cabin": "basic_economy", "created_at": "2024-05-04T14:07:11", "destination": "CLT", "flight_type": "one_way", "flights": [{"date": "2024-05-21", "destination": "EWR", "flight_num |
| 4 | `rt-000058-981d60e4` | `get_reservation_details` | `10` | `ok` | `False` | {"cabin": "economy", "created_at": "2024-05-02T04:38:01", "destination": "CLT", "flight_type": "round_trip", "flights": [{"date": "2024-05-23", "destination": "EWR", "flight_number |
| 5 | `rt-000069-3ccc0e7a` | `get_reservation_details` | `12` | `ok` | `False` | {"cabin": "basic_economy", "created_at": "2024-05-03T15:12:00", "destination": "ATL", "flight_type": "one_way", "flights": [{"date": "2024-05-24", "destination": "ATL", "flight_num |
| 6 | `rt-000080-4a47f2e3` | `get_reservation_details` | `14` | `ok` | `False` | {"cabin": "economy", "created_at": "2024-05-08T19:01:02", "destination": "PHL", "flight_type": "round_trip", "flights": [{"date": "2024-05-10", "destination": "PHL", "flight_number |
| 7 | `rt-000107-9f97a55c` | `search_direct_flight` | `20` | `ok` | `False` | [{"available_seats": {"basic_economy": 7, "business": 7, "economy": 1}, "date": null, "destination": "PHL", "flight_number": "HAT139", "origin": "ORD", "prices": {"basic_economy":  |
| 8 | `rt-000134-411e1a12` | `book_reservation` | `26` | `ok` | `True` | {"cabin": "economy", "created_at": "2024-05-15T15:00:00", "destination": "PHL", "flight_type": "one_way", "flights": [{"date": "2024-05-26", "destination": "PHL", "flight_number":  |

## Likely cause classification

Primary: `model_behavior_policy_confusion`.

- The user asked for the same flight as a prior reservation, which may have led the assistant to reason as though it was modifying that reservation.
- The airline policy's no passenger-count changes rule applies under Modify flight / Change passengers, not Book flight.
- The user simulator accepted the assistant's incorrect constraint and instructed booking only Sophia, producing a normal USER_STOP despite DB/action failure.

Not supported by artifacts:
- Not a turn-budget failure: max_steps was 30 and termination_reason was user_stop.
- Not missing read prerequisites: get_user_details, WUNA5K reservation details, and search_direct_flight all succeeded.
- Not missing book_reservation call: the call occurred and mutated DB, but with one passenger and $174 instead of two passengers and $348.
- Not an ActiveGraph-control issue: the run is trace-only and state packets were not fed back into tau2.

## Recommended next experiment

Rerun task 8 only after adding an agent prompt/control variant that explicitly distinguishes new bookings from modifying an existing reservation, then compare whether the assistant keeps Kevin when the searched flight has sufficient seats and total price is under $500. Keep ActiveGraph trace-only unless separately testing control.
