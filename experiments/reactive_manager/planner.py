"""Dry-run reactive-manager replay/fork/diff planning.

The planner consumes repository-owned smoke artifacts only. It never imports the
vendored tau2 package, never controls tau2 lifecycle/task state, and never calls
external LLM/API services.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any

from experiments.state_packets.packets import EXPECTED_FIXTURE_PACKET_COUNT, recompute_packet_hash, stable_hash
from experiments.trace_only.schema import EVENT_FIELDS

MANAGER_PLAN_SCHEMA_VERSION = "activegraph_reactive_manager_dry_run_plan.v1"
MANAGER_DECISION_SCHEMA_VERSION = "activegraph_reactive_manager_decision.v1"
REPLAY_PLAN_SCHEMA_VERSION = "activegraph_replay_plan.v1"
FORK_PLAN_SCHEMA_VERSION = "activegraph_fork_plan.v1"
DIFF_REPORT_SCHEMA_VERSION = "activegraph_diff_report.v1"
PASS_STATUS = "reactive_manager_dry_run_passed"
VALIDATION_FAILED_STATUS = "reactive_manager_validation_failed"
INPUTS_MISSING_STATUS = "reactive_manager_inputs_missing"

SAFE_FORK_SELECTORS = [
    {
        "fork_point_id": "fork-after-run-started",
        "position": "after",
        "event_type": "run.started",
        "reason": "Run metadata and safety provenance are available before task work begins.",
    },
    {
        "fork_point_id": "fork-after-task-started",
        "position": "after",
        "event_type": "task.started",
        "reason": "Task identity and seed are visible, but no fixture tool dispatch has occurred.",
    },
    {
        "fork_point_id": "fork-before-tool-dispatch-requested",
        "position": "before",
        "event_type": "tool.dispatch_requested",
        "reason": "Planner can identify the pre-tool boundary without replaying or invoking the tool.",
    },
    {
        "fork_point_id": "fork-after-evaluation-completed",
        "position": "after",
        "event_type": "evaluation.completed",
        "reason": "Post-evaluation comparisons can be planned after reward metadata exists.",
    },
]


def load_json(path: Any) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Any) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Any, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Any, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def packet_by_event_id(packets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {packet["source_event_id"]: packet for packet in packets}


def validate_trace_events(events: list[dict[str, Any]], *, expected_count: int) -> dict[str, Any]:
    errors: list[str] = []
    event_ids: list[str] = []
    for index, event in enumerate(events):
        missing = [field for field in EVENT_FIELDS if field not in event]
        if missing:
            errors.append(f"event at index {index} missing fields {missing}")
        expected_id = f"evt-{index + 1:06d}"
        if event.get("event_id") != expected_id:
            errors.append(f"event at index {index} expected id {expected_id}")
        if event.get("event_id") in event_ids:
            errors.append(f"duplicate event id {event.get('event_id')}")
        event_ids.append(event.get("event_id"))
    if len(events) != expected_count:
        errors.append(f"expected {expected_count} fixture events, found {len(events)}")
    parent_ids = {event.get("event_id") for event in events}
    for event in events:
        parent_event_id = event.get("parent_event_id")
        if parent_event_id is not None and parent_event_id not in parent_ids:
            errors.append(f"event {event.get('event_id')} references missing parent {parent_event_id}")
    return {"ok": not errors, "errors": errors, "event_count": len(events), "expected_event_count": expected_count}


def validate_activegraph_trace(activegraph_trace: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    if activegraph_trace.get("event_log") != events:
        errors.append("activegraph_trace.json event_log does not match events.jsonl")
    counts = activegraph_trace.get("counts", {})
    if counts.get("events") != len(events):
        errors.append("activegraph trace event count mismatch")
    graph = activegraph_trace.get("graph", {})
    if not isinstance(graph.get("nodes"), list):
        errors.append("activegraph trace graph.nodes must be a list")
    if not isinstance(graph.get("edges"), list):
        errors.append("activegraph trace graph.edges must be a list")
    adapter = activegraph_trace.get("adapter", {})
    if adapter.get("source_of_truth") != "events.jsonl TraceEvent stream":
        errors.append("activegraph adapter source_of_truth mismatch")
    if adapter.get("control_flow_owner") != "tau2 fixture smoke harness":
        errors.append("activegraph adapter control flow owner mismatch")
    if adapter.get("reactive_manager_support") is not False:
        errors.append("activegraph adapter claims reactive manager support")
    return {"ok": not errors, "errors": errors, "counts": counts}


def validate_packet_chain(packets: list[dict[str, Any]], events: list[dict[str, Any]], *, expected_count: int) -> dict[str, Any]:
    errors: list[str] = []
    event_ids = [event["event_id"] for event in events]
    previous_hash: str | None = None
    for index, packet in enumerate(packets):
        expected_packet_id = f"pkt-{index + 1:06d}"
        if packet.get("packet_id") != expected_packet_id:
            errors.append(f"packet index {index} expected id {expected_packet_id}")
        if packet.get("sequence_index") != index:
            errors.append(f"packet {packet.get('packet_id')} sequence_index mismatch")
        if packet.get("source_event_id") not in event_ids:
            errors.append(f"packet {packet.get('packet_id')} references missing event")
        elif event_ids[index] != packet.get("source_event_id"):
            errors.append(f"packet {packet.get('packet_id')} source event order mismatch")
        if packet.get("previous_packet_hash") != previous_hash:
            errors.append(f"packet {packet.get('packet_id')} previous_packet_hash mismatch")
        if packet.get("packet_hash") != recompute_packet_hash(packet):
            errors.append(f"packet {packet.get('packet_id')} packet_hash mismatch")
        previous_hash = packet.get("packet_hash")
        provenance = packet.get("provenance", {})
        if provenance.get("state_packets_control_tau2") is not False:
            errors.append(f"packet {packet.get('packet_id')} claims tau2 control")
    if len(packets) != expected_count:
        errors.append(f"expected {expected_count} fixture packets, found {len(packets)}")
    return {
        "ok": not errors,
        "errors": errors,
        "packet_count": len(packets),
        "expected_packet_count": expected_count,
        "hash_chain_valid": not any("hash" in error for error in errors),
        "all_packets_reference_events": not any("missing event" in error for error in errors),
    }


def build_replay_plan(events: list[dict[str, Any]], packets: list[dict[str, Any]], *, run_id: str) -> dict[str, Any]:
    packets_by_event = packet_by_event_id(packets)
    steps = []
    for index, event in enumerate(events):
        packet = packets_by_event[event["event_id"]]
        steps.append(
            {
                "step_id": f"replay-step-{index + 1:06d}",
                "sequence_index": index,
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "packet_id": packet["packet_id"],
                "packet_hash": packet["packet_hash"],
                "planned_operation": "observe_event_and_packet_only",
                "dry_run": True,
                "executed": False,
            }
        )
    return {
        "schema_version": REPLAY_PLAN_SCHEMA_VERSION,
        "run_id": run_id,
        "plan_type": "deterministic_trace_packet_replay_plan",
        "dry_run": True,
        "executed": False,
        "source_artifacts": ["events.jsonl", "state_packets.jsonl"],
        "step_count": len(steps),
        "steps": steps,
    }


def _find_event(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    for event in events:
        if event["event_type"] == event_type:
            return event
    raise ValueError(f"missing fixture event_type {event_type}")


def build_fork_plan(events: list[dict[str, Any]], packets: list[dict[str, Any]], *, run_id: str) -> dict[str, Any]:
    packets_by_event = packet_by_event_id(packets)
    fork_points = []
    for index, selector in enumerate(SAFE_FORK_SELECTORS):
        event = _find_event(events, selector["event_type"])
        packet = packets_by_event[event["event_id"]]
        fork_points.append(
            {
                "fork_point_id": selector["fork_point_id"],
                "sequence_index": index,
                "position": selector["position"],
                "source_event_id": event["event_id"],
                "source_event_type": event["event_type"],
                "source_packet_id": packet["packet_id"],
                "source_packet_hash": packet["packet_hash"],
                "safe_fixture_fork_point": True,
                "planned_operation": "record_plan_only_no_execution",
                "dry_run": True,
                "executed": False,
                "reason": selector["reason"],
            }
        )
    return {
        "schema_version": FORK_PLAN_SCHEMA_VERSION,
        "run_id": run_id,
        "plan_type": "safe_fixture_fork_points",
        "dry_run": True,
        "executed": False,
        "source_artifacts": ["events.jsonl", "state_packets.jsonl"],
        "fork_point_count": len(fork_points),
        "fork_points": fork_points,
    }


def _node_counts_by_kind(activegraph_trace: dict[str, Any]) -> dict[str, int]:
    return dict(sorted(Counter(node.get("kind") for node in activegraph_trace.get("graph", {}).get("nodes", [])).items()))


def _packet_snapshot(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet_id": packet["packet_id"],
        "packet_type": packet["packet_type"],
        "sequence_index": packet["sequence_index"],
        "source_event_id": packet["source_event_id"],
        "source_event_type": packet["source_event_type"],
        "state_hash": packet["state_hash"],
        "packet_hash": packet["packet_hash"],
        "state_scope": copy.deepcopy(packet["state_scope"]),
    }


def build_diff_report(
    events: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    activegraph_trace: dict[str, Any],
    fork_plan: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    packets_by_id = {packet["packet_id"]: packet for packet in packets}
    comparisons = []
    fork_points = fork_plan["fork_points"]
    for index in range(len(fork_points) - 1):
        left_point = fork_points[index]
        right_point = fork_points[index + 1]
        left_packet = packets_by_id[left_point["source_packet_id"]]
        right_packet = packets_by_id[right_point["source_packet_id"]]
        event_window = [
            event["event_id"]
            for event in events
            if left_packet["sequence_index"] <= events.index(event) <= right_packet["sequence_index"]
        ]
        comparisons.append(
            {
                "comparison_id": f"diff-{index + 1:06d}",
                "left_fork_point_id": left_point["fork_point_id"],
                "right_fork_point_id": right_point["fork_point_id"],
                "left_packet": _packet_snapshot(left_packet),
                "right_packet": _packet_snapshot(right_packet),
                "event_window": event_window,
                "packet_sequence_delta": right_packet["sequence_index"] - left_packet["sequence_index"],
                "source_event_type_delta": [left_packet["source_event_type"], right_packet["source_event_type"]],
                "state_hash_changed": left_packet["state_hash"] != right_packet["state_hash"],
                "dry_run": True,
                "executed": False,
            }
        )
    report = {
        "schema_version": DIFF_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "report_type": "deterministic_packet_and_projection_diff",
        "dry_run": True,
        "executed": False,
        "source_artifacts": ["events.jsonl", "activegraph_trace.json", "state_packets.jsonl"],
        "comparison_count": len(comparisons),
        "graph_projection_summary": {
            "counts": copy.deepcopy(activegraph_trace.get("counts", {})),
            "node_counts_by_kind": _node_counts_by_kind(activegraph_trace),
        },
        "comparisons": comparisons,
    }
    report["deterministic_report_hash"] = stable_hash(report)
    return report


def build_manager_decisions(
    fork_plan: dict[str, Any],
    replay_plan: dict[str, Any],
    diff_report: dict[str, Any],
    *,
    run_id: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []

    def add(decision_type: str, proposed_action: str, reason: str, provenance: dict[str, Any], source_event_id: str | None = None, source_packet_id: str | None = None) -> None:
        decisions.append(
            {
                "schema_version": MANAGER_DECISION_SCHEMA_VERSION,
                "decision_id": f"decision-{len(decisions) + 1:06d}",
                "timestamp": timestamp,
                "run_id": run_id,
                "decision_type": decision_type,
                "source_event_id": source_event_id,
                "source_packet_id": source_packet_id,
                "proposed_action": proposed_action,
                "dry_run": True,
                "executed": False,
                "reason": reason,
                "provenance": provenance,
            }
        )

    add(
        "build_replay_plan",
        "write replay_plan.json with deterministic event/packet ordering",
        "Replay is represented as an ordered plan only; no tau2 control flow is invoked.",
        {"source_artifacts": replay_plan["source_artifacts"], "step_count": replay_plan["step_count"]},
    )
    for fork_point in fork_plan["fork_points"]:
        add(
            "select_fixture_fork_point",
            "record safe fixture fork point without executing a fork",
            fork_point["reason"],
            {"fork_point_id": fork_point["fork_point_id"], "position": fork_point["position"]},
            source_event_id=fork_point["source_event_id"],
            source_packet_id=fork_point["source_packet_id"],
        )
    add(
        "build_diff_report",
        "write deterministic packet/projection diff report",
        "Diffs compare serialized artifacts only and do not feed decisions back into tau2.",
        {"source_artifacts": diff_report["source_artifacts"], "comparison_count": diff_report["comparison_count"], "deterministic_report_hash": diff_report["deterministic_report_hash"]},
    )
    return decisions


def validate_plans_and_decisions(
    replay_plan: dict[str, Any],
    fork_plan: dict[str, Any],
    diff_report: dict[str, Any],
    decisions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    no_llm_status: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    event_ids = {event["event_id"] for event in events}
    packet_ids = {packet["packet_id"] for packet in packets}
    for step in replay_plan.get("steps", []):
        if step.get("event_id") not in event_ids:
            errors.append(f"replay step {step.get('step_id')} references missing event")
        if step.get("packet_id") not in packet_ids:
            errors.append(f"replay step {step.get('step_id')} references missing packet")
        if step.get("dry_run") is not True or step.get("executed") is not False:
            errors.append(f"replay step {step.get('step_id')} is not dry-run unexecuted")
    for fork_point in fork_plan.get("fork_points", []):
        if fork_point.get("source_event_id") not in event_ids:
            errors.append(f"fork point {fork_point.get('fork_point_id')} references missing event")
        if fork_point.get("source_packet_id") not in packet_ids:
            errors.append(f"fork point {fork_point.get('fork_point_id')} references missing packet")
        if fork_point.get("dry_run") is not True or fork_point.get("executed") is not False:
            errors.append(f"fork point {fork_point.get('fork_point_id')} is not dry-run unexecuted")
    recomputed_diff_hash = stable_hash({key: value for key, value in diff_report.items() if key != "deterministic_report_hash"})
    if diff_report.get("deterministic_report_hash") != recomputed_diff_hash:
        errors.append("diff report deterministic hash mismatch")
    for decision in decisions:
        if decision.get("dry_run") is not True or decision.get("executed") is not False:
            errors.append(f"decision {decision.get('decision_id')} is not dry-run unexecuted")
        if "execute" in decision.get("proposed_action", "").lower() and "without executing" not in decision.get("proposed_action", "").lower():
            errors.append(f"decision {decision.get('decision_id')} appears to propose execution")
        if decision.get("source_event_id") is not None and decision.get("source_event_id") not in event_ids:
            errors.append(f"decision {decision.get('decision_id')} references missing event")
        if decision.get("source_packet_id") is not None and decision.get("source_packet_id") not in packet_ids:
            errors.append(f"decision {decision.get('decision_id')} references missing packet")
    if no_llm_status.get("llm_api_calls") is not False or no_llm_status.get("paid_llm_apis_called") is not False:
        errors.append("no_llm_status indicates LLM/API calls were made")
    if no_llm_status.get("real_tau2_episode_run") is not False:
        errors.append("no_llm_status indicates a real tau2 episode was run")
    return {
        "ok": not errors,
        "errors": errors,
        "replay_steps_reference_sources": not any("replay step" in error for error in errors),
        "fork_points_reference_sources": not any("fork point" in error for error in errors),
        "diff_report_deterministic": not any("diff report" in error for error in errors),
        "all_decisions_dry_run_unexecuted": not any("decision" in error for error in errors),
        "no_llm_api_calls_validated": no_llm_status.get("llm_api_calls") is False and no_llm_status.get("paid_llm_apis_called") is False,
        "no_live_tau2_episode_validated": no_llm_status.get("real_tau2_episode_run") is False,
    }


def build_manager_plan(
    *,
    run_id: str,
    validation: dict[str, Any],
    replay_plan: dict[str, Any],
    fork_plan: dict[str, Any],
    diff_report: dict[str, Any],
    decision_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": MANAGER_PLAN_SCHEMA_VERSION,
        "run_id": run_id,
        "manager_mode": "dry_run_observational_plan_only",
        "dry_run": True,
        "executed": False,
        "source_artifacts": ["events.jsonl", "activegraph_trace.json", "state_packets.jsonl", "state_packet_index.json"],
        "output_artifacts": ["manager_plan.json", "manager_decisions.jsonl", "replay_plan.json", "fork_plan.json", "diff_report.json"],
        "control_boundary": {
            "controls_tau2_execution": False,
            "controls_task_state": False,
            "controls_lifecycle": False,
            "feeds_packets_back_into_tau2": False,
            "calls_llm_or_api_services": False,
            "mutates_tau2_bench": False,
        },
        "counts": {
            "replay_steps": replay_plan["step_count"],
            "fork_points": fork_plan["fork_point_count"],
            "diff_comparisons": diff_report["comparison_count"],
            "manager_decisions": decision_count,
        },
        "validation": validation,
    }
