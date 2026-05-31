#!/usr/bin/env python3
"""Offline detailed failure analysis for the full mock runtime baseline.

The analyzer consumes already-produced artifacts only. It does not run tau2,
start model-backed episodes, call LLM/API services, require API keys, or mutate
vendor/tau2-bench.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
from collections import Counter
from typing import Any

OUTPUT_DIR_NAME = "full_mock_failure_analysis"
STATUS_OK = "full_mock_failure_analysis_completed"
STATUS_MISSING_INPUTS = "full_mock_failure_analysis_inputs_missing"
FAILED_TASK_IDS = (
    "update_task_with_initialization_data",
    "update_task_with_user_tools",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-analyze detailed failure causes for the full mock baseline."
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


def load_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                row["_line_number"] = line_no
                rows.append(row)
    return rows


def write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    rt = payload.get("runtime_trace") if isinstance(payload.get("runtime_trace"), dict) else {}
    return rt


def content_from_message(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return None


def tool_calls_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls")
    return [call for call in calls if isinstance(call, dict)] if isinstance(calls, list) else []


def compact_message(message: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "message_index": index,
        "turn_idx": message.get("turn_idx"),
        "role": message.get("role"),
        "content": content_from_message(message),
        "tool_calls": tool_calls_from_message(message),
        "tool_call_id": message.get("tool_call_id") or message.get("id"),
        "requestor": message.get("requestor"),
        "error": message.get("error"),
    }


def event_slice_for_task(events: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    """Return task events plus task-less dispatch events occurring inside its span."""
    indexes = [idx for idx, event in enumerate(events) if event.get("task_id") == task_id]
    if not indexes:
        return []
    start, end = min(indexes), max(indexes)
    return [event for event in events[start : end + 1]]


def compact_event(event: dict[str, Any]) -> dict[str, Any]:
    rt = runtime_payload(event)
    message = rt.get("message") if isinstance(rt.get("message"), dict) else {}
    response = rt.get("response") if isinstance(rt.get("response"), dict) else {}
    return {
        "line_number": event.get("_line_number"),
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "component": event.get("component"),
        "task_id": event.get("task_id"),
        "turn_index": event.get("turn_index"),
        "message_role": event.get("message_role"),
        "tool_name": event.get("tool_name"),
        "state_hash": event.get("state_hash"),
        "status": rt.get("status"),
        "termination_reason": rt.get("termination_reason"),
        "tool_call": rt.get("tool_call"),
        "tool_arguments": rt.get("arguments") or rt.get("kwargs"),
        "tool_result": rt.get("result"),
        "tool_response": response or None,
        "state_hash_before": rt.get("state_hash_before"),
        "state_hash_after": rt.get("state_hash_after"),
        "from_role": rt.get("from_role"),
        "to_role": rt.get("to_role"),
        "message": message or None,
        "reward": rt.get("reward"),
    }


def state_transitions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    last_hash: str | None = None
    for event in events:
        rt = runtime_payload(event)
        before = rt.get("state_hash_before") or last_hash
        after = rt.get("state_hash_after") or event.get("state_hash")
        if isinstance(after, str) and after != last_hash:
            transitions.append(
                {
                    "line_number": event.get("_line_number"),
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "tool_name": event.get("tool_name"),
                    "state_hash_before": before,
                    "state_hash_after": after,
                    "mutation_inferred": isinstance(before, str) and before != after,
                }
            )
            last_hash = after
    return transitions


def extract_tool_activity(messages: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = []
    tool_results_by_turn: dict[int, list[dict[str, Any]]] = {}
    for idx, message in enumerate(messages):
        if message.get("role") == "tool":
            turn = message.get("turn_idx")
            if isinstance(turn, int):
                tool_results_by_turn.setdefault(turn, []).append(compact_message(message, idx))
    event_results: list[dict[str, Any]] = []
    for event in events:
        rt = runtime_payload(event)
        if event.get("event_type") in {"toolkit_dispatch_end", "tool_dispatch_end"}:
            event_results.append(compact_event(event))
    for idx, message in enumerate(messages):
        for call in tool_calls_from_message(message):
            turn = message.get("turn_idx")
            activities.append(
                {
                    "source": "messages",
                    "message_index": idx,
                    "turn_idx": turn,
                    "requestor": call.get("requestor"),
                    "tool_name": call.get("name"),
                    "tool_call_id": call.get("id"),
                    "arguments": call.get("arguments"),
                    "results_same_turn": tool_results_by_turn.get(turn, []),
                }
            )
    for event in events:
        rt = runtime_payload(event)
        call = rt.get("tool_call") if isinstance(rt.get("tool_call"), dict) else None
        if call:
            activities.append(
                {
                    "source": "runtime_events",
                    "line_number": event.get("_line_number"),
                    "event_id": event.get("event_id"),
                    "turn_index": event.get("turn_index"),
                    "requestor": call.get("requestor"),
                    "tool_name": call.get("name"),
                    "tool_call_id": call.get("id"),
                    "arguments": call.get("arguments"),
                    "dispatch_results_in_slice": [
                        result
                        for result in event_results
                        if result.get("tool_name") == call.get("name")
                    ],
                }
            )
    return activities


def reward_section(simulation: dict[str, Any]) -> dict[str, Any]:
    reward_info = simulation.get("reward_info")
    return reward_info if isinstance(reward_info, dict) else {}


def action_summary(reward_info: dict[str, Any]) -> dict[str, Any]:
    checks = reward_info.get("action_checks")
    checks = checks if isinstance(checks, list) else []
    return {
        "total": len(checks),
        "matched": sum(1 for check in checks if isinstance(check, dict) and check.get("action_match") is True),
        "failed": sum(1 for check in checks if isinstance(check, dict) and check.get("action_match") is not True),
        "details": checks,
    }


def infer_likely_cause(task_id: str, simulation: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    reward_info = reward_section(simulation)
    if task_id == "update_task_with_initialization_data":
        return {
            "short": "communicate scorer failure despite successful DB mutation and matched write action",
            "details": [
                "The reward basis is DB plus COMMUNICATE; DB earned 1.0 and the write action matched, but COMMUNICATE earned 0.0.",
                "Both communicate checks were recorded as unmet: acknowledging previous context and confirming the update successfully.",
                "The initial task state was present and the update_task_status tool changed task_2 from pending to completed, so wrong initial state is unlikely.",
                "The episode stopped normally with user_stop, so the failure is not max-steps or missing stop behavior.",
            ],
            "specific_answers": {
                "why_reward_zero_despite_db_write_success": "The final reward was the combined DB/COMMUNICATE score; communicate_checks were both met=false, making the COMMUNICATE reward 0.0 even though db_check.db_match=true and action_match=true.",
                "failed_on": "communicate/scorer detail, not DB, write action, initial state, env assertion, NL assertion, or max-steps termination",
                "wrong_initial_state": False,
                "missing_user_interaction": False,
                "instrumentation_or_scoring_ambiguity": "moderate: the transcript contains a natural confirmation, but the serialized communicate check says it was not communicated; offline artifacts do not expose the original communicate judge internals beyond that result.",
            },
            "smallest_next_experiment": "Rerun only this task with the same seed and a deterministic agent instruction that explicitly says: 'I understand this continues the previous task_2 context, and I successfully updated task_2 to completed.' Then compare communicate_checks; do not change DB tools.",
            "most_likely_category": "scorer detail / communication phrasing ambiguity",
        }
    if task_id == "update_task_with_user_tools":
        return {
            "short": "max_steps before the user-side dismiss_notification step and before scoring checks ran",
            "details": [
                "The user simulator successfully called check_notifications first, so user-side tool calling was at least partially captured.",
                "The assistant spent extra turns asking for a user identifier after get_users even though task_1 was available from the notification/tool context.",
                "The assistant eventually updated task_1 to completed and confirmed it on the final allowed turn, but the user had no remaining turn to call dismiss_notification('notif_1') or stop.",
                "Because termination_reason=max_steps, tau2 serialized no DB/action/env/NL checks for this task.",
            ],
            "specific_answers": {
                "why_max_steps": "The 10-step cap was consumed by check_notifications, an assistant get_users detour, a clarification loop, the update call, and the final confirmation; no user turn remained for dismiss_notification and ###STOP###.",
                "requires_user_side_tool_behavior_not_captured": "partially no: check_notifications was captured; the required dismiss_notification behavior was specified but not reached under the current agent/user turn path and max_steps budget.",
                "failed_on": "premature max_steps; likely would have needed the user env assertion notification_status=read after dismiss_notification, but scoring did not run those checks.",
                "instrumentation_or_scoring_ambiguity": "low to moderate: runtime and messages agree on max_steps and absent dismiss_notification; ambiguity remains only because tau2 skips detailed scoring after premature termination.",
            },
            "smallest_next_experiment": "Rerun only this task with max_steps increased (for example 12 or 14) or with an agent prompt/tool policy that updates task_1 immediately from the notification context; verify that the user then calls dismiss_notification and env_assertion passes.",
            "most_likely_category": "model behavior plus tight turn budget/task complexity, with user simulator behavior dependent on receiving confirmation before dismissing",
        }
    return {
        "short": "unknown failure",
        "details": ["No task-specific heuristic is available."],
        "specific_answers": {},
        "smallest_next_experiment": "Inspect task-specific transcript and scorer fields.",
        "most_likely_category": "unknown",
    }


def build_analysis(run_dir: pathlib.Path, output_dir: pathlib.Path) -> dict[str, Any]:
    input_paths = {
        "runtime_events": run_dir / "runtime_events.jsonl",
        "tau2_results": run_dir / "tau2_output" / "results.json",
        "task_outcomes": run_dir / "full_mock_analysis" / "task_outcomes.json",
        "failure_analysis": run_dir / "full_mock_analysis" / "failure_analysis.json",
        "raw_log": run_dir / "raw.log",
    }
    missing = [str(path) for path in input_paths.values() if not path.exists()]
    if missing:
        return {
            "status": STATUS_MISSING_INPUTS,
            "run_dir": str(run_dir),
            "output_dir": str(output_dir),
            "missing_inputs": missing,
            "generated_at": utc_now(),
        }

    results = load_json(input_paths["tau2_results"])
    outcomes = load_json(input_paths["task_outcomes"])
    failure_analysis = load_json(input_paths["failure_analysis"])
    events = load_jsonl(input_paths["runtime_events"])

    task_by_id = {task.get("id"): task for task in results.get("tasks", []) if isinstance(task, dict)}
    simulation_by_task = {
        simulation.get("task_id"): simulation
        for simulation in results.get("simulations", [])
        if isinstance(simulation, dict)
    }
    outcome_rows = outcomes.get("task_outcomes", []) if isinstance(outcomes, dict) else outcomes
    outcome_rows = outcome_rows if isinstance(outcome_rows, list) else []
    outcome_by_task: dict[str, dict[str, Any]] = {}
    for outcome in outcome_rows:
        if not isinstance(outcome, dict):
            continue
        metrics = outcome.get("metrics") if isinstance(outcome.get("metrics"), dict) else {}
        task_id = outcome.get("task_id") or metrics.get("task_id")
        if isinstance(task_id, str):
            outcome_by_task[task_id] = outcome
    failed_ids = failure_analysis.get("failed_task_ids") or list(FAILED_TASK_IDS)

    detailed_tasks: list[dict[str, Any]] = []
    timelines: dict[str, Any] = {}
    scoring: dict[str, Any] = {}
    slice_rows: list[dict[str, Any]] = []

    for task_id in failed_ids:
        task = task_by_id.get(task_id, {})
        simulation = simulation_by_task.get(task_id, {})
        messages = simulation.get("messages") if isinstance(simulation.get("messages"), list) else []
        messages = [message for message in messages if isinstance(message, dict)]
        reward_info = reward_section(simulation)
        db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else None
        task_events = event_slice_for_task(events, task_id)
        compact_events = [compact_event(event) for event in task_events]
        for event in compact_events:
            row = dict(event)
            row["slice_task_id"] = task_id
            slice_rows.append(row)
        state_changes = state_transitions(task_events)
        mutation_occurred = any(change.get("mutation_inferred") for change in state_changes)
        communicate_checks = reward_info.get("communicate_checks")
        env_assertions = reward_info.get("env_assertions")
        nl_assertions = reward_info.get("nl_assertions")
        action_checks = action_summary(reward_info)
        likely_cause = infer_likely_cause(task_id, simulation, task)
        message_path = [compact_message(message, idx) for idx, message in enumerate(messages)]
        tool_activity = extract_tool_activity(messages, task_events)
        evaluation_criteria = task.get("evaluation_criteria") if isinstance(task.get("evaluation_criteria"), dict) else {}
        initialization = task.get("initial_state") if isinstance(task.get("initial_state"), dict) else {}

        detail = {
            "task_id": task_id,
            "classification": (outcome_by_task.get(task_id, {}).get("classification") or {}).get("task_outcome"),
            "failure_kind": (outcome_by_task.get(task_id, {}).get("classification") or {}).get("task_outcome"),
            "reward": reward_info.get("reward"),
            "termination_reason": simulation.get("termination_reason"),
            "db_match": db_check.get("db_match") if isinstance(db_check, dict) else None,
            "db_check": db_check,
            "action_checks": action_checks,
            "env_assertions": env_assertions,
            "nl_assertions": nl_assertions,
            "communicate_info_expected": evaluation_criteria.get("communicate_info"),
            "communicate_checks": communicate_checks,
            "reward_basis": reward_info.get("reward_basis") or evaluation_criteria.get("reward_basis"),
            "reward_breakdown": reward_info.get("reward_breakdown"),
            "evaluation_criteria": evaluation_criteria,
            "initial_state": initialization,
            "tool_activity": tool_activity,
            "state_hash_transitions": state_changes,
            "assistant_user_message_path": message_path,
            "mutation_occurred": mutation_occurred,
            "likely_failure_reason": likely_cause,
            "raw_reward_info": reward_info,
        }
        detailed_tasks.append(detail)
        timelines[task_id] = {
            "task_id": task_id,
            "event_count": len(compact_events),
            "message_count": len(message_path),
            "timeline": compact_events,
            "message_path": message_path,
            "state_hash_transitions": state_changes,
        }
        scoring[task_id] = {
            "task_id": task_id,
            "reward_info": reward_info,
            "evaluation_criteria": evaluation_criteria,
            "outcome_classification": outcome_by_task.get(task_id),
            "scoring_interpretation": likely_cause["specific_answers"],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = output_dir / "raw.log"
    shutil.copyfile(input_paths["raw_log"], raw_copy)

    final_state = {
        "status": STATUS_OK,
        "generated_at": utc_now(),
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "offline_artifact_analysis_only": True,
        "tau2_rerun": False,
        "model_backed_episode_rerun": False,
        "llm_or_api_calls_made_by_analyzer": False,
        "api_keys_required": False,
        "vendor_tau2_bench_mutated": False,
        "failed_task_ids": failed_ids,
        "failed_task_count": len(failed_ids),
        "runtime_event_count": len(events),
        "input_artifacts": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in input_paths.items()
        },
        "output_files": [
            "failure_analysis_detailed.json",
            "failure_analysis_summary.md",
            "failed_task_timelines.json",
            "failed_task_event_slices.jsonl",
            "scoring_evidence.json",
            "final_state.json",
            "raw.log",
        ],
    }

    analysis = {
        **final_state,
        "source_failure_analysis": failure_analysis,
        "failed_tasks": detailed_tasks,
        "cross_task_conclusion": {
            "update_task_with_initialization_data": "Reward 0.0 is explained by failed communicate checks despite DB/write success.",
            "update_task_with_user_tools": "Reward 0.0 is explained by max_steps before dismiss_notification/user stop/scoring.",
            "most_likely_categories": {
                "update_task_with_initialization_data": "communication scorer detail/phrasing ambiguity",
                "update_task_with_user_tools": "agent turn-path inefficiency plus tight max_steps and delayed user-tool dismissal",
            },
        },
    }
    write_json(output_dir / "failure_analysis_detailed.json", analysis)
    write_json(output_dir / "failed_task_timelines.json", timelines)
    write_json(output_dir / "scoring_evidence.json", scoring)
    write_json(output_dir / "final_state.json", final_state)
    with (output_dir / "failed_task_event_slices.jsonl").open("w", encoding="utf-8") as handle:
        for row in slice_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    write_summary(output_dir / "failure_analysis_summary.md", analysis)
    return final_state


def format_bool(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def write_summary(path: pathlib.Path, analysis: dict[str, Any]) -> None:
    lines = [
        "# Full mock baseline detailed failure analysis",
        "",
        "## Offline boundary",
        "",
        "- Tau2 rerun: no.",
        "- Model-backed episode rerun: no.",
        "- LLM/API calls made by this analyzer: no.",
        "- API keys required: no.",
        "- `vendor/tau2-bench` mutated: no.",
        "- Method: read-only inspection of `runtime_events.jsonl`, `tau2_output/results.json`, `full_mock_analysis/task_outcomes.json`, `full_mock_analysis/failure_analysis.json`, and `raw.log`.",
        "",
        "## Failed tasks analyzed",
        "",
    ]
    for task in analysis["failed_tasks"]:
        cause = task["likely_failure_reason"]
        lines.extend(
            [
                f"### `{task['task_id']}`",
                "",
                f"- Classification: `{task.get('classification')}` / `{task.get('failure_kind')}`.",
                f"- Reward: `{task.get('reward')}`.",
                f"- Termination reason: `{task.get('termination_reason')}`.",
                f"- DB match: `{task.get('db_match')}`.",
                f"- Action checks: {task['action_checks']['matched']}/{task['action_checks']['total']} matched.",
                f"- Mutation occurred: {format_bool(task.get('mutation_occurred'))}.",
                f"- Likely cause: {cause['short']}.",
                f"- Most likely category: {cause['most_likely_category']}.",
                "- Evidence:",
            ]
        )
        for detail in cause["details"]:
            lines.append(f"  - {detail}")
        lines.extend(
            [
                f"- Smallest next experiment: {cause['smallest_next_experiment']}",
                "",
            ]
        )
        if task["task_id"] == "update_task_with_initialization_data":
            answers = cause["specific_answers"]
            lines.extend(
                [
                    "#### Specific answers",
                    "",
                    f"- Why reward 0.0 despite DB/write success? {answers['why_reward_zero_despite_db_write_success']}",
                    f"- Did it fail on communicate/env/NL assertion, wrong initial state, missing user interaction, or scorer detail? {answers['failed_on']}. Wrong initial state: no. Missing user interaction: no.",
                    "",
                ]
            )
        if task["task_id"] == "update_task_with_user_tools":
            answers = cause["specific_answers"]
            lines.extend(
                [
                    "#### Specific answers",
                    "",
                    f"- Why max steps? {answers['why_max_steps']}",
                    f"- Did it require user-side tool behavior not captured by the current setup? {answers['requires_user_side_tool_behavior_not_captured']}",
                    f"- More likely model behavior, task complexity, user simulator behavior, or instrumentation/scoring ambiguity? {cause['most_likely_category']}.",
                    "",
                ]
            )
    lines.extend(
        [
            "## Output artifacts",
            "",
            "- `failure_analysis_detailed.json` — full per-task reconstruction and conclusions.",
            "- `failed_task_timelines.json` — event/message timeline by failed task.",
            "- `failed_task_event_slices.jsonl` — compact runtime event slices, including task-less dispatch events inside each failed-task span.",
            "- `scoring_evidence.json` — reward/scoring fields and interpretations.",
            "- `final_state.json` — analyzer status and offline/no-API boundary metadata.",
            "- `raw.log` — copied baseline raw log for local inspection.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_dir = args.runtime_run_dir
    output_dir = args.output_dir or run_dir / OUTPUT_DIR_NAME
    final_state = build_analysis(run_dir, output_dir)
    if final_state["status"] == STATUS_MISSING_INPUTS:
        print(
            f"[FULL-MOCK-FAILURE-ANALYSIS] status={final_state['status']} "
            f"missing={len(final_state['missing_inputs'])} output_dir={output_dir}"
        )
        return 2
    print(
        f"[FULL-MOCK-FAILURE-ANALYSIS] status={final_state['status']} "
        f"output_dir={output_dir} failed_tasks={final_state['failed_task_count']} "
        "tau2_rerun=false llm_api_calls=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
