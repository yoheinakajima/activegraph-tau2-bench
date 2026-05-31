#!/usr/bin/env python3
"""Project offline DB-mutation evidence from a runtime-traced tau2 baseline.

The analyzer reads existing artifacts only. It does not import tau2, execute tau2,
call model/LLM/API services, require API keys, mutate vendor/tau2-bench, or add
ActiveGraph control over tau2.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PASS_STATUS = "runtime_db_mutation_analysis_passed"
GAP_STATUS = "runtime_db_mutation_analysis_completed_with_gaps"
MISSING_STATUS = "runtime_db_mutation_analysis_inputs_missing"

REQUIRED_ARTIFACTS = {
    "runtime_events": pathlib.Path("runtime_events.jsonl"),
    "tau2_results": pathlib.Path("tau2_output/results.json"),
    "completion_path": pathlib.Path("runtime_success_analysis/completion_path.json"),
    "successful_runtime_trace_analysis": pathlib.Path(
        "runtime_success_analysis/successful_runtime_trace_analysis.json"
    ),
    "runtime_success_final_state": pathlib.Path("runtime_success_analysis/final_state.json"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline deterministic DB-diff / mutation-summary projection for a runtime-traced tau2 run."
    )
    parser.add_argument("--runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Defaults to <runtime-run-dir>/db_mutation_analysis/.",
    )
    return parser.parse_args()


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
        row["_line_number"] = line_number
        row["_sequence"] = line_number
        rows.append(row)
    return rows


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def payload(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("payload")
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("runtime_trace")
    return nested if isinstance(nested, dict) else raw


def first_simulation(results: dict[str, Any]) -> dict[str, Any]:
    simulations = results.get("simulations")
    if isinstance(simulations, list) and simulations and isinstance(simulations[0], dict):
        return simulations[0]
    return {}


def reward_info_from_results(results: dict[str, Any]) -> dict[str, Any]:
    reward = first_simulation(results).get("reward_info")
    return reward if isinstance(reward, dict) else {}


def action_checks(reward_info: dict[str, Any]) -> list[dict[str, Any]]:
    checks = reward_info.get("action_checks")
    return checks if isinstance(checks, list) else []


def action_dict(check: dict[str, Any]) -> dict[str, Any]:
    action = check.get("action")
    return action if isinstance(action, dict) else {}


def parse_tool_content(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def extract_result_payload(end_event: dict[str, Any] | None, toolkit_end: dict[str, Any] | None) -> Any:
    if toolkit_end is not None:
        result = payload(toolkit_end).get("result")
        if result is not None:
            return result
    if end_event is None:
        return None
    response = payload(end_event).get("response")
    if isinstance(response, dict):
        raw = response.get("raw")
        if isinstance(raw, dict) and "content" in raw:
            return parse_tool_content(raw.get("content"))
        if "content_preview" in response:
            return parse_tool_content(response.get("content_preview"))
    return None


def infer_mutation(tool_name: str | None, arguments: Any, result: Any) -> dict[str, Any]:
    result_obj = result if isinstance(result, dict) else {}
    args_obj = arguments if isinstance(arguments, dict) else {}
    if tool_name == "create_task":
        return {
            "operation": "create",
            "target_type": "task",
            "target": "task created",
            "object_id": result_obj.get("task_id"),
            "object_title": result_obj.get("title") or args_obj.get("title"),
            "object_status": result_obj.get("status"),
            "user_id": args_obj.get("user_id"),
        }
    operation = "write"
    target_type = None
    if isinstance(tool_name, str):
        if tool_name.startswith("create_"):
            operation = "create"
            target_type = tool_name.removeprefix("create_")
        elif tool_name.startswith("update_"):
            operation = "update"
            target_type = tool_name.removeprefix("update_")
        elif tool_name.startswith("delete_"):
            operation = "delete"
            target_type = tool_name.removeprefix("delete_")
    object_id = next((result_obj[key] for key in ("id", "task_id", "user_id") if key in result_obj), None)
    return {
        "operation": operation,
        "target_type": target_type,
        "target": f"{target_type or 'object'} {operation}",
        "object_id": object_id,
    }


def event_ref(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "line": event.get("_line_number"),
        "source_artifact": "runtime_events.jsonl",
    }


def compact_event(event: dict[str, Any]) -> dict[str, Any]:
    p = payload(event)
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "component": event.get("component"),
        "line": event.get("_line_number"),
        "phase": "evaluation_replay" if event.get("_after_evaluation_start") else "runtime_execution",
        "state_hash": event.get("state_hash"),
        "state_hash_before": p.get("state_hash_before"),
        "state_hash_after": p.get("state_hash_after"),
        "status": p.get("status"),
        "tool_name": event.get("tool_name"),
        "arguments": p.get("arguments") or p.get("kwargs"),
        "result": p.get("result"),
        "response_content": (
            p.get("response", {}).get("raw", {}).get("content")
            if isinstance(p.get("response"), dict) and isinstance(p.get("response", {}).get("raw"), dict)
            else None
        ),
    }


def find_previous(events: list[dict[str, Any]], sequence: int, event_type: str, tool_name: str | None) -> dict[str, Any] | None:
    for event in reversed(events[: sequence - 1]):
        if event.get("event_type") == event_type and (tool_name is None or event.get("tool_name") == tool_name):
            return event
    return None


def find_next(
    events: list[dict[str, Any]],
    start_sequence: int,
    event_type: str,
    tool_name: str | None,
    max_sequence: int | None = None,
) -> dict[str, Any] | None:
    for event in events[start_sequence:]:
        sequence = int(event.get("_sequence", 0))
        if max_sequence is not None and sequence > max_sequence:
            return None
        if event.get("event_type") == event_type and (tool_name is None or event.get("tool_name") == tool_name):
            return event
    return None


def source_artifact_index(run_dir: pathlib.Path, paths: dict[str, pathlib.Path]) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for label, relative in paths.items():
        path = run_dir / relative
        index[label] = {
            "path": rel(path),
            "present": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
        }
    return index


def build_analysis(run_dir: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any], str]:
    missing = [str(path) for path in REQUIRED_ARTIFACTS.values() if not (run_dir / path).is_file()]
    if missing:
        final_state = {
            "status": MISSING_STATUS,
            "runtime_run_dir": rel(run_dir),
            "missing_inputs": missing,
            "tau2_rerun_performed_by_analysis": False,
            "llm_api_calls_made_by_analysis": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_analysis": False,
            "activegraph_control_added": False,
            "activegraph_controlled_tau2": False,
        }
        raw_log = "\n".join(["runtime DB mutation analysis", f"status={MISSING_STATUS}", f"missing={missing}"]) + "\n"
        return final_state, [], {}, final_state, raw_log

    events = load_jsonl(run_dir / REQUIRED_ARTIFACTS["runtime_events"])
    results = load_json(run_dir / REQUIRED_ARTIFACTS["tau2_results"])
    completion_path = load_json(run_dir / REQUIRED_ARTIFACTS["completion_path"])
    success_analysis = load_json(run_dir / REQUIRED_ARTIFACTS["successful_runtime_trace_analysis"])
    success_final_state = load_json(run_dir / REQUIRED_ARTIFACTS["runtime_success_final_state"])

    evaluation_start_sequence = next(
        (int(event["_sequence"]) for event in events if event.get("event_type") == "evaluation_start"), None
    )
    for event in events:
        event["_after_evaluation_start"] = bool(
            evaluation_start_sequence is not None and int(event["_sequence"]) > evaluation_start_sequence
        )

    reward_info = reward_info_from_results(results)
    checks = action_checks(reward_info)
    write_checks = [check for check in checks if check.get("tool_type") == "write"]
    write_tool_names = sorted(
        {
            str(action_dict(check).get("name"))
            for check in write_checks
            if action_dict(check).get("name") is not None
        }
    )

    if not write_tool_names:
        write_tool_names = sorted(
            {
                str(event.get("tool_name"))
                for event in events
                if event.get("tool_name") and str(event.get("tool_name")).split("_", 1)[0] in {"create", "update", "delete"}
            }
        )

    mutation_events: list[dict[str, Any]] = []
    detected_writes: list[dict[str, Any]] = []
    runtime_starts = [
        event
        for event in events
        if event.get("event_type") == "tool_dispatch_start"
        and event.get("tool_name") in write_tool_names
        and not event.get("_after_evaluation_start")
    ]

    for index, start_event in enumerate(runtime_starts, start=1):
        tool_name = start_event.get("tool_name")
        start_sequence = int(start_event["_sequence"])
        end_event = find_next(events, start_sequence, "tool_dispatch_end", tool_name, evaluation_start_sequence)
        end_sequence = int(end_event["_sequence"]) if end_event is not None else None
        toolkit_start = find_next(events, start_sequence, "toolkit_dispatch_start", tool_name, end_sequence)
        toolkit_end = find_next(events, start_sequence, "toolkit_dispatch_end", tool_name, end_sequence)
        requested = find_previous(events, start_sequence, "tool_call_requested", tool_name)
        observed = find_next(events, end_sequence or start_sequence, "message_observed", None, evaluation_start_sequence)
        start_payload = payload(start_event)
        end_payload = payload(end_event) if end_event is not None else {}
        toolkit_end_payload = payload(toolkit_end) if toolkit_end is not None else {}
        arguments = start_payload.get("arguments") or (payload(toolkit_start).get("kwargs") if toolkit_start else None)
        result_payload = extract_result_payload(end_event, toolkit_end)
        state_hash_before = (
            end_payload.get("state_hash_before")
            or toolkit_end_payload.get("state_hash_before")
            or start_event.get("state_hash")
        )
        state_hash_after = (
            end_payload.get("state_hash_after")
            or toolkit_end_payload.get("state_hash_after")
            or (end_event or {}).get("state_hash")
        )
        related_events = [event for event in [requested, start_event, toolkit_start, toolkit_end, end_event, observed] if event]
        detected = {
            "write_index": index,
            "tool_name": tool_name,
            "requestor": start_payload.get("requestor"),
            "arguments": arguments,
            "tool_result_payload": result_payload,
            "status": end_payload.get("status") or toolkit_end_payload.get("status"),
            "state_hash_before": state_hash_before,
            "state_hash_after": state_hash_after,
            "state_hash_changed": bool(state_hash_before and state_hash_after and state_hash_before != state_hash_after),
            "inferred_mutation": infer_mutation(str(tool_name) if tool_name is not None else None, arguments, result_payload),
            "evidence_event_ids": [event.get("event_id") for event in related_events],
            "evidence": {event.get("event_type", f"event_{i}"): event_ref(event) for i, event in enumerate(related_events)},
        }
        detected_writes.append(detected)
        mutation_events.extend(compact_event(event) for event in related_events)

    evaluation_replay_events = [
        compact_event(event)
        for event in events
        if event.get("_after_evaluation_start") and event.get("tool_name") in write_tool_names
    ]
    mutation_events.extend(evaluation_replay_events)

    db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else {}
    confirmations = {
        "reward": reward_info.get("reward"),
        "db_match": db_check.get("db_match"),
        "db_reward": db_check.get("db_reward"),
        "write_actions_total": len(write_checks),
        "write_actions_matched": sum(1 for check in write_checks if check.get("action_match") is True),
        "action_checks": write_checks,
        "termination_reason": first_simulation(results).get("termination_reason"),
        "normal_stop": first_simulation(results).get("termination_reason") == "user_stop",
        "agent_errors": success_final_state.get("metrics", {}).get("agent_errors"),
        "user_errors": success_final_state.get("metrics", {}).get("user_errors"),
    }

    limitations = []
    if not any("db_before" in event or "db_after" in event for event in events):
        limitations.append(
            "No full before/after DB snapshot artifact is available; the projection uses tool-call evidence, tool-result payloads, state-hash transition evidence, and tau2 reward/DB/action checks."
        )
    if evaluation_replay_events:
        limitations.append(
            "Evaluation-phase tool replay events are retained as confirmation evidence but are not counted as additional live runtime writes."
        )
    if not detected_writes:
        limitations.append("No live runtime write tool dispatch was detected before evaluation_start.")

    confidence = "high" if detected_writes and confirmations["db_match"] is True and confirmations["reward"] == 1.0 else "medium"
    status = PASS_STATUS if detected_writes and confirmations["db_match"] is True else GAP_STATUS

    summary = {
        "status": status,
        "runtime_run_dir": rel(run_dir),
        "source_artifacts": source_artifact_index(run_dir, REQUIRED_ARTIFACTS),
        "inspected_runtime_event_count": len(events),
        "detected_write_count": len(detected_writes),
        "detected_write_tools": write_tool_names,
        "detected_writes": detected_writes,
        "evaluation_replay_write_event_count": len(evaluation_replay_events),
        "confirmation": confirmations,
        "completion_path_status": completion_path.get("status") if isinstance(completion_path, dict) else None,
        "successful_runtime_trace_analysis_status": success_analysis.get("status") if isinstance(success_analysis, dict) else None,
        "confidence": confidence,
        "limitations": limitations,
        "offline_boundaries": {
            "tau2_rerun_performed_by_analysis": False,
            "model_backed_episode_run_by_analysis": False,
            "llm_api_calls_made_by_analysis": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_analysis": False,
            "activegraph_control_added": False,
            "activegraph_controlled_tau2": False,
        },
    }

    evidence_index = {
        "runtime_run_dir": rel(run_dir),
        "source_artifacts": summary["source_artifacts"],
        "write_tool_event_ids": sorted(
            {
                event_id
                for write in detected_writes
                for event_id in write.get("evidence_event_ids", [])
                if event_id is not None
            }
        ),
        "evaluation_replay_event_ids": [event["event_id"] for event in evaluation_replay_events],
        "confirmation_sources": {
            "reward_db_action": rel(run_dir / REQUIRED_ARTIFACTS["tau2_results"]),
            "completion_path": rel(run_dir / REQUIRED_ARTIFACTS["completion_path"]),
            "success_final_state": rel(run_dir / REQUIRED_ARTIFACTS["runtime_success_final_state"]),
            "success_analysis": rel(run_dir / REQUIRED_ARTIFACTS["successful_runtime_trace_analysis"]),
        },
        "field_paths_used": [
            "runtime_events.jsonl[*].event_id",
            "runtime_events.jsonl[*].event_type",
            "runtime_events.jsonl[*].tool_name",
            "runtime_events.jsonl[*].state_hash",
            "runtime_events.jsonl[*].payload.runtime_trace.arguments",
            "runtime_events.jsonl[*].payload.runtime_trace.kwargs",
            "runtime_events.jsonl[*].payload.runtime_trace.result",
            "runtime_events.jsonl[*].payload.runtime_trace.response.raw.content",
            "runtime_events.jsonl[*].payload.runtime_trace.state_hash_before",
            "runtime_events.jsonl[*].payload.runtime_trace.state_hash_after",
            "tau2_output/results.json.simulations[0].reward_info.reward",
            "tau2_output/results.json.simulations[0].reward_info.db_check",
            "tau2_output/results.json.simulations[0].reward_info.action_checks",
            "runtime_success_analysis/final_state.json.metrics",
        ],
    }

    final_state = {
        "status": status,
        "runtime_run_dir": rel(run_dir),
        "detected_write_count": len(detected_writes),
        "detected_write_tools": write_tool_names,
        "inferred_mutations": [write["inferred_mutation"] for write in detected_writes],
        "reward": confirmations["reward"],
        "db_match": confirmations["db_match"],
        "db_reward": confirmations["db_reward"],
        "write_actions_matched": confirmations["write_actions_matched"],
        "write_actions_total": confirmations["write_actions_total"],
        "normal_stop": confirmations["normal_stop"],
        "agent_errors": confirmations["agent_errors"],
        "user_errors": confirmations["user_errors"],
        "confidence": confidence,
        "limitations": limitations,
        **summary["offline_boundaries"],
    }

    raw_log = "\n".join(
        [
            "runtime DB mutation analysis",
            f"runtime_run_dir={rel(run_dir)}",
            f"status={status}",
            f"runtime_events={len(events)}",
            f"detected_write_count={len(detected_writes)}",
            f"detected_write_tools={','.join(write_tool_names)}",
            f"reward={confirmations['reward']}",
            f"db_match={confirmations['db_match']}",
            f"write_actions={confirmations['write_actions_matched']}/{confirmations['write_actions_total']}",
            "tau2_rerun_performed_by_analysis=false",
            "llm_api_calls_made_by_analysis=false",
            "vendor_tau2_bench_mutated_by_analysis=false",
        ]
    ) + "\n"

    return summary, mutation_events, evidence_index, final_state, raw_log


def write_markdown(path: pathlib.Path, summary: dict[str, Any]) -> None:
    writes = summary.get("detected_writes", [])
    write_rows = "\n".join(
        f"| {write.get('write_index')} | `{write.get('tool_name')}` | `{write.get('status')}` | `{write.get('state_hash_before')}` | `{write.get('state_hash_after')}` | `{write.get('inferred_mutation', {}).get('target')}` | `{write.get('inferred_mutation', {}).get('object_id')}` |"
        for write in writes
    )
    if not write_rows:
        write_rows = "| _none_ | _none_ | _none_ | _none_ | _none_ | _none_ | _none_ |"

    evidence_lines = []
    for write in writes:
        evidence_lines.append(f"### Write {write.get('write_index')}: `{write.get('tool_name')}`")
        evidence_lines.append("")
        evidence_lines.append(f"- Arguments: `{json.dumps(write.get('arguments'), sort_keys=True)}`")
        evidence_lines.append(f"- Result payload: `{json.dumps(write.get('tool_result_payload'), sort_keys=True)}`")
        evidence_lines.append(
            f"- Inferred mutation: `{json.dumps(write.get('inferred_mutation'), sort_keys=True)}`"
        )
        evidence_lines.append(f"- Evidence event IDs: `{', '.join(write.get('evidence_event_ids', []))}`")
        evidence_lines.append("")

    confirmation = summary.get("confirmation", {})
    limitations = "\n".join(f"- {item}" for item in summary.get("limitations", [])) or "- None."
    content = f"""# Runtime DB mutation analysis

Status: `{summary.get('status')}`

Runtime run inspected: `{summary.get('runtime_run_dir')}`

This report is an offline deterministic projection from existing runtime-trace and tau2 result artifacts. It did not rerun tau2, did not run a model-backed episode, did not call LLM/API services, did not require API keys, did not mutate `vendor/tau2-bench`, and did not add ActiveGraph control over tau2.

## Detected write tools

| # | Tool | Status | State hash before | State hash after | Inferred target | Resulting object ID |
| ---: | --- | --- | --- | --- | --- | --- |
{write_rows}

{''.join(line + chr(10) for line in evidence_lines)}## Reward / DB / action confirmation

- Reward: `{confirmation.get('reward')}`
- DB match: `{confirmation.get('db_match')}`
- DB reward: `{confirmation.get('db_reward')}`
- Write actions matched: `{confirmation.get('write_actions_matched')}/{confirmation.get('write_actions_total')}`
- Normal stop: `{confirmation.get('normal_stop')}`
- Agent errors: `{confirmation.get('agent_errors')}`
- User errors: `{confirmation.get('user_errors')}`

## Evidence fields used

- Runtime tool dispatch start/end events.
- Toolkit dispatch result payloads.
- Tool message response content.
- State hash before/after fields.
- tau2 reward, DB check, and write action checks from `tau2_output/results.json`.
- Existing successful runtime-trace analysis final metrics.

## Confidence and limitations

Confidence: `{summary.get('confidence')}`

{limitations}
"""
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_dir = args.runtime_run_dir.resolve()
    out_dir = args.output_dir.resolve() if args.output_dir is not None else run_dir / "db_mutation_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary, mutation_events, evidence_index, final_state, raw_log = build_analysis(run_dir)
    except Exception as exc:  # noqa: BLE001 - command-line report should emit artifact on unexpected failure.
        final_state = {
            "status": "runtime_db_mutation_analysis_failed",
            "runtime_run_dir": rel(run_dir),
            "error": str(exc),
            "tau2_rerun_performed_by_analysis": False,
            "llm_api_calls_made_by_analysis": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_analysis": False,
            "activegraph_control_added": False,
            "activegraph_controlled_tau2": False,
        }
        write_json(out_dir / "final_state.json", final_state)
        (out_dir / "raw.log").write_text(f"runtime DB mutation analysis\nstatus=failed\nerror={exc}\n", encoding="utf-8")
        print(out_dir)
        print(final_state["status"])
        return 1

    write_json(out_dir / "db_mutation_summary.json", summary)
    write_markdown(out_dir / "db_mutation_summary.md", summary)
    with (out_dir / "mutation_events.jsonl").open("w", encoding="utf-8") as handle:
        for event in mutation_events:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
    write_json(out_dir / "mutation_evidence_index.json", evidence_index)
    write_json(out_dir / "final_state.json", final_state)
    (out_dir / "raw.log").write_text(raw_log, encoding="utf-8")

    print(out_dir)
    print(final_state["status"])
    return 0 if final_state["status"] in {PASS_STATUS, GAP_STATUS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
