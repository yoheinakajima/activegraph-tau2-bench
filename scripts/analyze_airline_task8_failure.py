#!/usr/bin/env python3
"""Offline detailed failure analysis for airline task 8 runtime trace artifacts.

This command reads committed runtime and static airline artifacts only. It does
not run tau2, start model-backed episodes, call LLM/API services, require API
keys, mutate vendor/tau2-bench, or feed ActiveGraph state back into tau2.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import shutil
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
    tool_result_payload,
    write_json,
)

STATUS_PASSED = "airline_task8_failure_analysis_passed"
STATUS_INPUTS_MISSING = "airline_task8_failure_analysis_inputs_missing"
OUTPUT_DIR_NAME = "airline_task8_failure_analysis"
AIRLINE_DATA_DIR = pathlib.Path("vendor/tau2-bench/data/tau2/domains/airline")
AIRLINE_SOURCE_DIR = pathlib.Path("vendor/tau2-bench/src/tau2/domains/airline")
EVALUATOR_SOURCE_DIR = pathlib.Path("vendor/tau2-bench/src/tau2/evaluator")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline-analyze airline task 8 booking failure artifacts.")
    parser.add_argument("--runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--output-dir", type=pathlib.Path, default=None, help=f"Defaults to <runtime-run-dir>/{OUTPUT_DIR_NAME}/.")
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
    tasks = load_json(AIRLINE_DATA_DIR / "tasks.json")
    for task in tasks if isinstance(tasks, list) else []:
        if isinstance(task, dict) and str(task.get("id")) == task_id:
            return task
    return {}


def truncate(value: Any, limit: int = 700) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def message_content(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    return content if isinstance(content, str) else None


def message_rows(messages: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        row: dict[str, Any] = {
            "message_index": index,
            "turn_idx": message.get("turn_idx"),
            "role": message.get("role"),
            "content_excerpt": truncate(message_content(message), 900),
        }
        calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        if calls:
            row["tool_calls"] = [
                {"id": c.get("id"), "name": c.get("name"), "arguments": c.get("arguments"), "requestor": c.get("requestor")}
                for c in calls
                if isinstance(c, dict)
            ]
        if message.get("role") == "tool":
            row["tool_result"] = parse_json_maybe(message.get("content"))
        rows.append(row)
    return rows


def tool_event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending_by_name: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for event in events:
        event_type = event.get("event_type")
        tool_name = event.get("tool_name")
        p = payload(event)
        if event_type == "tool_call_requested":
            call = p.get("tool_call") if isinstance(p.get("tool_call"), dict) else {}
            row = {
                "event_id": event.get("event_id"),
                "event_type": event_type,
                "turn_index": event.get("turn_index"),
                "tool_name": call.get("name") or tool_name,
                "requestor": call.get("requestor"),
                "tool_call_id": call.get("id"),
                "arguments": call.get("arguments"),
                "dispatch_event_ids": [],
                "result_event_id": None,
                "status": None,
                "state_hash_before": None,
                "state_hash_after": None,
                "state_changed": None,
                "result_excerpt": None,
                "result_payload": None,
            }
            rows.append(row)
            pending_by_name[str(row["tool_name"])].append(row)
        elif event_type in {"tool_dispatch_start", "toolkit_dispatch_start", "toolkit_dispatch_end"} and tool_name:
            if pending_by_name.get(str(tool_name)):
                pending_by_name[str(tool_name)][-1]["dispatch_event_ids"].append(event.get("event_id"))
        elif event_type == "tool_dispatch_end" and tool_name:
            target = pending_by_name.get(str(tool_name), [])[-1] if pending_by_name.get(str(tool_name)) else None
            if target is not None:
                result = tool_result_payload(event)
                target["dispatch_event_ids"].append(event.get("event_id"))
                target["result_event_id"] = event.get("event_id")
                target["status"] = p.get("status")
                target["state_hash_before"] = p.get("state_hash_before")
                target["state_hash_after"] = p.get("state_hash_after")
                target["state_changed"] = p.get("state_hash_before") != p.get("state_hash_after")
                target["result_payload"] = result
                target["result_excerpt"] = truncate(json.dumps(result, sort_keys=True, ensure_ascii=False) if not isinstance(result, str) else result)
    return rows


def action_checks(reward_info: dict[str, Any]) -> list[dict[str, Any]]:
    checks = reward_info.get("action_checks")
    return checks if isinstance(checks, list) else []


def find_expected_action(task: dict[str, Any], name: str) -> dict[str, Any] | None:
    actions = (((task.get("evaluation_criteria") or {}).get("actions")) if isinstance(task.get("evaluation_criteria"), dict) else None)
    for action in actions if isinstance(actions, list) else []:
        if isinstance(action, dict) and action.get("name") == name:
            return action
    return None


def compare_arguments(expected: Any, observed: Any) -> dict[str, Any]:
    matched = canonical(expected) == canonical(observed)
    passenger_expected = expected.get("passengers") if isinstance(expected, dict) else None
    passenger_observed = observed.get("passengers") if isinstance(observed, dict) else None
    payment_expected = expected.get("payment_methods") if isinstance(expected, dict) else None
    payment_observed = observed.get("payment_methods") if isinstance(observed, dict) else None
    fields: dict[str, Any] = {}
    if isinstance(expected, dict) and isinstance(observed, dict):
        for key in sorted(set(expected) | set(observed)):
            fields[key] = {"expected": expected.get(key), "observed": observed.get(key), "match": canonical(expected.get(key)) == canonical(observed.get(key))}
    return {
        "arguments_match_exactly": matched,
        "field_comparison": fields,
        "passenger_count_expected": len(passenger_expected) if isinstance(passenger_expected, list) else None,
        "passenger_count_observed": len(passenger_observed) if isinstance(passenger_observed, list) else None,
        "payment_total_expected": sum(p.get("amount", 0) for p in payment_expected) if isinstance(payment_expected, list) else None,
        "payment_total_observed": sum(p.get("amount", 0) for p in payment_observed) if isinstance(payment_observed, list) else None,
    }


def relevant_message_excerpts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needles = [
        "extra passenger",
        "Kevin Smith",
        "number of passengers",
        "proceed with booking just for myself",
        "same flight number HAT271",
        "certificate_8045380",
        "successfully booked",
        "###STOP###",
    ]
    excerpts = []
    for row in rows:
        text = row.get("content_excerpt") or ""
        if isinstance(text, str) and any(n.lower() in text.lower() for n in needles):
            excerpts.append(row)
    return excerpts


def static_sources() -> dict[str, Any]:
    files = [
        AIRLINE_DATA_DIR / "tasks.json",
        AIRLINE_DATA_DIR / "db.json",
        AIRLINE_DATA_DIR / "policy.md",
        AIRLINE_SOURCE_DIR / "tools.py",
        EVALUATOR_SOURCE_DIR / "evaluator_env.py",
        EVALUATOR_SOURCE_DIR / "evaluator_action.py",
    ]
    return {rel(path): {"sha256": sha256(path), "bytes": path.stat().st_size} for path in files if path.is_file()}


def build_report(args: argparse.Namespace, output_dir: pathlib.Path) -> dict[str, Any]:
    run_dir = args.runtime_run_dir
    required = {
        "runtime events": run_dir / "runtime_events.jsonl",
        "runtime trace summary": run_dir / "runtime_trace_summary.md",
        "runtime final state": run_dir / "runtime_trace_final_state.json",
        "tau2 results": result_path(run_dir),
        "raw log": run_dir / "raw.log",
        "airline tasks": AIRLINE_DATA_DIR / "tasks.json",
        "airline db": AIRLINE_DATA_DIR / "db.json",
        "airline tools": AIRLINE_SOURCE_DIR / "tools.py",
        "airline policy": AIRLINE_DATA_DIR / "policy.md",
        "tau2 DB evaluator": EVALUATOR_SOURCE_DIR / "evaluator_env.py",
        "tau2 action evaluator": EVALUATOR_SOURCE_DIR / "evaluator_action.py",
    }
    for label, path in required.items():
        require_file(path, label)

    events = load_jsonl(required["runtime events"])
    runtime_final_state = load_json(required["runtime final state"])
    results = load_json(required["tau2 results"])
    sim = first_simulation(results)
    task_id = str(sim.get("task_id") or "8")
    task = load_task(task_id)
    reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    checks = action_checks(reward_info)
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
    msg_rows = message_rows(messages)
    timeline = tool_event_rows(events)

    expected_book = find_expected_action(task, "book_reservation") or {}
    expected_book_args = expected_book.get("arguments") if isinstance(expected_book.get("arguments"), dict) else {}
    observed_book_calls = [row for row in timeline if row.get("tool_name") == "book_reservation"]
    observed_book_args = observed_book_calls[0].get("arguments") if observed_book_calls else None
    comparison = compare_arguments(expected_book_args, observed_book_args or {})

    expected_actions = (((task.get("evaluation_criteria") or {}).get("actions")) if isinstance(task.get("evaluation_criteria"), dict) else []) or []
    expected_by_name = {a.get("name"): a for a in expected_actions if isinstance(a, dict)}
    observed_by_name: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in timeline:
        observed_by_name[str(row.get("tool_name"))].append(row)

    action_expectations = []
    for check in checks:
        action = check.get("action") if isinstance(check, dict) and isinstance(check.get("action"), dict) else {}
        name = action.get("name")
        observed = observed_by_name.get(str(name), [])
        action_expectations.append(
            {
                "action_id": action.get("action_id"),
                "name": name,
                "tool_type": check.get("tool_type"),
                "expected_arguments": action.get("arguments"),
                "action_match": check.get("action_match"),
                "action_reward": check.get("action_reward"),
                "observed_call_event_ids": [o.get("event_id") for o in observed],
                "observed_result_event_ids": [o.get("result_event_id") for o in observed if o.get("result_event_id")],
                "observed_arguments": [o.get("arguments") for o in observed],
                "argument_comparison_for_first_call": compare_arguments(action.get("arguments"), observed[0].get("arguments") or {}) if observed else None,
            }
        )

    search_calls = [row for row in timeline if row.get("tool_name") == "search_direct_flight"]
    search_result = search_calls[0].get("result_payload") if search_calls else None
    hat271 = None
    if isinstance(search_result, list):
        hat271 = next((f for f in search_result if isinstance(f, dict) and f.get("flight_number") == "HAT271"), None)

    get_user_ids = [row.get("event_id") for row in timeline if row.get("tool_name") == "get_user_details"]
    get_res_ids = [row.get("event_id") for row in timeline if row.get("tool_name") == "get_reservation_details"]
    search_ids = [row.get("event_id") for row in search_calls]
    book_ids = [row.get("event_id") for row in observed_book_calls]

    user_accepted = any("go ahead" in (row.get("content_excerpt") or "").lower() and row.get("role") == "user" for row in msg_rows)
    user_refused_other_payment = "You do not accept any other mode of payment" in ((task.get("user_scenario") or {}).get("instructions") or {}).get("task_instructions", "")

    scoring_evidence = {
        "reward": reward_info.get("reward"),
        "reward_breakdown": reward_info.get("reward_breakdown"),
        "db_check": reward_info.get("db_check"),
        "termination_reason": sim.get("termination_reason"),
        "normal_user_stop": sim.get("termination_reason") == "user_stop",
        "action_checks": checks,
        "final_write_action_check": next((x for x in action_expectations if x.get("name") == "book_reservation"), None),
        "runtime_final_state_status": runtime_final_state.get("status") if isinstance(runtime_final_state, dict) else None,
    }

    expected_vs_observed = {
        "task_id": task_id,
        "task_purpose": ((task.get("description") or {}).get("purpose") if isinstance(task.get("description"), dict) else None),
        "exact_task_instruction": ((((task.get("user_scenario") or {}).get("instructions") or {}).get("task_instructions")) if isinstance(task.get("user_scenario"), dict) else None),
        "expected_successful_path": [
            "Obtain user details for sophia_silva_7557.",
            "Identify the May 10 ORD→PHL reservation WUNA5K and its flight number HAT271.",
            "Search ORD→PHL direct flights on 2024-05-26 and select HAT271.",
            "Because HAT271 economy has 3 seats and costs $174 per passenger, book Sophia plus Kevin for $348, below the $500 cap.",
            "Use one travel certificate, no baggage, and no travel insurance after explicit user confirmation.",
        ],
        "expected_db_mutation": expected_book_args,
        "observed_book_reservation_called": bool(observed_book_calls),
        "observed_book_reservation_event_ids": book_ids,
        "observed_book_reservation_arguments": observed_book_args,
        "observed_book_reservation_result": observed_book_calls[0].get("result_payload") if observed_book_calls else None,
        "book_reservation_absent": not bool(observed_book_calls),
        "book_reservation_absence_note": "Contrary to the initial failure interpretation, runtime_events.jsonl and results.json show book_reservation was called; the failed write action is an argument/DB mismatch, not an absent mutation.",
        "argument_comparison": comparison,
        "valid_hAT271_candidate_from_search": hat271,
        "required_prerequisites_gathered": {
            "user_id": True,
            "prior_reservation_WUNA5K": True,
            "target_flight_HAT271_found": hat271 is not None,
            "two_economy_seats_available": isinstance(hat271, dict) and (hat271.get("available_seats") or {}).get("economy", 0) >= 2,
            "two_passenger_total_under_500": isinstance(hat271, dict) and ((hat271.get("prices") or {}).get("economy", 999999) * 2) <= 500,
            "certificate_8045380_available": True,
            "explicit_confirmation_before_write": user_accepted,
        },
        "observed_conversation_path": relevant_message_excerpts(msg_rows),
        "user_acceptance_or_refusal": {
            "user_originally_requested_kevin": True,
            "user_accepted_agent_prompt_to_book_only_sophia": user_accepted,
            "user_refused_other_payment_modes_in_task": user_refused_other_payment,
        },
        "premature_stop_assessment": {
            "tau2_completed_with_user_stop": sim.get("termination_reason") == "user_stop",
            "agent_stopped_prematurely": False,
            "assessment": "The conversation ended normally after the agent reported success. The failure happened before stop: the agent booked a one-passenger reservation instead of the two-passenger expected mutation.",
        },
    }

    likely_cause = {
        "primary": "model_behavior_policy_confusion",
        "summary": "The assistant applied the modify-flight passenger-count rule to a new booking request, told the user Kevin could not be added, and then booked only Sophia. The booking tool itself supports up to five passengers and HAT271 had enough economy seats at a two-passenger total of $348.",
        "contributing_factors": [
            "The user asked for the same flight as a prior reservation, which may have led the assistant to reason as though it was modifying that reservation.",
            "The airline policy's no passenger-count changes rule applies under Modify flight / Change passengers, not Book flight.",
            "The user simulator accepted the assistant's incorrect constraint and instructed booking only Sophia, producing a normal USER_STOP despite DB/action failure.",
        ],
        "not_supported_by_artifacts": [
            "Not a turn-budget failure: max_steps was 30 and termination_reason was user_stop.",
            "Not missing read prerequisites: get_user_details, WUNA5K reservation details, and search_direct_flight all succeeded.",
            "Not missing book_reservation call: the call occurred and mutated DB, but with one passenger and $174 instead of two passengers and $348.",
            "Not an ActiveGraph-control issue: the run is trace-only and state packets were not fed back into tau2.",
        ],
        "failure_classification": {
            "model_behavior": True,
            "task_ambiguity": "minor: phrase 'same flight as recent flight' can invite modify-reservation framing, but task explicitly asks to book May 26 and add Kevin.",
            "policy_confusion": True,
            "missing_prompt_or_tool_affordance": "possible: the system could emphasize that booking a new reservation can include a different passenger count from a prior reservation.",
            "instrumentation_or_scoring_ambiguity": "low for this artifact: action check and DB check agree the expected two-passenger booking was not achieved.",
        },
    }

    report = {
        "status": STATUS_PASSED,
        "generated_at_utc": utc_now(),
        "runtime_run_dir": rel(run_dir),
        "analysis_boundaries": {
            "offline_artifact_analysis_only": True,
            "tau2_rerun_performed_by_analysis": False,
            "model_backed_episode_run_by_analysis": False,
            "llm_api_calls_made_by_analysis": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_analysis": False,
            "activegraph_control_added": False,
            "state_packets_fed_back_into_tau2": False,
        },
        "inputs": {label: {"path": rel(path), "sha256": sha256(path)} for label, path in required.items()},
        "static_sources": static_sources(),
        "runtime_overview": {
            "provider_model": ((results.get("info") or {}).get("agent_info") or {}).get("llm") if isinstance(results.get("info"), dict) else None,
            "max_steps": (results.get("info") or {}).get("max_steps") if isinstance(results.get("info"), dict) else None,
            "runtime_event_count": len(events),
            "runtime_event_types": counter_dict([e.get("event_type") for e in events]),
            "message_count": len(messages),
            "termination_reason": sim.get("termination_reason"),
            "reward": reward_info.get("reward"),
            "db_reward": (reward_info.get("db_check") or {}).get("db_reward") if isinstance(reward_info.get("db_check"), dict) else None,
        },
        "event_id_evidence": {
            "get_user_details": get_user_ids,
            "get_reservation_details": get_res_ids,
            "search_direct_flight": search_ids,
            "book_reservation": book_ids,
            "book_reservation_absent": not bool(book_ids),
            "final_action_check_failure": (next((x for x in action_expectations if x.get("name") == "book_reservation"), {}) or {}).get("action_match") is False,
            "final_db_check_failure": (reward_info.get("db_check") or {}).get("db_match") is False if isinstance(reward_info.get("db_check"), dict) else None,
        },
        "expected_vs_observed": expected_vs_observed,
        "action_expectation_analysis": {
            "read_actions_matched": sum(1 for x in action_expectations if x.get("tool_type") == "read" and x.get("action_match") is True),
            "read_actions_total": sum(1 for x in action_expectations if x.get("tool_type") == "read"),
            "write_actions_matched": sum(1 for x in action_expectations if x.get("tool_type") == "write" and x.get("action_match") is True),
            "write_actions_total": sum(1 for x in action_expectations if x.get("tool_type") == "write"),
            "actions": action_expectations,
        },
        "tool_call_timeline": timeline,
        "message_timeline": msg_rows,
        "scoring_evidence": scoring_evidence,
        "likely_cause": likely_cause,
        "recommended_next_experiment": "Rerun task 8 only after adding an agent prompt/control variant that explicitly distinguishes new bookings from modifying an existing reservation, then compare whether the assistant keeps Kevin when the searched flight has sufficient seats and total price is under $500. Keep ActiveGraph trace-only unless separately testing control.",
    }
    return report


def markdown_summary(report: dict[str, Any]) -> str:
    ev = report["expected_vs_observed"]
    scoring = report["scoring_evidence"]
    cause = report["likely_cause"]
    ids = report["event_id_evidence"]
    prereq = ev["required_prerequisites_gathered"]
    comp = ev["argument_comparison"]
    timeline = report["tool_call_timeline"]

    lines = [
        "# Airline task 8 failure analysis",
        "",
        f"- Status: `{report['status']}`",
        f"- Runtime run inspected: `{report['runtime_run_dir']}`",
        f"- Generated: `{report['generated_at_utc']}`",
        "- Analysis boundary: offline artifacts only; no tau2 rerun, no model-backed episode, no LLM/API calls, no API keys, no vendor mutation.",
        "",
        "## Conclusion",
        "",
        cause["summary"],
        "",
        "The important correction is that `book_reservation` was **not absent** in this artifact. It was called, succeeded at the tool level, and changed the DB, but it booked only Sophia for `$174`; the expected action and DB target required Sophia plus Kevin for `$348`.",
        "",
        "## Task goal and expected mutation",
        "",
        f"Purpose: {ev.get('task_purpose')}",
        "",
        "Expected successful path:",
    ]
    lines += [f"{i}. {step}" for i, step in enumerate(ev["expected_successful_path"], start=1)]
    lines += [
        "",
        "Expected `book_reservation` arguments:",
        "",
        "```json",
        json.dumps(ev["expected_db_mutation"], indent=2, sort_keys=True),
        "```",
        "",
        "## Observed path",
        "",
        f"- Termination reason: `{scoring.get('termination_reason')}`.",
        f"- Reward: `{scoring.get('reward')}`; DB check: `{json.dumps(scoring.get('db_check'), sort_keys=True)}`.",
        f"- `book_reservation` called: `{ev['observed_book_reservation_called']}`; absent: `{ev['book_reservation_absent']}`.",
        f"- Book event IDs: `{ids['book_reservation']}`.",
        f"- Passenger count expected vs observed: `{comp['passenger_count_expected']}` vs `{comp['passenger_count_observed']}`.",
        f"- Payment total expected vs observed: `${comp['payment_total_expected']}` vs `${comp['payment_total_observed']}`.",
        "",
        "Observed `book_reservation` arguments:",
        "",
        "```json",
        json.dumps(ev["observed_book_reservation_arguments"], indent=2, sort_keys=True),
        "```",
        "",
        "## Prerequisite evidence",
        "",
    ]
    lines += [f"- {key}: `{value}`" for key, value in prereq.items()]
    lines += [
        "",
        "Event IDs:",
        f"- `get_user_details`: `{ids['get_user_details']}`",
        f"- `get_reservation_details`: `{ids['get_reservation_details']}`",
        f"- `search_direct_flight`: `{ids['search_direct_flight']}`",
        f"- `book_reservation`: `{ids['book_reservation']}`",
        "",
        "HAT271 search candidate:",
        "",
        "```json",
        json.dumps(ev["valid_hAT271_candidate_from_search"], indent=2, sort_keys=True),
        "```",
        "",
        "## Tool/action timeline summary",
        "",
        "| # | Event | Tool | Turn | Status | State changed | Argument/result excerpt |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for i, row in enumerate(timeline, start=1):
        excerpt = row.get("result_excerpt") or json.dumps(row.get("arguments"), sort_keys=True)
        excerpt = str(excerpt).replace("\n", " ").replace("|", "\\|")[:180]
        lines.append(f"| {i} | `{row.get('event_id')}` | `{row.get('tool_name')}` | `{row.get('turn_index')}` | `{row.get('status')}` | `{row.get('state_changed')}` | {excerpt} |")
    lines += [
        "",
        "## Likely cause classification",
        "",
        f"Primary: `{cause['primary']}`.",
        "",
    ]
    lines += [f"- {item}" for item in cause["contributing_factors"]]
    lines += ["", "Not supported by artifacts:"]
    lines += [f"- {item}" for item in cause["not_supported_by_artifacts"]]
    lines += [
        "",
        "## Recommended next experiment",
        "",
        report["recommended_next_experiment"],
        "",
    ]
    return "\n".join(lines)


def final_state_from_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report["status"],
        "generated_at_utc": report["generated_at_utc"],
        "runtime_run_dir": report["runtime_run_dir"],
        "reward": report["runtime_overview"].get("reward"),
        "db_reward": report["runtime_overview"].get("db_reward"),
        "termination_reason": report["runtime_overview"].get("termination_reason"),
        "book_reservation_called": report["expected_vs_observed"].get("observed_book_reservation_called"),
        "failure_classification": report["likely_cause"].get("primary"),
        "analysis_boundaries": report["analysis_boundaries"],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve() if args.output_dir else args.runtime_run_dir.resolve() / OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = build_report(args, output_dir)
    except Exception as exc:  # noqa: BLE001 - emit diagnosable final_state/raw.log for missing artifact cases.
        final_state = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at_utc": utc_now(),
            "error": str(exc),
            "analysis_boundaries": {
                "offline_artifact_analysis_only": True,
                "tau2_rerun_performed_by_analysis": False,
                "model_backed_episode_run_by_analysis": False,
                "llm_api_calls_made_by_analysis": False,
                "requires_api_keys": False,
                "vendor_tau2_bench_mutated_by_analysis": False,
            },
        }
        write_json(output_dir / "final_state.json", final_state)
        (output_dir / "raw.log").write_text(f"airline task 8 failure analysis\nstatus={STATUS_INPUTS_MISSING}\nerror={exc}\n", encoding="utf-8")
        print(f"analysis_status={STATUS_INPUTS_MISSING}")
        print(f"error={exc}", file=sys.stderr)
        return 2

    write_json(output_dir / "airline_task8_failure_analysis.json", report)
    (output_dir / "airline_task8_failure_summary.md").write_text(markdown_summary(report), encoding="utf-8")
    write_json(output_dir / "action_expectation_analysis.json", report["action_expectation_analysis"])
    write_json(output_dir / "tool_call_timeline.json", report["tool_call_timeline"])
    write_json(output_dir / "expected_vs_observed.json", report["expected_vs_observed"])
    write_json(output_dir / "scoring_evidence.json", report["scoring_evidence"])
    write_json(output_dir / "final_state.json", final_state_from_report(report))
    shutil.copyfile(args.runtime_run_dir / "raw.log", output_dir / "raw.log")
    with (output_dir / "raw.log").open("a", encoding="utf-8") as log:
        log.write("\n--- offline airline task 8 failure analysis ---\n")
        log.write(f"generated_at_utc={report['generated_at_utc']}\n")
        log.write(f"status={report['status']}\n")
        log.write("tau2_rerun_performed_by_analysis=false\n")
        log.write("model_backed_episode_run_by_analysis=false\n")
        log.write("llm_api_calls_made_by_analysis=false\n")
        log.write("vendor_tau2_bench_mutated_by_analysis=false\n")

    print(rel(output_dir))
    print(report["status"])
    print(f"likely_cause={report['likely_cause']['primary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
