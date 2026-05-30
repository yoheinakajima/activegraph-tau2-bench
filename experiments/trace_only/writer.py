"""Append-only JSONL trace writer for Phase 2 no-LLM smoke runs."""
from __future__ import annotations

import json
import pathlib
from typing import Any

from experiments.trace_only.schema import TRACE_PHASE, TraceEvent, utc_timestamp


class TraceWriter:
    """Write trace events to a run-scoped append-only JSONL file.

    Event IDs are monotonic within the run so fixture-backed smoke output is
    deterministic aside from wall-clock timestamps and git provenance.
    """

    def __init__(self, path: pathlib.Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._next_id = 1
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
        state_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            event_id=f"evt-{self._next_id:06d}",
            timestamp=utc_timestamp(),
            run_id=self.run_id,
            phase=TRACE_PHASE,
            component=component,
            event_type=event_type,
            task_id=task_id,
            turn_index=turn_index,
            tool_name=tool_name,
            message_role=message_role,
            state_hash=state_hash,
            payload=payload or {},
            parent_event_id=parent_event_id,
        )
        self._next_id += 1
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_json_dict(), sort_keys=False) + "\n")
        return event
