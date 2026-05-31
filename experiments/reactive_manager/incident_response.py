"""Design-only incident-response contracts for future live-manager phases.

Phase 10 models incident declaration and rollback/recovery planning shape only.
Plans are source-linked and inert: they cannot execute rollback, mutate tau2,
call model/API services, or control tau2 lifecycle/task state.
"""
from __future__ import annotations

import copy
import dataclasses
from typing import Any

INCIDENT_DECLARATION_SCHEMA_VERSION = "activegraph_incident_declaration.v1"
INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION = "activegraph_incident_response_plan.v1"
INCIDENT_RESPONSE_DECISION_SCHEMA_VERSION = "activegraph_incident_response_decision.v1"
INCIDENT_RESPONSE_LIVE_READY = False


@dataclasses.dataclass(frozen=True)
class IncidentDeclaration:
    incident_id: str | None
    severity: str | None
    declared_by: str
    related_run_id: str
    affected_artifacts: list[str]
    requested_execute_rollback: bool = False
    requested_tau2_mutation: bool = False
    requested_model_api_call: bool = False
    schema_version: str = INCIDENT_DECLARATION_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class IncidentResponsePlan:
    incident_id: str | None
    severity: str | None
    declared_by: str
    related_run_id: str
    affected_artifacts: list[str]
    rollback_plan_ref: str | None
    replay_plan_ref: str | None
    fork_plan_ref: str | None
    audit_log_ref: str | None
    state_packet_index_ref: str | None
    containment_steps: list[str]
    recovery_steps: list[str]
    verification_steps: list[str]
    execute_rollback_requested: bool = False
    mutate_tau2_requested: bool = False
    model_api_call_requested: bool = False
    scenario: str = "unspecified"
    schema_version: str = INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class IncidentResponseDecision:
    decision_id: str
    incident_id: str | None
    scenario: str
    structurally_complete: bool
    accepted: bool
    plan_only: bool
    rollback_executed: bool
    status: str
    reason: str
    blockers: list[str]
    source_links: list[str]
    live_ready: bool = False
    live_execution_available: bool = False
    incident_response_live_ready: bool = INCIDENT_RESPONSE_LIVE_READY
    schema_version: str = INCIDENT_RESPONSE_DECISION_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def validate_incident_response_plan(plan: IncidentResponsePlan) -> IncidentResponseDecision:
    blockers: list[str] = []
    if not plan.incident_id:
        blockers.append("missing_incident_id")
    if not plan.severity:
        blockers.append("missing_severity")
    if not plan.rollback_plan_ref:
        blockers.append("missing_rollback_plan_ref")
    if not plan.replay_plan_ref:
        blockers.append("missing_replay_plan_ref")
    if not plan.fork_plan_ref:
        blockers.append("missing_fork_plan_ref")
    if not plan.audit_log_ref:
        blockers.append("missing_audit_log_ref")
    if not plan.state_packet_index_ref:
        blockers.append("missing_state_packet_index_ref")
    if not plan.affected_artifacts:
        blockers.append("missing_affected_artifacts")
    if not plan.containment_steps:
        blockers.append("missing_containment_steps")
    if not plan.recovery_steps:
        blockers.append("missing_recovery_steps")
    if not plan.verification_steps:
        blockers.append("missing_verification_steps")
    if plan.execute_rollback_requested:
        blockers.append("rollback_execution_unavailable")
    if plan.mutate_tau2_requested:
        blockers.append("tau2_mutation_rejected")
    if plan.model_api_call_requested:
        blockers.append("model_api_call_rejected")

    unique_blockers = sorted(set(blockers))
    structurally_complete = not unique_blockers
    status = "plan_only_disabled" if structurally_complete else "rejected"
    reason = "incident_plan_structurally_complete_but_rollback_execution_disabled" if structurally_complete else "incident_plan_rejected_fail_closed"
    source_links = [
        ref
        for ref in [plan.rollback_plan_ref, plan.replay_plan_ref, plan.fork_plan_ref, plan.audit_log_ref, plan.state_packet_index_ref]
        if ref
    ] + list(plan.affected_artifacts)
    return IncidentResponseDecision(
        decision_id=f"incident-response-decision-for-{plan.scenario}",
        incident_id=plan.incident_id,
        scenario=plan.scenario,
        structurally_complete=structurally_complete,
        accepted=False,
        plan_only=True,
        rollback_executed=False,
        status=status,
        reason=reason,
        blockers=unique_blockers or ["incident_response_live_ready_false", "rollback_execution_unavailable", "live_execution_unavailable_fail_closed"],
        source_links=source_links,
    )


def build_incident_response_contracts(*, run_id: str, artifact_paths: dict[str, str]) -> dict[str, Any]:
    """Build deterministic Phase 10 incident declaration/plan scenarios."""
    base_declaration = {
        "incident_id": "incident-phase10-000001",
        "severity": "sev3_mock_contract",
        "declared_by": "operator-fixture-phase10",
        "related_run_id": run_id,
        "affected_artifacts": [artifact_paths["manager_plan.json"], artifact_paths["state_packet_index.json"]],
    }
    base_plan = {
        "incident_id": base_declaration["incident_id"],
        "severity": base_declaration["severity"],
        "declared_by": base_declaration["declared_by"],
        "related_run_id": base_declaration["related_run_id"],
        "affected_artifacts": copy.deepcopy(base_declaration["affected_artifacts"]),
        "rollback_plan_ref": artifact_paths["manager_plan.json"],
        "replay_plan_ref": artifact_paths["replay_plan.json"],
        "fork_plan_ref": artifact_paths["fork_plan.json"],
        "audit_log_ref": artifact_paths["audit_log.jsonl"],
        "state_packet_index_ref": artifact_paths["state_packet_index.json"],
        "containment_steps": ["freeze live-manager promotion", "preserve generated artifacts", "keep tau2 ownership unchanged"],
        "recovery_steps": ["review replay plan", "review fork plan", "draft manual recovery checklist"],
        "verification_steps": ["verify live_ready remains false", "verify rollback_executed remains false", "verify vendor tree remains clean"],
        "execute_rollback_requested": False,
        "mutate_tau2_requested": False,
        "model_api_call_requested": False,
    }

    def plan(index: int, scenario: str, **updates: Any) -> IncidentResponsePlan:
        data = copy.deepcopy(base_plan)
        data["incident_id"] = f"incident-phase10-{index:06d}"
        data.update(updates)
        return IncidentResponsePlan(scenario=scenario, **data)

    plans = [
        plan(1, "complete_plan_only_incident"),
        plan(2, "missing_incident_id", incident_id=""),
        plan(3, "missing_severity", severity=""),
        plan(4, "missing_rollback_replay_fork_refs", rollback_plan_ref=None, replay_plan_ref=None, fork_plan_ref=None),
        plan(5, "missing_audit_ref", audit_log_ref=None),
        plan(6, "missing_state_packet_chain_ref", state_packet_index_ref=None),
        plan(7, "request_execute_rollback", execute_rollback_requested=True),
        plan(8, "request_tau2_mutation", mutate_tau2_requested=True),
        plan(9, "request_model_api_call", model_api_call_requested=True),
    ]
    declarations = [
        IncidentDeclaration(
            incident_id=item.incident_id,
            severity=item.severity,
            declared_by=item.declared_by,
            related_run_id=item.related_run_id,
            affected_artifacts=list(item.affected_artifacts),
            requested_execute_rollback=item.execute_rollback_requested,
            requested_tau2_mutation=item.mutate_tau2_requested,
            requested_model_api_call=item.model_api_call_requested,
        ).to_json_dict()
        for item in plans
    ]
    decisions = [validate_incident_response_plan(item).to_json_dict() for item in plans]
    disabled_count = sum(1 for decision in decisions if decision["status"] == "plan_only_disabled")
    rejected_count = sum(1 for decision in decisions if decision["status"] == "rejected")
    required_blockers = {
        "missing_incident_id",
        "missing_severity",
        "missing_rollback_plan_ref",
        "missing_replay_plan_ref",
        "missing_fork_plan_ref",
        "missing_audit_log_ref",
        "missing_state_packet_index_ref",
        "rollback_execution_unavailable",
        "tau2_mutation_rejected",
        "model_api_call_rejected",
    }
    observed_blockers = {blocker for decision in decisions for blocker in decision["blockers"]}
    contracts_ok = (
        INCIDENT_RESPONSE_LIVE_READY is False
        and disabled_count == 1
        and rejected_count == len(decisions) - 1
        and required_blockers.issubset(observed_blockers)
        and all(decision["accepted"] is False for decision in decisions)
        and all(decision["rollback_executed"] is False for decision in decisions)
    )
    return {
        "schema_version": "activegraph_incident_response_contracts.v1",
        "run_id": run_id,
        "incident_response_live_ready": INCIDENT_RESPONSE_LIVE_READY,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "incident_declarations": declarations,
        "incident_response_plans": [item.to_json_dict() for item in plans],
        "decisions": decisions,
        "structurally_complete_plan_only_count": disabled_count,
        "accepted_decision_count": 0,
        "rejected_decision_count": rejected_count,
        "required_blockers": sorted(required_blockers),
        "observed_blockers": sorted(observed_blockers),
        "rollback_execution_available": False,
        "rollback_executed": False,
        "contracts_ok": contracts_ok,
    }
