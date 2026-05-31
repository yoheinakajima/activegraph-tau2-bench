#!/usr/bin/env python3
"""Offline comparison for airline task 8 baseline vs prompt-variant failures.

This command reads committed runtime artifacts only. It does not run tau2, start
another model-backed episode, call LLM/API services, require API keys, mutate
vendor/tau2-bench, or implement any ActiveGraph control intervention.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
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

STATUS_PASSED = "airline_task8_prompt_variant_comparison_passed"
STATUS_INPUTS_MISSING = "airline_task8_prompt_variant_comparison_inputs_missing"
OUTPUT_DIR_NAME = "prompt_variant_comparison"
TASK_ID = "8"
AIRLINE_DATA_DIR = pathlib.Path("vendor/tau2-bench/data/tau2/domains/airline")
AIRLINE_SOURCE_DIR = pathlib.Path("vendor/tau2-bench/src/tau2/domains/airline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-compare airline task 8 baseline and prompt-variant failure artifacts."
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


def raw_log_path(run_dir: pathlib.Path) -> pathlib.Path:
    return run_dir / "raw.log"


def truncate(value: Any, limit: int = 900) -> Any:
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


def first_simulation(results: dict[str, Any]) -> dict[str, Any]:
    simulations = results.get("simulations")
    if isinstance(simulations, list) and simulations and isinstance(simulations[0], dict):
        return simulations[0]
    return {}


def load_task(task_id: str) -> dict[str, Any]:
    tasks_path = REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json"
    if not tasks_path.is_file():
        return {}
    tasks = load_json(tasks_path)
    for task in tasks if isinstance(tasks, list) else []:
        if isinstance(task, dict) and str(task.get("id")) == task_id:
            return task
    return {}


def action_checks(sim: dict[str, Any]) -> list[dict[str, Any]]:
    reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    checks = reward_info.get("action_checks") if isinstance(reward_info.get("action_checks"), list) else []
    return [check for check in checks if isinstance(check, dict)]


def summarize_results(results: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sim = first_simulation(results)
    reward = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    db_check = reward.get("db_check") if isinstance(reward.get("db_check"), dict) else {}
    checks = action_checks(sim)
    read_checks = [c for c in checks if c.get("tool_type") == "read"]
    write_checks = [c for c in checks if c.get("tool_type") == "write"]
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
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
        "message_count": len(messages),
        "runtime_event_count": len(events),
        "runtime_event_types": counter_dict([e.get("event_type") for e in events]),
    }


def expected_actions(sim: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for check in action_checks(sim):
        action = check.get("action") if isinstance(check.get("action"), dict) else {}
        name = action.get("name")
        if isinstance(name, str):
            rows[name] = {
                "action_id": action.get("action_id"),
                "tool_type": check.get("tool_type"),
                "expected_arguments": action.get("arguments"),
                "matched": check.get("action_match"),
                "reward": check.get("action_reward"),
            }
    return rows


def message_tool_calls(sim: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, message in enumerate(sim.get("messages") if isinstance(sim.get("messages"), list) else []):
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                rows.append(
                    {
                        "message_index": index,
                        "turn_idx": message.get("turn_idx"),
                        "name": call.get("name"),
                        "arguments": call.get("arguments"),
                        "requestor": call.get("requestor"),
                        "id": call.get("id"),
                    }
                )
    return rows


def last_call(calls: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for call in reversed(calls):
        if call.get("name") == name:
            return call
    return None


def all_calls(calls: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [call for call in calls if call.get("name") == name]


def tool_results(sim: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, message in enumerate(sim.get("messages") if isinstance(sim.get("messages"), list) else []):
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        rows.append(
            {
                "message_index": index,
                "turn_idx": message.get("turn_idx"),
                "content": parse_json_maybe(message.get("content")),
                "content_excerpt": truncate(message.get("content"), 1200),
            }
        )
    return rows


def message_path(sim: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, message in enumerate(sim.get("messages") if isinstance(sim.get("messages"), list) else []):
        if not isinstance(message, dict):
            continue
        calls = [call.get("name") for call in message.get("tool_calls") or [] if isinstance(call, dict)]
        content = message.get("content")
        rows.append(
            {
                "message_index": index,
                "turn_idx": message.get("turn_idx"),
                "role": message.get("role"),
                "tool_calls": calls,
                "content_excerpt": truncate(content, 360),
            }
        )
    return rows


def tool_event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "tool_call_requested":
            continue
        p = payload(event)
        call = p.get("tool_call") if isinstance(p.get("tool_call"), dict) else {}
        rows.append(
            {
                "event_id": event.get("event_id"),
                "turn_index": event.get("turn_index"),
                "tool_name": call.get("name") or event.get("tool_name"),
                "arguments": call.get("arguments"),
                "requestor": call.get("requestor"),
                "tool_call_id": call.get("id"),
            }
        )
    return rows


def argument_diff(expected: Any, baseline: Any, variant: Any) -> dict[str, Any]:
    return {
        "expected": expected,
        "baseline_observed": baseline,
        "variant_observed": variant,
        "baseline_matches_expected": canonical(expected) == canonical(baseline),
        "variant_matches_expected": canonical(expected) == canonical(variant),
        "baseline_vs_variant_same": canonical(baseline) == canonical(variant),
    }


def passengers(arguments: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(arguments, dict):
        return []
    raw = arguments.get("passengers")
    return [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []


def passenger_names(arguments: dict[str, Any] | None) -> list[str]:
    names = []
    for passenger in passengers(arguments):
        first = passenger.get("first_name")
        last = passenger.get("last_name")
        names.append(" ".join(str(x) for x in [first, last] if x))
    return names


def flight_numbers(arguments: dict[str, Any] | None) -> list[str]:
    if not isinstance(arguments, dict):
        return []
    flights = arguments.get("flights")
    if not isinstance(flights, list):
        return []
    return [str(f.get("flight_number")) for f in flights if isinstance(f, dict) and f.get("flight_number")]


def payment_amount(arguments: dict[str, Any] | None) -> Any:
    if not isinstance(arguments, dict):
        return None
    methods = arguments.get("payment_methods")
    if isinstance(methods, list) and methods and isinstance(methods[0], dict):
        return methods[0].get("amount")
    return None


def action_score_delta(baseline_sim: dict[str, Any], variant_sim: dict[str, Any]) -> dict[str, Any]:
    base = expected_actions(baseline_sim)
    var = expected_actions(variant_sim)
    names = sorted(set(base) | set(var))
    rows = []
    for name in names:
        b = base.get(name, {})
        v = var.get(name, {})
        rows.append(
            {
                "action_name": name,
                "tool_type": b.get("tool_type") or v.get("tool_type"),
                "baseline_match": b.get("matched"),
                "variant_match": v.get("matched"),
                "baseline_reward": b.get("reward"),
                "variant_reward": v.get("reward"),
                "reward_delta_variant_minus_baseline": (v.get("reward") or 0) - (b.get("reward") or 0),
                "matching_regressed": b.get("matched") is True and v.get("matched") is not True,
                "matching_improved": b.get("matched") is not True and v.get("matched") is True,
            }
        )
    return {
        "read_score": {
            "baseline": f"{sum(1 for c in action_checks(baseline_sim) if c.get('tool_type') == 'read' and c.get('action_match') is True)}/"
            f"{sum(1 for c in action_checks(baseline_sim) if c.get('tool_type') == 'read')}",
            "variant": f"{sum(1 for c in action_checks(variant_sim) if c.get('tool_type') == 'read' and c.get('action_match') is True)}/"
            f"{sum(1 for c in action_checks(variant_sim) if c.get('tool_type') == 'read')}",
        },
        "write_score": {
            "baseline": f"{sum(1 for c in action_checks(baseline_sim) if c.get('tool_type') == 'write' and c.get('action_match') is True)}/"
            f"{sum(1 for c in action_checks(baseline_sim) if c.get('tool_type') == 'write')}",
            "variant": f"{sum(1 for c in action_checks(variant_sim) if c.get('tool_type') == 'write' and c.get('action_match') is True)}/"
            f"{sum(1 for c in action_checks(variant_sim) if c.get('tool_type') == 'write')}",
        },
        "actions": rows,
    }


def message_path_delta(baseline_sim: dict[str, Any], variant_sim: dict[str, Any]) -> dict[str, Any]:
    base_path = message_path(baseline_sim)
    var_path = message_path(variant_sim)
    base_tools = [call["name"] for call in message_tool_calls(baseline_sim)]
    var_tools = [call["name"] for call in message_tool_calls(variant_sim)]
    diff = list(difflib.unified_diff(base_tools, var_tools, fromfile="baseline_tool_sequence", tofile="variant_tool_sequence", lineterm=""))
    return {
        "conversation_path_changed": canonical(base_path) != canonical(var_path),
        "baseline_message_count": len(base_path),
        "variant_message_count": len(var_path),
        "baseline_tool_sequence": base_tools,
        "variant_tool_sequence": var_tools,
        "tool_sequence_diff": diff,
        "notable_changes": [
            "Variant batched all five get_reservation_details calls in one assistant turn instead of serializing them.",
            "Variant did not call search_direct_flight before book_reservation, so the expected read action no longer matched.",
            "Variant attempted book_reservation earlier with both Sophia and Kevin but an underpayment amount.",
            "After the payment error, the user accepted dropping Kevin and the run stopped without a successful second book_reservation call.",
        ],
        "baseline_path": base_path,
        "variant_path": var_path,
    }


def build_tool_argument_delta(baseline_sim: dict[str, Any], variant_sim: dict[str, Any]) -> dict[str, Any]:
    expected = expected_actions(baseline_sim)
    base_calls = message_tool_calls(baseline_sim)
    var_calls = message_tool_calls(variant_sim)
    expected_search = expected.get("search_direct_flight", {}).get("expected_arguments")
    expected_book = expected.get("book_reservation", {}).get("expected_arguments")
    base_search = (last_call(base_calls, "search_direct_flight") or {}).get("arguments")
    var_search = (last_call(var_calls, "search_direct_flight") or {}).get("arguments")
    base_book = (last_call(base_calls, "book_reservation") or {}).get("arguments")
    var_book = (last_call(var_calls, "book_reservation") or {}).get("arguments")
    return {
        "search_direct_flight": argument_diff(expected_search, base_search, var_search),
        "book_reservation": argument_diff(expected_book, base_book, var_book),
        "book_reservation_focus": {
            "baseline_passengers": passenger_names(base_book),
            "variant_passengers": passenger_names(var_book),
            "expected_passengers": passenger_names(expected_book),
            "baseline_preserved_kevin": "Kevin Smith" in passenger_names(base_book),
            "variant_preserved_kevin": "Kevin Smith" in passenger_names(var_book),
            "baseline_flights": flight_numbers(base_book),
            "variant_flights": flight_numbers(var_book),
            "expected_flights": flight_numbers(expected_book),
            "baseline_selected_hAT271": "HAT271" in flight_numbers(base_book),
            "variant_selected_hAT271": "HAT271" in flight_numbers(var_book),
            "baseline_payment_amount": payment_amount(base_book),
            "variant_payment_amount": payment_amount(var_book),
            "expected_payment_amount": payment_amount(expected_book),
        },
        "all_baseline_tool_calls": base_calls,
        "all_variant_tool_calls": var_calls,
    }


def generalization_assessment() -> dict[str, Any]:
    return {
        "prompt_variant_classification": "task_specific_prompt_hack",
        "continued_prompt_iteration_recommended": False,
        "reason_not_recommended": (
            "The variant targeted one observed symptom (dropping a named passenger) and changed the path enough to regress "
            "a read-action match while still failing the write. Iterating this task-specific prompt would optimize around "
            "airline task 8 artifacts rather than solve the broader write-argument construction problem."
        ),
        "generalizable_failure_class": "multi-constraint write action argument construction after multi-step read evidence",
        "failure_class_description": (
            "The agent must carry forward user constraints, policy constraints, tool-result evidence, and price/payment constraints "
            "into one irreversible write call. The baseline lost an entity constraint; the variant preserved the entity but missed "
            "the evidence-gathering/search step and payment total."
        ),
        "distinction": {
            "task_specific_prompt_hacking": [
                "Adds benchmark-aware prose about preserving named passengers for this exact observed failure.",
                "May alter conversation trajectory and action matching without a general consistency check.",
                "Does not create a reusable representation of user constraints, tool evidence, intended mutation, or post-write verification.",
            ],
            "generalizable_runtime_support_activegraph_hypotheses": [
                "pre-write constraint packet",
                "entity/constraint ledger from user request and tool results",
                "write-intent vs tool-argument diff before dispatch",
                "policy/evidence checklist before irreversible booking",
                "post-tool mutation verification against intended constraints",
            ],
        },
        "proposed_interventions_not_implemented": [
            {
                "name": "pre-write constraint packet",
                "hypothesis": "Before any write, assemble a compact packet of required entities, dates, route, flight, cabin, price, payment, insurance, and baggage constraints.",
            },
            {
                "name": "entity/constraint ledger from user request and tool results",
                "hypothesis": "Maintain a ledger that separates user-stated constraints from tool-evidenced facts and highlights unresolved or contradictory fields.",
            },
            {
                "name": "write-intent vs tool-argument diff before dispatch",
                "hypothesis": "Compare the intended booking state to the actual book_reservation arguments and block/flag missing passengers, missing search evidence, or payment mismatches.",
            },
            {
                "name": "policy/evidence checklist before irreversible booking",
                "hypothesis": "Require explicit evidence for route/date/flight availability, passenger eligibility, payment coverage, and no-insurance/baggage choices before calling a write tool.",
            },
            {
                "name": "post-tool mutation verification against intended constraints",
                "hypothesis": "After a write, compare the resulting reservation against the pre-write packet to identify silent drops or mismatched totals immediately.",
            },
        ],
        "implemented_in_this_change": False,
    }


def load_optional_json(path: pathlib.Path) -> Any | None:
    if not path.is_file():
        return None
    return load_json(path)


def raw_log_summary(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "path": rel(path),
        "sha256": sha256(path),
        "line_count": len(text.splitlines()),
        "first_lines": text.splitlines()[:8],
        "last_lines": text.splitlines()[-8:],
    }


def write_summary(path: pathlib.Path, comparison: dict[str, Any], action_delta: dict[str, Any], arg_delta: dict[str, Any], msg_delta: dict[str, Any], gen: dict[str, Any]) -> None:
    base = comparison["baseline_summary"]
    var = comparison["variant_summary"]
    focus = arg_delta["book_reservation_focus"]
    lines = [
        "# Airline task 8 baseline vs prompt-variant comparison",
        "",
        "## Offline boundary",
        "",
        "- tau2 rerun: **no**.",
        "- Model-backed episode: **no**.",
        "- LLM/API calls: **no**.",
        "- API keys required: **no**.",
        "- `vendor/tau2-bench` mutation: **no**.",
        "",
        "## Result summary",
        "",
        f"- Baseline run: `{comparison['baseline_run_dir']}`; reward `{base['reward']}`, DB match `{base['db_match']}`, read score `{action_delta['read_score']['baseline']}`, write score `{action_delta['write_score']['baseline']}`.",
        f"- Prompt-variant run: `{comparison['variant_run_dir']}`; reward `{var['reward']}`, DB match `{var['db_match']}`, read score `{action_delta['read_score']['variant']}`, write score `{action_delta['write_score']['variant']}`.",
        "- Both runs terminated with `user_stop` but scored reward `0.0` because the required booking state/action did not match.",
        "",
        "## Action score deltas",
        "",
        "| Action | Type | Baseline | Variant | Delta | Regressed? |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in action_delta["actions"]:
        lines.append(
            f"| `{row['action_name']}` | {row['tool_type']} | {row['baseline_reward']} | {row['variant_reward']} | {row['reward_delta_variant_minus_baseline']} | {row['matching_regressed']} |"
        )
    lines.extend(
        [
            "",
            "## Tool argument deltas",
            "",
            f"- `search_direct_flight`: baseline arguments matched expected; variant made no `search_direct_flight` call, so read action matching regressed.",
            f"- `book_reservation`: baseline selected `{focus['baseline_flights']}` and paid `{focus['baseline_payment_amount']}`, but passengers were `{focus['baseline_passengers']}`.",
            f"- `book_reservation`: variant selected `{focus['variant_flights']}` and passengers were `{focus['variant_passengers']}`, but paid `{focus['variant_payment_amount']}` instead of `{focus['expected_payment_amount']}`.",
            f"- Kevin preserved in baseline write: `{focus['baseline_preserved_kevin']}`.",
            f"- Kevin preserved in variant write: `{focus['variant_preserved_kevin']}`.",
            f"- HAT271 selected in baseline write: `{focus['baseline_selected_hAT271']}`.",
            f"- HAT271 selected in variant write: `{focus['variant_selected_hAT271']}`.",
            "",
            "## Message path deltas",
            "",
            f"- Conversation path changed: `{msg_delta['conversation_path_changed']}`.",
            f"- Baseline message count: `{msg_delta['baseline_message_count']}`; variant message count: `{msg_delta['variant_message_count']}`.",
            "- Baseline tool sequence: " + ", ".join(f"`{x}`" for x in msg_delta["baseline_tool_sequence"]),
            "- Variant tool sequence: " + ", ".join(f"`{x}`" for x in msg_delta["variant_tool_sequence"]),
            "- The prompt variant batched reservation reads, skipped the flight search, and attempted the write earlier.",
            "",
            "## Why matching regressed or remained failed",
            "",
            "- `search_direct_flight` regressed because the prompt variant never called it. The scorer expected a read call with `origin=ORD`, `destination=PHL`, and `date=2024-05-26`.",
            "- `book_reservation` still failed because the variant preserved Kevin and selected HAT271 but sent payment amount `320` while the tool reported the actual total was `348`.",
            "- The baseline made the expected search and selected HAT271, but dropped Kevin and paid only `174`, producing a one-passenger booking.",
            "",
            "## Failure class and generalization assessment",
            "",
            f"- Failure class: **{gen['generalizable_failure_class']}**.",
            "- The current prompt variant is classified as **task-specific** and is **not recommended** for continued iteration.",
            f"- Reason: {gen['reason_not_recommended']}",
            "",
            "### Task-specific prompt hacking vs general runtime support",
            "",
            "Task-specific prompt hacking adds benchmark-specific prose and can move failures around. In this case it fixed the passenger-preservation symptom in the first write attempt but regressed the expected search action and still underpaid.",
            "",
            "Generalizable ActiveGraph-style runtime support should instead externalize and check the constraints around any irreversible write:",
            "",
        ]
    )
    for item in gen["proposed_interventions_not_implemented"]:
        lines.append(f"- **{item['name']}**: {item['hypothesis']}")
    lines.extend(["", "No intervention is implemented by this comparison script; it only records offline analysis artifacts.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    baseline_dir = args.baseline_run_dir
    variant_dir = args.variant_run_dir
    out_dir = args.output_dir or variant_dir / OUTPUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_lines: list[str] = []

    try:
        inputs = {
            "baseline_runtime_events": baseline_dir / "runtime_events.jsonl",
            "variant_runtime_events": variant_dir / "runtime_events.jsonl",
            "baseline_results": result_path(baseline_dir),
            "variant_results": result_path(variant_dir),
            "baseline_raw_log": raw_log_path(baseline_dir),
            "variant_raw_log": raw_log_path(variant_dir),
            "prompt_variant_json": variant_dir / "prompt_variant.json",
            "prompt_variant_txt": variant_dir / "prompt_variant.txt",
        }
        for label, path in inputs.items():
            require_file(path, label)

        raw_lines.append(f"[{utc_now()}] loaded required inputs")
        baseline_events = load_jsonl(inputs["baseline_runtime_events"])
        variant_events = load_jsonl(inputs["variant_runtime_events"])
        baseline_results = load_json(inputs["baseline_results"])
        variant_results = load_json(inputs["variant_results"])
        baseline_sim = first_simulation(baseline_results)
        variant_sim = first_simulation(variant_results)
        task = load_task(TASK_ID)

        action_delta = action_score_delta(baseline_sim, variant_sim)
        arg_delta = build_tool_argument_delta(baseline_sim, variant_sim)
        msg_delta = message_path_delta(baseline_sim, variant_sim)
        gen = generalization_assessment()

        comparison = {
            "status": STATUS_PASSED,
            "generated_at": utc_now(),
            "baseline_run_dir": rel(baseline_dir),
            "variant_run_dir": rel(variant_dir),
            "output_dir": rel(out_dir),
            "offline_boundary": {
                "tau2_rerun": False,
                "model_backed_episode": False,
                "llm_api_calls_made": False,
                "api_keys_required": False,
                "vendor_tau2_bench_mutated": False,
                "interventions_implemented": False,
            },
            "inputs": {label: {"path": rel(path), "sha256": sha256(path)} for label, path in inputs.items()},
            "additional_inputs": {
                "baseline_db_mismatch_analysis": {
                    "path": rel(baseline_dir / "airline_task8_failure_analysis" / "expected_vs_observed.json"),
                    "present": (baseline_dir / "airline_task8_failure_analysis" / "expected_vs_observed.json").is_file(),
                    "content": load_optional_json(baseline_dir / "airline_task8_failure_analysis" / "expected_vs_observed.json"),
                },
                "airline_task_static_data": {
                    "tasks_json": rel(REPO_ROOT / AIRLINE_DATA_DIR / "tasks.json"),
                    "task_8_excerpt": task,
                },
                "airline_tools_source": {
                    "source_dir": rel(REPO_ROOT / AIRLINE_SOURCE_DIR),
                    "inspected_by_script": False,
                    "note": "Static task/evaluator outputs and runtime artifacts were sufficient for this comparison.",
                },
            },
            "baseline_summary": summarize_results(baseline_results, baseline_events),
            "variant_summary": summarize_results(variant_results, variant_events),
            "answers": {
                "did_prompt_variant_change_conversation_path": msg_delta["conversation_path_changed"],
                "did_it_change_search_direct_flight_arguments": arg_delta["search_direct_flight"]["baseline_vs_variant_same"] is False,
                "did_it_change_book_reservation_arguments": arg_delta["book_reservation"]["baseline_vs_variant_same"] is False,
                "did_it_preserve_kevin": arg_delta["book_reservation_focus"]["variant_preserved_kevin"],
                "did_it_select_same_flight_HAT271": arg_delta["book_reservation_focus"]["variant_selected_hAT271"],
                "why_search_direct_flight_matching_regressed": "The variant did not call search_direct_flight; the expected action required ORD->PHL on 2024-05-26.",
                "why_book_reservation_still_failed": "The variant included Sophia and Kevin on HAT271 but used payment amount 320 instead of the required/actual total 348.",
                "failure_class": gen["generalizable_failure_class"],
            },
            "runtime_tool_events": {
                "baseline": tool_event_rows(baseline_events),
                "variant": tool_event_rows(variant_events),
            },
            "tool_results": {
                "baseline": tool_results(baseline_sim),
                "variant": tool_results(variant_sim),
            },
            "raw_log_summaries": {
                "baseline": raw_log_summary(inputs["baseline_raw_log"]),
                "variant": raw_log_summary(inputs["variant_raw_log"]),
            },
            "prompt_variant": {
                "json": load_json(inputs["prompt_variant_json"]),
                "text": inputs["prompt_variant_txt"].read_text(encoding="utf-8"),
            },
        }

        write_json(out_dir / "prompt_variant_comparison.json", comparison)
        write_json(out_dir / "action_score_delta.json", action_delta)
        write_json(out_dir / "tool_argument_delta.json", arg_delta)
        write_json(out_dir / "message_path_delta.json", msg_delta)
        write_json(out_dir / "generalization_assessment.json", gen)
        final_state = {
            "status": STATUS_PASSED,
            "generated_at": utc_now(),
            "output_dir": rel(out_dir),
            "artifacts": [
                rel(out_dir / "prompt_variant_comparison.json"),
                rel(out_dir / "prompt_variant_comparison_summary.md"),
                rel(out_dir / "action_score_delta.json"),
                rel(out_dir / "tool_argument_delta.json"),
                rel(out_dir / "message_path_delta.json"),
                rel(out_dir / "generalization_assessment.json"),
                rel(out_dir / "final_state.json"),
                rel(out_dir / "raw.log"),
            ],
            "offline_boundary": comparison["offline_boundary"],
        }
        write_json(out_dir / "final_state.json", final_state)
        write_summary(out_dir / "prompt_variant_comparison_summary.md", comparison, action_delta, arg_delta, msg_delta, gen)
        raw_lines.append(f"[{utc_now()}] wrote comparison artifacts to {rel(out_dir)}")
        (out_dir / "raw.log").write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
        print(json.dumps(final_state, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should persist failure state.
        final_state = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at": utc_now(),
            "output_dir": rel(out_dir),
            "error": str(exc),
            "offline_boundary": {
                "tau2_rerun": False,
                "model_backed_episode": False,
                "llm_api_calls_made": False,
                "api_keys_required": False,
                "vendor_tau2_bench_mutated": False,
                "interventions_implemented": False,
            },
        }
        write_json(out_dir / "final_state.json", final_state)
        raw_lines.append(f"[{utc_now()}] ERROR {exc}")
        (out_dir / "raw.log").write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
        print(json.dumps(final_state, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
