"""State-packet serialization and validation for trace-only smoke runs.

Phase 4 state packets are derived artifacts. They summarize an existing
TraceEvent stream and optional ActiveGraph trace projection without controlling
or mutating tau2 execution.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from collections import Counter
from typing import Any

from experiments.trace_only.schema import SCHEMA_VERSION as TRACE_EVENT_SCHEMA_VERSION
from experiments.trace_only.schema import canonical_json

STATE_PACKET_SCHEMA_VERSION = "activegraph_state_packet.v1"
STATE_PACKET_INDEX_SCHEMA_VERSION = "activegraph_state_packet_index.v1"
EXPECTED_FIXTURE_PACKET_COUNT = 18
NO_PREVIOUS_PACKET_HASH = None
CONTROL_CLAIM_KEYS = {
    "controls_tau2_execution",
    "controls_task_state",
    "controls_lifecycle",
    "reactive_manager_enabled",
    "activegraph_controls_tau2",
}
SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "credential",
    "authorization",
)

EVENT_TO_PACKET_TYPE = {
    "run.started": "run_state",
    "cli.config_inspected": "run_state",
    "batch.started": "run_state",
    "task.started": "task_state",
    "orchestrator.initialized": "task_state",
    "state.snapshot": "task_state",
    "turn.started": "turn_state",
    "message.observed": "turn_state",
    "tool.dispatch_requested": "tool_state",
    "tool.dispatch_completed": "tool_state",
    "evaluation.completed": "evaluation_state",
    "results.persisted": "result_state",
    "run.completed": "run_state",
}


@dataclasses.dataclass(frozen=True)
class StatePacket:
    """Serialized state packet derived from exactly one TraceEvent."""

    packet_id: str
    packet_type: str
    run_id: str
    created_at: str
    source_event_id: str
    source_event_type: str
    sequence_index: int
    state_scope: dict[str, Any]
    state_hash: str
    packet_hash: str | None
    previous_packet_hash: str | None
    payload: dict[str, Any]
    provenance: dict[str, Any]

    def unsigned_dict(self) -> dict[str, Any]:
        """Return the packet body before packet-hash signing."""
        data = dataclasses.asdict(self)
        data["packet_hash"] = None
        return data

    def to_json_dict(self) -> dict[str, Any]:
        """Return the serialized packet dictionary."""
        return dataclasses.asdict(self)


def stable_hash(value: Any) -> str:
    """Return a canonical SHA-256 hash for a JSON-serializable value."""
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def packet_type_for_event(event: dict[str, Any]) -> str:
    """Map a TraceEvent to a Phase 4 state-packet type."""
    return EVENT_TO_PACKET_TYPE.get(event["event_type"], "run_state")


def state_scope_for_event(event: dict[str, Any]) -> dict[str, Any]:
    """Build the deterministic packet scope for a TraceEvent."""
    return {
        "run_id": event["run_id"],
        "task_id": event.get("task_id"),
        "turn_index": event.get("turn_index"),
        "component": event["component"],
        "tool_name": event.get("tool_name"),
        "message_role": event.get("message_role"),
    }


def payload_for_event(
    event: dict[str, Any],
    *,
    activegraph_trace: dict[str, Any],
    packet_type: str,
) -> dict[str, Any]:
    """Build an observational payload from a TraceEvent and trace projection."""
    activegraph_counts = activegraph_trace.get("counts", {})
    return {
        "derived_from": "events.jsonl TraceEvent stream",
        "projection_reference": "activegraph_trace.json",
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
            "component": event["component"],
            "event_type": event["event_type"],
            "parent_event_id": event.get("parent_event_id"),
            "trace_state_hash": event.get("state_hash"),
        },
        "activegraph_projection_counts": {
            "events": activegraph_counts.get("events"),
            "nodes": activegraph_counts.get("nodes"),
            "edges": activegraph_counts.get("edges"),
        },
    }


def packet_provenance(
    *,
    tau2_upstream_commit: str,
    wrapper_repo_commit: str | None,
    command: str,
    activegraph_adapter: dict[str, Any],
    no_llm_status: dict[str, Any],
) -> dict[str, Any]:
    """Return provenance embedded in every packet."""
    return {
        "tau2_upstream_commit": tau2_upstream_commit,
        "wrapper_repo_commit": wrapper_repo_commit,
        "command": command,
        "trace_event_schema_version": TRACE_EVENT_SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "activegraph_adapter_mode": activegraph_adapter.get("mode"),
        "activegraph_runtime_available": activegraph_adapter.get("runtime_available"),
        "activegraph_runtime_module": activegraph_adapter.get("runtime_module"),
        "source_of_truth": "events.jsonl TraceEvent stream",
        "projection_artifact": "activegraph_trace.json",
        "no_llm_status": copy.deepcopy(no_llm_status),
        "state_packets_control_tau2": False,
    }


def build_state_packets(
    events: list[dict[str, Any]],
    *,
    activegraph_trace: dict[str, Any],
    tau2_upstream_commit: str,
    wrapper_repo_commit: str | None,
    command: str,
    no_llm_status: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a hash-chained packet list from ordered TraceEvent dictionaries."""
    activegraph_adapter = activegraph_trace.get("adapter", {})
    provenance = packet_provenance(
        tau2_upstream_commit=tau2_upstream_commit,
        wrapper_repo_commit=wrapper_repo_commit,
        command=command,
        activegraph_adapter=activegraph_adapter,
        no_llm_status=no_llm_status,
    )
    packets: list[dict[str, Any]] = []
    previous_packet_hash: str | None = NO_PREVIOUS_PACKET_HASH
    for index, event in enumerate(events):
        packet_type = packet_type_for_event(event)
        payload = payload_for_event(
            event,
            activegraph_trace=activegraph_trace,
            packet_type=packet_type,
        )
        state_material = {
            "packet_type": packet_type,
            "state_scope": state_scope_for_event(event),
            "source_event_id": event["event_id"],
            "source_event_type": event["event_type"],
            "payload": payload,
        }
        packet = StatePacket(
            packet_id=f"pkt-{index + 1:06d}",
            packet_type=packet_type,
            run_id=event["run_id"],
            created_at=event["timestamp"],
            source_event_id=event["event_id"],
            source_event_type=event["event_type"],
            sequence_index=index,
            state_scope=state_scope_for_event(event),
            state_hash=stable_hash(state_material),
            packet_hash=None,
            previous_packet_hash=previous_packet_hash,
            payload=payload,
            provenance=copy.deepcopy(provenance),
        )
        packet_dict = packet.to_json_dict()
        packet_dict["packet_hash"] = stable_hash(packet.unsigned_dict())
        packets.append(packet_dict)
        previous_packet_hash = packet_dict["packet_hash"]
    return packets


def recompute_packet_hash(packet: dict[str, Any]) -> str:
    """Recompute a packet hash with the packet_hash field unsigned."""
    unsigned = copy.deepcopy(packet)
    unsigned["packet_hash"] = None
    return stable_hash(unsigned)


def contains_secret_key(value: Any) -> bool:
    """Return True when a nested dict key appears to contain secret material.

    Boolean safety flags such as ``requires_api_keys: false`` are allowed
    because they prove no credential was needed rather than carrying a secret.
    """
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if any(fragment in key_lower for fragment in SECRET_KEY_FRAGMENTS):
                if nested is not False and nested is not None:
                    return True
            if contains_secret_key(nested):
                return True
    elif isinstance(value, list):
        return any(contains_secret_key(item) for item in value)
    return False


def validate_state_packets(
    packets: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]],
    activegraph_trace: dict[str, Any],
    tau2_upstream_commit: str,
    wrapper_repo_commit: str | None,
    no_llm_status: dict[str, Any],
    expected_packet_count: int = EXPECTED_FIXTURE_PACKET_COUNT,
) -> dict[str, Any]:
    """Validate ordering, provenance, hash chain, safety, and projection preservation."""
    errors: list[str] = []
    event_ids = [event["event_id"] for event in events]
    event_id_set = set(event_ids)

    if len(packets) != expected_packet_count:
        errors.append(f"expected {expected_packet_count} packets, found {len(packets)}")
    if len(packets) != len(events):
        errors.append(f"packet/event count mismatch packets={len(packets)} events={len(events)}")
    if activegraph_trace.get("event_log") != events:
        errors.append("activegraph_trace.json event_log no longer matches events.jsonl")
    if activegraph_trace.get("counts", {}).get("events") != len(events):
        errors.append("activegraph_trace.json event count does not match events.jsonl")

    previous_hash: str | None = NO_PREVIOUS_PACKET_HASH
    for expected_index, packet in enumerate(packets):
        if packet.get("sequence_index") != expected_index:
            errors.append(f"packet {packet.get('packet_id')} has non-monotonic sequence_index")
        expected_packet_id = f"pkt-{expected_index + 1:06d}"
        if packet.get("packet_id") != expected_packet_id:
            errors.append(f"packet index {expected_index} expected id {expected_packet_id}")
        if packet.get("previous_packet_hash") != previous_hash:
            errors.append(f"packet {packet.get('packet_id')} previous hash mismatch")
        actual_hash = packet.get("packet_hash")
        recomputed_hash = recompute_packet_hash(packet)
        if actual_hash != recomputed_hash:
            errors.append(f"packet {packet.get('packet_id')} packet_hash mismatch")
        previous_hash = actual_hash

        source_event_id = packet.get("source_event_id")
        if source_event_id not in event_id_set:
            errors.append(f"packet {packet.get('packet_id')} references missing event {source_event_id}")
        elif event_ids[expected_index] != source_event_id:
            errors.append(f"packet {packet.get('packet_id')} source event order mismatch")
        provenance = packet.get("provenance", {})
        if provenance.get("tau2_upstream_commit") != tau2_upstream_commit:
            errors.append(f"packet {packet.get('packet_id')} missing tau2 upstream provenance")
        if provenance.get("wrapper_repo_commit") != wrapper_repo_commit:
            errors.append(f"packet {packet.get('packet_id')} missing wrapper commit provenance")
        if provenance.get("state_packets_control_tau2") is not False:
            errors.append(f"packet {packet.get('packet_id')} claims packet control")
        control_boundary = packet.get("payload", {}).get("control_boundary", {})
        for key in CONTROL_CLAIM_KEYS:
            if control_boundary.get(key) is not False:
                errors.append(f"packet {packet.get('packet_id')} has unsafe control boundary {key}")
        packet_no_llm = provenance.get("no_llm_status", {})
        if packet_no_llm != no_llm_status:
            errors.append(f"packet {packet.get('packet_id')} no-LLM provenance mismatch")
        if contains_secret_key(packet):
            errors.append(f"packet {packet.get('packet_id')} contains secret-like key")

    if no_llm_status.get("llm_api_calls") is not False:
        errors.append("no_llm_status indicates LLM/API calls were made")
    if no_llm_status.get("paid_llm_apis_called") is not False:
        errors.append("no_llm_status indicates paid LLM APIs were called")

    packet_types = Counter(packet["packet_type"] for packet in packets)
    return {
        "ok": not errors,
        "errors": errors,
        "packet_count": len(packets),
        "expected_packet_count": expected_packet_count,
        "event_count": len(events),
        "packet_types": dict(sorted(packet_types.items())),
        "hash_chain_valid": not any("hash" in error for error in errors),
        "ordering_valid": not any("sequence" in error or "order" in error for error in errors),
        "all_packets_reference_events": not any("missing event" in error for error in errors),
        "activegraph_projection_preserved": activegraph_trace.get("event_log") == events,
        "no_llm_api_calls_validated": no_llm_status.get("llm_api_calls") is False
        and no_llm_status.get("paid_llm_apis_called") is False,
    }


def build_packet_index(
    packets: list[dict[str, Any]],
    *,
    validation: dict[str, Any],
    activegraph_trace_path: str,
    events_path: str,
) -> dict[str, Any]:
    """Build a compact lookup and validation index for state packets."""
    return {
        "schema_version": STATE_PACKET_INDEX_SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "events_path": events_path,
        "activegraph_trace_path": activegraph_trace_path,
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


def write_jsonl(path: Any, rows: list[dict[str, Any]]) -> None:
    """Write canonical JSONL rows for deterministic packet artifacts."""
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
