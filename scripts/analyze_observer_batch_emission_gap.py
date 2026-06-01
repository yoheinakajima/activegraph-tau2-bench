#!/usr/bin/env python3
"""Offline-diagnose passive observer emission coverage for a tau2 batch run.

This script reads already-produced runtime trace and observer artifacts only. It
never runs tau2, invokes model-backed episodes, calls LLM/API services, requires
API keys, mutates vendored tau2-bench code, or enables ActiveGraph control.
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime as dt
import json
import pathlib
import re
import stat
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_DIR_NAME = "observer_emission_gap_analysis"
STATUS_PASSED = "observer_emission_gap_analysis_completed"
STATUS_MISSED_WRITES = "observer_emission_gap_analysis_completed_with_missed_write_candidates"
STATUS_NO_WRITES = "observer_emission_gap_analysis_completed_no_write_candidates"
STATUS_INPUTS_MISSING = "observer_emission_gap_analysis_inputs_missing"

RUNTIME_DISPATCH_TYPES = {"tool_dispatch_start", "toolkit_dispatch_start"}
CANDIDATE_DISPATCH_TYPES = {"tool_dispatch_start", "toolkit_dispatch_start", "tool_call_requested"}
WRITE_NAME_HINTS = (
    "book",
    "cancel",
    "update",
    "modify",
    "create",
    "delete",
    "send",
    "write",
    "refund",
    "payment",
    "reserve",
)
READ_NAME_PREFIXES = ("get_", "list_", "search_", "find_", "lookup_", "check_")


class AnalysisInputError(RuntimeError):
    """Raised when required offline artifacts are missing or invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline-analyze observer emission coverage for a runtime-traced tau2 batch.")
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


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_path(path: pathlib.Path) -> pathlib.Path:
    return path if path.is_absolute() else REPO_ROOT / path


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise AnalysisInputError(f"missing required {label}: {rel(path)}")


def load_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnalysisInputError(f"invalid JSON in {rel(path)}: {exc}") from exc


def load_optional_json(path: pathlib.Path) -> Any | None:
    if not path.is_file():
        return None
    return load_json(path)


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnalysisInputError(f"invalid JSONL in {rel(path)} line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise AnalysisInputError(f"JSONL row in {rel(path)} line {line_number} is not an object")
        row["_line_number"] = line_number
        rows.append(row)
    return rows


def count_jsonl_lines(path: pathlib.Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def runtime_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("runtime_trace")
    return nested if isinstance(nested, dict) else payload


def maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def get_observer_write_hints() -> set[str]:
    observer_path = REPO_ROOT / "experiments" / "write_intent_observer" / "observer.py"
    text = observer_path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "WRITE_TOOL_HINTS":
                    value = ast.literal_eval(node.value)
                    return {str(item) for item in value}
    return set()


def parse_airline_tool_types() -> tuple[dict[str, str], list[dict[str, Any]]]:
    tools_path = REPO_ROOT / "vendor" / "tau2-bench" / "src" / "tau2" / "domains" / "airline" / "tools.py"
    tool_types: dict[str, str] = {}
    source_rows: list[dict[str, Any]] = []
    if not tools_path.is_file():
        return tool_types, source_rows
    pending_type: str | None = None
    decorator_re = re.compile(r"@is_tool\(ToolType\.([A-Z_]+)\)")
    def_re = re.compile(r"\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    for line_number, line in enumerate(tools_path.read_text(encoding="utf-8").splitlines(), start=1):
        match = decorator_re.search(line)
        if match:
            pending_type = match.group(1).lower()
            continue
        def_match = def_re.match(line)
        if def_match and pending_type:
            name = def_match.group(1)
            tool_types[name] = pending_type
            source_rows.append({"tool_name": name, "tool_type": pending_type, "source_path": rel(tools_path), "line": line_number})
            pending_type = None
    return tool_types, source_rows


def classify_tool(tool_name: str | None, airline_tool_types: dict[str, str], observer_hints: set[str]) -> dict[str, Any]:
    name = str(tool_name or "")
    source_type = airline_tool_types.get(name)
    name_hint_write = any(hint in name for hint in WRITE_NAME_HINTS) and not name.startswith(READ_NAME_PREFIXES)
    recognized_by_observer = name in observer_hints
    likely_write = source_type == "write" or recognized_by_observer or name_hint_write
    reasons: list[str] = []
    if source_type:
        reasons.append(f"airline_source_tool_type:{source_type}")
    if recognized_by_observer:
        reasons.append("observer_WRITE_TOOL_HINTS")
    if name_hint_write:
        reasons.append("write_name_hint")
    if name.startswith(READ_NAME_PREFIXES):
        reasons.append("read_name_prefix")
    return {
        "tool_name": name or None,
        "airline_source_tool_type": source_type,
        "recognized_by_observer": recognized_by_observer,
        "likely_write": bool(likely_write),
        "classification_reasons": reasons,
    }


def enrich_events_with_task_context(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_task_id: str | None = None
    enriched: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        event_type = event.get("event_type")
        explicit_task_id = event.get("task_id")
        if event_type == "simulation_start" and explicit_task_id is not None:
            current_task_id = str(explicit_task_id)
        inferred_task_id = str(explicit_task_id) if explicit_task_id is not None else current_task_id
        row = dict(event)
        row["_sequence_index"] = index
        row["inferred_task_id"] = inferred_task_id
        enriched.append(row)
        if event_type == "simulation_end":
            current_task_id = None
    return enriched


def result_path(run_dir: pathlib.Path) -> pathlib.Path:
    for candidate in (run_dir / "tau2_output" / "results.json", run_dir / "tau2_artifacts" / "results.json"):
        if candidate.is_file():
            return candidate
    return run_dir / "tau2_output" / "results.json"


def collect_results_tool_calls(results: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_task: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    simulations = results.get("simulations") if isinstance(results.get("simulations"), list) else []
    for sim in simulations:
        if not isinstance(sim, dict):
            continue
        task_id = str(sim.get("task_id"))
        messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            for call_index, call in enumerate(message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []):
                if not isinstance(call, dict):
                    continue
                by_task[task_id].append(
                    {
                        "message_index": message_index,
                        "call_index": call_index,
                        "turn_idx": message.get("turn_idx"),
                        "tool_name": call.get("name"),
                        "arguments": call.get("arguments"),
                        "requestor": call.get("requestor"),
                    }
                )
    return dict(by_task)


def summarize_results(results: dict[str, Any]) -> dict[str, Any]:
    simulations = results.get("simulations") if isinstance(results.get("simulations"), list) else []
    task_rows = []
    total_reward = 0.0
    reward_count = 0
    pass_count = 0
    normal_stop = 0
    max_steps = 0
    read_matched = read_total = db_matched = db_total = 0
    for sim in simulations:
        if not isinstance(sim, dict):
            continue
        reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
        reward = reward_info.get("reward")
        if isinstance(reward, (int, float)):
            total_reward += float(reward)
            reward_count += 1
            if reward >= 1.0:
                pass_count += 1
        termination_reason = sim.get("termination_reason")
        if termination_reason == "max_steps":
            max_steps += 1
        else:
            normal_stop += 1
        action_checks = reward_info.get("action_checks") if isinstance(reward_info.get("action_checks"), list) else []
        task_read_total = task_read_matched = 0
        for check in action_checks:
            if isinstance(check, dict) and check.get("tool_type") == "read":
                task_read_total += 1
                if check.get("action_match") is True:
                    task_read_matched += 1
        read_total += task_read_total
        read_matched += task_read_matched
        db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else {}
        if db_check:
            db_total += 1
            if db_check.get("db_match") is True:
                db_matched += 1
        task_rows.append(
            {
                "simulation_id": sim.get("id"),
                "task_id": sim.get("task_id"),
                "termination_reason": termination_reason,
                "reward": reward,
                "db_match": db_check.get("db_match"),
                "read_actions_matched": task_read_matched,
                "read_actions_total": task_read_total,
                "message_count": len(sim.get("messages") if isinstance(sim.get("messages"), list) else []),
            }
        )
    return {
        "total_simulations": len(simulations),
        "total_tasks": len({str(row.get("task_id")) for row in task_rows}),
        "average_reward": round(total_reward / reward_count, 3) if reward_count else None,
        "pass_rate": round(pass_count / reward_count, 3) if reward_count else None,
        "read_actions": {"matched": read_matched, "total": read_total},
        "db_match": {"matched": db_matched, "total": db_total},
        "normal_stop": normal_stop,
        "max_steps": max_steps,
        "tasks": task_rows,
    }


def file_writable_status(path: pathlib.Path) -> dict[str, Any]:
    exists = path.exists()
    parent = path.parent if path.parent.exists() else path.parent.parent
    mode = path.stat().st_mode if exists else None
    return {
        "path": rel(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "non_empty_jsonl_lines": count_jsonl_lines(path) if path.suffix == ".jsonl" else None,
        "owner_write_bit": bool(mode and mode & stat.S_IWUSR),
        "parent_exists": path.parent.exists(),
        "parent_owner_write_bit": bool(parent.exists() and parent.stat().st_mode & stat.S_IWUSR),
    }


def build_dispatch_index(events: list[dict[str, Any]], airline_tool_types: dict[str, str], observer_hints: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dispatch_rows: list[dict[str, Any]] = []
    write_candidates: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") not in CANDIDATE_DISPATCH_TYPES:
            continue
        payload = runtime_payload(event)
        tool_name = event.get("tool_name")
        classification = classify_tool(tool_name, airline_tool_types, observer_hints)
        args = payload.get("arguments") if "arguments" in payload else payload.get("kwargs")
        row = {
            "sequence_index": event.get("_sequence_index"),
            "line_number": event.get("_line_number"),
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "component": event.get("component"),
            "task_id": event.get("task_id"),
            "inferred_task_id": event.get("inferred_task_id"),
            "turn_index": event.get("turn_index"),
            "tool_name": tool_name,
            "arguments": args,
            "state_hash": event.get("state_hash"),
            **classification,
        }
        dispatch_rows.append(row)
        if event.get("event_type") in RUNTIME_DISPATCH_TYPES and classification["likely_write"]:
            write_candidates.append(row)
    return dispatch_rows, write_candidates


def unique_runtime_write_candidates(write_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse environment/toolkit double-observation of the same logical write."""
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in write_candidates:
        key = (row.get("inferred_task_id"), row.get("tool_name"), json.dumps(row.get("arguments"), sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def build_task_coverage(
    results: dict[str, Any],
    dispatch_rows: list[dict[str, Any]],
    write_candidates: list[dict[str, Any]],
    observer_counts: dict[str, int],
) -> dict[str, Any]:
    results_calls = collect_results_tool_calls(results)
    task_ids = sorted({str(task) for task in results_calls} | {str(row.get("inferred_task_id")) for row in dispatch_rows if row.get("inferred_task_id") is not None})
    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        task_dispatches = [row for row in dispatch_rows if str(row.get("inferred_task_id")) == task_id]
        task_writes = [row for row in write_candidates if str(row.get("inferred_task_id")) == task_id]
        requested = [row for row in task_dispatches if row.get("event_type") == "tool_call_requested"]
        rows.append(
            {
                "task_id": task_id,
                "runtime_dispatch_events": len([row for row in task_dispatches if row.get("event_type") in RUNTIME_DISPATCH_TYPES]),
                "tool_call_requested_events": len(requested),
                "tool_names": sorted({str(row.get("tool_name")) for row in task_dispatches if row.get("tool_name")}),
                "likely_write_candidate_events": len(task_writes),
                "likely_write_candidate_tools": sorted({str(row.get("tool_name")) for row in task_writes if row.get("tool_name")}),
                "observer_event_rows": observer_counts.get(task_id, 0),
                "results_tool_calls": len(results_calls.get(task_id, [])),
                "results_tool_names": sorted({str(row.get("tool_name")) for row in results_calls.get(task_id, []) if row.get("tool_name")}),
            }
        )
    return {
        "tasks_with_write_candidates": [row["task_id"] for row in rows if row["likely_write_candidate_events"] > 0],
        "tasks_with_observer_events": [row["task_id"] for row in rows if row["observer_event_rows"] > 0],
        "tasks": rows,
    }


def build_summary_md(analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    observer = analysis["observer_artifacts"]
    recommendation = analysis["recommendation"]
    hook = analysis["observer_hook_coverage"]
    task_cov = analysis["task_level_observer_coverage"]
    lines = [
        "# Observer Batch Emission Gap Analysis",
        "",
        "## Offline boundary",
        "",
        "- tau2 was not rerun by this analyzer.",
        "- No model-backed episode was run by this analyzer.",
        "- No LLM/API calls were made by this analyzer.",
        "- ActiveGraph control was not added or enabled.",
        "- `vendor/tau2-bench/` was read only for source classification and was not mutated.",
        "",
        "## Batch inspected",
        "",
        f"- Run directory: `{analysis['run_dir']}`",
        f"- Runtime status: `{summary.get('runtime_status')}`",
        f"- Total simulations: {summary.get('total_simulations')}",
        f"- Total tasks: {summary.get('total_tasks')}",
        f"- Runtime events: {summary.get('runtime_event_count')}",
        f"- Average reward: {summary.get('average_reward')}",
        f"- Pass rate: {summary.get('pass_rate')}",
        f"- Read actions: {summary.get('read_actions', {}).get('matched')}/{summary.get('read_actions', {}).get('total')}",
        f"- DB match: {summary.get('db_match', {}).get('matched')}/{summary.get('db_match', {}).get('total')}",
        f"- Normal stop: {summary.get('normal_stop')}",
        f"- Max steps: {summary.get('max_steps')}",
        "",
        "## Observer files",
        "",
    ]
    for name, info in observer.items():
        lines.append(f"- `{name}`: exists={info.get('exists')}, size={info.get('size_bytes')}, jsonl_lines={info.get('non_empty_jsonl_lines')}")
    lines.extend(
        [
            "",
            "## Runtime tool dispatch coverage",
            "",
            f"- `tool_dispatch_start` events: {summary.get('tool_dispatch_start_count')}",
            f"- `toolkit_dispatch_start` events: {summary.get('toolkit_dispatch_start_count')}",
            f"- Combined runtime dispatch start events: {summary.get('combined_runtime_dispatch_start_count')}",
            f"- `tool_call_requested` events: {summary.get('tool_call_requested_count')}",
            f"- Tool names observed: {', '.join(summary.get('tool_names_observed') or [])}",
            f"- Likely write candidate events: {summary.get('likely_write_candidate_event_count')}",
            f"- Unique likely write candidates after collapsing environment/toolkit duplicates: {summary.get('unique_likely_write_candidate_count')}",
            f"- Likely write tools observed: {', '.join(summary.get('likely_write_tools_observed') or []) or 'none'}",
            f"- Recognized observer write tools observed: {', '.join(hook.get('recognized_observer_write_tools_observed') or []) or 'none'}",
            f"- Likely write tools missed by observer hints: {', '.join(hook.get('likely_write_tools_not_in_observer_hints') or []) or 'none'}",
            "",
            "## Task-level coverage",
            "",
            "| Task | Runtime dispatches | Likely write events | Likely write tools | Observer rows |",
            "| --- | ---: | ---: | --- | ---: |",
        ]
    )
    for row in task_cov["tasks"]:
        lines.append(
            f"| {row['task_id']} | {row['runtime_dispatch_events']} | {row['likely_write_candidate_events']} | "
            f"{', '.join(row['likely_write_candidate_tools']) or 'none'} | {row['observer_event_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Finding",
            "",
            f"- Likely reason: **{recommendation['likely_reason']}**",
            f"- Recommendation: **{recommendation['action']}**",
            f"- Rationale: {recommendation['rationale']}",
            "",
            "## Answers to requested diagnostic questions",
            "",
            f"- Did any `book_reservation`/update/cancel/write tool occur? {summary.get('book_update_cancel_write_answer')}",
            f"- Which tasks had write candidates? {', '.join(task_cov.get('tasks_with_write_candidates') or []) or 'none'}",
            f"- Did observer emit zero because there were no recognized writes? {recommendation.get('zero_because_no_recognized_writes')}",
            f"- Did observer miss likely write candidates? {recommendation.get('observer_missed_likely_write_candidates')}",
            f"- Did multi-task/batch context propagation appear to be the main cause? {recommendation.get('batch_context_propagation_suspected')}",
            f"- Did observer context/artifact paths exist and stay writable? {recommendation.get('observer_artifact_paths_writable')}",
            f"- Did `observer_enabled` appear in final state? {summary.get('observer_enabled_in_final_state')}",
            f"- Are files empty due to hook logic or no observed write candidate match? {recommendation.get('empty_file_explanation')}",
            "",
            "## Output files",
            "",
        ]
    )
    for path in analysis["outputs"]:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    run_dir = resolve_path(args.runtime_run_dir)
    output_dir = resolve_path(args.output_dir) if args.output_dir else run_dir / OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    logs: list[str] = []

    def log(message: str) -> None:
        logs.append(f"{utc_now()} {message}")

    try:
        require_file(run_dir / "runtime_events.jsonl", "runtime events")
        require_file(run_dir / "runtime_trace_final_state.json", "runtime final state")
        require_file(result_path(run_dir), "tau2 results")

        runtime_events = enrich_events_with_task_context(load_jsonl(run_dir / "runtime_events.jsonl"))
        runtime_final_state = load_json(run_dir / "runtime_trace_final_state.json")
        observer_final_state = load_optional_json(run_dir / "observer_final_state.json")
        results = load_json(result_path(run_dir))
        observer_events = load_jsonl(run_dir / "observer_events.jsonl")
        constraint_snapshots = load_jsonl(run_dir / "constraint_ledger_snapshots.jsonl")
        write_diffs = load_jsonl(run_dir / "write_intent_diffs.jsonl")
        raw_log_text = (run_dir / "raw.log").read_text(encoding="utf-8", errors="replace") if (run_dir / "raw.log").is_file() else ""

        observer_hints = get_observer_write_hints()
        airline_tool_types, airline_source_rows = parse_airline_tool_types()
        dispatch_rows, write_candidate_events = build_dispatch_index(runtime_events, airline_tool_types, observer_hints)
        unique_writes = unique_runtime_write_candidates(write_candidate_events)
        results_summary = summarize_results(results)

        event_counts = collections.Counter(str(event.get("event_type")) for event in runtime_events)
        tool_counter = collections.Counter(str(row.get("tool_name")) for row in dispatch_rows if row.get("tool_name"))
        runtime_dispatch_tool_counter = collections.Counter(str(row.get("tool_name")) for row in dispatch_rows if row.get("event_type") in RUNTIME_DISPATCH_TYPES and row.get("tool_name"))
        likely_write_tools = sorted({str(row.get("tool_name")) for row in write_candidate_events if row.get("tool_name")})
        recognized_write_tools_observed = sorted(set(likely_write_tools) & observer_hints)
        likely_write_tools_not_in_observer_hints = sorted(set(likely_write_tools) - observer_hints)
        book_update_cancel = [tool for tool in likely_write_tools if tool == "book_reservation" or "update" in tool or "cancel" in tool or airline_tool_types.get(tool) == "write"]

        observer_counts_by_task = collections.Counter(str(event.get("task_id") or event.get("case_id")) for event in observer_events if event.get("task_id") or event.get("case_id"))
        task_coverage = build_task_coverage(results, dispatch_rows, write_candidate_events, dict(observer_counts_by_task))

        observer_files = {
            "observer_events.jsonl": file_writable_status(run_dir / "observer_events.jsonl"),
            "constraint_ledger_snapshots.jsonl": file_writable_status(run_dir / "constraint_ledger_snapshots.jsonl"),
            "write_intent_diffs.jsonl": file_writable_status(run_dir / "write_intent_diffs.jsonl"),
            "observer_final_state.json": file_writable_status(run_dir / "observer_final_state.json"),
            "raw.log": file_writable_status(run_dir / "raw.log"),
        }
        paths_writable = all(bool(info.get("exists")) and bool(info.get("owner_write_bit")) and bool(info.get("parent_owner_write_bit")) for info in observer_files.values())

        observer_enabled = bool(runtime_final_state.get("write_intent_observer_enabled"))
        observer_event_rows = len(observer_events)
        likely_write_count = len(write_candidate_events)
        recognized_candidate_count = sum(1 for row in write_candidate_events if row.get("recognized_by_observer"))
        if likely_write_count == 0:
            status = STATUS_NO_WRITES
            likely_reason = "no runtime write candidates were observed"
            action = "no code change needed if this run's task mix genuinely contained no writes"
            rationale = "The runtime dispatch stream did not contain source-classified or name-hinted write tools."
        elif recognized_candidate_count == 0 and observer_enabled and paths_writable:
            status = STATUS_MISSED_WRITES
            likely_reason = "runtime write tools occurred but were outside WRITE_TOOL_HINTS"
            action = "patch observer hook coverage"
            rationale = "Airline source-classified write tools were dispatched, but none matched the observer's current recognized write-tool set, so observe_runtime_tool_dispatch returned before emitting artifacts."
        elif not observer_enabled or not paths_writable:
            status = STATUS_MISSED_WRITES
            likely_reason = "observer context or artifact writer was unavailable"
            action = "patch batch context propagation or artifact writer initialization"
            rationale = "Runtime candidates existed, but observer enablement or artifact path writability was missing."
        elif recognized_candidate_count > 0 and observer_event_rows == 0:
            status = STATUS_MISSED_WRITES
            likely_reason = "recognized writes occurred but observer emitted no rows"
            action = "patch runtime hook emission path and batch context propagation"
            rationale = "At least one dispatched write matched observer hints, yet observer JSONL artifacts remained empty."
        else:
            status = STATUS_PASSED
            likely_reason = "observer output aligns with recognized write coverage"
            action = "no code change needed for this diagnostic"
            rationale = "The observer artifacts are consistent with the recognized write candidates observed in the runtime trace."

        summary = {
            **results_summary,
            "runtime_status": runtime_final_state.get("status"),
            "runtime_event_count": len(runtime_events),
            "runtime_event_type_counts": dict(sorted(event_counts.items())),
            "tool_dispatch_start_count": event_counts.get("tool_dispatch_start", 0),
            "toolkit_dispatch_start_count": event_counts.get("toolkit_dispatch_start", 0),
            "combined_runtime_dispatch_start_count": event_counts.get("tool_dispatch_start", 0) + event_counts.get("toolkit_dispatch_start", 0),
            "tool_call_requested_count": event_counts.get("tool_call_requested", 0),
            "tool_names_observed": sorted(tool_counter),
            "runtime_dispatch_tool_counts": dict(sorted(runtime_dispatch_tool_counter.items())),
            "likely_write_candidate_event_count": likely_write_count,
            "unique_likely_write_candidate_count": len(unique_writes),
            "likely_write_tools_observed": likely_write_tools,
            "recognized_observer_write_candidate_event_count": recognized_candidate_count,
            "observer_enabled_in_final_state": observer_enabled,
            "observer_final_state_event_count": (observer_final_state or {}).get("event_count"),
            "raw_log_mentions_observer": "observer" in raw_log_text.lower(),
            "book_update_cancel_write_answer": (", ".join(book_update_cancel) if book_update_cancel else "No book/update/cancel/source-classified write tool was observed."),
        }

        hook_coverage = {
            "observer_write_tool_hints": sorted(observer_hints),
            "airline_source_tool_types": airline_source_rows,
            "observed_tool_counts": dict(sorted(tool_counter.items())),
            "runtime_dispatch_tool_counts": dict(sorted(runtime_dispatch_tool_counter.items())),
            "observed_likely_write_tools": likely_write_tools,
            "recognized_observer_write_tools_observed": recognized_write_tools_observed,
            "likely_write_tools_not_in_observer_hints": likely_write_tools_not_in_observer_hints,
            "recognized_candidate_event_count": recognized_candidate_count,
            "missed_likely_write_candidate_event_count": likely_write_count - recognized_candidate_count,
            "coverage_ratio": round(recognized_candidate_count / likely_write_count, 3) if likely_write_count else None,
        }

        recommendation = {
            "status": status,
            "likely_reason": likely_reason,
            "action": action,
            "rationale": rationale,
            "no_code_change_needed_if_no_write_candidates_occurred": likely_write_count == 0,
            "patch_hook_coverage_if_write_candidates_occurred_but_observer_missed": likely_write_count > 0 and recognized_candidate_count < likely_write_count,
            "patch_batch_context_propagation_if_observer_enabled_state_or_artifact_writer_missing": likely_write_count > 0 and (not observer_enabled or not paths_writable or (recognized_candidate_count > 0 and observer_event_rows == 0)),
            "zero_because_no_recognized_writes": likely_write_count > 0 and recognized_candidate_count == 0,
            "observer_missed_likely_write_candidates": likely_write_count > 0 and recognized_candidate_count < likely_write_count,
            "batch_context_propagation_suspected": (not observer_enabled or not paths_writable or (recognized_candidate_count > 0 and observer_event_rows == 0)),
            "observer_artifact_paths_writable": paths_writable,
            "empty_file_explanation": "hook logic: observed likely airline writes did not match WRITE_TOOL_HINTS" if likely_write_count and recognized_candidate_count == 0 else ("no observed write candidate matched" if likely_write_count == 0 else likely_reason),
        }

        runtime_write_candidate_index = {
            "schema": "observer_emission_gap.runtime_write_candidate_index.v1",
            "run_dir": rel(run_dir),
            "created_at": utc_now(),
            "dispatch_events": dispatch_rows,
            "likely_write_candidate_events": write_candidate_events,
            "unique_likely_write_candidates": unique_writes,
        }

        final_state = {
            "schema": "observer_emission_gap.final_state.v1",
            "status": status,
            "run_dir": rel(run_dir),
            "output_dir": rel(output_dir),
            "created_at": utc_now(),
            "tau2_rerun_by_analyzer": False,
            "model_backed_episode_run_by_analyzer": False,
            "llm_or_api_calls_made_by_analyzer": False,
            "api_keys_required": False,
            "activegraph_control_added": False,
            "vendor_tau2_bench_mutated": False,
            "runtime_events_read": len(runtime_events),
            "likely_write_candidate_events": likely_write_count,
            "observer_event_rows": observer_event_rows,
            "recommendation": recommendation,
        }

        outputs = [
            output_dir / "observer_emission_gap_analysis.json",
            output_dir / "observer_emission_gap_summary.md",
            output_dir / "runtime_write_candidate_index.json",
            output_dir / "observer_hook_coverage.json",
            output_dir / "task_level_observer_coverage.json",
            output_dir / "final_state.json",
            output_dir / "raw.log",
        ]

        analysis = {
            "schema": "observer_emission_gap.analysis.v1",
            "run_dir": rel(run_dir),
            "output_dir": rel(output_dir),
            "created_at": utc_now(),
            "summary": summary,
            "observer_artifacts": observer_files,
            "observer_final_state": observer_final_state,
            "runtime_trace_final_state": runtime_final_state,
            "observer_hook_coverage": hook_coverage,
            "task_level_observer_coverage": task_coverage,
            "recommendation": recommendation,
            "outputs": [rel(path) for path in outputs],
            "offline_boundary": final_state,
        }

        write_json(output_dir / "runtime_write_candidate_index.json", runtime_write_candidate_index)
        write_json(output_dir / "observer_hook_coverage.json", hook_coverage)
        write_json(output_dir / "task_level_observer_coverage.json", task_coverage)
        write_json(output_dir / "final_state.json", final_state)
        write_json(output_dir / "observer_emission_gap_analysis.json", analysis)
        (output_dir / "observer_emission_gap_summary.md").write_text(build_summary_md(analysis), encoding="utf-8")
        log(f"status={status}")
        log(f"runtime_events={len(runtime_events)} likely_write_candidate_events={likely_write_count} observer_events={observer_event_rows}")
        log(f"likely_reason={likely_reason}")
        (output_dir / "raw.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
        print(f"status={status}")
        print(f"wrote={rel(output_dir)}")
        return 0
    except AnalysisInputError as exc:
        final_state = {
            "schema": "observer_emission_gap.final_state.v1",
            "status": STATUS_INPUTS_MISSING,
            "run_dir": rel(run_dir),
            "output_dir": rel(output_dir),
            "created_at": utc_now(),
            "error": str(exc),
            "tau2_rerun_by_analyzer": False,
            "llm_or_api_calls_made_by_analyzer": False,
            "vendor_tau2_bench_mutated": False,
        }
        write_json(output_dir / "final_state.json", final_state)
        log(f"error={exc}")
        (output_dir / "raw.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
