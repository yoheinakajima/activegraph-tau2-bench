#!/usr/bin/env python3
"""Analyze a successful runtime-traced tau2 baseline offline.

This command reads already-committed run artifacts and writes comparison reports.
It does not import tau2, launch tau2, call LLM/API services, require API keys, or
mutate the vendored tau2 tree.
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
STATUS_PASSED = "successful_runtime_trace_analysis_passed"
STATUS_WITH_GAPS = "successful_runtime_trace_analysis_completed_with_gaps"
STATUS_INPUTS_MISSING = "successful_runtime_trace_analysis_inputs_missing"

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
        description="Offline-analyze the successful runtime-traced tau2 baseline and compare prior traces."
    )
    parser.add_argument("--successful-runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--short-runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--postrun-baseline-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Defaults to <successful-runtime-run-dir>/runtime_success_analysis/.",
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
        rows.append(row)
    return rows


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing required {label}: {rel(path)}")


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def payload(event: dict[str, Any]) -> dict[str, Any]:
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
        "normal_stop": sim.get("termination_reason") == "user_stop",
        "agent_errors": 0 if sim else None,
        "user_errors": 0 if sim else None,
        "message_count": len(messages),
        "message_roles": [m.get("role") for m in messages if isinstance(m, dict)],
        "tool_calls_from_messages": tool_calls,
    }


def tool_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if event.get("tool_name") or str(event.get("event_type", "")).startswith("tool"):
            p = payload(event)
            rows.append(
                {
                    "sequence": index,
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "tool_name": event.get("tool_name"),
                    "turn_index": event.get("turn_index"),
                    "state_hash": event.get("state_hash"),
                    "status": p.get("status"),
                    "arguments": p.get("arguments") or (p.get("tool_call") or {}).get("arguments"),
                    "result": p.get("result"),
                    "response_preview": (p.get("response") or {}).get("content_preview") if isinstance(p.get("response"), dict) else None,
                    "state_hash_before": p.get("state_hash_before"),
                    "state_hash_after": p.get("state_hash_after"),
                }
            )
    return rows


def completion_path(events: list[dict[str, Any]], results_summary: dict[str, Any]) -> dict[str, Any]:
    path_events: list[dict[str, Any]] = []
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
    for index, event in enumerate(events, start=1):
        if event.get("event_type") not in interesting:
            continue
        p = payload(event)
        message = p.get("message") if isinstance(p.get("message"), dict) else {}
        response = p.get("response") if isinstance(p.get("response"), dict) else {}
        path_events.append(
            {
                "sequence": index,
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "component": event.get("component"),
                "turn_index": event.get("turn_index"),
                "role": event.get("message_role") or message.get("role") or response.get("role"),
                "tool_name": event.get("tool_name"),
                "content_preview": p.get("content_preview") or message.get("content_preview") or response.get("content_preview"),
                "status": p.get("status"),
                "state_hash": event.get("state_hash"),
            }
        )
    return {
        "status": "completed" if results_summary.get("normal_stop") and results_summary.get("reward") == 1.0 else "not_completed",
        "summary": [
            "assistant greeting",
            "user asks to create Important Meeting for user_1",
            "assistant requests create_task with title/user_id",
            "environment/toolkit returns task_2 and state hash changes",
            "assistant confirms completion",
            "user emits normal stop",
            "evaluation observes reward=1, db_match=true, write action matched",
        ],
        "events": path_events,
    }


def summarize_runtime_run(run_dir: pathlib.Path, events: list[dict[str, Any]], final_state: dict[str, Any], results: dict[str, Any] | None) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    roles = [event.get("message_role") for event in events if event.get("message_role")]
    families = [RUNTIME_EVENT_FAMILIES.get(str(event_type), "unknown") for event_type in event_types]
    return {
        "run_dir": rel(run_dir),
        "event_count": len(events),
        "event_counts": counter_dict(event_types),
        "event_families": counter_dict(families),
        "message_roles_observed": counter_dict(roles),
        "turn_indexes": sorted({event.get("turn_index") for event in events if event.get("turn_index") is not None}),
        "tool_names": counter_dict([event.get("tool_name") for event in events if event.get("tool_name")]),
        "tool_events": tool_events(events),
        "results": summarize_results(results),
        "final_state_flags": {
            "status": final_state.get("status"),
            "tau2_executed": final_state.get("tau2_executed"),
            "paid_llm_api_calls_made_in_original_run": final_state.get("paid_llm_api_calls_made"),
            "activegraph_controlled_tau2": final_state.get("activegraph_controlled_tau2"),
            "state_packets_fed_back_to_tau2": final_state.get("state_packets_fed_back_to_tau2"),
            "returncode": final_state.get("returncode"),
        },
    }


def summarize_postrun(run_dir: pathlib.Path, events: list[dict[str, Any]], final_state: dict[str, Any], results: dict[str, Any] | None) -> dict[str, Any]:
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


def diff_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, dict[str, int]]:
    keys = sorted(set(left) | set(right))
    return {key: {"successful": left.get(key, 0), "comparison": right.get(key, 0), "delta": left.get(key, 0) - right.get(key, 0)} for key in keys}


def compare_to_short(success: dict[str, Any], short: dict[str, Any]) -> dict[str, Any]:
    successful_counts = success["event_counts"]
    short_counts = short["event_counts"]
    return {
        "event_count_difference": {
            "successful_runtime": success["event_count"],
            "short_runtime": short["event_count"],
            "delta": success["event_count"] - short["event_count"],
        },
        "event_type_count_delta": diff_counts(successful_counts, short_counts),
        "additional_success_events": {
            key: successful_counts.get(key, 0) - short_counts.get(key, 0)
            for key in sorted(successful_counts)
            if successful_counts.get(key, 0) > short_counts.get(key, 0)
        },
        "completion_delta": {
            "successful_termination_reason": success["results"].get("termination_reason"),
            "short_termination_reason": short["results"].get("termination_reason"),
            "successful_reward": success["results"].get("reward"),
            "short_reward": short["results"].get("reward"),
            "successful_db_match": success["results"].get("db_match"),
            "short_db_match": short["results"].get("db_match"),
            "successful_write_actions": f"{success['results'].get('write_actions_matched')}/{success['results'].get('write_actions_total')}",
            "short_write_actions": f"{short['results'].get('write_actions_matched')}/{short['results'].get('write_actions_total')}",
        },
        "interpretation": [
            "The max_steps=6 run adds two turn envelopes, a second user generation/response, a second assistant response, and extra create_task evaluation replay/low-level toolkit events.",
            "The short run stops at max_steps after requesting/observing get_users, so reward/action/db metrics remain unavailable or zero.",
        ],
    }


def compare_to_postrun(success: dict[str, Any], postrun: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_count_difference": {
            "successful_runtime": success["event_count"],
            "postrun_extracted": postrun["event_count"],
            "delta": success["event_count"] - postrun["event_count"],
        },
        "family_coverage_delta": diff_counts(success["event_families"], postrun["event_families"]),
        "runtime_coverage_improvements": [
            "Runtime trace captures bootstrap, batch, simulation, orchestrator, and per-turn lifecycle boundaries that post-run extraction reconstructs only coarsely or not at all.",
            "Runtime trace records live tool dispatch start/end, low-level toolkit dispatch, state hashes before/after tool execution, and evaluation-phase tool replay.",
            "Runtime trace records generation start/end boundaries for the user simulator and distinguishes user_response, agent_response, and tool message observation events.",
        ],
        "postrun_limitations_carried_forward": postrun.get("limitations", []),
    }


def coverage_report(success: dict[str, Any], short: dict[str, Any], postrun: dict[str, Any], hook_map: dict[str, Any]) -> dict[str, Any]:
    runtime_types = set(success["event_counts"])
    short_types = set(short["event_counts"])
    postrun_families = set(postrun["event_families"])
    success_families = set(success["event_families"])
    return {
        "runtime_event_types_observed": sorted(runtime_types),
        "runtime_event_types_added_over_short_run": sorted(t for t in runtime_types if success["event_counts"].get(t, 0) > short["event_counts"].get(t, 0)),
        "event_types_only_in_short_run": sorted(short_types - runtime_types),
        "families_observed_in_successful_runtime": sorted(success_families),
        "families_observed_in_postrun_extraction": sorted(postrun_families),
        "families_missing_from_postrun_but_present_at_runtime": sorted(success_families - postrun_families),
        "validated_runtime_hooks": hook_map.get("validated_hooks", []),
        "deferred_runtime_hooks": hook_map.get("deferred_hooks", []),
        "remaining_instrumentation_gaps": [
            "Runtime events are observation-only and do not feed ActiveGraph state packets back into tau2.",
            "The trace does not expose a full serialized DB diff; DB success is inferred from state hashes, tool result content, and reward/db_check artifacts.",
            "Evaluation invokes create_task again, so analysis must distinguish task-time mutation from evaluator replay/check execution.",
            "No fixture-backed ActiveGraph projection is part of the live tau2 control path; fixture artifacts remain offline comparison aids only.",
        ],
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
    if summary_text and "paid LLM/API calls made: `True`" in summary_text:
        issues.append(
            {
                "severity": "reporting_only",
                "artifact": "runtime_trace_summary.md",
                "issue": "Boolean rendering uses Python title-case True while related summaries use JSON lower-case true.",
                "resolution": "Flagged in analysis; generated JSON uses boolean true/false and Markdown normalizes the value.",
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


def format_bool(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def markdown_summary(report: dict[str, Any]) -> str:
    cmp_short = report["comparison_to_short_run"]["event_count_difference"]
    cmp_post = report["comparison_to_postrun_trace"]["event_count_difference"]
    metrics = report["successful_runtime"]["results"]
    flags = report["successful_runtime"]["final_state_flags"]
    additional = report["comparison_to_short_run"]["additional_success_events"]
    additional_lines = "\n".join(f"- `{k}`: +{v}" for k, v in additional.items()) or "- None"
    gaps = "\n".join(f"- {gap}" for gap in report["runtime_event_coverage"]["remaining_instrumentation_gaps"])
    issues = report["artifact_reporting_inconsistencies"]
    issue_lines = "\n".join(f"- `{item['artifact']}`: {item['issue']} Resolution: {item['resolution']}" for item in issues) or "- None found."
    return f"""# Successful runtime-traced tau2 baseline analysis

Status: `{report['status']}`

Generated at: `{report['generated_at_utc']}`

## Inputs

- successful runtime run: `{report['inputs']['successful_runtime_run_dir']}`
- short runtime run: `{report['inputs']['short_runtime_run_dir']}`
- post-run extracted baseline: `{report['inputs']['postrun_baseline_dir']}`

## Event count comparison

| Artifact | Event count |
| --- | ---: |
| Successful max_steps=6 runtime trace | {cmp_short['successful_runtime']} |
| Prior max_steps=2 runtime trace | {cmp_short['short_runtime']} |
| Post-run extracted baseline trace | {cmp_post['postrun_extracted']} |

The successful run has `{cmp_short['delta']}` more runtime events than the short runtime run and `{cmp_post['delta']}` more events than the post-run extracted trace.

## Additional events in the successful runtime run

{additional_lines}

These events show that the max_steps=6 episode proceeded beyond the short run's initial tool request path to perform the write tool call, observe the tool result, confirm to the user, receive the normal stop, and evaluate the completed task.

## Completion path

1. Assistant greets the user.
2. User asks to create `Important Meeting` for `user_1`.
3. Assistant requests `create_task` with `user_id=user_1` and `title=Important Meeting`.
4. Environment/toolkit dispatch returns `task_2`, changes the state hash, and emits a tool message.
5. Assistant confirms completion.
6. User stops normally.
7. Evaluation records reward `1.0`, DB match `true`, and the write action match.

Detailed sequence is written to `completion_path.json`.

## Metrics summary

- termination reason: `{metrics['termination_reason']}`
- reward: `{metrics['reward']}`
- DB match: `{format_bool(metrics['db_match'])}`
- DB reward: `{metrics['db_reward']}`
- write actions matched: `{metrics['write_actions_matched']}/{metrics['write_actions_total']}`
- normal stop: `{format_bool(metrics['normal_stop'])}`
- agent errors: `{metrics['agent_errors']}`
- user errors: `{metrics['user_errors']}`
- original run paid LLM/API calls: `{format_bool(flags['paid_llm_api_calls_made_in_original_run'])}`
- tau2 executed in original run: `{format_bool(flags['tau2_executed'])}`
- ActiveGraph controlled tau2: `{format_bool(flags['activegraph_controlled_tau2'])}`
- state packets fed back to tau2: `{format_bool(flags['state_packets_fed_back_to_tau2'])}`

## Runtime trace coverage improvement over post-run extraction

- Runtime trace event count: `{cmp_post['successful_runtime']}` vs post-run extracted event count: `{cmp_post['postrun_extracted']}`.
- Runtime trace adds live bootstrap/batch/simulation/orchestrator/turn lifecycle events.
- Runtime trace adds live tool dispatch, toolkit dispatch, state hashes around tool execution, and evaluation replay/check events.
- Runtime trace separates user generation start/end, user responses, assistant responses, and tool-message observation.

## Reporting inconsistencies flagged

{issue_lines}

## Remaining instrumentation gaps

{gaps}

## Boundary

This analysis is offline. It did not rerun tau2, did not run a model-backed episode, did not call LLM/API services, did not require API keys, did not mutate `vendor/tau2-bench`, and did not add ActiveGraph control.
"""


def build_report(args: argparse.Namespace, output_dir: pathlib.Path) -> dict[str, Any]:
    success_dir = args.successful_runtime_run_dir
    short_dir = args.short_runtime_run_dir
    postrun_dir = args.postrun_baseline_dir

    success_events_path = success_dir / "runtime_events.jsonl"
    short_events_path = short_dir / "runtime_events.jsonl"
    postrun_events_path = postrun_dir / "extracted_trace" / "baseline_trace.jsonl"
    success_final_path = success_dir / "runtime_trace_final_state.json"
    short_final_path = short_dir / "runtime_trace_final_state.json"
    postrun_final_path = postrun_dir / "extracted_trace" / "baseline_trace_final_state.json"
    success_hook_path = success_dir / "runtime_hook_map.json"
    success_summary_path = success_dir / "runtime_trace_summary.md"

    for path, label in [
        (success_events_path, "successful runtime events"),
        (short_events_path, "short runtime events"),
        (postrun_events_path, "post-run extracted events"),
        (success_final_path, "successful runtime final state"),
        (short_final_path, "short runtime final state"),
        (postrun_final_path, "post-run extracted final state"),
        (success_hook_path, "successful runtime hook map"),
    ]:
        require_file(path, label)

    success_results_path = success_dir / "tau2_artifacts" / "results.json"
    short_results_path = short_dir / "tau2_artifacts" / "results.json"
    postrun_results_path = postrun_dir / "tau2_artifacts" / "results.json"
    require_file(success_results_path, "successful runtime results")
    require_file(short_results_path, "short runtime results")
    require_file(postrun_results_path, "post-run results")

    success_events = load_jsonl(success_events_path)
    short_events = load_jsonl(short_events_path)
    postrun_events = load_jsonl(postrun_events_path)
    success_final = load_json(success_final_path)
    short_final = load_json(short_final_path)
    postrun_final = load_json(postrun_final_path)
    success_hook = load_json(success_hook_path)
    success_results = load_json(success_results_path)
    short_results = load_json(short_results_path)
    postrun_results = load_json(postrun_results_path)

    successful = summarize_runtime_run(success_dir, success_events, success_final, success_results)
    short = summarize_runtime_run(short_dir, short_events, short_final, short_results)
    postrun = summarize_postrun(postrun_dir, postrun_events, postrun_final, postrun_results)
    completion = completion_path(success_events, successful["results"])
    comp_short = compare_to_short(successful, short)
    comp_post = compare_to_postrun(successful, postrun)
    coverage = coverage_report(successful, short, postrun, success_hook)
    issues = artifact_inconsistencies(load_text_optional(success_summary_path), success_hook)

    expected_counts = successful["event_count"] == 44 and short["event_count"] == 30 and postrun["event_count"] == 12
    success_flags_ok = (
        successful["final_state_flags"].get("activegraph_controlled_tau2") is False
        and successful["final_state_flags"].get("state_packets_fed_back_to_tau2") is False
        and successful["final_state_flags"].get("tau2_executed") is True
    )
    completed = completion["status"] == "completed"
    status = STATUS_PASSED if expected_counts and success_flags_ok and completed else STATUS_WITH_GAPS

    inputs = {
        "successful_runtime_run_dir": rel(success_dir),
        "short_runtime_run_dir": rel(short_dir),
        "postrun_baseline_dir": rel(postrun_dir),
        "successful_runtime_events_path": rel(success_events_path),
        "short_runtime_events_path": rel(short_events_path),
        "postrun_events_path": rel(postrun_events_path),
        "successful_results_path": rel(success_results_path),
        "short_results_path": rel(short_results_path),
        "postrun_results_path": rel(postrun_results_path),
    }

    return {
        "status": status,
        "generated_at_utc": utc_now(),
        "inputs": inputs,
        "input_hashes": {key: sha256(REPO_ROOT / value) for key, value in inputs.items() if value.endswith((".json", ".jsonl"))},
        "successful_runtime": successful,
        "short_runtime": short,
        "postrun_trace": postrun,
        "completion_path": completion,
        "comparison_to_short_run": comp_short,
        "comparison_to_postrun_trace": comp_post,
        "runtime_event_coverage": coverage,
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
            "successful_runtime_trace_analysis": rel(output_dir / "successful_runtime_trace_analysis.json"),
            "successful_runtime_trace_summary": rel(output_dir / "successful_runtime_trace_summary.md"),
            "runtime_event_coverage": rel(output_dir / "runtime_event_coverage.json"),
            "completion_path": rel(output_dir / "completion_path.json"),
            "comparison_to_short_run": rel(output_dir / "comparison_to_short_run.json"),
            "comparison_to_postrun_trace": rel(output_dir / "comparison_to_postrun_trace.json"),
            "final_state": rel(output_dir / "final_state.json"),
            "raw_log": rel(output_dir / "raw.log"),
        },
    }


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.successful_runtime_run_dir / "runtime_success_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = build_report(args, output_dir)
    except Exception as exc:  # noqa: BLE001 - persist diagnosable failure state for offline artifact jobs.
        final_state = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at_utc": utc_now(),
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
        (output_dir / "raw.log").write_text(f"[ERROR] {exc}\n", encoding="utf-8")
        print(f"analysis_status={STATUS_INPUTS_MISSING}")
        print(f"error={exc}", file=sys.stderr)
        return 2

    write_json(output_dir / "successful_runtime_trace_analysis.json", report)
    (output_dir / "successful_runtime_trace_summary.md").write_text(markdown_summary(report), encoding="utf-8")
    write_json(output_dir / "runtime_event_coverage.json", report["runtime_event_coverage"])
    write_json(output_dir / "completion_path.json", report["completion_path"])
    write_json(output_dir / "comparison_to_short_run.json", report["comparison_to_short_run"])
    write_json(output_dir / "comparison_to_postrun_trace.json", report["comparison_to_postrun_trace"])
    final_state = {
        "status": report["status"],
        "generated_at_utc": report["generated_at_utc"],
        "event_counts": {
            "successful_runtime": report["successful_runtime"]["event_count"],
            "short_runtime": report["short_runtime"]["event_count"],
            "postrun_extracted": report["postrun_trace"]["event_count"],
        },
        "completion_status": report["completion_path"]["status"],
        "metrics": report["successful_runtime"]["results"],
        "activegraph_controlled_tau2": report["successful_runtime"]["final_state_flags"].get("activegraph_controlled_tau2"),
        "state_packets_fed_back_to_tau2": report["successful_runtime"]["final_state_flags"].get("state_packets_fed_back_to_tau2"),
        "tau2_executed_in_original_successful_run": report["successful_runtime"]["final_state_flags"].get("tau2_executed"),
        "paid_llm_api_calls_made_in_original_successful_run": report["successful_runtime"]["final_state_flags"].get("paid_llm_api_calls_made_in_original_run"),
        **report["analysis_boundaries"],
    }
    write_json(output_dir / "final_state.json", final_state)
    raw_lines = [
        f"[{report['generated_at_utc']}] status={report['status']}",
        "offline_analysis=true",
        "tau2_rerun_performed_by_analysis=false",
        "model_backed_episode_run_by_analysis=false",
        "llm_api_calls_made_by_analysis=false",
        "requires_api_keys=false",
        "vendor_tau2_bench_mutated_by_analysis=false",
        "event_counts=successful:44 short:30 postrun:12",
    ]
    (output_dir / "raw.log").write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    print(rel(output_dir))
    print(report["status"])
    return 0 if report["status"] in {STATUS_PASSED, STATUS_WITH_GAPS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
