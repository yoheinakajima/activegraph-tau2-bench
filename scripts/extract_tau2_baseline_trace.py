#!/usr/bin/env python3
"""Extract a normalized trace from a completed tau2 model baseline run.

This is a post-run artifact parser only. It does not import or execute tau2, does
not call LLM/API services, and writes extraction artifacts under the supplied run
directory.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PASSED_STATUS = "tau2_model_baseline_passed"
TRACE_PHASE = "real_tau2_model_baseline_extracted"
TRACE_MODE = "post_run_extraction"
SCHEMA_VERSION = "trace_event.v1"
OUTPUT_DIR_NAME = "extracted_trace"
SOURCE_FILE_NAMES = {
    "raw.log",
    "summary.md",
    "final_state.json",
    "tau2_output/results.json",
    "tau2_artifacts/results.json",
}
EVENT_FIELDS = [
    "event_id",
    "timestamp",
    "run_id",
    "phase",
    "component",
    "event_type",
    "task_id",
    "turn_index",
    "tool_name",
    "message_role",
    "state_hash",
    "payload",
    "parent_event_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a post-run normalized trace from completed tau2 model baseline artifacts."
    )
    parser.add_argument("--run-dir", required=True, type=pathlib.Path, help="Completed tau2 model baseline run directory.")
    parser.add_argument(
        "--allow-failed",
        action="store_true",
        help="Allow extraction when final_state.json is not tau2_model_baseline_passed.",
    )
    return parser.parse_args()


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def state_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parser_for(path: pathlib.Path, run_dir: pathlib.Path) -> str:
    name = str(path.relative_to(run_dir))
    if name in {"final_state.json", "tau2_output/results.json", "tau2_artifacts/results.json"}:
        return "json"
    if name == "summary.md":
        return "markdown_metadata"
    if name == "raw.log":
        return "tau2_wrapper_raw_log_text"
    return "unsupported"


def source_artifact_files(run_dir: pathlib.Path) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for relative in sorted(SOURCE_FILE_NAMES):
        path = run_dir / relative
        if path.is_file():
            found.append(path)
    return found


def artifact_entry(path: pathlib.Path, run_dir: pathlib.Path, parser: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": rel(path),
        "relative_path": str(path.relative_to(run_dir)),
        "size_bytes": len(data),
        "sha256": content_hash_bytes(data),
        "parser": parser,
        "contributed_events": False,
        "event_count": 0,
        "notes": [],
    }


@dataclasses.dataclass
class EventWriter:
    path: pathlib.Path
    run_id: str

    def __post_init__(self) -> None:
        self.next_id = 1
        self.events: list[dict[str, Any]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(
        self,
        *,
        component: str,
        event_type: str,
        task_id: str | None = None,
        turn_index: int | None = None,
        tool_name: str | None = None,
        message_role: str | None = None,
        state_hash_value: str | None = None,
        payload: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
        timestamp: str | None = None,
    ) -> str:
        event = {
            "event_id": f"evt-{self.next_id:06d}",
            "timestamp": timestamp or utc_now(),
            "run_id": self.run_id,
            "phase": TRACE_PHASE,
            "component": component,
            "event_type": event_type,
            "task_id": task_id,
            "turn_index": turn_index,
            "tool_name": tool_name,
            "message_role": message_role,
            "state_hash": state_hash_value,
            "payload": payload or {},
            "parent_event_id": parent_event_id,
        }
        self.next_id += 1
        ordered = {field: event[field] for field in EVENT_FIELDS}
        self.events.append(ordered)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(ordered, sort_keys=False, ensure_ascii=False) + "\n")
        return ordered["event_id"]


def compact_message_payload(message: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trace_mode": TRACE_MODE,
        "fixture_backed": False,
        "tau2_rerun": False,
        "llm_api_calls_made_by_extractor": False,
        "content": message.get("content"),
        "has_tool_calls": bool(message.get("tool_calls")),
        "is_audio": message.get("is_audio"),
        "cost": message.get("cost"),
        "usage": message.get("usage"),
        "contains_speech": message.get("contains_speech"),
    }
    if message.get("id"):
        payload["message_id"] = message.get("id")
    raw_data = message.get("raw_data")
    if isinstance(raw_data, dict):
        payload["raw_data_summary"] = {
            "id": raw_data.get("id"),
            "model": raw_data.get("model"),
            "object": raw_data.get("object"),
            "created": raw_data.get("created"),
            "usage": raw_data.get("usage"),
        }
    return payload


def extract_events(
    *,
    run_dir: pathlib.Path,
    final_state: dict[str, Any],
    results: dict[str, Any] | None,
    writer: EventWriter,
) -> tuple[list[str], list[str]]:
    limitations: list[str] = []
    event_types: list[str] = []

    def emit(**kwargs: Any) -> str:
        event_id = writer.emit(**kwargs)
        event_types.append(kwargs["event_type"])
        return event_id

    common_flags = {
        "trace_mode": TRACE_MODE,
        "fixture_backed": False,
        "tau2_rerun": False,
        "llm_api_calls_made_by_extractor": False,
    }
    run_id = writer.run_id
    root_id = emit(
        component="baseline.wrapper",
        event_type="baseline.run.started",
        timestamp=final_state.get("timestamp_utc") or utc_now(),
        payload={
            **common_flags,
            "source_run_dir": rel(run_dir),
            "status": final_state.get("status"),
            "provider": final_state.get("provider"),
            "model": final_state.get("model"),
            "tau2_model_name": final_state.get("tau2_model_name"),
            "domain": final_state.get("domain"),
            "task_id": final_state.get("task_id"),
            "max_steps": final_state.get("max_steps"),
            "concurrency": final_state.get("concurrency"),
            "run_id_source": "run directory name",
        },
    )
    event_types[-1] = "baseline.run.started"

    config_parent = root_id
    config_payload = {
        **common_flags,
        "tau2_command": final_state.get("tau2_command"),
        "tau2_cwd": final_state.get("tau2_cwd"),
        "tau2_output_path": final_state.get("tau2_output_path"),
        "paid_api_acknowledged_in_source_run": final_state.get("paid_api_acknowledged"),
        "extractor_api_key_requirement": False,
    }
    if results and isinstance(results.get("info"), dict):
        info = results["info"]
        config_payload["tau2_results_info"] = {
            "git_commit": info.get("git_commit"),
            "num_trials": info.get("num_trials"),
            "max_steps": info.get("max_steps"),
            "max_errors": info.get("max_errors"),
            "seed": info.get("seed"),
            "agent_info": info.get("agent_info"),
            "user_info": info.get("user_info"),
            "environment_info": info.get("environment_info"),
        }
    config_id = emit(
        component="baseline.config",
        event_type="baseline.config.loaded",
        task_id=final_state.get("task_id"),
        payload=config_payload,
        parent_event_id=config_parent,
    )

    if not results:
        limitations.append("tau2_output/results.json was unavailable or unsupported; no task/message/evaluation events extracted.")
        emit(
            component="baseline.wrapper",
            event_type="baseline.run.completed",
            payload={**common_flags, "status": final_state.get("status"), "limitations": limitations},
            parent_event_id=root_id,
        )
        return event_types, limitations

    tasks = results.get("tasks") if isinstance(results.get("tasks"), list) else []
    simulations = results.get("simulations") if isinstance(results.get("simulations"), list) else []
    task_descriptions = {task.get("id"): task for task in tasks if isinstance(task, dict)}

    if not simulations:
        limitations.append("tau2 results.json did not contain simulations; no turn-level events extracted.")

    limitations.append("wrapper raw.log and summary.md were inspected for provenance but do not contain structured turn data beyond fields already represented in final_state.json/results.json.")

    latest_parent = config_id
    for sim_index, simulation in enumerate(simulations):
        if not isinstance(simulation, dict):
            limitations.append(f"simulation index {sim_index} is not an object and was skipped.")
            continue
        task_id = simulation.get("task_id") or final_state.get("task_id")
        task_payload = {
            **common_flags,
            "simulation_id": simulation.get("id"),
            "simulation_index": sim_index,
            "trial": simulation.get("trial"),
            "seed": simulation.get("seed"),
            "mode": simulation.get("mode"),
            "start_time": simulation.get("start_time"),
            "end_time": simulation.get("end_time"),
            "duration": simulation.get("duration"),
            "termination_reason": simulation.get("termination_reason"),
        }
        if task_id in task_descriptions:
            task = task_descriptions[task_id]
            task_payload["task_description"] = task.get("description")
            task_payload["ticket"] = task.get("ticket")
            task_payload["user_scenario"] = task.get("user_scenario")
            task_payload["evaluation_criteria"] = task.get("evaluation_criteria")
        task_event_id = emit(
            component="baseline.simulation",
            event_type="baseline.task.started",
            task_id=task_id,
            timestamp=simulation.get("start_time") or simulation.get("timestamp") or None,
            payload=task_payload,
            parent_event_id=latest_parent,
        )
        latest_parent = task_event_id

        messages = simulation.get("messages") if isinstance(simulation.get("messages"), list) else []
        if not messages:
            limitations.append(f"simulation {simulation.get('id') or sim_index} contained no messages.")
        tool_requests: dict[str, str] = {}
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                limitations.append(f"message index {message_index} in simulation {sim_index} is not an object and was skipped.")
                continue
            role = message.get("role")
            turn_index = message.get("turn_idx")
            message_id = emit(
                component="baseline.message",
                event_type="baseline.message.observed",
                task_id=task_id,
                turn_index=turn_index if isinstance(turn_index, int) else None,
                message_role=role,
                timestamp=message.get("timestamp") or None,
                payload={**compact_message_payload(message), "message_index": message_index},
                parent_event_id=latest_parent,
            )
            latest_parent = message_id

            tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
            for tool_index, tool_call in enumerate(tool_calls):
                if not isinstance(tool_call, dict):
                    limitations.append(f"tool call index {tool_index} in message {message_index} is not an object and was skipped.")
                    continue
                tool_call_id = tool_call.get("id")
                request_id = emit(
                    component="baseline.tool",
                    event_type="baseline.tool.requested",
                    task_id=task_id,
                    turn_index=turn_index if isinstance(turn_index, int) else None,
                    tool_name=tool_call.get("name"),
                    timestamp=message.get("timestamp") or None,
                    payload={
                        **common_flags,
                        "tool_call_id": tool_call_id,
                        "arguments": tool_call.get("arguments"),
                        "requestor": tool_call.get("requestor"),
                        "message_index": message_index,
                        "tool_call_index": tool_index,
                    },
                    parent_event_id=message_id,
                )
                if isinstance(tool_call_id, str):
                    tool_requests[tool_call_id] = request_id

            if role == "tool":
                parent = tool_requests.get(str(message.get("id")), message_id)
                emit(
                    component="baseline.tool",
                    event_type="baseline.tool.completed",
                    task_id=task_id,
                    turn_index=turn_index if isinstance(turn_index, int) else None,
                    tool_name=None,
                    timestamp=message.get("timestamp") or None,
                    payload={
                        **common_flags,
                        "tool_call_id": message.get("id"),
                        "requestor": message.get("requestor"),
                        "error": message.get("error"),
                        "content": message.get("content"),
                        "message_index": message_index,
                    },
                    parent_event_id=parent,
                )

        if simulation.get("ticks") is None:
            limitations.append(f"simulation {simulation.get('id') or sim_index} did not serialize tick-level events; no tick events were emitted.")
        if simulation.get("effect_timeline") is None:
            limitations.append(f"simulation {simulation.get('id') or sim_index} did not serialize an effect_timeline; no state transition timeline was emitted.")
        if simulation.get("speech_environment") is None:
            limitations.append(f"simulation {simulation.get('id') or sim_index} has no speech_environment artifact; no audio events were emitted.")

        reward_info = simulation.get("reward_info")
        if isinstance(reward_info, dict):
            if reward_info.get("db_check") is None:
                limitations.append(f"simulation {simulation.get('id') or sim_index} reward_info.db_check is null; no database assertion detail was emitted.")
            if reward_info.get("action_checks") is None:
                limitations.append(f"simulation {simulation.get('id') or sim_index} reward_info.action_checks is null; no action check detail was emitted.")
            if reward_info.get("nl_assertions") is None:
                limitations.append(f"simulation {simulation.get('id') or sim_index} reward_info.nl_assertions is null; no natural-language assertion detail was emitted.")
            eval_hash = state_hash(reward_info)
            latest_parent = emit(
                component="baseline.evaluator",
                event_type="baseline.evaluation.observed",
                task_id=task_id,
                state_hash_value=eval_hash,
                timestamp=simulation.get("end_time") or simulation.get("timestamp") or None,
                payload={
                    **common_flags,
                    "reward_info": reward_info,
                    "termination_reason": simulation.get("termination_reason"),
                    "agent_cost": simulation.get("agent_cost"),
                    "user_cost": simulation.get("user_cost"),
                },
                parent_event_id=latest_parent,
            )
        else:
            limitations.append(f"simulation {simulation.get('id') or sim_index} had no reward_info object.")

    persisted_id = emit(
        component="baseline.results",
        event_type="baseline.result.persisted",
        task_id=final_state.get("task_id"),
        payload={
            **common_flags,
            "source_results_path": rel(run_dir / "tau2_output" / "results.json"),
            "copied_tau2_artifacts": final_state.get("copied_tau2_artifacts", []),
            "results_timestamp": results.get("timestamp"),
            "simulation_count": len(simulations),
            "task_count": len(tasks),
        },
        parent_event_id=latest_parent,
    )
    emit(
        component="baseline.wrapper",
        event_type="baseline.run.completed",
        timestamp=final_state.get("timestamp_utc") or utc_now(),
        payload={
            **common_flags,
            "status": final_state.get("status"),
            "reason": final_state.get("reason"),
            "returncode": final_state.get("returncode"),
            "run_id": run_id,
            "limitations": limitations,
        },
        parent_event_id=persisted_id,
    )
    return event_types, limitations


def write_summary(
    path: pathlib.Path,
    *,
    run_dir: pathlib.Path,
    final_state: dict[str, Any],
    event_types: list[str],
    limitations: list[str],
    output_files: list[pathlib.Path],
    artifact_count: int,
) -> None:
    unique_event_types = sorted(set(event_types))
    lines = [
        "# tau2 baseline trace extraction",
        "",
        f"- source run directory: `{rel(run_dir)}`",
        f"- source status: `{final_state.get('status')}`",
        f"- phase: `{TRACE_PHASE}`",
        f"- trace mode: `{TRACE_MODE}`",
        "- fixture backed: `False`",
        "- tau2 rerun: `False`",
        "- LLM/API calls made by extractor: `False`",
        f"- task_id: `{final_state.get('task_id')}`",
        f"- provider: `{final_state.get('provider')}`",
        f"- model: `{final_state.get('model')}`",
        f"- artifacts inspected: `{artifact_count}`",
        f"- trace events extracted: `{len(event_types)}`",
        "",
        "## Output files",
        "",
    ]
    lines.extend(f"- `{rel(file)}`" for file in output_files)
    lines.extend(["", "## Event types emitted", ""])
    lines.extend(f"- `{event_type}`" for event_type in unique_event_types)
    lines.extend(["", "## Limitations", ""])
    if limitations:
        lines.extend(f"- {limitation}" for limitation in limitations)
    else:
        lines.append("- No extraction limitations were observed for the supported artifact fields.")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This extractor reads completed run artifacts only. It does not import tau2, launch tau2, call LLM/API services, require API keys, or mutate `vendor/tau2-bench`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"error: run directory does not exist: {args.run_dir}", file=sys.stderr)
        return 2

    final_state_path = run_dir / "final_state.json"
    if not final_state_path.is_file():
        print(f"error: missing final_state.json in {rel(run_dir)}", file=sys.stderr)
        return 2
    try:
        final_state = load_json(final_state_path)
    except json.JSONDecodeError as exc:
        print(f"error: cannot parse {rel(final_state_path)}: {exc}", file=sys.stderr)
        return 2
    status = final_state.get("status")
    if status != PASSED_STATUS and not args.allow_failed:
        print(
            f"error: refusing to extract run with status {status!r}; expected {PASSED_STATUS!r} "
            "or pass --allow-failed",
            file=sys.stderr,
        )
        return 2

    output_dir = run_dir / OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "baseline_trace.jsonl"
    index_path = output_dir / "baseline_artifact_index.json"
    summary_path = output_dir / "baseline_trace_summary.md"
    final_path = output_dir / "baseline_trace_final_state.json"

    files = source_artifact_files(run_dir)
    artifact_entries: list[dict[str, Any]] = []
    artifact_by_relative: dict[str, dict[str, Any]] = {}
    missing_notes: list[str] = []
    for expected in sorted(SOURCE_FILE_NAMES):
        if not (run_dir / expected).is_file():
            missing_notes.append(f"missing expected artifact: {expected}")
    for file in files:
        parser = parser_for(file, run_dir)
        entry = artifact_entry(file, run_dir, parser)
        artifact_entries.append(entry)
        artifact_by_relative[entry["relative_path"]] = entry

    results: dict[str, Any] | None = None
    results_path = run_dir / "tau2_output" / "results.json"
    if results_path.is_file():
        try:
            loaded = load_json(results_path)
            if isinstance(loaded, dict):
                results = loaded
                artifact_by_relative["tau2_output/results.json"]["contributed_events"] = True
            else:
                missing_notes.append("tau2_output/results.json is not a JSON object and did not contribute events.")
        except json.JSONDecodeError as exc:
            missing_notes.append(f"tau2_output/results.json could not be parsed: {exc}")
    else:
        missing_notes.append("tau2_output/results.json is unavailable; only wrapper metadata can be extracted.")

    for relative in ["final_state.json", "summary.md", "raw.log"]:
        if relative in artifact_by_relative:
            artifact_by_relative[relative]["contributed_events"] = relative == "final_state.json"
    if "tau2_artifacts/results.json" in artifact_by_relative:
        artifact_by_relative["tau2_artifacts/results.json"]["notes"].append(
            "copy of tau2_output/results.json; indexed but not parsed for duplicate events"
        )

    run_id = run_dir.name
    writer = EventWriter(trace_path, run_id)
    event_types, limitations = extract_events(run_dir=run_dir, final_state=final_state, results=results, writer=writer)
    limitations.extend(missing_notes)

    counts_by_source = {
        "final_state.json": 3,  # run.started, config.loaded, and run.completed use wrapper final_state.
        "tau2_output/results.json": max(0, len(event_types) - 3) if results else 0,
        "summary.md": 0,
        "raw.log": 0,
        "tau2_artifacts/results.json": 0,
    }
    for relative, count in counts_by_source.items():
        if relative in artifact_by_relative:
            artifact_by_relative[relative]["event_count"] = count
            artifact_by_relative[relative]["contributed_events"] = count > 0

    output_files = [trace_path, summary_path, final_path, index_path]
    final_extraction_state = {
        "status": "tau2_baseline_trace_extraction_passed",
        "timestamp_utc": utc_now(),
        "source_run_dir": rel(run_dir),
        "source_status": status,
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "event_schema_fields": EVENT_FIELDS,
        "phase": TRACE_PHASE,
        "trace_mode": TRACE_MODE,
        "fixture_backed": False,
        "tau2_rerun": False,
        "llm_api_calls_made_by_extractor": False,
        "requires_api_keys": False,
        "vendor_tau2_bench_mutated": False,
        "task_id": final_state.get("task_id"),
        "provider": final_state.get("provider"),
        "model": final_state.get("model"),
        "artifacts_inspected": len(artifact_entries),
        "event_count": len(event_types),
        "event_types_emitted": event_types,
        "unique_event_types_emitted": sorted(set(event_types)),
        "limitations": limitations,
        "output_files": [rel(file) for file in output_files],
    }
    final_path.write_text(json.dumps(final_extraction_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    artifact_index = {
        "source_run_directory": rel(run_dir),
        "generated_at_utc": utc_now(),
        "trace_mode": TRACE_MODE,
        "phase": TRACE_PHASE,
        "fixture_backed": False,
        "tau2_rerun": False,
        "llm_api_calls_made_by_extractor": False,
        "files_inspected": artifact_entries,
        "missing_or_unsupported_artifact_notes": limitations,
        "supported_tau2_formats": [
            "wrapper final_state.json object",
            "wrapper summary.md markdown",
            "wrapper raw.log text",
            "tau2 results.json object with tasks[] and simulations[].messages[]",
        ],
        "unsupported_tau2_formats_observed": [],
    }
    index_path.write_text(json.dumps(artifact_index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_summary(
        summary_path,
        run_dir=run_dir,
        final_state=final_state,
        event_types=event_types,
        limitations=limitations,
        output_files=output_files,
        artifact_count=len(artifact_entries),
    )

    print(rel(output_dir))
    print("tau2_baseline_trace_extraction_passed")
    print(f"artifacts_inspected={len(artifact_entries)}")
    print(f"trace_events_extracted={len(event_types)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
