#!/usr/bin/env python3
"""Project an extracted real tau2 baseline trace into offline ActiveGraph-style artifacts.

The projection is observational only: it reads already-extracted TraceEvent JSONL
artifacts, builds graph/state-packet artifacts, and never runs tau2 or calls LLM
or API services.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import traceback
from collections import Counter
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION, canonical_json  # noqa: E402

PROJECTION_SCHEMA_VERSION = "activegraph_baseline_projection.v1"
STATE_PACKET_SCHEMA_VERSION = "activegraph_baseline_state_packet.v1"
STATE_PACKET_INDEX_SCHEMA_VERSION = "activegraph_baseline_state_packet_index.v1"
TRACE_PHASE = "real_tau2_model_baseline_extracted"
OUTPUT_DIR_NAME = "activegraph_projection"
PASS_STATUS = "activegraph_baseline_projection_passed"
GAP_STATUS = "activegraph_baseline_projection_completed_with_gaps"
FAILED_STATUS = "activegraph_baseline_projection_failed"
INPUTS_MISSING_STATUS = "activegraph_baseline_projection_inputs_missing"
NO_PREVIOUS_PACKET_HASH = None
CONTROL_CLAIM_KEYS = {
    "controls_tau2_execution",
    "controls_task_state",
    "controls_lifecycle",
    "reactive_manager_enabled",
    "activegraph_controls_tau2",
}

PACKET_TYPE_BY_BASELINE_EVENT = {
    "baseline.run.started": "run_state",
    "baseline.config.loaded": "run_state",
    "baseline.task.started": "task_state",
    "baseline.message.observed": "turn_state",
    "baseline.tool.requested": "tool_state",
    "baseline.tool.completed": "tool_state",
    "baseline.evaluation.observed": "evaluation_state",
    "baseline.result.persisted": "result_state",
    "baseline.run.completed": "run_state",
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def stable_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def content_hash(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{rel(path)} line {line_number} is not valid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{rel(path)} line {line_number} is not a JSON object")
            events.append(value)
    return events


def write_json(path: pathlib.Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


def git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def load_tau2_upstream_commit() -> str | None:
    marker = REPO_ROOT / "vendor" / "tau2-bench.UPSTREAM_COMMIT"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip() or None
    return None


def packet_type_for_event(event: dict[str, Any]) -> str:
    return PACKET_TYPE_BY_BASELINE_EVENT.get(str(event.get("event_type")), "run_state")


def state_scope_for_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": event.get("run_id"),
        "task_id": event.get("task_id"),
        "turn_index": event.get("turn_index"),
        "component": event.get("component"),
        "tool_name": event.get("tool_name"),
        "message_role": event.get("message_role"),
    }


def source_artifact_ids_for_event(event: dict[str, Any], artifact_index: dict[str, Any]) -> list[str]:
    files = artifact_index.get("files_inspected") if isinstance(artifact_index, dict) else []
    if not isinstance(files, list):
        return []
    event_type = event.get("event_type")
    component = str(event.get("component"))
    selected: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        relative_path = entry.get("relative_path")
        if not relative_path:
            continue
        include = False
        if entry.get("contributed_events"):
            if relative_path == "final_state.json" and event_type in {
                "baseline.run.started",
                "baseline.config.loaded",
                "baseline.run.completed",
            }:
                include = True
            if relative_path == "tau2_output/results.json" and event_type not in {
                "baseline.run.started",
                "baseline.run.completed",
            }:
                include = True
        if component in {"baseline.wrapper", "baseline.config"} and relative_path in {"summary.md", "raw.log"}:
            include = True
        if include:
            selected.append(f"artifact:source:{relative_path}")
    return sorted(set(selected))


class ProjectionBuilder:
    def __init__(self, *, run_id: str, baseline_run_dir: pathlib.Path, artifact_index: dict[str, Any]):
        self.run_id = run_id
        self.baseline_run_dir = baseline_run_dir
        self.artifact_index = artifact_index
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._edge_keys: set[tuple[str, str, str]] = set()

    def upsert_node(self, kind: str, node_id: str, attributes: dict[str, Any]) -> None:
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = {"id": node_id, "kind": kind, "attributes": copy.deepcopy(attributes)}
            return
        existing["attributes"].update(copy.deepcopy(attributes))

    def add_edge(self, edge_type: str, source: str, target: str, attributes: dict[str, Any] | None = None) -> None:
        key = (edge_type, source, target)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(
            {
                "id": f"edge-{len(self.edges) + 1:06d}",
                "type": edge_type,
                "source": source,
                "target": target,
                "attributes": copy.deepcopy(attributes or {}),
            }
        )

    def add_artifact_nodes(self, *, trace_path: pathlib.Path, final_state_path: pathlib.Path, artifact_index_path: pathlib.Path) -> None:
        projection_inputs = [
            ("baseline_trace", trace_path),
            ("baseline_trace_final_state", final_state_path),
            ("baseline_artifact_index", artifact_index_path),
        ]
        for artifact_type, path in projection_inputs:
            node_id = f"artifact:extracted:{path.name}"
            self.upsert_node(
                "artifact",
                node_id,
                {
                    "artifact_type": artifact_type,
                    "path": rel(path),
                    "sha256": content_hash(path),
                    "source": "extracted_trace",
                },
            )
            self.add_edge("run_references_artifact", f"run:{self.run_id}", node_id)

        for entry in self.artifact_index.get("files_inspected", []) if isinstance(self.artifact_index, dict) else []:
            if not isinstance(entry, dict) or not entry.get("relative_path"):
                continue
            node_id = f"artifact:source:{entry['relative_path']}"
            self.upsert_node(
                "artifact",
                node_id,
                {
                    "artifact_type": "source_run_artifact",
                    "path": entry.get("path"),
                    "relative_path": entry.get("relative_path"),
                    "sha256": entry.get("sha256"),
                    "parser": entry.get("parser"),
                    "contributed_events": entry.get("contributed_events"),
                    "event_count": entry.get("event_count"),
                    "notes": entry.get("notes", []),
                },
            )
            self.add_edge("run_references_artifact", f"run:{self.run_id}", node_id)

    def project_event(self, event: dict[str, Any], *, sequence_index: int, previous_event: dict[str, Any] | None) -> None:
        event_id = str(event["event_id"])
        event_node_id = f"event:{event_id}"
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        task_id = event.get("task_id") or payload.get("task_id")
        self.upsert_node(
            "run",
            f"run:{self.run_id}",
            {
                "run_id": self.run_id,
                "baseline_run_dir": rel(self.baseline_run_dir),
                "source": "extracted real tau2 baseline trace",
                "projection_mode": "offline_observational_only",
            },
        )
        self.upsert_node(
            "component",
            f"component:{event['component']}",
            {"component": event["component"]},
        )
        self.upsert_node(
            "event",
            event_node_id,
            {
                "event_id": event_id,
                "original_event_type": event.get("event_type"),
                "component": event.get("component"),
                "timestamp": event.get("timestamp"),
                "sequence_index": sequence_index,
                "phase": event.get("phase"),
                "task_id": event.get("task_id"),
                "turn_index": event.get("turn_index"),
                "tool_name": event.get("tool_name"),
                "message_role": event.get("message_role"),
                "state_hash": event.get("state_hash"),
            },
        )
        self.add_edge("run_contains_event", f"run:{self.run_id}", event_node_id, {"sequence_index": sequence_index})
        self.add_edge("event_has_component", event_node_id, f"component:{event['component']}")
        if previous_event is not None:
            self.add_edge("event_follows_previous_event", event_node_id, f"event:{previous_event['event_id']}")
        if task_id:
            task_node_id = f"task:{task_id}"
            self.upsert_node("task", task_node_id, {"task_id": task_id, "run_id": self.run_id})
            self.add_edge("run_has_task", f"run:{self.run_id}", task_node_id)
            self.add_edge("event_belongs_to_task", event_node_id, task_node_id)
        if event.get("message_role"):
            role_node_id = f"message_role:{event['message_role']}"
            self.upsert_node("message_role", role_node_id, {"message_role": event["message_role"]})
            self.add_edge("event_has_message_role", event_node_id, role_node_id)
        if event.get("tool_name"):
            tool_node_id = f"tool:{event['tool_name']}"
            self.upsert_node("tool", tool_node_id, {"tool_name": event["tool_name"]})
            self.add_edge("event_uses_tool", event_node_id, tool_node_id)
        if event.get("event_type") in {"baseline.evaluation.observed", "baseline.result.persisted"}:
            result_node_id = f"evaluation_result:{event_id}"
            self.upsert_node(
                "evaluation_result",
                result_node_id,
                {
                    "source_event_id": event_id,
                    "event_type": event.get("event_type"),
                    "reward": payload.get("reward"),
                    "done": payload.get("done"),
                    "termination_reason": payload.get("termination_reason"),
                    "reward_info_present": payload.get("reward_info") is not None,
                },
            )
            self.add_edge("event_observes_evaluation_result", event_node_id, result_node_id)
        self.add_edge("event_references_source_artifact", event_node_id, "artifact:extracted:baseline_trace.jsonl")
        for artifact_id in source_artifact_ids_for_event(event, self.artifact_index):
            self.add_edge("event_references_source_artifact", event_node_id, artifact_id)

    def attach_packets(self, packets: list[dict[str, Any]]) -> None:
        for packet in packets:
            packet_node_id = f"packet:{packet['packet_id']}"
            event_node_id = f"event:{packet['source_event_id']}"
            self.upsert_node(
                "state_packet",
                packet_node_id,
                {
                    "packet_id": packet["packet_id"],
                    "packet_type": packet["packet_type"],
                    "source_event_id": packet["source_event_id"],
                    "sequence_index": packet["sequence_index"],
                    "state_hash": packet["state_hash"],
                    "packet_hash": packet["packet_hash"],
                    "previous_packet_hash": packet["previous_packet_hash"],
                },
            )
            self.add_edge("packet_derives_from_event", packet_node_id, event_node_id)

    def export(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self.nodes.values(), key=lambda node: (node["kind"], node["id"])),
            "edges": copy.deepcopy(self.edges),
        }


def build_packet_payload(event: dict[str, Any], *, packet_type: str, projection_counts: dict[str, int]) -> dict[str, Any]:
    return {
        "derived_from": "real extracted tau2 baseline TraceEvent",
        "packet_semantics": "observational_serialized_state_only",
        "control_boundary": {
            "controls_tau2_execution": False,
            "controls_task_state": False,
            "controls_lifecycle": False,
            "reactive_manager_enabled": False,
            "activegraph_controls_tau2": False,
        },
        "source_event": copy.deepcopy(event),
        "observed_lifecycle": {
            "packet_type": packet_type,
            "component": event.get("component"),
            "event_type": event.get("event_type"),
            "parent_event_id": event.get("parent_event_id"),
            "trace_state_hash": event.get("state_hash"),
        },
        "activegraph_projection_counts_at_packet_build": projection_counts,
        "execution_boundary_note": "Packet was derived after the tau2 baseline completed and is never fed back into tau2.",
    }


def packet_provenance(
    *,
    baseline_run_dir: pathlib.Path,
    trace_path: pathlib.Path,
    final_state_path: pathlib.Path,
    artifact_index_path: pathlib.Path,
    tau2_upstream_commit: str | None,
    wrapper_repo_commit: str | None,
    command: str,
) -> dict[str, Any]:
    return {
        "baseline_run_dir": rel(baseline_run_dir),
        "baseline_trace_path": rel(trace_path),
        "baseline_trace_final_state_path": rel(final_state_path),
        "baseline_artifact_index_path": rel(artifact_index_path),
        "tau2_upstream_commit": tau2_upstream_commit,
        "wrapper_repo_commit": wrapper_repo_commit,
        "command": command,
        "trace_event_schema_version": SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "source_of_truth": "already-extracted real tau2 baseline TraceEvent stream",
        "projection_artifact": "activegraph_baseline_projection.json",
        "tau2_rerun": False,
        "llm_api_calls_made_by_projection": False,
        "requires_api_keys": False,
        "state_packets_control_tau2": False,
    }


def build_state_packets(events: list[dict[str, Any]], *, provenance: dict[str, Any], projection_counts: dict[str, int]) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    previous_packet_hash: str | None = NO_PREVIOUS_PACKET_HASH
    for index, event in enumerate(events):
        packet_type = packet_type_for_event(event)
        payload = build_packet_payload(event, packet_type=packet_type, projection_counts=projection_counts)
        state_scope = state_scope_for_event(event)
        state_material = {
            "packet_type": packet_type,
            "sequence_index": index,
            "state_scope": state_scope,
            "source_event_id": event["event_id"],
            "source_event_type": event["event_type"],
            "source_event_state_hash": event.get("state_hash"),
            "source_event_payload_hash": stable_hash(event.get("payload", {})),
        }
        packet = {
            "packet_id": f"pkt-{index + 1:06d}",
            "packet_type": packet_type,
            "run_id": event["run_id"],
            "created_at": event["timestamp"],
            "source_event_id": event["event_id"],
            "source_event_type": event["event_type"],
            "sequence_index": index,
            "state_scope": state_scope,
            "state_hash": stable_hash(state_material),
            "packet_hash": None,
            "previous_packet_hash": previous_packet_hash,
            "payload": payload,
            "provenance": copy.deepcopy(provenance),
        }
        packet["packet_hash"] = stable_hash({**packet, "packet_hash": None})
        packets.append(packet)
        previous_packet_hash = packet["packet_hash"]
    return packets


def recompute_packet_hash(packet: dict[str, Any]) -> str:
    unsigned = copy.deepcopy(packet)
    unsigned["packet_hash"] = None
    return stable_hash(unsigned)


def validate_projection_inputs(events: list[dict[str, Any]], final_state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not events:
        errors.append("baseline_trace.jsonl did not contain any events")
    for index, event in enumerate(events):
        missing = [field for field in EVENT_FIELDS if field not in event]
        if missing:
            errors.append(f"event index {index} missing TraceEvent fields: {missing}")
        if event.get("phase") != TRACE_PHASE:
            errors.append(f"event {event.get('event_id')} has unexpected phase {event.get('phase')}")
    if final_state.get("event_count") is not None and final_state.get("event_count") != len(events):
        errors.append(f"baseline final state event_count={final_state.get('event_count')} but trace has {len(events)}")
    return errors


def validate_state_packets(packets: list[dict[str, Any]], *, events: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    event_ids = [event["event_id"] for event in events]
    event_id_set = set(event_ids)
    if len(packets) != len(events):
        errors.append(f"packet/event count mismatch packets={len(packets)} events={len(events)}")
    previous_hash: str | None = NO_PREVIOUS_PACKET_HASH
    for expected_index, packet in enumerate(packets):
        if packet.get("sequence_index") != expected_index:
            errors.append(f"packet {packet.get('packet_id')} has non-monotonic sequence_index")
        if packet.get("packet_id") != f"pkt-{expected_index + 1:06d}":
            errors.append(f"packet index {expected_index} has unexpected packet_id {packet.get('packet_id')}")
        if packet.get("previous_packet_hash") != previous_hash:
            errors.append(f"packet {packet.get('packet_id')} previous hash mismatch")
        if packet.get("packet_hash") != recompute_packet_hash(packet):
            errors.append(f"packet {packet.get('packet_id')} packet_hash mismatch")
        previous_hash = packet.get("packet_hash")
        source_event_id = packet.get("source_event_id")
        if source_event_id not in event_id_set:
            errors.append(f"packet {packet.get('packet_id')} references missing event {source_event_id}")
        elif event_ids[expected_index] != source_event_id:
            errors.append(f"packet {packet.get('packet_id')} source event order mismatch")
        if packet.get("provenance", {}).get("state_packets_control_tau2") is not False:
            errors.append(f"packet {packet.get('packet_id')} claims state-packet control")
        control_boundary = packet.get("payload", {}).get("control_boundary", {})
        for key in CONTROL_CLAIM_KEYS:
            if control_boundary.get(key) is not False:
                errors.append(f"packet {packet.get('packet_id')} has unsafe control boundary {key}")
    packet_types = Counter(packet["packet_type"] for packet in packets)
    return {
        "ok": not errors,
        "errors": errors,
        "packet_count": len(packets),
        "event_count": len(events),
        "packet_types": dict(sorted(packet_types.items())),
        "hash_chain_valid": not any("hash" in error for error in errors),
        "ordering_valid": not any("sequence" in error or "order" in error for error in errors),
        "all_packets_reference_events": not any("missing event" in error for error in errors),
        "packet_count_matches_event_count": len(packets) == len(events),
        "state_packets_control_tau2": False,
    }


def build_packet_index(packets: list[dict[str, Any]], *, validation: dict[str, Any], projection_path: pathlib.Path, events_path: pathlib.Path) -> dict[str, Any]:
    return {
        "schema_version": STATE_PACKET_INDEX_SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "events_path": rel(events_path),
        "activegraph_projection_path": rel(projection_path),
        "packet_count": len(packets),
        "first_packet_hash": packets[0]["packet_hash"] if packets else None,
        "last_packet_hash": packets[-1]["packet_hash"] if packets else None,
        "packet_types": validation["packet_types"],
        "validation": validation,
        "packets": [
            {
                "packet_id": packet["packet_id"],
                "packet_type": packet["packet_type"],
                "sequence_index": packet["sequence_index"],
                "source_event_id": packet["source_event_id"],
                "source_event_type": packet["source_event_type"],
                "state_hash": packet["state_hash"],
                "packet_hash": packet["packet_hash"],
                "previous_packet_hash": packet["previous_packet_hash"],
            }
            for packet in packets
        ],
    }


def optional_trace_comparison(baseline_run_dir: pathlib.Path) -> dict[str, Any] | None:
    comparison_dir = baseline_run_dir / "trace_comparison"
    report_path = comparison_dir / "trace_comparison_report.json"
    final_state_path = comparison_dir / "final_state.json"
    if report_path.is_file():
        report = read_json(report_path)
        return {
            "available": True,
            "report_path": rel(report_path),
            "final_state_path": rel(final_state_path) if final_state_path.is_file() else None,
            "status": report.get("status") if isinstance(report, dict) else None,
        }
    return {
        "available": False,
        "expected_path": rel(report_path),
        "note": "Optional fixture-vs-baseline trace comparison artifact was not present; projection continued from extracted baseline trace only.",
    }


def status_from(validation_errors: list[str], packet_validation: dict[str, Any], gaps: list[str]) -> str:
    if validation_errors or not packet_validation.get("ok"):
        return FAILED_STATUS
    if gaps:
        return GAP_STATUS
    return PASS_STATUS


def write_summary(path: pathlib.Path, final_state: dict[str, Any]) -> None:
    files = "\n".join(f"- `{artifact}`" for artifact in final_state["output_files"])
    gaps = "\n".join(f"- {gap}" for gap in final_state["known_coverage_gaps"]) or "- None observed."
    packet_validation = final_state["state_packet_validation"]
    content = f"""# ActiveGraph projection from real tau2 baseline trace

- Timestamp (UTC): `{final_state['timestamp_utc']}`
- Baseline run: `{final_state['baseline_run_id']}`
- Projection status: `{final_state['status']}`
- Baseline events: `{final_state['baseline_event_count']}`
- Projected nodes: `{final_state['projected_node_count']}`
- Projected edges: `{final_state['projected_edge_count']}`
- State packets: `{final_state['state_packet_count']}`
- Hash chain valid: `{packet_validation['hash_chain_valid']}`
- Packet ordering valid: `{packet_validation['ordering_valid']}`
- Every packet references a baseline event: `{packet_validation['all_packets_reference_events']}`
- Packet count matches event count: `{packet_validation['packet_count_matches_event_count']}`
- tau2 rerun by projection: `{final_state['tau2_rerun']}`
- LLM/API calls made by projection: `{final_state['llm_api_calls_made_by_projection']}`
- Requires API keys: `{final_state['requires_api_keys']}`
- ActiveGraph controls tau2: `{final_state['activegraph_controls_tau2']}`
- Vendor tau2-bench mutated: `{final_state['vendor_tau2_bench_mutated']}`

## Output artifacts

{files}

## Known coverage gaps

{gaps}

## Boundary

This artifact is an offline projection over an already-extracted real tau2
baseline TraceEvent stream. It does not rerun tau2, does not call LLM/API
services, does not require API keys, and does not implement ActiveGraph execution
control.
"""
    path.write_text(content, encoding="utf-8")


def write_raw_log(path: pathlib.Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def project(args: argparse.Namespace) -> int:
    baseline_run_dir = pathlib.Path(args.baseline_run_dir)
    if not baseline_run_dir.is_absolute():
        baseline_run_dir = (REPO_ROOT / baseline_run_dir).resolve()
    output_dir = baseline_run_dir / OUTPUT_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_lines = [
        f"timestamp_utc={utc_now()}",
        f"command={' '.join(sys.argv)}",
        f"baseline_run_dir={rel(baseline_run_dir)}",
        "boundary=tau2_not_rerun,llm_api_calls_not_made,api_keys_not_required,activegraph_execution_control_not_implemented",
    ]

    trace_path = baseline_run_dir / "extracted_trace" / "baseline_trace.jsonl"
    final_state_path = baseline_run_dir / "extracted_trace" / "baseline_trace_final_state.json"
    artifact_index_path = baseline_run_dir / "extracted_trace" / "baseline_artifact_index.json"
    required = [trace_path, final_state_path, artifact_index_path]
    missing = [rel(path) for path in required if not path.is_file()]
    if missing:
        final_state = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "status": INPUTS_MISSING_STATUS,
            "timestamp_utc": utc_now(),
            "baseline_run_dir": rel(baseline_run_dir),
            "missing_inputs": missing,
            "tau2_rerun": False,
            "llm_api_calls_made_by_projection": False,
            "requires_api_keys": False,
            "activegraph_controls_tau2": False,
        }
        write_json(output_dir / "activegraph_projection_final_state.json", final_state)
        raw_lines.append(f"status={INPUTS_MISSING_STATUS}")
        raw_lines.append(f"missing_inputs={missing}")
        write_raw_log(output_dir / "raw.log", raw_lines)
        return 2

    events = read_jsonl(trace_path)
    baseline_final_state = read_json(final_state_path)
    artifact_index = read_json(artifact_index_path)
    baseline_run_id = baseline_final_state.get("run_id") or (events[0].get("run_id") if events else baseline_run_dir.name)
    validation_errors = validate_projection_inputs(events, baseline_final_state)
    comparison = optional_trace_comparison(baseline_run_dir)
    extraction_limitations = baseline_final_state.get("limitations") or artifact_index.get("missing_or_unsupported_artifact_notes", [])
    known_gaps = list(dict.fromkeys(str(item) for item in extraction_limitations))
    if comparison and not comparison.get("available"):
        known_gaps.append(str(comparison.get("note")))

    builder = ProjectionBuilder(run_id=str(baseline_run_id), baseline_run_dir=baseline_run_dir, artifact_index=artifact_index)
    builder.add_artifact_nodes(trace_path=trace_path, final_state_path=final_state_path, artifact_index_path=artifact_index_path)
    previous_event: dict[str, Any] | None = None
    for index, event in enumerate(events):
        builder.project_event(event, sequence_index=index, previous_event=previous_event)
        previous_event = event
    pre_packet_graph = builder.export()
    pre_packet_counts = {"nodes": len(pre_packet_graph["nodes"]), "edges": len(pre_packet_graph["edges"]), "events": len(events)}
    provenance = packet_provenance(
        baseline_run_dir=baseline_run_dir,
        trace_path=trace_path,
        final_state_path=final_state_path,
        artifact_index_path=artifact_index_path,
        tau2_upstream_commit=load_tau2_upstream_commit(),
        wrapper_repo_commit=git_commit(),
        command=" ".join(sys.argv),
    )
    packets = build_state_packets(events, provenance=provenance, projection_counts=pre_packet_counts)
    packet_validation = validate_state_packets(packets, events=events)
    builder.attach_packets(packets)
    graph = builder.export()
    node_count = len(graph["nodes"])
    edge_count = len(graph["edges"])
    status = status_from(validation_errors, packet_validation, known_gaps)

    projection_path = output_dir / "activegraph_baseline_projection.json"
    events_path = output_dir / "activegraph_baseline_events.jsonl"
    packets_path = output_dir / "activegraph_baseline_state_packets.jsonl"
    packet_index_path = output_dir / "activegraph_baseline_state_packet_index.json"
    summary_path = output_dir / "activegraph_projection_summary.md"
    projection_final_state_path = output_dir / "activegraph_projection_final_state.json"
    raw_log_path = output_dir / "raw.log"

    projection = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "trace_event_schema_version": baseline_final_state.get("schema_version") or SCHEMA_VERSION,
        "baseline_run_id": baseline_run_id,
        "status": status,
        "created_at": utc_now(),
        "projection_mode": "offline_activegraph_style_observational_projection",
        "source_of_truth": rel(trace_path),
        "control_boundary": {
            "tau2_rerun": False,
            "llm_api_calls_made_by_projection": False,
            "requires_api_keys": False,
            "activegraph_controls_tau2": False,
            "activegraph_execution_control_implemented": False,
        },
        "metadata": {
            "provider": baseline_final_state.get("provider") or (events[0].get("payload", {}).get("provider") if events else None),
            "model": baseline_final_state.get("model") or (events[0].get("payload", {}).get("model") if events else None),
            "domain": (events[0].get("payload", {}).get("domain") if events else None),
            "task_id": baseline_final_state.get("task_id"),
            "max_steps": (events[0].get("payload", {}).get("max_steps") if events else None),
            "tau2_upstream_commit": provenance["tau2_upstream_commit"],
            "wrapper_repo_commit": provenance["wrapper_repo_commit"],
            "extraction_limitations": extraction_limitations,
            "optional_trace_comparison": comparison,
        },
        "counts": {
            "events": len(events),
            "nodes": node_count,
            "edges": edge_count,
            "state_packets": len(packets),
            "artifact_nodes": sum(1 for node in graph["nodes"] if node["kind"] == "artifact"),
            "component_nodes": sum(1 for node in graph["nodes"] if node["kind"] == "component"),
            "message_role_nodes": sum(1 for node in graph["nodes"] if node["kind"] == "message_role"),
            "tool_nodes": sum(1 for node in graph["nodes"] if node["kind"] == "tool"),
            "evaluation_result_nodes": sum(1 for node in graph["nodes"] if node["kind"] == "evaluation_result"),
        },
        "event_log": copy.deepcopy(events),
        "graph": graph,
        "state_packet_index_path": rel(packet_index_path),
        "known_coverage_gaps": known_gaps,
        "validation": {
            "input_errors": validation_errors,
            "state_packet_validation": packet_validation,
        },
    }
    packet_index = build_packet_index(packets, validation=packet_validation, projection_path=projection_path, events_path=events_path)
    final_state = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "status": status,
        "timestamp_utc": utc_now(),
        "baseline_run_id": baseline_run_id,
        "baseline_run_dir": rel(baseline_run_dir),
        "baseline_event_count": len(events),
        "projected_node_count": node_count,
        "projected_edge_count": edge_count,
        "state_packet_count": len(packets),
        "state_packet_validation": packet_validation,
        "known_coverage_gaps": known_gaps,
        "projection_validation_errors": validation_errors,
        "provider": projection["metadata"]["provider"],
        "model": projection["metadata"]["model"],
        "domain": projection["metadata"]["domain"],
        "task_id": projection["metadata"]["task_id"],
        "max_steps": projection["metadata"]["max_steps"],
        "tau2_upstream_commit": provenance["tau2_upstream_commit"],
        "wrapper_repo_commit": provenance["wrapper_repo_commit"],
        "optional_trace_comparison": comparison,
        "output_files": [
            rel(projection_path),
            rel(events_path),
            rel(packets_path),
            rel(packet_index_path),
            rel(summary_path),
            rel(projection_final_state_path),
            rel(raw_log_path),
        ],
        "tau2_rerun": False,
        "llm_api_calls_made_by_projection": False,
        "requires_api_keys": False,
        "activegraph_controls_tau2": False,
        "vendor_tau2_bench_mutated": False,
    }

    write_json(projection_path, projection)
    write_jsonl(events_path, events)
    write_jsonl(packets_path, packets)
    write_json(packet_index_path, packet_index)
    write_json(projection_final_state_path, final_state)
    write_summary(summary_path, final_state)
    raw_lines.extend(
        [
            f"status={status}",
            f"baseline_event_count={len(events)}",
            f"projected_node_count={node_count}",
            f"projected_edge_count={edge_count}",
            f"state_packet_count={len(packets)}",
            f"hash_chain_valid={packet_validation['hash_chain_valid']}",
            f"ordering_valid={packet_validation['ordering_valid']}",
            f"all_packets_reference_events={packet_validation['all_packets_reference_events']}",
            f"known_gap_count={len(known_gaps)}",
        ]
    )
    if validation_errors:
        raw_lines.append(f"projection_validation_errors={validation_errors}")
    if packet_validation.get("errors"):
        raw_lines.append(f"state_packet_errors={packet_validation['errors']}")
    write_raw_log(raw_log_path, raw_lines)
    print(f"projection_status={status}")
    print(f"baseline_run_id={baseline_run_id}")
    print(f"baseline_event_count={len(events)}")
    print(f"projected_node_count={node_count}")
    print(f"projected_edge_count={edge_count}")
    print(f"state_packet_count={len(packets)}")
    print(f"hash_chain_valid={packet_validation['hash_chain_valid']}")
    print(f"output_dir={rel(output_dir)}")
    return 0 if status in {PASS_STATUS, GAP_STATUS} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run-dir", required=True, help="Path to a completed tau2 baseline run with extracted_trace artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return project(args)
    except Exception as exc:  # noqa: BLE001 - top-level CLI error capture for raw.log/final_state diagnostics.
        baseline_run_dir = pathlib.Path(args.baseline_run_dir)
        if not baseline_run_dir.is_absolute():
            baseline_run_dir = (REPO_ROOT / baseline_run_dir).resolve()
        output_dir = baseline_run_dir / OUTPUT_DIR_NAME
        output_dir.mkdir(parents=True, exist_ok=True)
        final_state = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "status": FAILED_STATUS,
            "timestamp_utc": utc_now(),
            "baseline_run_dir": rel(baseline_run_dir),
            "error": str(exc),
            "tau2_rerun": False,
            "llm_api_calls_made_by_projection": False,
            "requires_api_keys": False,
            "activegraph_controls_tau2": False,
        }
        write_json(output_dir / "activegraph_projection_final_state.json", final_state)
        write_raw_log(
            output_dir / "raw.log",
            [
                f"timestamp_utc={utc_now()}",
                f"command={' '.join(sys.argv)}",
                f"status={FAILED_STATUS}",
                f"error={exc}",
                traceback.format_exc(),
            ],
        )
        print(f"projection_status={FAILED_STATUS}", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
