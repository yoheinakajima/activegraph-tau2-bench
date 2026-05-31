#!/usr/bin/env python3
"""Offline write-intent constraint analysis for airline task 8.

This command reads committed runtime, result, prior-analysis, and static airline
artifacts only. It does not run tau2, start model-backed episodes, call LLM/API
services, require API keys, mutate vendor/tau2-bench, or add ActiveGraph
control over tau2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from analyze_runtime_trace_outcome import (  # noqa: E402
    counter_dict,
    load_json,
    load_jsonl,
    payload,
    rel,
    require_file,
    sha256,
    write_json,
)

STATUS_PASSED = "airline_task8_write_intent_analysis_passed"
STATUS_INPUTS_MISSING = "airline_task8_write_intent_analysis_inputs_missing"
OUTPUT_DIR_NAME = "write_intent_analysis"
AIRLINE_DATA_DIR = pathlib.Path("vendor/tau2-bench/data/tau2/domains/airline")
AIRLINE_SOURCE_DIR = pathlib.Path("vendor/tau2-bench/src/tau2/domains/airline")
TASK_ID = "8"
BASELINE_LABEL = "baseline"
VARIANT_LABEL = "variant"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-analyze airline task 8 pre-write constraints and write intent arguments."
    )
    parser.add_argument("--baseline-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--variant-run-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help=f"Defaults to <variant-run-dir>/{OUTPUT_DIR_NAME}/.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def result_path(run_dir: pathlib.Path) -> pathlib.Path:
    for candidate in (run_dir / "tau2_output" / "results.json", run_dir / "tau2_artifacts" / "results.json"):
        if candidate.is_file():
            return candidate
    return run_dir / "tau2_output" / "results.json"


def first_simulation(results: dict[str, Any]) -> dict[str, Any]:
    simulations = results.get("simulations")
    if isinstance(simulations, list) and simulations and isinstance(simulations[0], dict):
        return simulations[0]
    return {}


def load_task(task_id: str) -> dict[str, Any]:
    tasks = load_json(REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json")
    for task in tasks if isinstance(tasks, list) else []:
        if isinstance(task, dict) and str(task.get("id")) == task_id:
            return task
    return {}


def maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def truncate(value: Any, limit: int = 700) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def passenger_key(passenger: dict[str, Any]) -> str:
    return "|".join(str(passenger.get(k, "")) for k in ("first_name", "last_name", "dob"))


def money_sum(methods: Any) -> int | float | None:
    if not isinstance(methods, list):
        return None
    total: int | float = 0
    for method in methods:
        if isinstance(method, dict) and isinstance(method.get("amount"), (int, float)):
            total += method["amount"]
    return total


def load_optional_json(path: pathlib.Path) -> Any | None:
    if not path.is_file():
        return None
    return load_json(path)


def collect_tool_calls(sim: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message_index, message in enumerate(sim.get("messages") if isinstance(sim.get("messages"), list) else []):
        if not isinstance(message, dict):
            continue
        for call_index, call in enumerate(message.get("tool_calls") or []):
            if isinstance(call, dict):
                rows.append(
                    {
                        "message_index": message_index,
                        "call_index": call_index,
                        "turn_idx": message.get("turn_idx"),
                        "id": call.get("id"),
                        "name": call.get("name"),
                        "requestor": call.get("requestor"),
                        "arguments": call.get("arguments"),
                    }
                )
    return rows


def collect_tool_results(sim: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message_index, message in enumerate(sim.get("messages") if isinstance(sim.get("messages"), list) else []):
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        content = maybe_json(message.get("content"))
        rows.append(
            {
                "message_index": message_index,
                "turn_idx": message.get("turn_idx"),
                "content": content,
                "content_excerpt": truncate(message.get("content"), 1200),
            }
        )
    return rows


def call_names_before(calls: list[dict[str, Any]], message_index: int) -> list[str]:
    return [str(call.get("name")) for call in calls if isinstance(call.get("message_index"), int) and call["message_index"] < message_index]


def first_call(calls: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for call in calls:
        if call.get("name") == name:
            return call
    return None


def all_calls(calls: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [call for call in calls if call.get("name") == name]


def action_checks(sim: dict[str, Any]) -> list[dict[str, Any]]:
    reward = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    checks = reward.get("action_checks") if isinstance(reward.get("action_checks"), list) else []
    return [check for check in checks if isinstance(check, dict)]


def expected_action_args(sim: dict[str, Any], name: str) -> dict[str, Any]:
    for check in action_checks(sim):
        action = check.get("action") if isinstance(check.get("action"), dict) else {}
        if action.get("name") == name and isinstance(action.get("arguments"), dict):
            return action["arguments"]
    return {}


def result_summary(results: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sim = first_simulation(results)
    reward = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    db_check = reward.get("db_check") if isinstance(reward.get("db_check"), dict) else {}
    read_checks = [c for c in action_checks(sim) if c.get("tool_type") == "read"]
    write_checks = [c for c in action_checks(sim) if c.get("tool_type") == "write"]
    return {
        "simulation_id": sim.get("id"),
        "task_id": sim.get("task_id"),
        "termination_reason": sim.get("termination_reason"),
        "reward": reward.get("reward"),
        "db_match": db_check.get("db_match"),
        "db_reward": db_check.get("db_reward"),
        "read_actions_matched": sum(1 for c in read_checks if c.get("action_match") is True),
        "read_actions_total": len(read_checks),
        "write_actions_matched": sum(1 for c in write_checks if c.get("action_match") is True),
        "write_actions_total": len(write_checks),
        "message_count": len(sim.get("messages") if isinstance(sim.get("messages"), list) else []),
        "runtime_event_count": len(events),
        "runtime_event_types": counter_dict([e.get("event_type") for e in events]),
    }


def source_evidence(kind: str, path: pathlib.Path, detail: str, value: Any = None) -> dict[str, Any]:
    row = {"kind": kind, "path": rel(path), "detail": detail}
    if value is not None:
        row["value"] = value
    return row


def build_constraint_ledger(task: dict[str, Any], db: dict[str, Any], baseline_sim: dict[str, Any]) -> dict[str, Any]:
    task_path = REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json"
    db_path = REPO_ROOT / AIRLINE_DATA_DIR / "db.json"
    source_path = REPO_ROOT / AIRLINE_SOURCE_DIR / "tools.py"
    expected = expected_action_args(baseline_sim, "book_reservation")
    expected_search = expected_action_args(baseline_sim, "search_direct_flight")
    instructions = (
        task.get("user_scenario", {})
        .get("instructions", {})
        .get("task_instructions", "")
    )
    user_id = expected.get("user_id") or "sophia_silva_7557"
    reservation = db.get("reservations", {}).get("WUNA5K", {}) if isinstance(db.get("reservations"), dict) else {}
    flight_number = expected.get("flights", [{}])[0].get("flight_number") if expected.get("flights") else "HAT271"
    travel_date = expected.get("flights", [{}])[0].get("date") if expected.get("flights") else "2024-05-26"
    cabin = expected.get("cabin") or "economy"
    flight = db.get("flights", {}).get(flight_number, {}) if isinstance(db.get("flights"), dict) else {}
    flight_date = flight.get("dates", {}).get(travel_date, {}) if isinstance(flight.get("dates"), dict) else {}
    unit_price = flight_date.get("prices", {}).get(cabin) if isinstance(flight_date.get("prices"), dict) else None
    passenger_count = len(expected.get("passengers", [])) if isinstance(expected.get("passengers"), list) else None
    expected_total = unit_price * passenger_count if isinstance(unit_price, (int, float)) and isinstance(passenger_count, int) else money_sum(expected.get("payment_methods"))
    certificate = db.get("users", {}).get(user_id, {}).get("payment_methods", {}).get("certificate_8045380", {})

    constraints = [
        {
            "id": "preserve_named_passengers",
            "category": "passengers/entities",
            "constraint": "Book Sophia Silva and added passenger Kevin Smith unless the total price is above $500.",
            "required_value": expected.get("passengers"),
            "evidence_sources": [
                source_evidence("task data", task_path, "task 8 task_instructions names Kevin Smith DOB 2001-04-12 and conditional drop rule", instructions),
                source_evidence("task data", task_path, "expected book_reservation.passengers", expected.get("passengers")),
                source_evidence("reservation detail", db_path, "WUNA5K contains Sophia Silva DOB 1957-10-05", reservation.get("passengers")),
            ],
        },
        {
            "id": "origin_destination",
            "category": "origin/destination",
            "constraint": "Book ORD to PHL.",
            "required_value": {"origin": expected.get("origin"), "destination": expected.get("destination")},
            "evidence_sources": [
                source_evidence("user request", task_path, "reason_for_call and task instructions specify ORD to PHL"),
                source_evidence("reservation detail", db_path, "WUNA5K recent flight route", {"origin": reservation.get("origin"), "destination": reservation.get("destination")}),
                source_evidence("task data", task_path, "expected search_direct_flight route", expected_search),
            ],
        },
        {
            "id": "travel_date",
            "category": "travel date",
            "constraint": "Book the new one-way outbound for 2024-05-26.",
            "required_value": travel_date,
            "evidence_sources": [
                source_evidence("user request", task_path, "reason_for_call says May 26"),
                source_evidence("task data", task_path, "expected search_direct_flight.date", expected_search.get("date")),
            ],
        },
        {
            "id": "selected_flight",
            "category": "selected flight",
            "constraint": "Use the same May 10 ORD→PHL flight number, HAT271, on the new travel date.",
            "required_value": expected.get("flights"),
            "evidence_sources": [
                source_evidence("reservation detail", db_path, "WUNA5K outbound flight is HAT271 ORD→PHL on 2024-05-10", reservation.get("flights", [{}])[0] if reservation.get("flights") else None),
                source_evidence("flight-search result", db_path, "HAT271 is available on 2024-05-26", {"status": flight_date.get("status"), "available_seats": flight_date.get("available_seats")}),
                source_evidence("task data", task_path, "expected book_reservation.flights", expected.get("flights")),
            ],
        },
        {
            "id": "cabin_class",
            "category": "cabin/class",
            "constraint": "Use economy cabin.",
            "required_value": cabin,
            "evidence_sources": [
                source_evidence("user request", task_path, "task says user is ok with economy"),
                source_evidence("reservation detail", db_path, "WUNA5K cabin", reservation.get("cabin")),
                source_evidence("task data", task_path, "expected book_reservation.cabin", expected.get("cabin")),
            ],
        },
        {
            "id": "baggage",
            "category": "baggage constraints",
            "constraint": "No baggage for this booking.",
            "required_value": {"total_baggages": expected.get("total_baggages"), "nonfree_baggages": expected.get("nonfree_baggages")},
            "evidence_sources": [
                source_evidence("user request", task_path, "task says user does not have any baggages"),
                source_evidence("task data", task_path, "expected baggage arguments", {"total_baggages": expected.get("total_baggages"), "nonfree_baggages": expected.get("nonfree_baggages")}),
            ],
        },
        {
            "id": "seat_preference",
            "category": "seat constraints",
            "constraint": "Aisle and middle seats together are requested, but book_reservation has no seat-assignment argument.",
            "required_value": {"requested": "aisle and middle seat together", "tool_argument_supported": False},
            "evidence_sources": [
                source_evidence("user request", task_path, "task instructions include aisle and middle seat together"),
                source_evidence("policy/tool source", source_path, "book_reservation signature has no seat selection field"),
            ],
        },
        {
            "id": "payment_price",
            "category": "payment/price constraints",
            "constraint": "Use only certificate_8045380 and pay exactly the total price when it is <= $500; with two passengers on HAT271 economy the total is $348.",
            "required_value": {"payment_methods": expected.get("payment_methods"), "unit_price": unit_price, "passengers": passenger_count, "expected_total": expected_total, "certificate_balance": certificate.get("amount")},
            "evidence_sources": [
                source_evidence("user request", task_path, "task says use only one certificate, willing to pay up to $500, drop Kevin iff price is above $500"),
                source_evidence("flight-search result", db_path, "HAT271 2024-05-26 economy price and seats", flight_date),
                source_evidence("reservation detail", db_path, "user profile certificate_8045380 balance", certificate),
                source_evidence("policy/tool source", source_path, "book_reservation requires total_payment == total_price and deducts certificates"),
            ],
        },
        {
            "id": "insurance",
            "category": "policy constraints",
            "constraint": "No travel insurance.",
            "required_value": expected.get("insurance"),
            "evidence_sources": [
                source_evidence("user request", task_path, "task says user does not need travel insurance"),
                source_evidence("task data", task_path, "expected book_reservation.insurance", expected.get("insurance")),
            ],
        },
        {
            "id": "prerequisite_search_evidence",
            "category": "policy constraints",
            "constraint": "Before booking, gather search_direct_flight evidence for ORD→PHL on 2024-05-26 to support availability and current price.",
            "required_value": expected_search,
            "evidence_sources": [
                source_evidence("task data", task_path, "expected read action before write", expected_search),
                source_evidence("policy/tool source", source_path, "search_direct_flight returns available direct flights for date/origin/destination"),
            ],
        },
    ]
    return {
        "status": "ledger_built_from_offline_artifacts",
        "task_id": TASK_ID,
        "expected_write_arguments": expected,
        "constraints": constraints,
        "derived_price_calculation": {
            "flight_number": flight_number,
            "date": travel_date,
            "cabin": cabin,
            "unit_price": unit_price,
            "passenger_count": passenger_count,
            "insurance_fee": 0 if expected.get("insurance") == "no" else None,
            "nonfree_baggage_fee": 50 * (expected.get("nonfree_baggages") or 0),
            "expected_total": expected_total,
            "drop_second_passenger_condition_triggered": bool(isinstance(expected_total, (int, float)) and expected_total > 500),
        },
        "offline_boundary": offline_boundary(),
    }


def prior_search_supported(sim: dict[str, Any], write_message_index: int | None, flight_number: str, date: str, cabin: str) -> dict[str, Any]:
    if write_message_index is None:
        return {"has_prior_search_direct_flight": False, "matched_flight_in_prior_search_result": False, "matched_price": None}
    calls = collect_tool_calls(sim)
    results = collect_tool_results(sim)
    search_calls = [c for c in calls if c.get("name") == "search_direct_flight" and c.get("message_index", 10**9) < write_message_index]
    matched: dict[str, Any] | None = None
    for result in results:
        if not isinstance(result.get("message_index"), int) or result["message_index"] >= write_message_index:
            continue
        content = result.get("content")
        if not isinstance(content, list):
            continue
        for row in content:
            if isinstance(row, dict) and row.get("flight_number") == flight_number:
                prices = row.get("prices") if isinstance(row.get("prices"), dict) else {}
                matched = {
                    "message_index": result["message_index"],
                    "flight_number": row.get("flight_number"),
                    "origin": row.get("origin"),
                    "destination": row.get("destination"),
                    "date_requested_by_call": search_calls[-1].get("arguments", {}).get("date") if search_calls else date,
                    "available_seats": row.get("available_seats"),
                    "price_for_cabin": prices.get(cabin),
                }
    return {
        "has_prior_search_direct_flight": bool(search_calls),
        "search_call_arguments": [c.get("arguments") for c in search_calls],
        "matched_flight_in_prior_search_result": matched is not None,
        "matched_price": matched.get("price_for_cabin") if matched else None,
        "matched_search_result": matched,
    }


def compare_run_to_ledger(label: str, sim: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    calls = collect_tool_calls(sim)
    write = first_call(calls, "book_reservation")
    args = write.get("arguments") if isinstance(write, dict) and isinstance(write.get("arguments"), dict) else {}
    expected = ledger["expected_write_arguments"]
    expected_passengers = expected.get("passengers") if isinstance(expected.get("passengers"), list) else []
    actual_passengers = args.get("passengers") if isinstance(args.get("passengers"), list) else []
    expected_keys = {passenger_key(p): p for p in expected_passengers if isinstance(p, dict)}
    actual_keys = {passenger_key(p): p for p in actual_passengers if isinstance(p, dict)}
    dropped = [p for key, p in expected_keys.items() if key not in actual_keys]
    extra = [p for key, p in actual_keys.items() if key not in expected_keys]
    payment_total = money_sum(args.get("payment_methods"))
    expected_total = ledger["derived_price_calculation"].get("expected_total")
    flight = args.get("flights", [{}])[0] if isinstance(args.get("flights"), list) and args.get("flights") else {}
    support = prior_search_supported(
        sim,
        write.get("message_index") if isinstance(write, dict) else None,
        str(flight.get("flight_number") or expected.get("flights", [{}])[0].get("flight_number")),
        str(flight.get("date") or expected.get("flights", [{}])[0].get("date")),
        str(args.get("cabin") or expected.get("cabin")),
    )
    mismatches: list[dict[str, Any]] = []
    for field in ("user_id", "origin", "destination", "flight_type", "cabin", "flights", "total_baggages", "nonfree_baggages", "insurance"):
        if args.get(field) != expected.get(field):
            mismatches.append({"field": field, "expected": expected.get(field), "actual": args.get(field)})
    if dropped:
        mismatches.append({"field": "passengers", "issue": "dropped_required_entities", "dropped": dropped})
    if extra:
        mismatches.append({"field": "passengers", "issue": "unexpected_entities", "extra": extra})
    if payment_total != expected_total:
        mismatches.append({"field": "payment_methods.amount", "issue": "payment_total_mismatch", "expected_total": expected_total, "actual_total": payment_total})
    if not support["has_prior_search_direct_flight"]:
        mismatches.append({"field": "prerequisite_evidence", "issue": "missing_prior_search_direct_flight"})
    elif not support["matched_flight_in_prior_search_result"]:
        mismatches.append({"field": "prerequisite_evidence", "issue": "prior_search_did_not_support_selected_flight"})

    sufficient_evidence_before_write = (
        bool(write)
        and support["has_prior_search_direct_flight"]
        and support["matched_flight_in_prior_search_result"]
        and bool(all_calls(calls, "get_user_details"))
        and bool(all_calls(calls, "get_reservation_details"))
    )
    unsupported: list[str] = []
    if not support["has_prior_search_direct_flight"]:
        unsupported.extend(["flight availability", "current selected-flight price", "seat availability on requested date"])
    if payment_total != expected_total:
        unsupported.append("payment amount equals computed total")
    if dropped:
        unsupported.append("complete passenger set from task constraints")

    return {
        "run_label": label,
        "book_reservation_call": write,
        "actual_arguments": args,
        "expected_arguments": expected,
        "prior_tool_sequence_before_write": call_names_before(calls, write.get("message_index") if isinstance(write, dict) else 10**9),
        "dropped_entities": dropped,
        "extra_entities": extra,
        "payment_total": payment_total,
        "expected_payment_total": expected_total,
        "price_payment_mismatch": payment_total != expected_total,
        "missing_prerequisite_evidence": [m for m in mismatches if m.get("field") == "prerequisite_evidence"],
        "write_happened_before_sufficient_evidence": bool(write) and not sufficient_evidence_before_write,
        "write_arguments_unsupported_by_prior_tool_results": unsupported,
        "search_support": support,
        "field_mismatches": mismatches,
        "verdict": "matches_ledger" if not mismatches else "violates_ledger",
    }


def event_tool_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        et = event.get("event_type")
        if et not in {"tool_call_requested", "tool_dispatch_start", "tool_dispatch_end", "toolkit_dispatch_start", "toolkit_dispatch_end"}:
            continue
        p = payload(event)
        call = p.get("tool_call") if isinstance(p.get("tool_call"), dict) else {}
        result = p.get("result") if "result" in p else p.get("tool_result")
        rows.append(
            {
                "event_id": event.get("event_id"),
                "event_type": et,
                "timestamp": event.get("timestamp"),
                "turn_index": event.get("turn_index"),
                "tool_name": call.get("name") or event.get("tool_name"),
                "arguments": call.get("arguments"),
                "state_hash": event.get("state_hash"),
                "state_hash_before": p.get("state_hash_before"),
                "state_hash_after": p.get("state_hash_after"),
                "state_changed": p.get("state_changed"),
                "result_excerpt": truncate(json.dumps(result, sort_keys=True, ensure_ascii=False) if result is not None else None, 700),
            }
        )
    return rows


def build_evidence_timeline(label: str, sim: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
    rows: list[dict[str, Any]] = []
    for idx, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        tool_calls = [c.get("name") for c in message.get("tool_calls") or [] if isinstance(c, dict)]
        content = message.get("content")
        kind = None
        if message.get("role") == "user":
            text = content or ""
            if any(term in text for term in ["Kevin Smith", "checked baggage", "travel insurance", "certificate", "HAT271", "May 26"]):
                kind = "user_constraint_evidence"
        if tool_calls:
            kind = "tool_call"
        if message.get("role") == "tool":
            parsed = maybe_json(content)
            if isinstance(parsed, list):
                kind = "flight_search_result" if any(isinstance(x, dict) and x.get("flight_number") == "HAT271" for x in parsed) else "tool_result"
            elif isinstance(parsed, dict) and parsed.get("reservation_id") == "WUNA5K":
                kind = "reservation_detail_evidence"
            elif isinstance(parsed, str) and parsed.startswith("Error:"):
                kind = "write_error"
            else:
                kind = "tool_result"
        if kind:
            rows.append(
                {
                    "message_index": idx,
                    "turn_idx": message.get("turn_idx"),
                    "role": message.get("role"),
                    "kind": kind,
                    "tool_calls": tool_calls,
                    "content_excerpt": truncate(content, 900),
                }
            )
    return {
        "run_label": label,
        "message_evidence": rows,
        "runtime_tool_events": event_tool_rows(events),
        "runtime_event_counts": counter_dict([e.get("event_type") for e in events]),
    }


def intervention_hypotheses() -> dict[str, Any]:
    return {
        "status": "general_intervention_hypotheses_only_no_control_added",
        "avoid_task_specific_prompt_tuning": True,
        "recommended_direction": "general pre-write constraint/check mechanism aligned with future ActiveGraph manager behavior",
        "hypotheses": [
            {
                "name": "pre-write constraint packet",
                "description": "Construct a structured packet of required entities, route/date, selected flight, class, baggage, insurance, price, payment method, and prerequisite evidence before any irreversible booking write.",
                "classification": ["offline-detectable now", "runtime-observable next", "requires future control/manager behavior"],
                "offline_detectable_now": "Existing traces can show whether actual write arguments violate the packet.",
                "runtime_observable_next": "Runtime tracing can observe when a write is about to dispatch and whether the packet has required evidence.",
                "future_control_manager_behavior": "A manager would need authority to block, repair, or request clarification before dispatch.",
            },
            {
                "name": "entity/constraint ledger from user request and tool results",
                "description": "Maintain a durable ledger that merges user constraints with reservation, search, policy, and tool outputs so later write construction cannot silently drop entities or overwrite constraints.",
                "classification": ["offline-detectable now", "runtime-observable next", "requires future control/manager behavior"],
                "offline_detectable_now": "Completed artifacts can reconstruct a ledger for audits like this one.",
                "runtime_observable_next": "A future trace hook can update the ledger after each observed user or tool message.",
                "future_control_manager_behavior": "A manager can enforce ledger invariants across planning and tool dispatch.",
            },
            {
                "name": "write-intent vs tool-argument diff before dispatch",
                "description": "Diff intended constraints against concrete tool arguments before the tool call, flagging missing passengers, unsupported flight selection, or payment totals that do not equal known prices.",
                "classification": ["offline-detectable now", "runtime-observable next", "requires future control/manager behavior"],
                "offline_detectable_now": "The same diff can be run after the episode using saved arguments.",
                "runtime_observable_next": "The diff can be computed at tool_call_requested time.",
                "future_control_manager_behavior": "Blocking or editing arguments requires an explicit control plane not added here.",
            },
            {
                "name": "policy/evidence checklist before irreversible booking",
                "description": "Require evidence for user identity, source reservation, selected flight availability, current price, passenger count, payment coverage, and no-insurance/no-baggage policy before booking.",
                "classification": ["offline-detectable now", "runtime-observable next", "requires future control/manager behavior"],
                "offline_detectable_now": "Traces show whether prerequisite read actions occurred before the write.",
                "runtime_observable_next": "The checklist can be observed and scored in live traces before a write.",
                "future_control_manager_behavior": "A future manager could prevent irreversible writes until the checklist passes.",
            },
            {
                "name": "post-tool mutation verification against intended constraints",
                "description": "After a write, compare the resulting reservation or error against the pre-write packet to detect silent drops, mismatched totals, or failed mutations immediately.",
                "classification": ["offline-detectable now", "runtime-observable next", "requires future control/manager behavior"],
                "offline_detectable_now": "Saved tool results and final state can be compared to intended constraints after the run.",
                "runtime_observable_next": "A trace observer can verify tool_dispatch_end results against intent.",
                "future_control_manager_behavior": "Remediation, rollback, or follow-up correction requires future control behavior.",
            },
        ],
    }


def offline_boundary() -> dict[str, bool]:
    return {
        "tau2_rerun": False,
        "model_backed_episode": False,
        "llm_api_calls": False,
        "api_keys_required": False,
        "vendor_tau2_bench_mutated": False,
        "activegraph_control_added": False,
    }


def write_summary(path: pathlib.Path, analysis: dict[str, Any]) -> None:
    ledger = analysis["constraint_ledger"]
    diffs = analysis["write_argument_diff"]
    baseline = diffs[BASELINE_LABEL]
    variant = diffs[VARIANT_LABEL]
    price = ledger["derived_price_calculation"]
    lines = [
        "# Airline task 8 write-intent constraint analysis",
        "",
        "## Offline boundary",
        "",
        "- tau2 rerun: **no**.",
        "- Model-backed episode: **no**.",
        "- LLM/API calls: **no**.",
        "- API keys required: **no**.",
        "- `vendor/tau2-bench` mutation: **no**.",
        "- ActiveGraph control added: **no**.",
        "",
        "## Constraint ledger summary",
        "",
        f"- Required passengers: `{ledger['expected_write_arguments'].get('passengers')}`.",
        "- Route/date/flight: `ORD` → `PHL`, `2024-05-26`, selected flight `HAT271`.",
        f"- Cabin/baggage/insurance: `{ledger['expected_write_arguments'].get('cabin')}`, total baggage `{ledger['expected_write_arguments'].get('total_baggages')}`, nonfree baggage `{ledger['expected_write_arguments'].get('nonfree_baggages')}`, insurance `{ledger['expected_write_arguments'].get('insurance')}`.",
        f"- Price/payment: HAT271 economy unit price `${price.get('unit_price')}` × `{price.get('passenger_count')}` passengers = `${price.get('expected_total')}`, payable with `certificate_8045380` whose balance is `$500`.",
        f"- Conditional passenger drop triggered: `{price.get('drop_second_passenger_condition_triggered')}`; therefore Kevin should remain in the write intent.",
        "",
        "## Baseline write-argument diff",
        "",
        f"- Verdict: `{baseline['verdict']}`.",
        f"- Dropped entities: `{baseline['dropped_entities']}`.",
        f"- Payment total: `{baseline['payment_total']}` vs expected `{baseline['expected_payment_total']}`.",
        f"- Prior search evidence present: `{baseline['search_support']['has_prior_search_direct_flight']}`; selected flight supported by search result: `{baseline['search_support']['matched_flight_in_prior_search_result']}`.",
        f"- Write before sufficient evidence: `{baseline['write_happened_before_sufficient_evidence']}`.",
        f"- Unsupported argument aspects: `{baseline['write_arguments_unsupported_by_prior_tool_results']}`.",
        "",
        "## Prompt-variant write-argument diff",
        "",
        f"- Verdict: `{variant['verdict']}`.",
        f"- Dropped entities: `{variant['dropped_entities']}`.",
        f"- Payment total: `{variant['payment_total']}` vs expected `{variant['expected_payment_total']}`.",
        f"- Prior search evidence present: `{variant['search_support']['has_prior_search_direct_flight']}`; selected flight supported by search result: `{variant['search_support']['matched_flight_in_prior_search_result']}`.",
        f"- Write before sufficient evidence: `{variant['write_happened_before_sufficient_evidence']}`.",
        f"- Unsupported argument aspects: `{variant['write_arguments_unsupported_by_prior_tool_results']}`.",
        "",
        "## Evidence timeline summary",
        "",
        "- Baseline gathered user details, read WUNA5K, searched ORD→PHL for 2024-05-26, then wrote a one-passenger HAT271 booking for `$174`.",
        "- Prompt variant gathered user details and WUNA5K, preserved Sophia + Kevin, but attempted `book_reservation` without prior `search_direct_flight` evidence and paid `$320` for a `$348` write.",
        "- Static task data and airline DB confirm the expected two-passenger total is `$348` and below the `$500` certificate threshold.",
        "",
        "## General intervention hypotheses",
        "",
    ]
    for hypo in analysis["general_intervention_hypotheses"]["hypotheses"]:
        lines.append(f"- **{hypo['name']}**: {hypo['description']} Classifications: `{', '.join(hypo['classification'])}`.")
    lines.extend(
        [
            "",
            "## Why not more task-specific prompt tuning",
            "",
            "Further task-specific prompt tuning is not recommended because the prompt variant fixed one symptom (preserving Kevin) while regressing prerequisite read evidence and still constructing an invalid payment amount. The general failure class is multi-constraint write action argument construction after multi-step read evidence; the next ActiveGraph-aligned direction is a general pre-write constraint/check mechanism, not more benchmark-specific prompt prose.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def raw_log(output_dir: pathlib.Path, analysis: dict[str, Any]) -> str:
    lines = [
        f"status={STATUS_PASSED}",
        f"generated_at={analysis['generated_at']}",
        f"baseline_run_dir={analysis['baseline_run_dir']}",
        f"variant_run_dir={analysis['variant_run_dir']}",
        "offline_boundary=" + json.dumps(analysis["offline_boundary"], sort_keys=True),
        "baseline_verdict=" + analysis["write_argument_diff"][BASELINE_LABEL]["verdict"],
        "variant_verdict=" + analysis["write_argument_diff"][VARIANT_LABEL]["verdict"],
        f"outputs_dir={rel(output_dir)}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    baseline_run_dir = args.baseline_run_dir
    variant_run_dir = args.variant_run_dir
    output_dir = args.output_dir or variant_run_dir / OUTPUT_DIR_NAME

    required = [
        (baseline_run_dir / "runtime_events.jsonl", "baseline runtime events"),
        (result_path(baseline_run_dir), "baseline results"),
        (variant_run_dir / "runtime_events.jsonl", "variant runtime events"),
        (result_path(variant_run_dir), "variant results"),
        (variant_run_dir / "prompt_variant_comparison" / "prompt_variant_comparison.json", "variant comparison"),
        (REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json", "airline tasks"),
        (REPO_ROOT / AIRLINE_DATA_DIR / "db.json", "airline db"),
        (REPO_ROOT / AIRLINE_SOURCE_DIR / "tools.py", "airline tools source"),
    ]
    try:
        for path, label in required:
            require_file(path, label)
    except RuntimeError as exc:
        print(f"status={STATUS_INPUTS_MISSING}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2

    baseline_events = load_jsonl(baseline_run_dir / "runtime_events.jsonl")
    variant_events = load_jsonl(variant_run_dir / "runtime_events.jsonl")
    baseline_results = load_json(result_path(baseline_run_dir))
    variant_results = load_json(result_path(variant_run_dir))
    baseline_sim = first_simulation(baseline_results)
    variant_sim = first_simulation(variant_results)
    task = load_task(TASK_ID)
    db = load_json(REPO_ROOT / AIRLINE_DATA_DIR / "db.json")
    ledger = build_constraint_ledger(task, db, baseline_sim)
    write_diff = {
        BASELINE_LABEL: compare_run_to_ledger(BASELINE_LABEL, baseline_sim, ledger),
        VARIANT_LABEL: compare_run_to_ledger(VARIANT_LABEL, variant_sim, ledger),
    }
    timeline = {
        BASELINE_LABEL: build_evidence_timeline(BASELINE_LABEL, baseline_sim, baseline_events),
        VARIANT_LABEL: build_evidence_timeline(VARIANT_LABEL, variant_sim, variant_events),
    }
    hypotheses = intervention_hypotheses()
    prior_analysis = {
        "baseline_failure_analysis": load_optional_json(baseline_run_dir / "airline_task8_failure_analysis" / "airline_task8_failure_analysis.json"),
        "baseline_expected_vs_observed": load_optional_json(baseline_run_dir / "airline_task8_failure_analysis" / "expected_vs_observed.json"),
        "variant_prompt_comparison": load_optional_json(variant_run_dir / "prompt_variant_comparison" / "prompt_variant_comparison.json"),
        "variant_tool_argument_delta": load_optional_json(variant_run_dir / "prompt_variant_comparison" / "tool_argument_delta.json"),
    }
    final_state = {
        "status": STATUS_PASSED,
        "generated_at": utc_now(),
        "offline_boundary": offline_boundary(),
        "baseline_summary": result_summary(baseline_results, baseline_events),
        "variant_summary": result_summary(variant_results, variant_events),
        "source_artifacts": {
            "baseline_runtime_events": {"path": rel(baseline_run_dir / "runtime_events.jsonl"), "sha256": sha256(baseline_run_dir / "runtime_events.jsonl")},
            "baseline_results": {"path": rel(result_path(baseline_run_dir)), "sha256": sha256(result_path(baseline_run_dir))},
            "variant_runtime_events": {"path": rel(variant_run_dir / "runtime_events.jsonl"), "sha256": sha256(variant_run_dir / "runtime_events.jsonl")},
            "variant_results": {"path": rel(result_path(variant_run_dir)), "sha256": sha256(result_path(variant_run_dir))},
            "airline_tasks": {"path": rel(REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json"), "sha256": sha256(REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json")},
            "airline_db": {"path": rel(REPO_ROOT / AIRLINE_DATA_DIR / "db.json"), "sha256": sha256(REPO_ROOT / AIRLINE_DATA_DIR / "db.json")},
            "airline_tools": {"path": rel(REPO_ROOT / AIRLINE_SOURCE_DIR / "tools.py"), "sha256": sha256(REPO_ROOT / AIRLINE_SOURCE_DIR / "tools.py")},
        },
    }
    analysis = {
        "status": STATUS_PASSED,
        "generated_at": final_state["generated_at"],
        "baseline_run_dir": rel(baseline_run_dir),
        "variant_run_dir": rel(variant_run_dir),
        "offline_boundary": offline_boundary(),
        "constraint_ledger": ledger,
        "write_argument_diff": write_diff,
        "evidence_timeline": timeline,
        "general_intervention_hypotheses": hypotheses,
        "prior_analysis_inputs": prior_analysis,
        "final_state": final_state,
        "conclusion": {
            "failure_class": "multi-constraint write action argument construction after multi-step read evidence",
            "task_specific_prompt_tuning_recommended": False,
            "next_direction": "general pre-write constraint/check mechanism",
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "constraint_ledger.json", ledger)
    write_json(output_dir / "write_argument_diff.json", write_diff)
    write_json(output_dir / "evidence_timeline.json", timeline)
    write_json(output_dir / "general_intervention_hypotheses.json", hypotheses)
    write_json(output_dir / "final_state.json", final_state)
    write_json(output_dir / "write_intent_analysis.json", analysis)
    write_summary(output_dir / "write_intent_summary.md", analysis)
    (output_dir / "raw.log").write_text(raw_log(output_dir, analysis), encoding="utf-8")

    print(f"status={STATUS_PASSED}")
    print(f"output_dir={rel(output_dir)}")
    print(f"baseline_verdict={write_diff[BASELINE_LABEL]['verdict']}")
    print(f"variant_verdict={write_diff[VARIANT_LABEL]['verdict']}")
    print("tau2_rerun=false")
    print("llm_api_calls=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
