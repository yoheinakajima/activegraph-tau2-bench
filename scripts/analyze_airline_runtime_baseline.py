#!/usr/bin/env python3
"""Analyze the first successful airline runtime-traced tau2 baseline offline.

The analyzer reads committed artifacts and static airline domain files only. It
never runs tau2, starts a model-backed episode, calls LLM/API services, requires
API keys, mutates vendor/tau2-bench, or adds ActiveGraph control.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import shutil
from typing import Any

from analyze_runtime_trace_outcome import (
    RUNTIME_EVENT_FAMILIES,
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

STATUS_PASSED = "airline_runtime_baseline_analysis_passed"
STATUS_WITH_GAPS = "airline_runtime_baseline_analysis_completed_with_gaps"
STATUS_INPUTS_MISSING = "airline_runtime_baseline_analysis_inputs_missing"
OUTPUT_DIR_NAME = "airline_analysis"
AIRLINE_DATA_DIR = pathlib.Path("vendor/tau2-bench/data/tau2/domains/airline")
AIRLINE_SOURCE_DIR = pathlib.Path("vendor/tau2-bench/src/tau2/domains/airline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-analyze the committed successful airline runtime-traced tau2 baseline run."
    )
    parser.add_argument("--runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help=f"Defaults to <runtime-run-dir>/{OUTPUT_DIR_NAME}/.",
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


def load_task(tasks_path: pathlib.Path, task_id: str | None) -> dict[str, Any]:
    tasks = load_json(tasks_path)
    if not isinstance(tasks, list):
        return {}
    for task in tasks:
        if isinstance(task, dict) and str(task.get("id")) == str(task_id):
            return task
    return {}


def nested_get(obj: Any, path: list[str], default: Any = None) -> Any:
    cur = obj
    for part in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
    return cur if cur is not None else default


def message_text(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return None


def truncate(value: str | None, limit: int = 320) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def message_timeline(messages: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        row = {
            "message_index": index,
            "turn_idx": message.get("turn_idx"),
            "role": message.get("role"),
            "timestamp": message.get("timestamp"),
            "content_preview": truncate(message_text(message)),
            "cost": message.get("cost"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens") or token_sum(usage),
            "tool_calls": [
                {
                    "id": call.get("id"),
                    "name": call.get("name"),
                    "arguments": call.get("arguments"),
                    "requestor": call.get("requestor"),
                }
                for call in tool_calls
                if isinstance(call, dict)
            ],
        }
        if message.get("role") == "tool":
            row["tool_result"] = parse_json_maybe(message.get("content"))
        rows.append(row)
    return rows


def token_sum(usage: dict[str, Any]) -> int | None:
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt + completion
    return None


def token_cost_summary(messages: list[Any], sim: dict[str, Any]) -> dict[str, Any]:
    by_role: dict[str, dict[str, Any]] = collections.defaultdict(lambda: {"messages": 0, "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    totals = {"messages": 0, "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role"))
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        prompt = usage.get("prompt_tokens") if isinstance(usage.get("prompt_tokens"), int) else 0
        completion = usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"), int) else 0
        total = usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else prompt + completion
        cost = message.get("cost") if isinstance(message.get("cost"), (int, float)) else 0.0
        for bucket in (totals, by_role[role]):
            bucket["messages"] += 1
            bucket["cost"] += cost
            bucket["prompt_tokens"] += prompt
            bucket["completion_tokens"] += completion
            bucket["total_tokens"] += total
    return {
        "agent_cost_reported": sim.get("agent_cost"),
        "user_cost_reported": sim.get("user_cost"),
        "total_cost_reported": (sim.get("agent_cost") or 0) + (sim.get("user_cost") or 0),
        "from_messages": {"total": totals, "by_role": dict(sorted(by_role.items()))},
        "token_usage_available": totals["total_tokens"] > 0,
    }


def compact_runtime_event(event: dict[str, Any]) -> dict[str, Any]:
    p = payload(event)
    message = p.get("message") if isinstance(p.get("message"), dict) else {}
    response = p.get("response") if isinstance(p.get("response"), dict) else {}
    tool_call = p.get("tool_call") if isinstance(p.get("tool_call"), dict) else {}
    return {
        "sequence": event.get("_sequence"),
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "timestamp": event.get("timestamp"),
        "component": event.get("component"),
        "task_id": event.get("task_id"),
        "turn_index": event.get("turn_index"),
        "message_role": event.get("message_role"),
        "tool_name": event.get("tool_name") or tool_call.get("name"),
        "content_preview": truncate(p.get("content_preview") or message.get("content_preview") or response.get("content_preview")),
        "tool_call": tool_call or None,
        "status": p.get("status"),
        "state_hash": event.get("state_hash"),
        "state_hash_before": p.get("state_hash_before"),
        "state_hash_after": p.get("state_hash_after"),
        "result_payload": tool_result_payload(event),
    }


def task_timeline(events: list[dict[str, Any]], messages: list[Any]) -> dict[str, Any]:
    interesting = {
        "simulation_start",
        "simulation_execution_start",
        "orchestrator_run_start",
        "turn_start",
        "user_response",
        "agent_response",
        "tool_call_requested",
        "message_observed",
        "evaluation_start",
        "evaluation_end",
        "simulation_execution_end",
        "simulation_end",
    }
    return {
        "messages": message_timeline(messages),
        "runtime_events": [compact_runtime_event(event) for event in events if event.get("event_type") in interesting],
    }


def tool_timeline(events: list[dict[str, Any]], messages: list[Any]) -> dict[str, Any]:
    tool_events = [event for event in events if event.get("tool_name") or event.get("event_type") in {"tool_call_requested", "message_observed"}]
    calls_from_messages = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                calls_from_messages.append(
                    {
                        "turn_idx": message.get("turn_idx"),
                        "id": call.get("id"),
                        "name": call.get("name"),
                        "arguments": call.get("arguments"),
                        "requestor": call.get("requestor"),
                    }
                )
    return {
        "tool_call_count_from_messages": len(calls_from_messages),
        "tool_calls_from_messages": calls_from_messages,
        "tool_event_count": len(tool_events),
        "tool_events": [compact_runtime_event(event) for event in tool_events],
        "read_tool_calls": [call for call in calls_from_messages if call.get("name") and not str(call.get("name")).startswith(("book_", "cancel_", "update_", "delete_", "modify_"))],
        "write_tool_calls": [call for call in calls_from_messages if call.get("name") and str(call.get("name")).startswith(("book_", "cancel_", "update_", "delete_", "modify_"))],
        "state_hash_changes": [
            compact_runtime_event(event)
            for event in tool_events
            if payload(event).get("state_hash_before") and payload(event).get("state_hash_after") and payload(event).get("state_hash_before") != payload(event).get("state_hash_after")
        ],
    }


def scoring_evidence(sim: dict[str, Any], task: dict[str, Any], events: list[dict[str, Any]], initial_reservation: dict[str, Any]) -> dict[str, Any]:
    reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    evaluation_events = [compact_runtime_event(event) for event in events if event.get("event_type") in {"evaluation_start", "evaluation_end", "simulation_execution_end"}]
    return {
        "task_id": sim.get("task_id"),
        "reward_info": reward_info,
        "termination_reason": sim.get("termination_reason"),
        "normal_stop": sim.get("termination_reason") == "user_stop",
        "evaluation_criteria": task.get("evaluation_criteria"),
        "expected_behavior_summary": [
            "Task asks the simulated user to cancel reservation EHGLP3 but avoid cancellation if no refund is available.",
            "Evaluation expects the agent to refuse or avoid proceeding with the disallowed cancellation.",
            "No write action was expected for task 0; preserving the DB is sufficient for the DB portion of the reward.",
        ],
        "initial_reservation_evidence": initial_reservation,
        "evaluation_runtime_events": evaluation_events,
        "db_unchanged_inferred_from": "reward_info.db_check.db_match is true and no write tool call/state-hash change was observed in runtime tool events.",
    }


def domain_evidence(task: dict[str, Any], db: dict[str, Any]) -> dict[str, Any]:
    reservation_id = "EHGLP3"
    user_id = "emma_kim_9957"
    return {
        "airline_task": {
            "id": task.get("id"),
            "purpose": nested_get(task, ["description", "purpose"]),
            "task_instructions": nested_get(task, ["user_scenario", "instructions", "task_instructions"]),
            "reason_for_call": nested_get(task, ["user_scenario", "instructions", "reason_for_call"]),
            "known_info": nested_get(task, ["user_scenario", "instructions", "known_info"]),
            "evaluation_criteria": task.get("evaluation_criteria"),
        },
        "airline_static_db_excerpt": {
            "reservation_id": reservation_id,
            "reservation": nested_get(db, ["reservations", reservation_id], {}),
            "user_id": user_id,
            "user": nested_get(db, ["users", user_id], {}),
        },
        "relevant_source_files": [
            {
                "path": str(AIRLINE_DATA_DIR / "tasks.json"),
                "why": "Contains task 0 purpose, user scenario, and evaluation criteria.",
            },
            {
                "path": str(AIRLINE_DATA_DIR / "db.json"),
                "why": "Contains reservation EHGLP3 and user emma_kim_9957 static baseline data.",
            },
            {
                "path": str(AIRLINE_DATA_DIR / "policy.md"),
                "why": "Defines cancellation/refund rules used by the agent.",
            },
            {
                "path": str(AIRLINE_SOURCE_DIR / "tools.py"),
                "why": "Defines get_reservation_details as a read tool and cancel_reservation as a write tool.",
            },
        ],
    }


def runtime_coverage(events: list[dict[str, Any]], final_state: dict[str, Any]) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    observed = set(str(event_type) for event_type in event_types)
    families = [RUNTIME_EVENT_FAMILIES.get(str(event_type), "unknown") for event_type in event_types]
    return {
        "total_events": len(events),
        "event_counts": counter_dict(event_types),
        "event_families": counter_dict(families),
        "observed_event_types": sorted(observed),
        "known_event_types_missing_from_run": [event_type for event_type in sorted(RUNTIME_EVENT_FAMILIES) if event_type not in observed],
        "unknown_event_type_count": sum(1 for family in families if family == "unknown"),
        "final_state_event_counts_match_jsonl": final_state.get("event_counts") == counter_dict(event_types),
        "captures_better_than_postrun_results": [
            "Per-event ordering and timestamps across turn, tool, and evaluation phases.",
            "Tool dispatch boundaries, arguments, result payloads, and state hashes before/after dispatch.",
            "Agent/user generation events and role-to-role message flow, not just final messages.",
            "Evidence that the only tool call was read-only and no state hash changed before evaluation.",
        ],
        "remaining_airline_instrumentation_gaps": [
            "Tool events do not carry task_id on environment/toolkit dispatch events in this run, so they must be associated by order/context.",
            "The trace records state hashes but not a structured DB diff for unchanged/no-write airline cases.",
            "Post-run reward output does not include detailed LLM-judge text for the communicate assertion when communicate_info is empty.",
            "Policy-rule decisions are inferred from dialogue/tool data; there is no explicit runtime event for refund-rule rationale.",
        ],
    }


def build_report(run_dir: pathlib.Path, output_dir: pathlib.Path) -> dict[str, Any]:
    runtime_events_path = run_dir / "runtime_events.jsonl"
    final_state_path = run_dir / "runtime_trace_final_state.json"
    runtime_summary_path = run_dir / "runtime_trace_summary.md"
    results_path = result_path(run_dir)
    raw_log_path = run_dir / "raw.log"
    tasks_path = AIRLINE_DATA_DIR / "tasks.json"
    db_path = AIRLINE_DATA_DIR / "db.json"
    policy_path = AIRLINE_DATA_DIR / "policy.md"
    tools_path = AIRLINE_SOURCE_DIR / "tools.py"
    for path, label in (
        (runtime_events_path, "runtime events"),
        (final_state_path, "runtime final state"),
        (runtime_summary_path, "runtime trace summary"),
        (results_path, "tau2 results"),
        (raw_log_path, "raw log"),
        (tasks_path, "airline tasks"),
        (db_path, "airline db"),
        (policy_path, "airline policy"),
        (tools_path, "airline tools source"),
    ):
        require_file(path, label)

    events = load_jsonl(runtime_events_path)
    final_state = load_json(final_state_path)
    results = load_json(results_path)
    db = load_json(db_path)
    sim = first_simulation(results)
    task_id = str(sim.get("task_id") or "0")
    task = load_task(tasks_path, task_id)
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
    initial_reservation = nested_get(db, ["reservations", "EHGLP3"], {})
    coverage = runtime_coverage(events, final_state)
    tool_path = tool_timeline(events, messages)
    scoring = scoring_evidence(sim, task, events, initial_reservation)
    costs = token_cost_summary(messages, sim)
    event_counts = coverage["event_counts"]
    reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else {}
    analysis_boundaries = {
        "offline_analysis_only": True,
        "tau2_rerun_performed_by_analysis": False,
        "model_backed_episode_run_by_analysis": False,
        "llm_api_calls_made_by_analysis": False,
        "requires_api_keys": False,
        "vendor_tau2_bench_mutated_by_analysis": False,
        "activegraph_control_added": False,
        "original_run_paid_llm_api_calls_made": final_state.get("paid_llm_api_calls_made"),
        "original_run_tau2_executed": final_state.get("tau2_executed"),
    }
    status = STATUS_PASSED if reward_info.get("reward") == 1.0 and db_check.get("db_match") is True and sim.get("termination_reason") == "user_stop" else STATUS_WITH_GAPS
    return {
        "status": status,
        "generated_at_utc": utc_now(),
        "title": "First successful airline runtime-traced baseline analysis",
        "inputs": {
            "runtime_run_dir": rel(run_dir),
            "runtime_events": rel(runtime_events_path),
            "runtime_trace_final_state": rel(final_state_path),
            "runtime_trace_summary": rel(runtime_summary_path),
            "tau2_results": rel(results_path),
            "raw_log": rel(raw_log_path),
            "airline_tasks": rel(tasks_path),
            "airline_db": rel(db_path),
            "airline_policy": rel(policy_path),
            "airline_tools_source": rel(tools_path),
            "artifact_hashes": {
                rel(runtime_events_path): sha256(runtime_events_path),
                rel(final_state_path): sha256(final_state_path),
                rel(results_path): sha256(results_path),
                rel(raw_log_path): sha256(raw_log_path),
                rel(tasks_path): sha256(tasks_path),
                rel(db_path): sha256(db_path),
                rel(policy_path): sha256(policy_path),
                rel(tools_path): sha256(tools_path),
            },
        },
        "analysis_boundaries": analysis_boundaries,
        "run_configuration": {
            "provider": "openai" if "openai/" in str(nested_get(results, ["info", "agent_info", "llm"], "")) else None,
            "agent_model": nested_get(results, ["info", "agent_info", "llm"]),
            "user_model": nested_get(results, ["info", "user_info", "llm"]),
            "domain": nested_get(results, ["info", "environment_info", "domain_name"]),
            "num_trials": nested_get(results, ["info", "num_trials"]),
            "max_steps": nested_get(results, ["info", "max_steps"]),
            "task_selection": final_state.get("task_selection_mode"),
            "tau2_command_display": final_state.get("tau2_command_display"),
        },
        "task_reward_summary": {
            "task_id": task_id,
            "simulation_id": sim.get("id"),
            "trial": sim.get("trial"),
            "seed": sim.get("seed"),
            "duration_seconds": sim.get("duration"),
            "termination_reason": sim.get("termination_reason"),
            "normal_stop": sim.get("termination_reason") == "user_stop",
            "reward": reward_info.get("reward"),
            "db_match": db_check.get("db_match"),
            "db_reward": db_check.get("db_reward"),
            "reward_basis": reward_info.get("reward_basis"),
            "reward_breakdown": reward_info.get("reward_breakdown"),
            "action_checks": reward_info.get("action_checks"),
            "nl_assertions": reward_info.get("nl_assertions"),
            "communicate_checks": reward_info.get("communicate_checks"),
        },
        "domain_evidence": domain_evidence(task, db),
        "turn_path_summary": {
            "message_count": len(messages),
            "message_roles": counter_dict([m.get("role") for m in messages if isinstance(m, dict)]),
            "agent_user_turns": [row for row in message_timeline(messages) if row.get("role") in {"assistant", "user"}],
            "conversation_outcome": "Agent declined refund-eligible cancellation, user chose not to cancel, and user simulator emitted ###STOP###.",
        },
        "tool_path_summary": {
            "tool_call_count": tool_path["tool_call_count_from_messages"],
            "tool_names": counter_dict([call.get("name") for call in tool_path["tool_calls_from_messages"] if call.get("name")]),
            "read_tool_call_count": len(tool_path["read_tool_calls"]),
            "write_tool_call_count": len(tool_path["write_tool_calls"]),
            "state_hash_change_count": len(tool_path["state_hash_changes"]),
        },
        "runtime_trace_coverage": coverage,
        "cost_and_token_summary": costs,
        "scoring_evidence": scoring,
        "event_type_coverage": {
            "event_count": len(events),
            "event_counts": event_counts,
            "agent_response_events": event_counts.get("agent_response", 0),
            "user_response_events": event_counts.get("user_response", 0),
            "tool_execution_events": sum(event_counts.get(name, 0) for name in ("tool_call_requested", "tool_dispatch_start", "tool_dispatch_end", "toolkit_dispatch_start", "toolkit_dispatch_end")),
            "evaluation_events": sum(event_counts.get(name, 0) for name in ("evaluation_start", "evaluation_end")),
        },
    }


def markdown_summary(report: dict[str, Any]) -> str:
    task = report["task_reward_summary"]
    tool = report["tool_path_summary"]
    coverage = report["runtime_trace_coverage"]
    costs = report["cost_and_token_summary"]
    domain = report["domain_evidence"]["airline_task"]
    return "\n".join(
        [
            "# Airline runtime-traced baseline analysis",
            "",
            f"- Status: `{report['status']}`",
            f"- Runtime run inspected: `{report['inputs']['runtime_run_dir']}`",
            f"- Task: `{task['task_id']}` — {domain.get('purpose')}",
            f"- Reward: `{task['reward']}`; DB match: `{task['db_match']}`; DB reward: `{task['db_reward']}`; termination: `{task['termination_reason']}`.",
            f"- Runtime events: `{coverage['total_events']}` across `{len(coverage['observed_event_types'])}` event types.",
            f"- Tool path: `{tool['tool_call_count']}` call(s), `{tool['read_tool_call_count']}` read, `{tool['write_tool_call_count']}` write, `{tool['state_hash_change_count']}` state-hash changes.",
            f"- Cost: agent `${costs['agent_cost_reported']:.6f}`, user `${costs['user_cost_reported']:.6f}`, total `${costs['total_cost_reported']:.6f}`.",
            f"- Tokens from messages: `{costs['from_messages']['total']['total_tokens']}` total (`{costs['from_messages']['total']['prompt_tokens']}` prompt, `{costs['from_messages']['total']['completion_tokens']}` completion).",
            "",
            "## Task goal and outcome",
            "",
            f"- Reason for call: {markdown_field(domain.get('reason_for_call'))}",
            f"- Known info: {markdown_field(domain.get('known_info'))}",
            f"- Task instructions: {markdown_field(domain.get('task_instructions'))}",
            "- The agent used `get_reservation_details` to verify reservation EHGLP3, explained that the current reservation had no insurance and basic-economy/change-of-plan cancellation did not qualify for a refund, and did not call a cancellation/write tool.",
            "- The user declined to cancel without a refund and ended with `###STOP###`, matching the expected refusal/no-write behavior.",
            "",
            "## Runtime trace coverage",
            "",
            *[f"- `{name}`: {count}" for name, count in coverage["event_counts"].items()],
            "",
            "## What runtime trace captures beyond post-run results",
            "",
            *[f"- {item}" for item in coverage["captures_better_than_postrun_results"]],
            "",
            "## Remaining airline instrumentation gaps",
            "",
            *[f"- {item}" for item in coverage["remaining_airline_instrumentation_gaps"]],
            "",
            "## Offline boundary",
            "",
            "- This analysis did not rerun tau2, did not run another model-backed episode, did not call LLM/API services, did not require API keys, and did not mutate `vendor/tau2-bench`.",
        ]
    ) + "\n"


def markdown_field(value: Any) -> str:
    if value is None:
        return ""
    return "\n".join(line.rstrip() for line in str(value).strip().splitlines())


def final_state_from_report(report: dict[str, Any]) -> dict[str, Any]:
    task = report["task_reward_summary"]
    return {
        "status": report["status"],
        "generated_at_utc": report["generated_at_utc"],
        "runtime_run_dir": report["inputs"]["runtime_run_dir"],
        "task_id": task["task_id"],
        "reward": task["reward"],
        "db_match": task["db_match"],
        "termination_reason": task["termination_reason"],
        "event_count": report["runtime_trace_coverage"]["total_events"],
        "tool_call_count": report["tool_path_summary"]["tool_call_count"],
        "write_tool_call_count": report["tool_path_summary"]["write_tool_call_count"],
        "analysis_boundaries": report["analysis_boundaries"],
        "outputs": [
            "airline_baseline_analysis.json",
            "airline_baseline_summary.md",
            "airline_task_timeline.json",
            "airline_tool_timeline.json",
            "airline_scoring_evidence.json",
            "final_state.json",
            "raw.log",
        ],
    }


def write_outputs(run_dir: pathlib.Path, output_dir: pathlib.Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = load_json(result_path(run_dir))
    sim = first_simulation(results)
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
    events = load_jsonl(run_dir / "runtime_events.jsonl")
    write_json(output_dir / "airline_baseline_analysis.json", report)
    (output_dir / "airline_baseline_summary.md").write_text(markdown_summary(report), encoding="utf-8")
    write_json(output_dir / "airline_task_timeline.json", task_timeline(events, messages))
    write_json(output_dir / "airline_tool_timeline.json", tool_timeline(events, messages))
    write_json(output_dir / "airline_scoring_evidence.json", report["scoring_evidence"])
    write_json(output_dir / "final_state.json", final_state_from_report(report))
    shutil.copyfile(run_dir / "raw.log", output_dir / "raw.log")


def main() -> int:
    args = parse_args()
    run_dir = args.runtime_run_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir is not None else run_dir / OUTPUT_DIR_NAME
    try:
        report = build_report(run_dir, output_dir)
        write_outputs(run_dir, output_dir, report)
    except Exception as exc:  # noqa: BLE001 - produces inspectable offline failure artifact.
        output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at_utc": utc_now(),
            "error": str(exc),
            "analysis_boundaries": {
                "offline_analysis_only": True,
                "tau2_rerun_performed_by_analysis": False,
                "model_backed_episode_run_by_analysis": False,
                "llm_api_calls_made_by_analysis": False,
                "requires_api_keys": False,
                "vendor_tau2_bench_mutated_by_analysis": False,
            },
        }
        write_json(output_dir / "final_state.json", failure)
        (output_dir / "raw.log").write_text(f"status={STATUS_INPUTS_MISSING}\nerror={exc}\n", encoding="utf-8")
        print(f"analysis_status={STATUS_INPUTS_MISSING}")
        print(f"error={exc}")
        return 2
    print(rel(output_dir))
    print(report["status"])
    print(f"task_id={report['task_reward_summary']['task_id']} reward={report['task_reward_summary']['reward']} db_match={report['task_reward_summary']['db_match']}")
    return 0 if report["status"] in {STATUS_PASSED, STATUS_WITH_GAPS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
