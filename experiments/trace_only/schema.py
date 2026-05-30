"""Trace event schema primitives for no-LLM tau2-bench observability.

The schema is intentionally repository-owned and independent of the vendored
upstream tau2-bench tree. Phase 2 records fixture-backed baseline lifecycle
observations only; future phases can reuse the same event envelope around real
runtime hooks.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from typing import Any

SCHEMA_VERSION = "trace_event.v1"
TRACE_PHASE = "phase_2_trace_only_baseline"

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


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for event emission."""
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    """Serialize data in a deterministic JSON form suitable for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def state_hash(value: Any) -> str:
    """Return a stable SHA-256 hash for a JSON-serializable state snapshot."""
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class TraceEvent:
    """Append-only JSONL event envelope used by the Phase 2 trace smoke."""

    event_id: str
    timestamp: str
    run_id: str
    phase: str
    component: str
    event_type: str
    task_id: str | None = None
    turn_index: int | None = None
    tool_name: str | None = None
    message_role: str | None = None
    state_hash: str | None = None
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    parent_event_id: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """Return the complete schema with stable field ordering."""
        data = dataclasses.asdict(self)
        return {field: data[field] for field in EVENT_FIELDS}
