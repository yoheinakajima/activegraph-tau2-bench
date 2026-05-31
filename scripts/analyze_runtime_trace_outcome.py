#!/usr/bin/env python3
"""Classify and summarize a runtime-traced tau2 baseline outcome offline.

The analyzer reads existing run artifacts only. It does not import tau2, launch
another episode, call LLM/API services, require API keys, mutate vendor/tau2-bench,
or add ActiveGraph control over tau2.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS_PASSED = "runtime_trace_outcome_analysis_passed"
STATUS_WITH_GAPS = "runtime_trace_outcome_analysis_completed_with_gaps"
STATUS_INPUTS_MISSING = "runtime_trace_outcome_analysis_inputs_missing"

WRITE_PREFIXES = ("create_", "update_", "delete_")
OUTCOME_CLASSES = {
    "success",
    "failed_no_write",
    "failed_partial_progress",
    "failed_max_steps",
    "failed_unknown",
}

RUNTIME_EVENT_FAMILIES = {
    "trace_bootstrap_start": "run_lifecycle",
    "trace_bootstrap_end": "run_lifecycle",
    "batch_start": "run_lifecycle",
    "batch_end": "run_lifecycle",
    "result_persistence_start": "result_persistence",
    "result_persistence_end": "result_persistence",
    "simulation_start": "simulation_lifecycle",
    "simulation_end": "simulation_lifecycle",
    "simulation_execution_start": "simulation_lifecycle",
    "simulation_execution_end": "simulation_lifecycle",
    "orchestrator_run_start": "orchestrator_lifecycle",
    "orchestrator_run_end": "orchestrator_lifecycle",
    "turn_start": "turn_lifecycle",
    "turn_end": "turn_lifecycle",
    "user_generate_start": "message_generation",
    "user_generate_end": "message_generation",
    "user_response": "message_observed",
    "agent_response": "message_observed",
    "message_observed": "message_observed",
    "tool_call_requested": "tool_execution",
    "tool_dispatch_start": "tool_execution",
    "tool_dispatch_end": "tool_execution",
    "toolkit_dispatch_start": "tool_execution",
    "toolkit_dispatch_end": "tool_execution",
    "evaluation_start": "evaluation",
    "evaluation_end": "evaluation",
}

POSTRUN_TO_RUNTIME_FAMILIES = {
    "baseline.run.started": "run_lifecycle",
    "baseline.run.completed": "run_lifecycle",
    "baseline.config.loaded": "configuration",
    "baseline.task.started": "simulation_lifecycle",
    "baseline.message.observed": "message_observed",
    "baseline.tool.requested": "tool_execution",
    "baseline.tool.completed": "tool_execution",
    "baseline.evaluation.observed": "evaluation",
    "baseline.result.persisted": "result_persistence",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-classify a runtime-traced tau2 baseline as success, no-write failure, partial-progress failure, max-steps failure, or unknown failure."
    )
    parser.add_argument("--runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--reference-success-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--postrun-baseline-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Defaults to <runtime-run-dir>/runtime_outcome_analysis/.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def sha256(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_optional(path: pathlib.Path) -> Any | None:
    if not path.is_file():
        return None
    return load_json(path)


def load_text_optional(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{rel(path)} line {line_number} is invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise RuntimeError(f"{rel(path)} line {line_number} is not a JSON object")
        row = dict(row)
        row["_sequence"] = line_number
        rows.append(row)
    return rows


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing required {label}: {rel(path)}")


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def payload(event: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    raw = event.get("payload")
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("runtime_trace")
    return nested if isinstance(nested, dict) else raw


def counter_dict(values: list[Any]) -> dict[str, int]:
    return dict(sorted(collections.Counter(str(value) for value in values).items()))


def first_simulation(results: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(results, dict):
        return {}
    simulations = results.get("simulations")
    if isinstance(simulations, list) and simulations and isinstance(simulations[0], dict):
        return simulations[0]
    return {}


def result_path(run_dir: pathlib.Path) -> pathlib.Path:
    for candidate in (run_dir / "tau2_output" / "results.json", run_dir / "tau2_artifacts" / "results.json"):
        if candidate.is_file():
            return candidate
    return run_dir / "tau2_output" / "results.json"


def summarize_results(results: dict[str, Any] | None) -> dict[str, Any]:
    sim = first_simulation(results)
    info = results.get("info", {}) if isinstance(results, dict) else {}
    reward = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    db_check = reward.get("db_check") if isinstance(reward.get("db_check"), dict) else None
    action_checks = reward.get("action_checks") if isinstance(reward.get("action_checks"), list) else []
    write_actions = [a for a in action_checks if isinstance(a, dict) and a.get("tool_type") == "write"]
    matched_write_actions = [a for a in write_actions if a.get("action_match") is True]
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
    tool_calls: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                tool_calls.append(
                    {
                        "turn_idx": message.get("turn_idx"),
                        "name": call.get("name"),
                        "arguments": call.get("arguments"),
                        "requestor": call.get("requestor"),
                        "id": call.get("id"),
                    }
                )
    return {
        "run_info": {
            "provider_model": info.get("agent_info", {}).get("llm") if isinstance(info.get("agent_info"), dict) else None,
            "max_steps": info.get("max_steps") if isinstance(info, dict) else None,
            "num_trials": info.get("num_trials") if isinstance(info, dict) else None,
        },
        "simulation_id": sim.get("id"),
        "task_id": sim.get("task_id"),
        "termination_reason": sim.get("termination_reason"),
        "duration_seconds": sim.get("duration"),
        "agent_cost": sim.get("agent_cost"),
        "user_cost": sim.get("user_cost"),
        "reward": reward.get("reward"),
        "db_match": db_check.get("db_match") if isinstance(db_check, dict) else None,
        "db_reward": db_check.get("db_reward") if isinstance(db_check, dict) else None,
        "action_checks_total": len(action_checks),
        "write_actions_total": len(write_actions),
        "write_actions_matched": len(matched_write_actions),
        "write_action_names": [
            (check.get("action") or {}).get("name")
            for check in write_actions
            if isinstance(check.get("action"), dict) and (check.get("action") or {}).get("name")
        ],
        "normal_stop": sim.get("termination_reason") == "user_stop",
        "agent_errors": 0 if sim else None,
        "user_errors": 0 if sim else None,
        "message_count": len(messages),
        "message_roles": [m.get("role") for m in messages if isinstance(m, dict)],
        "tool_calls_from_messages": tool_calls,
    }


def is_write_tool_name(tool_name: Any, expected_write_names: set[str]) -> bool:
    if not isinstance(tool_name, str) or not tool_name:
        return False
    return tool_name in expected_write_names or tool_name.startswith(WRITE_PREFIXES)


def parse_tool_content(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def tool_result_payload(event: dict[str, Any]) -> Any:
    p = payload(event)
    if "result" in p:
        return p.get("result")
    response = p.get("response")
    if isinstance(response, dict):
        raw = response.get("raw")
        if isinstance(raw, dict) and "content" in raw:
            return parse_tool_content(raw.get("content"))
        if "content_preview" in response:
            return parse_tool_content(response.get("content_preview"))
    return None


def evaluation_start_sequence(events: list[dict[str, Any]]) -> int | None:
    return next((int(event["_sequence"]) for event in events if event.get("event_type") == "evaluation_start"), None)


def evidence_from_events(events: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    eval_start = evaluation_start_sequence(events)
    expected_write_names = {str(name) for name in metrics.get("write_action_names", []) if name}
    if not expected_write_names:
        expected_write_names = {
            str(event.get("tool_name"))
            for event in events
            if is_write_tool_name(event.get("tool_name"), set())
        }

    def before_eval(event: dict[str, Any]) -> bool:
        return eval_start is None or int(event["_sequence"]) < eval_start

    live_write_events = [
        event
        for event in events
        if before_eval(event) and is_write_tool_name(event.get("tool_name"), expected_write_names)
    ]
    live_write_dispatch_starts = [event for event in live_write_events if event.get("event_type") == "tool_dispatch_start"]
    live_write_dispatch_ends = [event for event in live_write_events if event.get("event_type") == "tool_dispatch_end"]
    evaluation_write_events = [
        event
        for event in events
        if eval_start is not None
        and int(event["_sequence"]) > eval_start
        and is_write_tool_name(event.get("tool_name"), expected_write_names)
    ]

    state_hash_changes: list[dict[str, Any]] = []
    tool_result_payloads: list[Any] = []
    for event in live_write_events:
        p = payload(event)
        before = p.get("state_hash_before") or event.get("state_hash")
        after = p.get("state_hash_after")
        if before and after and before != after:
            state_hash_changes.append(
                {
                    "event_id": event.get("event_id"),
                    "tool_name": event.get("tool_name"),
                    "state_hash_before": before,
                    "state_hash_after": after,
                }
            )
        result = tool_result_payload(event)
        if result is not None:
            tool_result_payloads.append(result)

    live_write_tools = sorted({str(event.get("tool_name")) for event in live_write_dispatch_starts if event.get("tool_name")})
    result_object_ids = sorted(
        {
            str(result[key])
            for result in tool_result_payloads
            if isinstance(result, dict)
            for key in ("task_id", "id", "user_id")
            if key in result and result.get(key) is not None
        }
    )
    return {
        "evaluation_start_sequence": eval_start,
        "expected_write_tool_names": sorted(expected_write_names),
        "live_write_tool_detected_before_evaluation": bool(live_write_dispatch_starts),
        "live_write_dispatch_count_before_evaluation": len(live_write_dispatch_starts),
        "live_write_dispatch_end_count_before_evaluation": len(live_write_dispatch_ends),
        "live_write_tools_before_evaluation": live_write_tools,
        "live_write_event_ids_before_evaluation": [event.get("event_id") for event in live_write_events],
        "evaluation_write_event_count": len(evaluation_write_events),
        "evaluation_write_event_ids": [event.get("event_id") for event in evaluation_write_events],
        "state_hash_changed_during_live_write": bool(state_hash_changes),
        "state_hash_changes": state_hash_changes,
        "tool_result_payloads_observed": tool_result_payloads,
        "tool_result_payload_count": len(tool_result_payloads),
        "result_object_ids": result_object_ids,
        "mutation_evidence_present": bool(live_write_dispatch_starts or state_hash_changes or tool_result_payloads),
    }


def classify_task_outcome(metrics: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    reward = metrics.get("reward")
    db_match = metrics.get("db_match")
    write_total = metrics.get("write_actions_total") or 0
    write_matched = metrics.get("write_actions_matched") or 0
    normal_stop = metrics.get("normal_stop") is True
    termination_reason = metrics.get("termination_reason")
    success = reward == 1.0 and db_match is True and (write_total == 0 or write_matched == write_total) and normal_stop
    no_live_write = not evidence.get("live_write_tool_detected_before_evaluation")
    mutation_evidence = evidence.get("mutation_evidence_present") is True
    max_steps = termination_reason == "max_steps"

    reasons: list[str] = []
    if success:
        outcome = "success"
        reasons.append("reward is 1.0, DB match is true, expected write actions matched, and the episode stopped normally")
    elif write_total > 0 and write_matched == 0 and normal_stop and no_live_write:
        outcome = "failed_no_write"
        reasons.append("an expected write action existed but no live write tool dispatch was detected before evaluation")
    elif mutation_evidence and (reward != 1.0 or db_match is not True or (write_total > 0 and write_matched < write_total) or not normal_stop):
        outcome = "failed_partial_progress"
        reasons.append("live mutation evidence was present, but benchmark success criteria were not satisfied")
    elif max_steps:
        outcome = "failed_max_steps"
        reasons.append("the run terminated by max_steps before satisfying benchmark success criteria")
    else:
        outcome = "failed_unknown"
        reasons.append("the available reward, DB, action, stop, and mutation evidence did not match a more specific failure class")

    if max_steps and outcome != "success":
        reasons.append("termination_reason=max_steps indicates premature termination")
    if db_match is False:
        reasons.append("DB match is false")
    elif db_match is None:
        reasons.append("DB match was not checked or not present")
    if reward != 1.0:
        reasons.append(f"reward is {reward!r}, not 1.0")
    if write_total and write_matched < write_total:
        reasons.append(f"write actions matched {write_matched}/{write_total}")

    return {
        "task_outcome": outcome,
        "outcome_is_success": outcome == "success",
        "classification_reasons": reasons,
        "classification_inputs": {
            "reward": reward,
            "db_match": db_match,
            "db_reward": metrics.get("db_reward"),
            "write_actions_matched": write_matched,
            "write_actions_total": write_total,
            "normal_stop": normal_stop,
            "termination_reason": termination_reason,
            "live_write_tool_detected_before_evaluation": evidence.get("live_write_tool_detected_before_evaluation"),
            "state_hash_changed_during_live_write": evidence.get("state_hash_changed_during_live_write"),
            "tool_result_payload_count": evidence.get("tool_result_payload_count"),
            "mutation_evidence_present": mutation_evidence,
        },
        "rules": {
            "success": "reward == 1.0 and db_match is true and expected write actions match and normal_stop is true",
            "failed_no_write": "expected write action exists, no live write dispatch before evaluation, normal_stop is true, and success criteria fail",
            "failed_partial_progress": "live mutation evidence exists, but reward/DB/action/stop criteria fail",
            "failed_max_steps": "termination_reason is max_steps and no more specific mutation/no-write failure class applies",
            "failed_unknown": "fallback for incomplete or conflicting evidence",
        },
    }


def runtime_summary(run_dir: pathlib.Path, events: list[dict[str, Any]], final_state: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    roles = [event.get("message_role") for event in events if event.get("message_role")]
    families = [RUNTIME_EVENT_FAMILIES.get(str(event_type), "unknown") for event_type in event_types]
    metrics = summarize_results(results)
    evidence = evidence_from_events(events, metrics)
    return {
        "run_dir": rel(run_dir),
        "event_count": len(events),
        "event_counts": counter_dict(event_types),
        "event_families": counter_dict(families),
        "message_roles_observed": counter_dict(roles),
        "turn_indexes": sorted({event.get("turn_index") for event in events if event.get("turn_index") is not None}),
        "tool_names": counter_dict([event.get("tool_name") for event in events if event.get("tool_name")]),
        "results": metrics,
        "mutation_evidence": evidence,
        "final_state_flags": {
            "status": final_state.get("status"),
            "tau2_executed": final_state.get("tau2_executed"),
            "paid_llm_api_calls_made_in_original_run": final_state.get("paid_llm_api_calls_made"),
            "activegraph_controlled_tau2": final_state.get("activegraph_controlled_tau2"),
            "state_packets_fed_back_to_tau2": final_state.get("state_packets_fed_back_to_tau2"),
            "returncode": final_state.get("returncode"),
        },
    }


def postrun_summary(run_dir: pathlib.Path, events: list[dict[str, Any]], final_state: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    families = [POSTRUN_TO_RUNTIME_FAMILIES.get(str(event_type), "unknown") for event_type in event_types]
    return {
        "run_dir": rel(run_dir),
        "event_count": len(events),
        "event_counts": counter_dict(event_types),
        "event_families": counter_dict(families),
        "tool_names": counter_dict([event.get("tool_name") for event in events if event.get("tool_name")]),
        "results": summarize_results(results),
        "final_state_flags": {
            "status": final_state.get("status"),
            "fixture_backed": final_state.get("fixture_backed"),
            "tau2_rerun": final_state.get("tau2_rerun"),
            "llm_api_calls_made_by_extractor": final_state.get("llm_api_calls_made_by_extractor"),
        },
        "limitations": final_state.get("limitations", []),
    }


def diff_counts(left: dict[str, int], right: dict[str, int], left_label: str, right_label: str) -> dict[str, dict[str, int]]:
    keys = sorted(set(left) | set(right))
    return {
        key: {left_label: left.get(key, 0), right_label: right.get(key, 0), "delta": left.get(key, 0) - right.get(key, 0)}
        for key in keys
    }


def artifact_inconsistencies(summary_text: str | None, hook_map: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if summary_text and "/Users/" in summary_text:
        issues.append(
            {
                "severity": "reporting_only",
                "artifact": "runtime_trace_summary.md",
                "issue": "Summary embeds an absolute local macOS path for runtime_events/command output.",
                "resolution": "Flagged in analysis; generated reports use repository-relative paths.",
            }
        )
    repo_root = hook_map.get("repo_root")
    if isinstance(repo_root, str) and repo_root.startswith("/Users/"):
        issues.append(
            {
                "severity": "reporting_only",
                "artifact": "runtime_hook_map.json",
                "issue": "Hook map records the source machine's absolute repo_root.",
                "resolution": "Flagged in analysis; no vendored code or source artifact was mutated.",
            }
        )
    return issues


def compact_path_event(event: dict[str, Any]) -> dict[str, Any]:
    p = payload(event)
    message = p.get("message") if isinstance(p.get("message"), dict) else {}
    response = p.get("response") if isinstance(p.get("response"), dict) else {}
    result = tool_result_payload(event)
    return {
        "sequence": event.get("_sequence"),
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "component": event.get("component"),
        "turn_index": event.get("turn_index"),
        "role": event.get("message_role") or message.get("role") or response.get("role"),
        "tool_name": event.get("tool_name"),
        "content_preview": p.get("content_preview") or message.get("content_preview") or response.get("content_preview"),
        "status": p.get("status"),
        "state_hash": event.get("state_hash"),
        "state_hash_before": p.get("state_hash_before"),
        "state_hash_after": p.get("state_hash_after"),
        "result_payload": result,
    }


def build_completion_or_failure_path(events: list[dict[str, Any]], metrics: dict[str, Any], classification: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    interesting = {
        "turn_start",
        "user_response",
        "agent_response",
        "tool_call_requested",
        "message_observed",
        "tool_dispatch_start",
        "tool_dispatch_end",
        "toolkit_dispatch_start",
        "toolkit_dispatch_end",
        "evaluation_start",
        "evaluation_end",
        "orchestrator_run_end",
    }
    path_events = [compact_path_event(event) for event in events if event.get("event_type") in interesting]
    outcome = classification["task_outcome"]
    expected = evidence.get("expected_write_tool_names") or []
    live = evidence.get("live_write_tools_before_evaluation") or []
    result_ids = evidence.get("result_object_ids") or []
    summary: list[str]
    if outcome == "success":
        summary = [
            "The runtime path completed successfully.",
            f"The run stopped normally with reward={metrics.get('reward')!r}, db_match={metrics.get('db_match')!r}, and write actions {metrics.get('write_actions_matched')}/{metrics.get('write_actions_total')}.",
            f"Live write tools before evaluation: {', '.join(live) if live else 'none recorded'}.",
        ]
    elif outcome == "failed_no_write":
        summary = [
            "The intended mutation was absent from the live runtime path.",
            f"Expected write tools from reward action checks: {', '.join(expected) if expected else 'none recorded'}.",
            "No live write tool dispatch was detected before evaluation, so the benchmark failed despite a normal stop.",
        ]
    elif outcome == "failed_partial_progress":
        summary = [
            "The runtime trace contains mutation evidence, but the benchmark result failed.",
            f"Live write tools before evaluation: {', '.join(live) if live else 'none recorded'}.",
            f"Observed result object IDs: {', '.join(result_ids) if result_ids else 'none recorded'}.",
        ]
    elif outcome == "failed_max_steps":
        summary = [
            "The episode terminated prematurely at max_steps before satisfying benchmark success criteria.",
            f"Live write tools before evaluation: {', '.join(live) if live else 'none recorded'}.",
        ]
    else:
        summary = [
            "The run failed, but available runtime evidence did not identify a more specific failure path.",
            f"Reward={metrics.get('reward')!r}, db_match={metrics.get('db_match')!r}, termination_reason={metrics.get('termination_reason')!r}.",
        ]
    if metrics.get("termination_reason") == "max_steps" and outcome != "success":
        summary.append("Premature termination is explicitly present: termination_reason=max_steps.")
    return {
        "status": "completed" if outcome == "success" else "failed",
        "task_outcome": outcome,
        "summary": summary,
        "metrics": metrics,
        "mutation_evidence": evidence,
        "events": path_events,
    }


def build_report(args: argparse.Namespace, output_dir: pathlib.Path) -> dict[str, Any]:
    run_dir = args.runtime_run_dir.resolve()
    reference_dir = args.reference_success_run_dir.resolve()
    postrun_dir = args.postrun_baseline_dir.resolve()

    run_events_path = run_dir / "runtime_events.jsonl"
    run_final_path = run_dir / "runtime_trace_final_state.json"
    run_results_path = result_path(run_dir)
    hook_path = run_dir / "runtime_hook_map.json"
    reference_events_path = reference_dir / "runtime_events.jsonl"
    reference_final_path = reference_dir / "runtime_trace_final_state.json"
    reference_results_path = result_path(reference_dir)
    postrun_events_path = postrun_dir / "extracted_trace" / "baseline_trace.jsonl"
    postrun_final_path = postrun_dir / "extracted_trace" / "baseline_trace_final_state.json"
    postrun_results_path = result_path(postrun_dir)

    for path, label in [
        (run_events_path, "runtime events"),
        (run_final_path, "runtime final state"),
        (run_results_path, "runtime tau2 results"),
        (hook_path, "runtime hook map"),
        (reference_events_path, "reference success runtime events"),
        (reference_final_path, "reference success runtime final state"),
        (reference_results_path, "reference success tau2 results"),
        (postrun_events_path, "post-run extracted events"),
        (postrun_final_path, "post-run extracted final state"),
        (postrun_results_path, "post-run tau2 results"),
    ]:
        require_file(path, label)

    run_events = load_jsonl(run_events_path)
    run_final = load_json(run_final_path)
    run_results = load_json(run_results_path)
    hook_map = load_json(hook_path)
    reference = runtime_summary(reference_dir, load_jsonl(reference_events_path), load_json(reference_final_path), load_json(reference_results_path))
    runtime = runtime_summary(run_dir, run_events, run_final, run_results)
    postrun = postrun_summary(postrun_dir, load_jsonl(postrun_events_path), load_json(postrun_final_path), load_json(postrun_results_path))
    classification = classify_task_outcome(runtime["results"], runtime["mutation_evidence"])
    if classification["task_outcome"] not in OUTCOME_CLASSES:
        raise RuntimeError(f"unexpected task_outcome: {classification['task_outcome']}")
    path = build_completion_or_failure_path(run_events, runtime["results"], classification, runtime["mutation_evidence"])
    issues = artifact_inconsistencies(load_text_optional(run_dir / "runtime_trace_summary.md"), hook_map)

    status = STATUS_PASSED if classification["task_outcome"] == "success" else STATUS_WITH_GAPS
    inputs = {
        "runtime_run_dir": rel(run_dir),
        "reference_success_run_dir": rel(reference_dir),
        "postrun_baseline_dir": rel(postrun_dir),
        "runtime_events_path": rel(run_events_path),
        "runtime_results_path": rel(run_results_path),
        "runtime_final_state_path": rel(run_final_path),
        "reference_success_events_path": rel(reference_events_path),
        "reference_success_results_path": rel(reference_results_path),
        "postrun_events_path": rel(postrun_events_path),
        "postrun_results_path": rel(postrun_results_path),
    }
    runtime_vs_reference = {
        "event_count_difference": {
            "runtime": runtime["event_count"],
            "reference_success": reference["event_count"],
            "delta": runtime["event_count"] - reference["event_count"],
        },
        "event_type_count_delta": diff_counts(runtime["event_counts"], reference["event_counts"], "runtime", "reference_success"),
        "metric_delta": {
            "runtime_task_id": runtime["results"].get("task_id"),
            "reference_task_id": reference["results"].get("task_id"),
            "runtime_reward": runtime["results"].get("reward"),
            "reference_reward": reference["results"].get("reward"),
            "runtime_db_match": runtime["results"].get("db_match"),
            "reference_db_match": reference["results"].get("db_match"),
            "runtime_write_actions": f"{runtime['results'].get('write_actions_matched')}/{runtime['results'].get('write_actions_total')}",
            "reference_write_actions": f"{reference['results'].get('write_actions_matched')}/{reference['results'].get('write_actions_total')}",
        },
    }
    runtime_vs_postrun = {
        "event_count_difference": {
            "runtime": runtime["event_count"],
            "postrun_extracted": postrun["event_count"],
            "delta": runtime["event_count"] - postrun["event_count"],
        },
        "family_coverage_delta": diff_counts(runtime["event_families"], postrun["event_families"], "runtime", "postrun_extracted"),
        "postrun_limitations_carried_forward": postrun.get("limitations", []),
    }
    generated = utc_now()
    return {
        "title": "runtime-traced tau2 baseline analysis",
        "status": status,
        "generated_at_utc": generated,
        "inputs": inputs,
        "input_hashes": {key: sha256(REPO_ROOT / value) for key, value in inputs.items() if value.endswith((".json", ".jsonl"))},
        "task_outcome": classification["task_outcome"],
        "metric_classification": classification,
        "runtime_trace": runtime,
        "reference_success_runtime_trace": reference,
        "postrun_trace": postrun,
        "completion_or_failure_path": path,
        "comparison_to_reference_success_run": runtime_vs_reference,
        "comparison_to_postrun_trace": runtime_vs_postrun,
        "artifact_reporting_inconsistencies": issues,
        "analysis_boundaries": {
            "tau2_rerun_performed_by_analysis": False,
            "model_backed_episode_run_by_analysis": False,
            "llm_api_calls_made_by_analysis": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_analysis": False,
            "activegraph_control_added": False,
        },
        "outputs": {
            "output_dir": rel(output_dir),
            "runtime_outcome_analysis": rel(output_dir / "runtime_outcome_analysis.json"),
            "runtime_outcome_summary": rel(output_dir / "runtime_outcome_summary.md"),
            "completion_or_failure_path": rel(output_dir / "completion_or_failure_path.json"),
            "metric_classification": rel(output_dir / "metric_classification.json"),
            "final_state": rel(output_dir / "final_state.json"),
            "raw_log": rel(output_dir / "raw.log"),
        },
    }


def format_bool(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def markdown_summary(report: dict[str, Any]) -> str:
    runtime = report["runtime_trace"]
    metrics = runtime["results"]
    evidence = runtime["mutation_evidence"]
    classification = report["metric_classification"]
    cmp_ref = report["comparison_to_reference_success_run"]["event_count_difference"]
    cmp_post = report["comparison_to_postrun_trace"]["event_count_difference"]
    reasons = "\n".join(f"- {reason}" for reason in classification["classification_reasons"])
    path_lines = "\n".join(f"- {item}" for item in report["completion_or_failure_path"]["summary"])
    issue_lines = "\n".join(
        f"- `{item['artifact']}`: {item['issue']} Resolution: {item['resolution']}"
        for item in report["artifact_reporting_inconsistencies"]
    ) or "- None found."
    return f"""# Runtime-traced tau2 baseline analysis

Status: `{report['status']}`

Task outcome: `{report['task_outcome']}`

Generated at: `{report['generated_at_utc']}`

## Inputs

- runtime run: `{report['inputs']['runtime_run_dir']}`
- reference success run: `{report['inputs']['reference_success_run_dir']}`
- post-run extracted baseline: `{report['inputs']['postrun_baseline_dir']}`

## Outcome classification

{reasons}

## Completion or failure path

{path_lines}

Detailed sequence is written to `completion_or_failure_path.json`.

## Metrics summary

- task id: `{metrics.get('task_id')}`
- termination reason: `{metrics.get('termination_reason')}`
- reward: `{metrics.get('reward')}`
- DB match: `{format_bool(metrics.get('db_match'))}`
- DB reward: `{metrics.get('db_reward')}`
- write actions matched: `{metrics.get('write_actions_matched')}/{metrics.get('write_actions_total')}`
- normal stop: `{format_bool(metrics.get('normal_stop'))}`
- live write tool before evaluation: `{format_bool(evidence.get('live_write_tool_detected_before_evaluation'))}`
- live write tools: `{', '.join(evidence.get('live_write_tools_before_evaluation') or []) or 'none'}`
- state hash changed during live write: `{format_bool(evidence.get('state_hash_changed_during_live_write'))}`
- tool result payload count: `{evidence.get('tool_result_payload_count')}`

## Comparison context

| Artifact | Event count |
| --- | ---: |
| Runtime run under analysis | {cmp_ref['runtime']} |
| Reference success runtime trace | {cmp_ref['reference_success']} |
| Post-run extracted baseline trace | {cmp_post['postrun_extracted']} |

The runtime run has `{cmp_ref['delta']}` events relative to the reference success run and `{cmp_post['delta']}` events relative to the post-run extracted trace.

## Reporting inconsistencies flagged

{issue_lines}

## Boundary

This analysis is offline. It did not rerun tau2, did not run a model-backed episode, did not call LLM/API services, did not require API keys, did not mutate `vendor/tau2-bench`, and did not add ActiveGraph control.
"""


def final_state_from_report(report: dict[str, Any]) -> dict[str, Any]:
    runtime = report["runtime_trace"]
    metrics = runtime["results"]
    evidence = runtime["mutation_evidence"]
    return {
        "status": report["status"],
        "generated_at_utc": report["generated_at_utc"],
        "title": report["title"],
        "task_outcome": report["task_outcome"],
        "runtime_run_dir": report["inputs"]["runtime_run_dir"],
        "metrics": metrics,
        "classification_inputs": report["metric_classification"]["classification_inputs"],
        "mutation_evidence": evidence,
        "activegraph_controlled_tau2": runtime["final_state_flags"].get("activegraph_controlled_tau2"),
        "state_packets_fed_back_to_tau2": runtime["final_state_flags"].get("state_packets_fed_back_to_tau2"),
        "tau2_executed_in_original_run": runtime["final_state_flags"].get("tau2_executed"),
        "paid_llm_api_calls_made_in_original_run": runtime["final_state_flags"].get("paid_llm_api_calls_made_in_original_run"),
        **report["analysis_boundaries"],
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve() if args.output_dir is not None else args.runtime_run_dir.resolve() / "runtime_outcome_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = build_report(args, output_dir)
    except Exception as exc:  # noqa: BLE001 - command-line artifact should capture diagnosable failures.
        final_state = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at_utc": utc_now(),
            "title": "runtime-traced tau2 baseline analysis",
            "error": str(exc),
            "analysis_boundaries": {
                "tau2_rerun_performed_by_analysis": False,
                "model_backed_episode_run_by_analysis": False,
                "llm_api_calls_made_by_analysis": False,
                "requires_api_keys": False,
                "vendor_tau2_bench_mutated_by_analysis": False,
                "activegraph_control_added": False,
            },
        }
        write_json(output_dir / "final_state.json", final_state)
        (output_dir / "raw.log").write_text(f"runtime-traced tau2 baseline analysis\nstatus={STATUS_INPUTS_MISSING}\nerror={exc}\n", encoding="utf-8")
        print(f"analysis_status={STATUS_INPUTS_MISSING}")
        print(f"error={exc}", file=sys.stderr)
        return 2

    write_json(output_dir / "runtime_outcome_analysis.json", report)
    (output_dir / "runtime_outcome_summary.md").write_text(markdown_summary(report), encoding="utf-8")
    write_json(output_dir / "completion_or_failure_path.json", report["completion_or_failure_path"])
    write_json(output_dir / "metric_classification.json", report["metric_classification"])
    final_state = final_state_from_report(report)
    write_json(output_dir / "final_state.json", final_state)
    raw_lines = [
        "runtime-traced tau2 baseline analysis",
        f"generated_at_utc={report['generated_at_utc']}",
        f"status={report['status']}",
        f"task_outcome={report['task_outcome']}",
        "offline_analysis=true",
        "tau2_rerun_performed_by_analysis=false",
        "model_backed_episode_run_by_analysis=false",
        "llm_api_calls_made_by_analysis=false",
        "requires_api_keys=false",
        "vendor_tau2_bench_mutated_by_analysis=false",
    ]
    (output_dir / "raw.log").write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    print(rel(output_dir))
    print(report["status"])
    print(f"task_outcome={report['task_outcome']}")
    return 0 if report["status"] in {STATUS_PASSED, STATUS_WITH_GAPS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
