"""Schema helpers for passive write-intent observer artifacts.

The schema is intentionally repository-owned and JSON-only so it can be
emitted from no-LLM smokes and from optional runtime trace hooks without
importing or mutating vendored tau2-bench code.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "write_intent_observer.v1"
WARNING_PHASES = {
    "pre_write_detectable",
    "runtime_observable",
    "post_write_only",
    "requires_future_control",
}
BOUNDARY_FLAGS = {
    "passive_observer_only": True,
    "activegraph_control_enabled": False,
    "blocks_tool_calls": False,
    "rewrites_tool_arguments": False,
    "repairs_or_rolls_back": False,
    "feeds_state_packets_back_to_tau2": False,
    "mutates_vendor_tau2_bench": False,
    "llm_or_api_calls_made": False,
}

WarningPhase = Literal[
    "pre_write_detectable",
    "runtime_observable",
    "post_write_only",
    "requires_future_control",
]


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source: str
    description: str
    turn_index: int | None = None
    tool_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "description": self.description,
            "turn_index": self.turn_index,
            "tool_name": self.tool_name,
        }


@dataclass(frozen=True)
class ObserverWarning:
    code: str
    phase: WarningPhase
    severity: Literal["info", "low", "medium", "high"]
    message: str
    evidence_refs: list[str] = field(default_factory=list)
    requires_future_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        if self.phase not in WARNING_PHASES:
            raise ValueError(f"invalid warning phase: {self.phase}")
        return {
            "code": self.code,
            "phase": self.phase,
            "severity": self.severity,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
            "requires_future_control": self.requires_future_control,
        }


class JsonlWriter:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")

    def write(self, payload: dict[str, Any]) -> None:
        self._handle.write(json_dumps(payload) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()
