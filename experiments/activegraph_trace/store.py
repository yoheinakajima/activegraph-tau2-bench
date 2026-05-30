"""Trace-only ActiveGraph adapter seam.

This module deliberately models ActiveGraph as an append-only trace projection,
not as a source of task state or control flow. If a real ActiveGraph runtime is
not importable, the smoke uses the deterministic in-memory store below so Phase
3 artifacts remain inspectable without API keys or paid model calls.
"""
from __future__ import annotations

import copy
import importlib.util
from dataclasses import dataclass, field
from typing import Any, Protocol

from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION, TraceEvent

MOCK_ADAPTER_MODE = "mock_in_memory_append_only_projection"
RUNTIME_ADAPTER_MODE = "runtime_importable_trace_projection"
UNAVAILABLE_STATUS = "activegraph_unavailable"
MOCK_STATUS = "activegraph_trace_mock_passed"
RUNTIME_STATUS = "activegraph_trace_runtime_passed"


class ActiveGraphTraceStore(Protocol):
    """Minimal append-only trace store interface for Phase 3."""

    adapter_mode: str
    runtime_available: bool

    def ingest(self, event: TraceEvent) -> None:
        """Append one TraceEvent without mutating it or controlling execution."""

    def export(self, *, provenance: dict[str, Any]) -> dict[str, Any]:
        """Return a deterministic graph/log projection suitable for JSON export."""


@dataclass
class InMemoryActiveGraphTraceStore:
    """Deterministic mock ActiveGraph-style append-only trace projection.

    The store treats each TraceEvent as an immutable log entry and projects a
    small graph over the same stream: run, task, component, event, state, tool,
    and message-role nodes plus parent/containment edges. It does not produce or
    own tau2 state, decisions, or control flow.
    """

    adapter_mode: str = MOCK_ADAPTER_MODE
    runtime_available: bool = False
    runtime_module: str | None = None
    _events: list[dict[str, Any]] = field(default_factory=list)
    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _edges: list[dict[str, Any]] = field(default_factory=list)
    _edge_keys: set[tuple[str, str, str]] = field(default_factory=set)

    def ingest(self, event: TraceEvent) -> None:
        event_dict = copy.deepcopy(event.to_json_dict())
        self._events.append(event_dict)
        self._project_event(event_dict)

    def export(self, *, provenance: dict[str, Any]) -> dict[str, Any]:
        nodes = sorted(self._nodes.values(), key=lambda node: (node["kind"], node["id"]))
        return {
            "schema_version": "activegraph_trace_projection.v1",
            "trace_event_schema_version": SCHEMA_VERSION,
            "trace_event_fields_preserved": EVENT_FIELDS,
            "adapter": {
                "mode": self.adapter_mode,
                "runtime_available": self.runtime_available,
                "runtime_module": self.runtime_module,
                "source_of_truth": "events.jsonl TraceEvent stream",
                "control_flow_owner": "tau2 fixture smoke harness",
                "state_packet_support": False,
                "reactive_manager_support": False,
            },
            "provenance": provenance,
            "counts": {
                "events": len(self._events),
                "nodes": len(nodes),
                "edges": len(self._edges),
            },
            "event_log": copy.deepcopy(self._events),
            "graph": {
                "nodes": nodes,
                "edges": copy.deepcopy(self._edges),
            },
        }

    def _project_event(self, event: dict[str, Any]) -> None:
        run_id = event["run_id"]
        event_node_id = f"event:{event['event_id']}"
        self._upsert_node("run", f"run:{run_id}", {"run_id": run_id})
        self._upsert_node(
            "component",
            f"component:{event['component']}",
            {"component": event["component"]},
        )
        self._upsert_node(
            "event",
            event_node_id,
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "component": event["component"],
                "timestamp": event["timestamp"],
                "phase": event["phase"],
            },
        )
        self._add_edge("contains_event", f"run:{run_id}", event_node_id)
        self._add_edge("emitted_by", event_node_id, f"component:{event['component']}")

        parent_event_id = event.get("parent_event_id")
        if parent_event_id:
            self._add_edge("parent_event", event_node_id, f"event:{parent_event_id}")

        task_id = event.get("task_id")
        if task_id:
            task_node_id = f"task:{task_id}"
            self._upsert_node("task", task_node_id, {"task_id": task_id})
            self._add_edge("scoped_to_task", event_node_id, task_node_id)
            self._add_edge("has_task", f"run:{run_id}", task_node_id)

        state_hash = event.get("state_hash")
        if state_hash:
            state_node_id = f"state:{state_hash}"
            self._upsert_node("state", state_node_id, {"state_hash": state_hash})
            self._add_edge("observed_state", event_node_id, state_node_id)

        tool_name = event.get("tool_name")
        if tool_name:
            tool_node_id = f"tool:{tool_name}"
            self._upsert_node("tool", tool_node_id, {"tool_name": tool_name})
            self._add_edge("references_tool", event_node_id, tool_node_id)

        message_role = event.get("message_role")
        if message_role:
            role_node_id = f"message_role:{message_role}"
            self._upsert_node("message_role", role_node_id, {"message_role": message_role})
            self._add_edge("has_message_role", event_node_id, role_node_id)

    def _upsert_node(self, kind: str, node_id: str, attributes: dict[str, Any]) -> None:
        existing = self._nodes.get(node_id)
        if existing is None:
            self._nodes[node_id] = {"id": node_id, "kind": kind, "attributes": dict(attributes)}
            return
        existing["attributes"].update(attributes)

    def _add_edge(self, edge_type: str, source: str, target: str) -> None:
        key = (edge_type, source, target)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self._edges.append({"type": edge_type, "source": source, "target": target})


def detect_activegraph_runtime() -> tuple[bool, str | None]:
    """Return whether an ActiveGraph runtime module appears importable.

    Candidate names are intentionally conservative. The smoke does not import or
    execute runtime code because Phase 3 must remain no-LLM/API-call safe.
    """
    for module_name in ("activegraph", "active_graph"):
        if importlib.util.find_spec(module_name) is not None:
            return True, module_name
    return False, None


def build_trace_store() -> InMemoryActiveGraphTraceStore:
    """Build the Phase 3 trace store, using mock projection when runtime is absent."""
    runtime_available, runtime_module = detect_activegraph_runtime()
    if runtime_available:
        return InMemoryActiveGraphTraceStore(
            adapter_mode=RUNTIME_ADAPTER_MODE,
            runtime_available=True,
            runtime_module=runtime_module,
        )
    return InMemoryActiveGraphTraceStore(runtime_module=None)


def status_for_store(store: ActiveGraphTraceStore) -> str:
    """Return the externally reported smoke status for a completed store export."""
    if store.runtime_available:
        return RUNTIME_STATUS
    return MOCK_STATUS
