#!/usr/bin/env python3
"""Analyze a full mock runtime-traced tau2 baseline run offline.

This script reads already-produced artifacts only. It does not import tau2, run
another model-backed episode, call LLM/API services, require API keys, mutate
vendor/tau2-bench, or add ActiveGraph control.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
from typing import Any

from analyze_runtime_trace_outcome import (
    RUNTIME_EVENT_FAMILIES,
    classify_task_outcome,
    counter_dict,
    evidence_from_events,
    load_json,
    load_jsonl,
    payload,
    rel,
    require_file,
    sha256,
    write_json,
)

STATUS_PASSED = "full_mock_runtime_baseline_analysis_passed"
STATUS_WITH_FAILURES = "full_mock_runtime_baseline_analysis_completed_with_failures"
STATUS_INPUTS_MISSING = "full_mock_runtime_baseline_analysis_inputs_missing"
OUTPUT_DIR_NAME = "full_mock_analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-analyze the committed full mock runtime-traced tau2 baseline run."
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
    return run_dir / "tau2_output" / "results.json"


def safe_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def action_check_summary(reward_info: dict[str, Any]) -> dict[str, Any]:
    checks = reward_info.get("action_checks") if isinstance(reward_info.get("action_checks"), list) else []
    write_checks = [check for check in checks if isinstance(check, dict) and check.get("tool_type") == "write"]
    matched = [check for check in checks if isinstance(check, dict) and check.get("action_match") is True]
    matched_writes = [check for check in write_checks if check.get("action_match") is True]
    return {
        "total": len(checks),
        "matched": len(matched),
        "failed": len(checks) - len(matched),
        "write_total": len(write_checks),
        "write_matched": len(matched_writes),
        "write_failed": len(write_checks) - len(matched_writes),
        "write_action_names": [
            check.get("action", {}).get("name")
            for check in write_checks
            if isinstance(check.get("action"), dict) and check.get("action", {}).get("name")
        ],
        "details": checks,
    }


def tool_calls_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                calls.append(
                    {
                        "turn_idx": message.get("turn_idx"),
                        "message_role": message.get("role"),
                        "id": call.get("id"),
                        "name": call.get("name"),
                        "requestor": call.get("requestor"),
                        "arguments": call.get("arguments"),
                    }
                )
    return calls


def compact_tool_event(event: dict[str, Any]) -> dict[str, Any]:
    p = payload(event)
    return {
        "sequence": event.get("_sequence"),
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "task_id": event.get("task_id"),
        "turn_index": event.get("turn_index"),
        "tool_name": event.get("tool_name"),
        "status": p.get("status"),
        "state_hash_before": p.get("state_hash_before"),
        "state_hash_after": p.get("state_hash_after"),
    }


def simulation_metrics(simulation: dict[str, Any]) -> dict[str, Any]:
    reward_info = simulation.get("reward_info") if isinstance(simulation.get("reward_info"), dict) else {}
    db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else None
    action_summary = action_check_summary(reward_info)
    messages = simulation.get("messages") if isinstance(simulation.get("messages"), list) else []
    agent_cost = simulation.get("agent_cost")
    user_cost = simulation.get("user_cost")
    total_cost = None
    if isinstance(agent_cost, (int, float)) or isinstance(user_cost, (int, float)):
        total_cost = (agent_cost or 0) + (user_cost or 0)
    return {
        "simulation_id": simulation.get("id"),
        "task_id": simulation.get("task_id"),
        "trial": simulation.get("trial"),
        "seed": simulation.get("seed"),
        "termination_reason": simulation.get("termination_reason"),
        "normal_stop": simulation.get("termination_reason") == "user_stop",
        "max_steps_stop": simulation.get("termination_reason") == "max_steps",
        "duration_seconds": simulation.get("duration"),
        "reward": reward_info.get("reward"),
        "db_match": db_check.get("db_match") if isinstance(db_check, dict) else None,
        "db_reward": db_check.get("db_reward") if isinstance(db_check, dict) else None,
        "action_checks_total": action_summary["total"],
        "action_checks_matched": action_summary["matched"],
        "action_checks_failed": action_summary["failed"],
        "write_actions_total": action_summary["write_total"],
        "write_actions_matched": action_summary["write_matched"],
        "write_actions_failed": action_summary["write_failed"],
        "write_action_names": action_summary["write_action_names"],
        "action_checks": action_summary["details"],
        "agent_cost": agent_cost,
        "user_cost": user_cost,
        "total_cost": total_cost,
        "message_count": len(messages),
        "message_roles": counter_dict([m.get("role") for m in messages if isinstance(m, dict) and m.get("role")]),
        "tool_calls_from_messages": tool_calls_from_messages(messages),
    }


def events_by_task(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for event in events:
        task_id = event.get("task_id")
        if task_id:
            grouped[str(task_id)].append(event)
    return dict(grouped)


def task_event_summary(task_id: str, events: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    tool_events = [event for event in events if event.get("tool_name")]
    evidence = evidence_from_events(events, metrics)
    tool_calls = [event for event in events if event.get("event_type") == "tool_call_requested"]
    dispatch_starts = [event for event in events if event.get("event_type") in {"tool_dispatch_start", "toolkit_dispatch_start"}]
    return {
        "task_id": task_id,
        "event_count": len(events),
        "event_counts": counter_dict(event_types),
        "event_families": counter_dict([RUNTIME_EVENT_FAMILIES.get(str(event_type), "unknown") for event_type in event_types]),
        "turn_indexes": sorted({event.get("turn_index") for event in events if event.get("turn_index") is not None}),
        "tool_names": counter_dict([event.get("tool_name") for event in tool_events if event.get("tool_name")]),
        "tool_call_requested_count": len(tool_calls),
        "tool_dispatch_start_count": len(dispatch_starts),
        "tool_events": [compact_tool_event(event) for event in tool_events],
        "mutation_evidence": evidence,
    }



def full_mock_classification(metrics: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Classify using shared rules, then align success with tau2 reward pass semantics.

    The single-run outcome classifier intentionally requires a DB match for
    success. Full mock contains tasks whose reward basis may exclude DB or whose
    expected behavior is refusal/no-write, so benchmark pass/fail is the task
    reward. We still preserve DB/action/stop evidence in classification inputs
    and reasons.
    """
    classification = classify_task_outcome(metrics, evidence)
    write_total = metrics.get("write_actions_total") or 0
    write_matched = metrics.get("write_actions_matched") or 0
    benchmark_pass = (
        metrics.get("reward") == 1.0
        and metrics.get("normal_stop") is True
        and (write_total == 0 or write_matched == write_total)
    )
    original_outcome = classification.get("task_outcome")
    if benchmark_pass and original_outcome != "success":
        classification = dict(classification)
        classification["task_outcome"] = "success"
        classification["outcome_is_success"] = True
        reasons = list(classification.get("classification_reasons", []))
        reasons.insert(
            0,
            "tau2 benchmark reward is 1.0, expected write actions matched, and the episode stopped normally",
        )
        if metrics.get("db_match") is False:
            reasons.append("DB mismatch is retained as a notable metric, but this task's aggregate reward still passed")
        classification["classification_reasons"] = list(dict.fromkeys(reasons))
        classification["shared_classifier_outcome_before_full_mock_reward_alignment"] = original_outcome
    return classification

def classify_failure_kind(task: dict[str, Any]) -> str:
    classification = task["classification"]["task_outcome"]
    if classification == "success":
        return "passed"
    if task["metrics"].get("max_steps_stop"):
        return "max_steps"
    if task["metrics"].get("write_actions_total", 0) > task["metrics"].get("write_actions_matched", 0):
        return "write_action_mismatch"
    if task["metrics"].get("db_match") is False:
        return "db_mismatch"
    if task["metrics"].get("reward") != 1.0:
        evidence = task["runtime_events"].get("mutation_evidence", {})
        if evidence.get("mutation_evidence_present") or task["metrics"].get("db_match") is True:
            return "partial_progress"
        return "non_db_or_communication_reward_loss"
    return "unknown"


def infer_failure_explanation(task: dict[str, Any]) -> list[str]:
    metrics = task["metrics"]
    reasons = list(task["classification"].get("classification_reasons", []))
    if metrics.get("max_steps_stop"):
        reasons.append("Task ended with termination_reason=max_steps rather than user_stop.")
    if metrics.get("db_match") is False:
        reasons.append("Evaluator reported db_match=false.")
    if metrics.get("db_match") is None:
        reasons.append("No DB check was available for this task.")
    if metrics.get("write_actions_total", 0) > metrics.get("write_actions_matched", 0):
        reasons.append(
            f"Write actions matched {metrics.get('write_actions_matched')}/{metrics.get('write_actions_total')}."
        )
    if metrics.get("reward") != 1.0:
        reasons.append(f"Reward was {metrics.get('reward')!r} rather than 1.0.")
    if metrics.get("task_id") == "impossible_task_1" and task["classification"].get("task_outcome") == "success":
        reasons.append("Impossible/refusal behavior appears expected and passed the evaluator.")
    return list(dict.fromkeys(reasons))


def benchmark_summary(tasks: list[dict[str, Any]], results: dict[str, Any], final_state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [task for task in tasks if task["classification"]["task_outcome"] == "success"]
    failed = [task for task in tasks if task["classification"]["task_outcome"] != "success"]
    rewards = [task["metrics"].get("reward") for task in tasks if isinstance(task["metrics"].get("reward"), (int, float))]
    db_checked = [task for task in tasks if task["metrics"].get("db_match") is not None]
    db_matched = [task for task in db_checked if task["metrics"].get("db_match") is True]
    write_total = sum(task["metrics"].get("write_actions_total", 0) for task in tasks)
    write_matched = sum(task["metrics"].get("write_actions_matched", 0) for task in tasks)
    normal_stop = [task for task in tasks if task["metrics"].get("normal_stop")]
    max_steps = [task for task in tasks if task["metrics"].get("max_steps_stop")]
    costs = [task["metrics"].get("total_cost") for task in tasks if isinstance(task["metrics"].get("total_cost"), (int, float))]
    info = results.get("info") if isinstance(results.get("info"), dict) else {}
    return {
        "status_observed": final_state.get("status"),
        "provider": "openai" if "openai/" in json.dumps(info) else None,
        "model": info.get("agent_info", {}).get("llm") if isinstance(info.get("agent_info"), dict) else None,
        "domain": info.get("domain"),
        "num_tasks_requested": final_state.get("num_tasks"),
        "task_selection_mode": final_state.get("task_selection_mode"),
        "max_steps": info.get("max_steps"),
        "concurrency": info.get("max_concurrency"),
        "total_runtime_events": len(events),
        "total_simulations": safe_len(results.get("simulations")),
        "total_tasks": len(tasks),
        "average_reward": sum(rewards) / len(rewards) if rewards else None,
        "pass_rate": len(passed) / len(tasks) if tasks else None,
        "number_passed": len(passed),
        "number_failed": len(failed),
        "passed_task_ids": [task["task_id"] for task in passed],
        "failed_task_ids": [task["task_id"] for task in failed],
        "db_match": {"matched": len(db_matched), "checked": len(db_checked)},
        "write_actions": {"matched": write_matched, "total": write_total},
        "normal_stop_count": len(normal_stop),
        "max_steps_count": len(max_steps),
        "cost": {
            "total_available_cost": sum(costs) if costs else None,
            "tasks_with_cost": len(costs),
            "tasks_missing_cost": len(tasks) - len(costs),
        },
        "activegraph_controlled_tau2": final_state.get("activegraph_controlled_tau2"),
        "state_packets_fed_back_to_tau2": final_state.get("state_packets_fed_back_to_tau2"),
        "tau2_executed_in_original_run": final_state.get("tau2_executed"),
        "llm_api_calls_made_in_original_run": final_state.get("paid_llm_api_calls_made"),
        "tau2_rerun_by_analysis": False,
        "llm_api_calls_made_by_analysis": False,
    }


def runtime_event_coverage(events: list[dict[str, Any]], final_state: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    families = [RUNTIME_EVENT_FAMILIES.get(str(event_type), "unknown") for event_type in event_types]
    expected_core = sorted(RUNTIME_EVENT_FAMILIES)
    observed = set(str(event_type) for event_type in event_types)
    return {
        "total_events": len(events),
        "event_counts": counter_dict(event_types),
        "event_families": counter_dict(families),
        "observed_event_types": sorted(observed),
        "expected_runtime_event_types_known_to_analyzer": expected_core,
        "known_event_types_missing_from_run": [event_type for event_type in expected_core if event_type not in observed],
        "unknown_event_type_count": sum(1 for family in families if family == "unknown"),
        "final_state_event_counts_match_jsonl": final_state.get("event_counts") == counter_dict(event_types),
        "tasks_with_events": [task["task_id"] for task in tasks if task["runtime_events"]["event_count"] > 0],
        "tasks_without_events": [task["task_id"] for task in tasks if task["runtime_events"]["event_count"] == 0],
        "instrumentation_notes": [
            "Runtime events cover batch, simulation, turn, message, tool, evaluation, and result-persistence families.",
            "The trace is observational only; ActiveGraph did not control tau2 and state packets were not fed back.",
        ],
    }


def mutation_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for task in tasks:
        metrics = task["metrics"]
        evidence = task["runtime_events"]["mutation_evidence"]
        rows.append(
            {
                "task_id": task["task_id"],
                "outcome": task["classification"]["task_outcome"],
                "expected_write_actions": metrics.get("write_action_names", []),
                "write_actions_matched": metrics.get("write_actions_matched"),
                "write_actions_total": metrics.get("write_actions_total"),
                "live_write_tool_detected_before_evaluation": evidence.get("live_write_tool_detected_before_evaluation"),
                "live_write_tools_before_evaluation": evidence.get("live_write_tools_before_evaluation"),
                "state_hash_changed_during_live_write": evidence.get("state_hash_changed_during_live_write"),
                "tool_result_payload_count": evidence.get("tool_result_payload_count"),
                "result_object_ids": evidence.get("result_object_ids"),
            }
        )
    return {
        "tasks": rows,
        "totals": {
            "tasks_with_expected_writes": sum(1 for row in rows if row["write_actions_total"]),
            "tasks_with_live_write_detection": sum(1 for row in rows if row["live_write_tool_detected_before_evaluation"]),
            "tasks_with_state_hash_change": sum(1 for row in rows if row["state_hash_changed_during_live_write"]),
            "expected_write_actions_total": sum(row["write_actions_total"] or 0 for row in rows),
            "expected_write_actions_matched": sum(row["write_actions_matched"] or 0 for row in rows),
        },
    }


def failure_analysis(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [task for task in tasks if task["classification"]["task_outcome"] != "success"]
    notable = []
    for task in failures:
        notable.append(
            {
                "task_id": task["task_id"],
                "classification": task["classification"]["task_outcome"],
                "failure_kind": classify_failure_kind(task),
                "termination_reason": task["metrics"].get("termination_reason"),
                "reward": task["metrics"].get("reward"),
                "db_match": task["metrics"].get("db_match"),
                "write_actions": {
                    "matched": task["metrics"].get("write_actions_matched"),
                    "total": task["metrics"].get("write_actions_total"),
                },
                "inferable_reasons": infer_failure_explanation(task),
            }
        )
    return {
        "failed_task_count": len(failures),
        "failed_task_ids": [task["task_id"] for task in failures],
        "classification_counts": counter_dict([task["classification"]["task_outcome"] for task in tasks]),
        "failure_kind_counts": counter_dict([classify_failure_kind(task) for task in failures]),
        "notable_failure_cases": notable,
    }


def markdown_summary(report: dict[str, Any]) -> str:
    summary = report["benchmark_summary"]
    failures = report["failure_analysis"]["notable_failure_cases"]
    coverage = report["runtime_event_coverage"]
    outcome_rows = []
    for task in report["task_outcomes"]:
        outcome_rows.append(
            "| {task_id} | {outcome} | {reward} | {termination} | {db} | {writes} | {events} |".format(
                task_id=task["task_id"],
                outcome=task["classification"]["task_outcome"],
                reward=task["metrics"].get("reward"),
                termination=task["metrics"].get("termination_reason"),
                db=task["metrics"].get("db_match"),
                writes=f"{task['metrics'].get('write_actions_matched')}/{task['metrics'].get('write_actions_total')}",
                events=task["runtime_events"].get("event_count"),
            )
        )
    failure_lines = [
        f"- `{case['task_id']}`: {case['classification']} ({case['failure_kind']}) — "
        + "; ".join(case["inferable_reasons"])
        for case in failures
    ] or ["- None; all tasks passed."]
    return "\n".join(
        [
            "# Full mock runtime-traced tau2 baseline analysis",
            "",
            f"- Status: `{report['status']}`",
            f"- Runtime run inspected: `{report['inputs']['runtime_run_dir']}`",
            f"- Total tasks: {summary['total_tasks']}",
            f"- Pass rate: {summary['pass_rate']:.3f}",
            f"- Average reward: {summary['average_reward']:.4f}",
            f"- Passed tasks: {', '.join(f'`{task_id}`' for task_id in summary['passed_task_ids'])}",
            f"- Failed tasks: {', '.join(f'`{task_id}`' for task_id in summary['failed_task_ids'])}",
            f"- DB match: {summary['db_match']['matched']}/{summary['db_match']['checked']}",
            f"- Write actions: {summary['write_actions']['matched']}/{summary['write_actions']['total']}",
            f"- Normal stop / max steps: {summary['normal_stop_count']} / {summary['max_steps_count']}",
            f"- Runtime events: {coverage['total_events']}",
            f"- tau2 rerun by analysis: {summary['tau2_rerun_by_analysis']}",
            f"- LLM/API calls by analysis: {summary['llm_api_calls_made_by_analysis']}",
            f"- ActiveGraph controlled tau2: {summary['activegraph_controlled_tau2']}",
            f"- State packets fed back to tau2: {summary['state_packets_fed_back_to_tau2']}",
            "",
            "## Per-task outcomes",
            "",
            "| Task | Classification | Reward | Termination | DB match | Writes | Events |",
            "| --- | --- | ---: | --- | --- | ---: | ---: |",
            *outcome_rows,
            "",
            "## Failure analysis",
            "",
            *failure_lines,
            "",
            "## Runtime event coverage",
            "",
            f"- Event families: `{json.dumps(coverage['event_families'], sort_keys=True)}`",
            f"- Event counts match final state: `{coverage['final_state_event_counts_match_jsonl']}`",
            f"- Tasks without runtime events: {', '.join(coverage['tasks_without_events']) or 'none'}",
            "",
            "## Offline boundary",
            "",
            "This analysis read existing JSON/JSONL/Markdown/log artifacts only. It did not rerun tau2, did not run a model-backed episode, did not call LLM/API services, did not require API keys, did not mutate `vendor/tau2-bench`, and did not add ActiveGraph control.",
            "",
        ]
    )


def build_report(args: argparse.Namespace, output_dir: pathlib.Path) -> dict[str, Any]:
    run_dir = args.runtime_run_dir.resolve()
    paths = {
        "runtime_events": run_dir / "runtime_events.jsonl",
        "runtime_final_state": run_dir / "runtime_trace_final_state.json",
        "runtime_summary": run_dir / "runtime_trace_summary.md",
        "results": result_path(run_dir),
        "raw_log": run_dir / "raw.log",
    }
    for label, path in paths.items():
        require_file(path, label)

    events = load_jsonl(paths["runtime_events"])
    final_state = load_json(paths["runtime_final_state"])
    results = load_json(paths["results"])
    runtime_summary_text = paths["runtime_summary"].read_text(encoding="utf-8")
    raw_log_text = paths["raw_log"].read_text(encoding="utf-8")
    simulations = results.get("simulations") if isinstance(results.get("simulations"), list) else []
    grouped_events = events_by_task(events)

    tasks: list[dict[str, Any]] = []
    for simulation in simulations:
        if not isinstance(simulation, dict):
            continue
        metrics = simulation_metrics(simulation)
        task_id = str(metrics.get("task_id"))
        task_events = grouped_events.get(task_id, [])
        event_summary = task_event_summary(task_id, task_events, metrics)
        classification = full_mock_classification(metrics, event_summary["mutation_evidence"])
        task = {
            "task_id": task_id,
            "metrics": metrics,
            "runtime_events": event_summary,
            "classification": classification,
            "passed": classification["task_outcome"] == "success",
        }
        task["failure_or_success_notes"] = infer_failure_explanation(task)
        tasks.append(task)

    bench = benchmark_summary(tasks, results, final_state, events)
    failures = failure_analysis(tasks)
    coverage = runtime_event_coverage(events, final_state, tasks)
    mutations = mutation_summary(tasks)
    status = STATUS_PASSED if not failures["failed_task_ids"] else STATUS_WITH_FAILURES
    return {
        "status": status,
        "generated_at": utc_now(),
        "inputs": {
            "runtime_run_dir": rel(run_dir),
            **{f"{label}_path": rel(path) for label, path in paths.items()},
            "input_hashes": {label: sha256(path) for label, path in paths.items()},
        },
        "offline_boundary": {
            "tau2_rerun_by_analysis": False,
            "model_backed_episode_run_by_analysis": False,
            "llm_api_calls_made_by_analysis": False,
            "api_keys_required_by_analysis": False,
            "vendor_tau2_bench_mutated_by_analysis": False,
            "activegraph_control_added_by_analysis": False,
        },
        "benchmark_summary": bench,
        "task_outcomes": tasks,
        "failure_analysis": failures,
        "runtime_event_coverage": coverage,
        "mutation_summary": mutations,
        "source_artifact_observations": {
            "runtime_trace_summary_line_count": len(runtime_summary_text.splitlines()),
            "raw_log_line_count": len(raw_log_text.splitlines()),
            "raw_log_tail": raw_log_text.splitlines()[-20:],
        },
    }


def write_outputs(report: dict[str, Any], output_dir: pathlib.Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "full_mock_baseline_analysis.json", report)
    write_json(output_dir / "task_outcomes.json", report["task_outcomes"])
    write_json(output_dir / "failure_analysis.json", report["failure_analysis"])
    write_json(output_dir / "runtime_event_coverage.json", report["runtime_event_coverage"])
    write_json(output_dir / "mutation_summary.json", report["mutation_summary"])
    final_state = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "inputs": report["inputs"],
        "offline_boundary": report["offline_boundary"],
        "benchmark_summary": report["benchmark_summary"],
    }
    write_json(output_dir / "final_state.json", final_state)
    (output_dir / "full_mock_baseline_summary.md").write_text(markdown_summary(report), encoding="utf-8")
    raw_log = [
        "full mock runtime-traced tau2 baseline analysis",
        f"status={report['status']}",
        f"runtime_run_dir={report['inputs']['runtime_run_dir']}",
        "tau2_rerun_by_analysis=false",
        "llm_api_calls_made_by_analysis=false",
        "vendor_tau2_bench_mutated_by_analysis=false",
        f"total_tasks={report['benchmark_summary']['total_tasks']}",
        f"pass_rate={report['benchmark_summary']['pass_rate']:.3f}",
        f"average_reward={report['benchmark_summary']['average_reward']:.4f}",
    ]
    (output_dir / "raw.log").write_text("\n".join(raw_log) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = (args.output_dir or args.runtime_run_dir / OUTPUT_DIR_NAME).resolve()
    try:
        report = build_report(args, output_dir)
        write_outputs(report, output_dir)
    except Exception as exc:  # noqa: BLE001 - CLI should emit machine-readable failure state.
        output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at": utc_now(),
            "error": str(exc),
            "offline_boundary": {
                "tau2_rerun_by_analysis": False,
                "model_backed_episode_run_by_analysis": False,
                "llm_api_calls_made_by_analysis": False,
                "api_keys_required_by_analysis": False,
                "vendor_tau2_bench_mutated_by_analysis": False,
                "activegraph_control_added_by_analysis": False,
            },
        }
        write_json(output_dir / "final_state.json", failure)
        (output_dir / "raw.log").write_text(f"status={STATUS_INPUTS_MISSING}\nerror={exc}\n", encoding="utf-8")
        print(f"[FULL-MOCK-ANALYSIS] status={STATUS_INPUTS_MISSING} error={exc}")
        return 1
    print(
        "[FULL-MOCK-ANALYSIS] "
        f"status={report['status']} output_dir={rel(output_dir)} "
        f"tasks={report['benchmark_summary']['total_tasks']} "
        f"pass_rate={report['benchmark_summary']['pass_rate']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
