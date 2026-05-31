#!/usr/bin/env python3
"""Compare a runtime-traced tau2 baseline with a post-run extracted baseline trace.

This command is an offline artifact comparator only. It reads already-produced
JSON/JSONL/Markdown artifacts, writes comparison artifacts, and does not import
or execute tau2, call LLM/API services, require API keys, or mutate the vendored
tau2 tree.
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
STATUS_PASSED = "runtime_vs_postrun_comparison_passed"
STATUS_REMAINING_GAPS = "runtime_vs_postrun_comparison_completed_with_remaining_gaps"
STATUS_FAILED = "runtime_vs_postrun_comparison_failed"
STATUS_INPUTS_MISSING = "runtime_vs_postrun_inputs_missing"


class ComparisonInputError(RuntimeError):
    """Raised when required offline comparison artifacts are missing or invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-compare a runtime trace against a post-run extracted tau2 baseline trace."
    )
    parser.add_argument(
        "--runtime-run-dir",
        required=True,
        type=pathlib.Path,
        help="Runtime-traced tau2 baseline run directory containing runtime_events.jsonl.",
    )
    parser.add_argument(
        "--postrun-baseline-dir",
        required=True,
        type=pathlib.Path,
        help="Completed tau2 baseline run directory containing extracted_trace/.",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Optional output directory. Defaults to <runtime-run-dir>/runtime_vs_postrun_comparison/.",
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


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ComparisonInputError(f"{rel(path)} line {line_number} is invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ComparisonInputError(f"{rel(path)} line {line_number} is not a JSON object")
        events.append(row)
    return events


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise ComparisonInputError(f"missing required {label}: {rel(path)}")


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def sorted_non_null(values: list[Any]) -> list[Any]:
    return sorted({value for value in values if value is not None}, key=lambda item: str(item))


def set_summary(values: list[Any]) -> dict[str, Any]:
    unique = sorted_non_null(values)
    return {"count": len(unique), "values": unique}


def runtime_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("runtime_trace")
    return nested if isinstance(nested, dict) else payload


def semantic_family(event_type: str | None) -> str:
    if not event_type:
        return "unknown"
    mapping = {
        "trace_bootstrap_start": "run_started",
        "trace_bootstrap_end": "run_completed",
        "batch_start": "batch_started",
        "batch_end": "batch_completed",
        "simulation_start": "task_started",
        "simulation_end": "task_completed",
        "simulation_execution_start": "simulation_execution_started",
        "simulation_execution_end": "simulation_execution_completed",
        "orchestrator_run_start": "orchestrator_started",
        "orchestrator_run_end": "orchestrator_completed",
        "turn_start": "turn_started",
        "turn_end": "turn_completed",
        "user_generate_start": "user_generation_started",
        "user_generate_end": "user_generation_completed",
        "user_response": "message_observed",
        "agent_response": "message_observed",
        "message_observed": "message_observed",
        "tool_call_requested": "tool_requested",
        "tool_dispatch_start": "tool_dispatch_started",
        "tool_dispatch_end": "tool_completed",
        "toolkit_dispatch_start": "toolkit_dispatch_started",
        "toolkit_dispatch_end": "toolkit_completed",
        "evaluation_start": "evaluation_started",
        "evaluation_end": "evaluation_observed",
        "result_persistence_start": "result_persistence_started",
        "result_persistence_end": "results_persisted",
        "baseline.run.started": "run_started",
        "baseline.run.completed": "run_completed",
        "baseline.config.loaded": "config_observed",
        "baseline.task.started": "task_started",
        "baseline.message.observed": "message_observed",
        "baseline.tool.requested": "tool_requested",
        "baseline.tool.completed": "tool_completed",
        "baseline.evaluation.observed": "evaluation_observed",
        "baseline.result.persisted": "results_persisted",
    }
    return mapping.get(event_type, event_type)


def counter_dict(values: list[Any]) -> dict[str, int]:
    return dict(sorted(collections.Counter(str(value) for value in values).items()))


def schema_report(runtime_events: list[dict[str, Any]], postrun_events: list[dict[str, Any]]) -> dict[str, Any]:
    expected = set(EVENT_FIELDS)
    runtime_fields = set().union(*(event.keys() for event in runtime_events)) if runtime_events else set()
    postrun_fields = set().union(*(event.keys() for event in postrun_events)) if postrun_events else set()
    return {
        "expected_event_fields": EVENT_FIELDS,
        "runtime_fields": sorted(runtime_fields),
        "postrun_fields": sorted(postrun_fields),
        "common_fields": sorted(runtime_fields & postrun_fields),
        "runtime_missing_expected_fields": sorted(expected - runtime_fields),
        "postrun_missing_expected_fields": sorted(expected - postrun_fields),
        "runtime_extra_fields": sorted(runtime_fields - expected),
        "postrun_extra_fields": sorted(postrun_fields - expected),
        "compatible_envelope": runtime_fields == expected and postrun_fields == expected,
    }


def summarize_trace(label: str, events: list[dict[str, Any]], final_state: dict[str, Any] | None, results: dict[str, Any] | None) -> dict[str, Any]:
    event_types = [event.get("event_type") for event in events]
    payloads = [runtime_payload(event) for event in events]
    simulations = results.get("simulations", []) if isinstance(results, dict) else []
    first_sim = simulations[0] if simulations and isinstance(simulations[0], dict) else {}
    messages = first_sim.get("messages") if isinstance(first_sim.get("messages"), list) else []
    reward_info = first_sim.get("reward_info") if isinstance(first_sim.get("reward_info"), dict) else {}
    usage_events = [event for event in events if runtime_payload(event).get("message", {}).get("raw", {}).get("usage")]
    cost_events = [event for event in events if runtime_payload(event).get("message", {}).get("raw", {}).get("cost") is not None]
    return {
        "label": label,
        "event_count": len(events),
        "event_type_counts": counter_dict(event_types),
        "semantic_family_counts": counter_dict([semantic_family(str(event_type)) for event_type in event_types]),
        "components": sorted_non_null([event.get("component") for event in events]),
        "task_ids": set_summary([event.get("task_id") for event in events]),
        "turn_indexes": set_summary([event.get("turn_index") for event in events]),
        "message_roles": set_summary([event.get("message_role") for event in events]),
        "tool_names": set_summary([event.get("tool_name") for event in events]),
        "state_hashes": set_summary([event.get("state_hash") for event in events]),
        "state_hash_event_count": sum(1 for event in events if event.get("state_hash")),
        "parent_link_event_count": sum(1 for event in events if event.get("parent_event_id")),
        "usage_metadata_event_count": len(usage_events),
        "cost_metadata_event_count": len(cost_events),
        "results_metadata": {
            "available": isinstance(results, dict),
            "timestamp": results.get("timestamp") if isinstance(results, dict) else None,
            "task_count": len(results.get("tasks", [])) if isinstance(results, dict) and isinstance(results.get("tasks"), list) else None,
            "simulation_count": len(simulations) if isinstance(simulations, list) else None,
            "message_count": len(messages),
            "termination_reason": first_sim.get("termination_reason"),
            "agent_cost": first_sim.get("agent_cost"),
            "user_cost": first_sim.get("user_cost"),
            "ticks_present": first_sim.get("ticks") is not None,
            "effect_timeline_present": first_sim.get("effect_timeline") is not None,
            "reward_info_keys": sorted(reward_info.keys()),
            "db_check_present": reward_info.get("db_check") is not None,
            "action_checks_present": reward_info.get("action_checks") is not None,
            "nl_assertions_present": reward_info.get("nl_assertions") is not None,
        },
        "final_state": final_state or {},
        "payload_key_counts": counter_dict([key for payload in payloads for key in payload.keys()]),
    }


def event_type_alignment(runtime_events: list[dict[str, Any]], postrun_events: list[dict[str, Any]]) -> dict[str, Any]:
    runtime_types = collections.Counter(str(event.get("event_type")) for event in runtime_events)
    postrun_types = collections.Counter(str(event.get("event_type")) for event in postrun_events)
    runtime_families = collections.Counter(semantic_family(str(event.get("event_type"))) for event in runtime_events)
    postrun_families = collections.Counter(semantic_family(str(event.get("event_type"))) for event in postrun_events)
    return {
        "runtime_event_count": len(runtime_events),
        "postrun_event_count": len(postrun_events),
        "runtime_event_type_counts": dict(sorted(runtime_types.items())),
        "postrun_event_type_counts": dict(sorted(postrun_types.items())),
        "exact_event_types_common": sorted(set(runtime_types) & set(postrun_types)),
        "runtime_only_event_types": sorted(set(runtime_types) - set(postrun_types)),
        "postrun_only_event_types": sorted(set(postrun_types) - set(runtime_types)),
        "semantic_family_counts": {
            "runtime": dict(sorted(runtime_families.items())),
            "postrun": dict(sorted(postrun_families.items())),
            "common": sorted(set(runtime_families) & set(postrun_families)),
            "runtime_only": sorted(set(runtime_families) - set(postrun_families)),
            "postrun_only": sorted(set(postrun_families) - set(runtime_families)),
        },
        "interpretation": [
            "Exact event_type names differ because runtime tracing records live hook names while post-run extraction emits baseline.* normalized names.",
            "Semantic families are the comparison contract for lifecycle, messages, tool requests/completions, evaluation, and result persistence.",
            "Runtime-only start/end families are expected improvements when hooks observe boundaries as they happen.",
        ],
    }


def artifact_manifest(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    return [
        {"path": rel(path), "available": path.is_file(), "sha256": sha256(path) if path.is_file() else None}
        for path in paths
    ]


def directory_manifest(path: pathlib.Path, expected_files: list[str]) -> dict[str, Any]:
    return {
        "path": rel(path),
        "available": path.is_dir(),
        "files": artifact_manifest([path / name for name in expected_files]),
    }


def build_gaps(runtime_summary: dict[str, Any], postrun_summary: dict[str, Any], alignment: dict[str, Any], postrun_final: dict[str, Any] | None) -> dict[str, Any]:
    closed: list[str] = []
    remaining: list[str] = []
    missed_fields: list[str] = []

    runtime_families = set(alignment["semantic_family_counts"]["runtime"])
    common_families = set(alignment["semantic_family_counts"]["common"])
    runtime_counts = runtime_summary["event_type_counts"]

    if {"turn_started", "turn_completed"}.issubset(runtime_families):
        closed.append("Runtime trace closes the turn-level boundary gap with turn_start and turn_end events.")
    if {"tool_requested", "tool_dispatch_started", "tool_completed", "toolkit_dispatch_started", "toolkit_completed"}.issubset(runtime_families):
        closed.append("Runtime trace closes the tool dispatch gap with request, environment dispatch, and toolkit dispatch events.")
    if runtime_counts.get("agent_response", 0) or runtime_counts.get("user_response", 0):
        closed.append("Runtime trace adds explicit agent_response and user_response boundaries in addition to serialized messages.")
    if {"evaluation_started", "evaluation_observed"}.issubset(runtime_families):
        closed.append("Runtime trace adds evaluation start/end boundaries instead of only post-run reward observation.")
    if {"result_persistence_started", "results_persisted"}.issubset(runtime_families):
        closed.append("Runtime trace adds result persistence start/end boundaries around tau2 result saving.")
    if runtime_summary["state_hash_event_count"] > postrun_summary["state_hash_event_count"]:
        closed.append("Runtime trace improves state snapshot coverage with repeated environment/toolkit state hashes around turns and tools.")
    if runtime_summary["results_metadata"].get("agent_cost") is not None and runtime_summary["results_metadata"].get("user_cost") is not None:
        closed.append("Runtime run artifacts retain provider/model token and cost metadata in copied tau2 results.")

    if not runtime_summary["results_metadata"].get("ticks_present"):
        remaining.append("tick-level internals are still missing; tau2 results serialize ticks as null and runtime hooks do not emit tick events.")
    if not runtime_summary["results_metadata"].get("effect_timeline_present"):
        remaining.append("effect timeline transitions are still missing; tau2 results serialize effect_timeline as null and runtime hooks do not reconstruct it.")
    if not runtime_summary["results_metadata"].get("db_check_present"):
        remaining.append("detailed DB assertion checks remain missing because reward_info.db_check is null.")
    if not runtime_summary["results_metadata"].get("action_checks_present"):
        remaining.append("detailed action assertion checks remain missing because reward_info.action_checks is null.")
    if not runtime_summary["results_metadata"].get("nl_assertions_present"):
        remaining.append("detailed natural-language assertion checks remain missing because reward_info.nl_assertions is null.")
    if runtime_summary["usage_metadata_event_count"] == 0:
        missed_fields.append("runtime response events summarize messages but do not promote usage/token metadata to first-class event fields.")
    if runtime_summary["cost_metadata_event_count"] == 0:
        missed_fields.append("runtime response events summarize messages but do not promote cost metadata to first-class event fields.")
    if "config_observed" not in common_families and "config_observed" not in runtime_families:
        missed_fields.append("runtime events do not emit a config_observed equivalent; config remains available in tau2 results artifacts.")
    if postrun_summary["turn_indexes"]["values"] != runtime_summary["turn_indexes"]["values"]:
        missed_fields.append("turn indexes do not align exactly: post-run extraction uses serialized message turn_idx values while runtime hooks use orchestrator step_count boundaries.")

    postrun_limitations = list((postrun_final or {}).get("limitations", []))
    return {
        "gaps_closed": closed,
        "remaining_runtime_hook_coverage_gaps": sorted(set(remaining)),
        "missed_message_tool_evaluator_fields": sorted(set(missed_fields)),
        "postrun_extraction_limitations_observed": sorted(set(postrun_limitations)),
        "posture": "Runtime tracing materially improves boundary and dispatch evidence, but remaining gaps are expected until deeper tau2 internals/evaluator details are exposed.",
    }


def write_summary(path: pathlib.Path, report: dict[str, Any], gaps: dict[str, Any]) -> None:
    alignment = report["event_type_alignment"]
    lines = [
        "# Runtime trace vs post-run extracted trace comparison",
        "",
        f"- status: `{report['status']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- runtime_run_dir: `{report['inputs']['runtime_run_dir']}`",
        f"- postrun_baseline_dir: `{report['inputs']['postrun_baseline_dir']}`",
        f"- runtime_event_count: `{report['event_counts']['runtime']}`",
        f"- postrun_event_count: `{report['event_counts']['postrun']}`",
        f"- schema_compatible_envelope: `{report['schema_alignment']['compatible_envelope']}`",
        f"- runtime_paid_llm_api_calls_made: `{report['runtime_run_inspection']['final_state'].get('paid_llm_api_calls_made')}`",
        f"- activegraph_controlled_tau2: `{report['runtime_run_inspection']['final_state'].get('activegraph_controlled_tau2')}`",
        f"- state_packets_fed_back_to_tau2: `{report['runtime_run_inspection']['final_state'].get('state_packets_fed_back_to_tau2')}`",
        f"- tau2_rerun_performed_by_comparison: `{report['no_rerun_no_api_guarantees']['tau2_rerun_performed_by_comparison']}`",
        f"- llm_api_calls_made_by_comparison: `{report['no_rerun_no_api_guarantees']['llm_api_calls_made_by_comparison']}`",
        f"- requires_api_keys: `{report['no_rerun_no_api_guarantees']['requires_api_keys']}`",
        "",
        "## Event-type alignment",
        "",
        f"- exact common event types: `{len(alignment['exact_event_types_common'])}`",
        f"- common semantic event families: `{', '.join(alignment['semantic_family_counts']['common'])}`",
        f"- runtime-only event types: `{', '.join(alignment['runtime_only_event_types'])}`",
        f"- postrun-only event types: `{', '.join(alignment['postrun_only_event_types'])}`",
        "",
        "## Coverage summary",
        "",
        f"- runtime task ids: `{report['coverage']['runtime']['task_ids']['values']}`",
        f"- post-run task ids: `{report['coverage']['postrun']['task_ids']['values']}`",
        f"- runtime turn indexes: `{report['coverage']['runtime']['turn_indexes']['values']}`",
        f"- post-run turn indexes: `{report['coverage']['postrun']['turn_indexes']['values']}`",
        f"- runtime message roles: `{report['coverage']['runtime']['message_roles']['values']}`",
        f"- post-run message roles: `{report['coverage']['postrun']['message_roles']['values']}`",
        f"- runtime tool names: `{report['coverage']['runtime']['tool_names']['values']}`",
        f"- post-run tool names: `{report['coverage']['postrun']['tool_names']['values']}`",
        f"- runtime state-hash events: `{report['coverage']['runtime']['state_hash_event_count']}`",
        f"- post-run state-hash events: `{report['coverage']['postrun']['state_hash_event_count']}`",
        "",
        "## Previous post-run extraction gaps now closed",
        "",
    ]
    lines.extend(f"- {item}" for item in gaps["gaps_closed"])
    lines.extend(["", "## Remaining runtime hook coverage gaps", ""])
    lines.extend(f"- {item}" for item in gaps["remaining_runtime_hook_coverage_gaps"])
    lines.extend(["", "## Missed message/tool/evaluator fields", ""])
    lines.extend(f"- {item}" for item in gaps["missed_message_tool_evaluator_fields"])
    lines.extend(["", "## Optional comparison inputs", ""])
    for key in ("trace_comparison", "activegraph_projection"):
        directory = report["optional_postrun_artifacts"][key]
        lines.append(f"- {key}: available=`{directory['available']}` path=`{directory['path']}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This comparison reads existing runtime-trace and post-run extraction artifacts only. It does not run tau2, does not run a model-backed episode, does not call LLM/API services, does not require API keys, does not feed state packets back to tau2, and does not mutate `vendor/tau2-bench`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    runtime_run_dir = args.runtime_run_dir.resolve()
    postrun_baseline_dir = args.postrun_baseline_dir.resolve()
    output_dir = (args.output_dir.resolve() if args.output_dir else runtime_run_dir / "runtime_vs_postrun_comparison")

    runtime_events_path = runtime_run_dir / "runtime_events.jsonl"
    runtime_summary_path = runtime_run_dir / "runtime_trace_summary.md"
    runtime_final_path = runtime_run_dir / "runtime_trace_final_state.json"
    runtime_hook_map_path = runtime_run_dir / "runtime_hook_map.json"
    runtime_results_path = runtime_run_dir / "tau2_output" / "results.json"
    runtime_artifact_results_path = runtime_run_dir / "tau2_artifacts" / "results.json"

    postrun_extracted_dir = postrun_baseline_dir / "extracted_trace"
    postrun_events_path = postrun_extracted_dir / "baseline_trace.jsonl"
    postrun_final_path = postrun_extracted_dir / "baseline_trace_final_state.json"
    postrun_summary_path = postrun_extracted_dir / "baseline_trace_summary.md"
    postrun_index_path = postrun_extracted_dir / "baseline_artifact_index.json"
    postrun_results_path = postrun_baseline_dir / "tau2_output" / "results.json"

    output_files = [
        output_dir / "runtime_vs_postrun_comparison.json",
        output_dir / "runtime_vs_postrun_summary.md",
        output_dir / "runtime_coverage_gaps.json",
        output_dir / "event_type_alignment.json",
        output_dir / "final_state.json",
        output_dir / "raw.log",
    ]

    try:
        require_file(runtime_events_path, "runtime runtime_events.jsonl")
        require_file(runtime_summary_path, "runtime runtime_trace_summary.md")
        require_file(runtime_final_path, "runtime runtime_trace_final_state.json")
        require_file(runtime_hook_map_path, "runtime runtime_hook_map.json")
        require_file(postrun_events_path, "post-run extracted_trace/baseline_trace.jsonl")
        require_file(postrun_final_path, "post-run extracted_trace/baseline_trace_final_state.json")
        require_file(postrun_index_path, "post-run extracted_trace/baseline_artifact_index.json")

        runtime_events = load_jsonl(runtime_events_path)
        postrun_events = load_jsonl(postrun_events_path)
        runtime_final = load_json(runtime_final_path)
        runtime_hook_map = load_json(runtime_hook_map_path)
        runtime_results = load_json_optional(runtime_results_path) or load_json_optional(runtime_artifact_results_path)
        postrun_final = load_json(postrun_final_path)
        postrun_index = load_json(postrun_index_path)
        postrun_results = load_json_optional(postrun_results_path)
    except Exception as exc:  # noqa: BLE001 - convert input failures into final_state artifacts when possible.
        output_dir.mkdir(parents=True, exist_ok=True)
        final_state = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at_utc": utc_now(),
            "runtime_run_dir": rel(runtime_run_dir),
            "postrun_baseline_dir": rel(postrun_baseline_dir),
            "error": str(exc),
            "tau2_rerun_performed_by_comparison": False,
            "model_backed_episode_run_by_comparison": False,
            "llm_api_calls_made_by_comparison": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_comparison": False,
        }
        write_json(output_dir / "final_state.json", final_state)
        (output_dir / "raw.log").write_text(f"[ERROR] {exc}\n", encoding="utf-8")
        print(f"comparison_status={STATUS_INPUTS_MISSING}")
        print(f"error={exc}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    schema = schema_report(runtime_events, postrun_events)
    alignment = event_type_alignment(runtime_events, postrun_events)
    runtime_summary = summarize_trace("runtime", runtime_events, runtime_final, runtime_results)
    postrun_summary = summarize_trace("postrun", postrun_events, postrun_final, postrun_results)
    gaps = build_gaps(runtime_summary, postrun_summary, alignment, postrun_final)

    status = STATUS_PASSED
    if not schema["compatible_envelope"]:
        status = STATUS_FAILED
    elif gaps["remaining_runtime_hook_coverage_gaps"] or gaps["missed_message_tool_evaluator_fields"]:
        status = STATUS_REMAINING_GAPS

    optional = {
        "trace_comparison": directory_manifest(
            postrun_baseline_dir / "trace_comparison",
            ["trace_comparison_report.json", "trace_comparison_summary.md", "coverage_gaps.json", "final_state.json"],
        ),
        "activegraph_projection": directory_manifest(
            postrun_baseline_dir / "activegraph_projection",
            [
                "activegraph_baseline_projection.json",
                "activegraph_baseline_events.jsonl",
                "activegraph_baseline_state_packets.jsonl",
                "activegraph_projection_final_state.json",
            ],
        ),
    }

    report = {
        "status": status,
        "generated_at_utc": utc_now(),
        "inputs": {
            "runtime_run_dir": rel(runtime_run_dir),
            "runtime_events_path": rel(runtime_events_path),
            "runtime_summary_path": rel(runtime_summary_path),
            "runtime_final_state_path": rel(runtime_final_path),
            "runtime_hook_map_path": rel(runtime_hook_map_path),
            "runtime_results_path": rel(runtime_results_path) if runtime_results_path.is_file() else None,
            "runtime_artifact_results_path": rel(runtime_artifact_results_path) if runtime_artifact_results_path.is_file() else None,
            "postrun_baseline_dir": rel(postrun_baseline_dir),
            "postrun_events_path": rel(postrun_events_path),
            "postrun_final_state_path": rel(postrun_final_path),
            "postrun_summary_path": rel(postrun_summary_path) if postrun_summary_path.is_file() else None,
            "postrun_artifact_index_path": rel(postrun_index_path),
            "postrun_results_path": rel(postrun_results_path) if postrun_results_path.is_file() else None,
        },
        "event_counts": {"runtime": len(runtime_events), "postrun": len(postrun_events)},
        "schema_alignment": schema,
        "event_type_alignment": alignment,
        "coverage": {"runtime": runtime_summary, "postrun": postrun_summary},
        "runtime_run_inspection": {
            "final_state": runtime_final,
            "hook_map_schema": runtime_hook_map.get("schema"),
            "validated_hooks": runtime_hook_map.get("validated_hooks", []),
            "deferred_hooks": runtime_hook_map.get("deferred_hooks", []),
        },
        "postrun_trace_inspection": {
            "final_state": postrun_final,
            "artifact_index": postrun_index,
        },
        "optional_postrun_artifacts": optional,
        "runtime_coverage_gaps": gaps,
        "no_rerun_no_api_guarantees": {
            "tau2_rerun_performed_by_comparison": False,
            "model_backed_episode_run_by_comparison": False,
            "llm_api_calls_made_by_comparison": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_comparison": False,
            "activegraph_controlled_tau2_by_comparison": False,
            "state_packets_fed_back_to_tau2_by_comparison": False,
        },
        "artifact_provenance": {
            "runtime_artifacts": artifact_manifest(
                [runtime_events_path, runtime_summary_path, runtime_final_path, runtime_hook_map_path, runtime_results_path, runtime_artifact_results_path]
            ),
            "postrun_artifacts": artifact_manifest(
                [postrun_events_path, postrun_final_path, postrun_summary_path, postrun_index_path, postrun_results_path]
            ),
        },
        "output_files": [rel(path) for path in output_files],
    }
    final_state = {
        "status": status,
        "generated_at_utc": report["generated_at_utc"],
        "runtime_run_dir": rel(runtime_run_dir),
        "postrun_baseline_dir": rel(postrun_baseline_dir),
        "output_dir": rel(output_dir),
        "runtime_event_count": len(runtime_events),
        "postrun_event_count": len(postrun_events),
        "gaps_closed_count": len(gaps["gaps_closed"]),
        "remaining_runtime_hook_coverage_gap_count": len(gaps["remaining_runtime_hook_coverage_gaps"]),
        "missed_message_tool_evaluator_field_count": len(gaps["missed_message_tool_evaluator_fields"]),
        "runtime_paid_llm_api_calls_made": runtime_final.get("paid_llm_api_calls_made"),
        "runtime_tau2_executed": runtime_final.get("tau2_executed"),
        "activegraph_controlled_tau2": runtime_final.get("activegraph_controlled_tau2"),
        "state_packets_fed_back_to_tau2": runtime_final.get("state_packets_fed_back_to_tau2"),
        "tau2_rerun_performed_by_comparison": False,
        "model_backed_episode_run_by_comparison": False,
        "llm_api_calls_made_by_comparison": False,
        "requires_api_keys": False,
        "vendor_tau2_bench_mutated_by_comparison": False,
        "output_files": [rel(path) for path in output_files],
    }

    write_json(output_dir / "event_type_alignment.json", alignment)
    write_json(output_dir / "runtime_coverage_gaps.json", gaps)
    write_json(output_dir / "runtime_vs_postrun_comparison.json", report)
    write_json(output_dir / "final_state.json", final_state)
    write_summary(output_dir / "runtime_vs_postrun_summary.md", report, gaps)
    (output_dir / "raw.log").write_text(
        "\n".join(
            [
                f"comparison_status={status}",
                f"runtime_run_dir={rel(runtime_run_dir)}",
                f"postrun_baseline_dir={rel(postrun_baseline_dir)}",
                f"runtime_event_count={len(runtime_events)}",
                f"postrun_event_count={len(postrun_events)}",
                "tau2_rerun_performed_by_comparison=false",
                "model_backed_episode_run_by_comparison=false",
                "llm_api_calls_made_by_comparison=false",
                "requires_api_keys=false",
                "vendor_tau2_bench_mutated_by_comparison=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"comparison_status={status}")
    print(f"output_dir={rel(output_dir)}")
    print(f"runtime_event_count={len(runtime_events)}")
    print(f"postrun_event_count={len(postrun_events)}")
    return 1 if status == STATUS_FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
