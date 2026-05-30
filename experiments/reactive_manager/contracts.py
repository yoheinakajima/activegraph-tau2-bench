"""Reactive-manager execution contract data models.

Phase 6 defines structured request/decision records for a future opt-in live
reactive manager. The records are intentionally inert: they describe safety
contracts and fail-closed decisions, but they do not execute tau2 control flow.
"""
from __future__ import annotations

import dataclasses
from typing import Any

CONTRACT_SCHEMA_VERSION = "activegraph_reactive_manager_execution_contract.v1"
CONTRACT_DECISION_SCHEMA_VERSION = "activegraph_reactive_manager_execution_decision.v1"
CONTRACT_REPORT_SCHEMA_VERSION = "activegraph_reactive_manager_contract_report.v1"
PASS_STATUS = "reactive_manager_contracts_passed"
FAILED_STATUS = "reactive_manager_contracts_failed"
INPUTS_MISSING_STATUS = "reactive_manager_contract_inputs_missing"
PLAN_ONLY_MODE = "plan_only"
LIVE_CONTROL_MODE = "live_control"


@dataclasses.dataclass(frozen=True)
class ReactiveManagerSafetyPolicy:
    """Safety policy for all execution-like requests in Phase 6."""

    schema_version: str = CONTRACT_SCHEMA_VERSION
    phase: str = "phase_6_guarded_execution_contracts"
    allowlisted_execution_modes: tuple[str, ...] = (PLAN_ONLY_MODE,)
    live_execution_available: bool = False
    require_explicit_opt_in: bool = True
    require_dry_run: bool = True
    require_operator_acknowledgment: bool = True
    require_events_provenance: bool = True
    require_graph_provenance: bool = True
    require_state_packet_provenance: bool = True
    require_valid_state_packet_hash_chain: bool = True
    require_valid_replay_fork_diff_plan: bool = True
    require_no_pending_validation_errors: bool = True
    require_vendor_unchanged: bool = True
    forbid_api_keys_or_secrets: bool = True
    forbid_model_backed_episode_execution: bool = True
    forbid_tau2_control_flow: bool = True
    fail_closed_by_default: bool = True

    def to_json_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["allowlisted_execution_modes"] = list(self.allowlisted_execution_modes)
        return data


@dataclasses.dataclass(frozen=True)
class ReactiveManagerExecutionRequest:
    """A deterministic, source-linked request for an execution-like boundary."""

    request_id: str
    scenario: str
    run_id: str
    execution_mode: str
    dry_run: bool
    explicit_opt_in: bool
    operator_acknowledgment: str | None
    requested_action: str
    artifact_paths: dict[str, str]
    provenance: dict[str, Any]
    validation: dict[str, Any]
    payload: dict[str, Any]
    schema_version: str = CONTRACT_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ReactiveManagerGuardResult:
    """Result for one safety gate."""

    gate: str
    passed: bool
    reason: str
    source_links: list[str]

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ContractValidationResult:
    """Aggregate validation result for a request and safety policy."""

    ok: bool
    errors: list[str]
    guard_results: list[ReactiveManagerGuardResult]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "guard_results": [result.to_json_dict() for result in self.guard_results],
        }


@dataclasses.dataclass(frozen=True)
class ReactiveManagerExecutionDecision:
    """Structured execution decision emitted by a contract executor."""

    decision_id: str
    request_id: str
    scenario: str
    run_id: str
    accepted: bool
    status: str
    dry_run: bool
    executed: bool
    execution_mode: str
    executor: str
    reason: str
    refusal_reasons: list[str]
    validation: ContractValidationResult
    source_links: list[str]
    schema_version: str = CONTRACT_DECISION_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "scenario": self.scenario,
            "run_id": self.run_id,
            "accepted": self.accepted,
            "status": self.status,
            "dry_run": self.dry_run,
            "executed": self.executed,
            "execution_mode": self.execution_mode,
            "executor": self.executor,
            "reason": self.reason,
            "refusal_reasons": list(self.refusal_reasons),
            "validation": self.validation.to_json_dict(),
            "source_links": list(self.source_links),
        }
