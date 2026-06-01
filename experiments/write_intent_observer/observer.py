"""Deterministic passive write-intent observer.

This module emits observational artifacts only. It never blocks calls, rewrites
arguments, repairs state, rolls back writes, or feeds packets back into tau2.
"""
from __future__ import annotations

import json
import pathlib
import uuid
from typing import Any

from .schema import BOUNDARY_FLAGS, SCHEMA_VERSION, JsonlWriter, ObserverWarning, utc_now

WRITE_TOOL_HINTS = {"book_reservation", "create_task", "update_task", "delete_task", "send_message", "modify_reservation"}


def _get_path(payload: dict[str, Any], dotted: str) -> Any:
    current: Any = payload
    for part in dotted.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _argument_entities(arguments: dict[str, Any]) -> set[str]:
    entities: set[str] = set()
    for key in ("entity_refs", "entities", "required_entities"):
        value = arguments.get(key)
        if isinstance(value, list):
            entities.update(str(item) for item in value)
    passengers = arguments.get("passengers")
    if isinstance(passengers, list):
        for passenger in passengers:
            if isinstance(passenger, dict) and passenger.get("name") is not None:
                entities.add(str(passenger["name"]))
            elif passenger is not None:
                entities.add(str(passenger))
    for key in ("task_id", "user_id", "reservation_id"):
        if arguments.get(key) is not None:
            entities.add(str(arguments[key]))
            entities.add(f"task:{arguments[key]}")
    return entities


def _severity_penalty(severity: str) -> float:
    return {"info": 0.03, "low": 0.08, "medium": 0.18, "high": 0.30}.get(severity, 0.1)


class PassiveWriteIntentObserver:
    def __init__(self, out_dir: pathlib.Path, *, run_id: str | None = None):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or self.out_dir.name
        self.event_writer = JsonlWriter(self.out_dir / "observer_events.jsonl")
        self.ledger_writer = JsonlWriter(self.out_dir / "constraint_ledger_snapshots.jsonl")
        self.diff_writer = JsonlWriter(self.out_dir / "write_intent_diffs.jsonl")
        self.event_count = 0
        self.warning_counts: dict[str, int] = {}
        self.case_results: list[dict[str, Any]] = []

    def close(self) -> None:
        self.event_writer.close()
        self.ledger_writer.close()
        self.diff_writer.close()

    def _event(self, event_type: str, case_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        self.event_count += 1
        event = {
            "schema": SCHEMA_VERSION,
            "event_id": f"wio-{self.event_count:06d}-{uuid.uuid4().hex[:8]}",
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "event_type": event_type,
            "case_id": case_id,
            "payload": payload,
            "observer_boundary": dict(BOUNDARY_FLAGS),
        }
        self.event_writer.write(event)
        return event

    def observe_case(self, case: dict[str, Any]) -> dict[str, Any]:
        case_id = case["case_id"]
        ledger = case.get("ledger", {})
        evidence = ledger.get("evidence", [])
        evidence_tool_names = {item.get("tool_name") for item in evidence if isinstance(item, dict)}
        ledger_snapshot = {
            "schema": SCHEMA_VERSION,
            "snapshot_id": f"ledger-{case_id}",
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "case_id": case_id,
            "domain": case.get("domain"),
            "source": case.get("source"),
            "constraint_ledger": ledger,
            "evidence_refs": evidence,
            "observer_boundary": dict(BOUNDARY_FLAGS),
        }
        self.ledger_writer.write(ledger_snapshot)
        self._event("constraint_ledger_snapshot", case_id, ledger_snapshot)

        write_tool_names = set(case.get("write_tool_names") or WRITE_TOOL_HINTS)
        write_calls = [call for call in case.get("tool_calls", []) if call.get("tool_name") in write_tool_names]
        warnings: list[ObserverWarning] = []
        diffs: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []

        if case.get("expected_write") and not write_calls:
            warnings.append(ObserverWarning("no_write_observed", "runtime_observable", "high", "Expected write intent was not observed at runtime.", [ref.get("evidence_id") for ref in evidence if ref.get("evidence_id")]))

        for call in write_calls:
            arguments = call.get("arguments") or {}
            candidate = {
                "schema": SCHEMA_VERSION,
                "candidate_id": f"intent-{case_id}-{call.get('event_id', len(candidates) + 1)}",
                "case_id": case_id,
                "turn_index": call.get("turn_index"),
                "tool_name": call.get("tool_name"),
                "proposed_write_arguments": arguments,
                "evidence_refs": evidence,
                "observer_boundary": dict(BOUNDARY_FLAGS),
            }
            candidates.append(candidate)
            self._event("write_intent_candidate", case_id, candidate)

            missing_entities = sorted(set(ledger.get("required_entities", [])) - _argument_entities(arguments))
            if missing_entities:
                warnings.append(ObserverWarning("required_entity_missing", "pre_write_detectable", "high", f"Required entities missing from proposed write arguments: {', '.join(missing_entities)}.", [ref.get("evidence_id") for ref in evidence if ref.get("evidence_id")]))

            arg_mismatches: list[dict[str, Any]] = []
            for path, expected in (ledger.get("expected_write_args") or {}).items():
                actual = _get_path(arguments, path)
                if actual != expected:
                    code = "payment_mismatch" if "payment" in path else "price_mismatch" if "price" in path or "total" in path else "write_argument_mismatch"
                    severity = "high" if code in {"payment_mismatch", "price_mismatch"} else "medium"
                    warnings.append(ObserverWarning(code, "pre_write_detectable", severity, f"Argument `{path}` was `{actual}` but ledger expected `{expected}`.", [ref.get("evidence_id") for ref in evidence if ref.get("evidence_id")]))
                    arg_mismatches.append({"path": path, "expected": expected, "actual": actual, "code": code})

            missing_reads = sorted(set(ledger.get("required_prerequisite_reads", [])) - evidence_tool_names)
            if missing_reads:
                warnings.append(ObserverWarning("write_before_prerequisite_read", "runtime_observable", "high", f"Write was observed before prerequisite read evidence: {', '.join(missing_reads)}.", []))

            selected_option = arguments.get("selected_option") or arguments.get("assignee") or arguments.get("status")
            supported_options = set(ledger.get("supported_options", []))
            if supported_options and selected_option is not None and selected_option not in supported_options:
                warnings.append(ObserverWarning("selected_option_unsupported", "pre_write_detectable", "medium", f"Selected option `{selected_option}` was not supported by ledger evidence.", [ref.get("evidence_id") for ref in evidence if ref.get("evidence_id")]))

            if any(w.phase == "pre_write_detectable" and w.severity in {"medium", "high"} for w in warnings):
                warnings.append(ObserverWarning("requires_future_control_to_block", "requires_future_control", "info", "Preventing this write would require future ActiveGraph control; this observer only emits artifacts.", [], True))

            diff = {
                "schema": SCHEMA_VERSION,
                "diff_id": f"diff-{case_id}-{call.get('event_id', len(diffs) + 1)}",
                "timestamp": utc_now(),
                "run_id": self.run_id,
                "case_id": case_id,
                "tool_name": call.get("tool_name"),
                "proposed_write_arguments": arguments,
                "argument_vs_ledger_diff": {
                    "missing_entities": missing_entities,
                    "argument_mismatches": arg_mismatches,
                    "missing_prerequisite_reads": missing_reads,
                    "selected_option": selected_option,
                    "selected_option_supported": not (supported_options and selected_option is not None and selected_option not in supported_options),
                },
                "observer_boundary": dict(BOUNDARY_FLAGS),
            }
            diffs.append(diff)
            self.diff_writer.write(diff)
            self._event("write_argument_diff", case_id, diff)

        post = case.get("post_write_state") or {}
        if post and post.get("matches_expected") is False:
            # No-write cases already get runtime_observable; emit post-write mismatch too.
            warnings.append(ObserverWarning("post_write_state_mismatch", "post_write_only", "medium", post.get("description") or "Post-write state did not match expected state.", []))
        evaluation = case.get("evaluation") or {}
        if evaluation.get("ambiguous"):
            warnings.append(ObserverWarning("scoring_evaluation_ambiguity", "post_write_only", "low", evaluation.get("description") or "Scoring/evaluation ambiguity observed.", []))

        # Deduplicate warning dicts while preserving order.
        seen: set[tuple[str, str]] = set()
        warning_dicts: list[dict[str, Any]] = []
        for warning in warnings:
            key = (warning.code, warning.message)
            if key in seen:
                continue
            seen.add(key)
            item = warning.to_dict()
            warning_dicts.append(item)
            self.warning_counts[item["phase"]] = self.warning_counts.get(item["phase"], 0) + 1

        readiness_score = max(0.0, round(1.0 - sum(_severity_penalty(w["severity"]) for w in warning_dicts), 2))
        result = {
            "case_id": case_id,
            "label": case.get("label"),
            "domain": case.get("domain"),
            "write_intents_observed": len(write_calls),
            "readiness_score": readiness_score,
            "warnings": warning_dicts,
            "warning_codes": [warning["code"] for warning in warning_dicts],
            "candidate_count": len(candidates),
            "diff_count": len(diffs),
            "expected_warning_codes": case.get("expected_warning_codes", []),
        }
        self.case_results.append(result)
        self._event("readiness_score", case_id, {"case_id": case_id, "readiness_score": readiness_score, "warnings": warning_dicts})
        return result

    def observe_runtime_tool_dispatch(self, *, task_id: str | None, tool_name: str | None, arguments: dict[str, Any] | None, turn_index: int | None = None, state_hash: str | None = None) -> None:
        """Emit a best-effort runtime candidate from live trace hooks.

        This method intentionally has no return value used by tau2 execution.
        It cannot block, mutate, or rewrite dispatch arguments.
        """
        if tool_name not in WRITE_TOOL_HINTS:
            return
        payload = {
            "schema": SCHEMA_VERSION,
            "candidate_id": f"runtime-intent-{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "turn_index": turn_index,
            "tool_name": tool_name,
            "state_hash": state_hash,
            "proposed_write_arguments": arguments or {},
            "evidence_refs": [],
            "warnings": [
                ObserverWarning(
                    "runtime_candidate_without_fixture_ledger",
                    "runtime_observable",
                    "low",
                    "Runtime write candidate observed without fixture/offline expected ledger; no control action taken.",
                    [],
                ).to_dict()
            ],
            "readiness_score": 0.92,
            "observer_boundary": dict(BOUNDARY_FLAGS),
        }
        self._event("write_intent_candidate", task_id, payload)

    def final_state(self, status: str) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "status": status,
            "run_id": self.run_id,
            "event_count": self.event_count,
            "case_count": len(self.case_results),
            "warning_counts_by_phase": dict(sorted(self.warning_counts.items())),
            "case_results": self.case_results,
            "artifacts": [
                "observer_events.jsonl",
                "constraint_ledger_snapshots.jsonl",
                "write_intent_diffs.jsonl",
                "observer_summary.md",
                "observer_final_state.json",
                "raw.log",
            ],
            "observer_boundary": dict(BOUNDARY_FLAGS),
        }


def validate_jsonl(path: pathlib.Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            json.loads(line)
            count += 1
    return count
