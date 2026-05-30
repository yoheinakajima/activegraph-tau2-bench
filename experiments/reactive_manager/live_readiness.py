"""Fail-closed live-readiness validation for Phase 7 opt-in proposals."""
from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any

from experiments.reactive_manager.guards import SECRET_VALUE_PATTERN
from experiments.reactive_manager.live_opt_in import LIVE_OPT_IN_DISABLED_ACK, LIVE_SCOPE_CONTRACT_ONLY, LiveManagerOptInProposal

LIVE_READINESS_DECISION_SCHEMA_VERSION = "activegraph_live_reactive_manager_readiness_decision.v1"
LIVE_READINESS_REPORT_SCHEMA_VERSION = "activegraph_live_reactive_manager_readiness_report.v1"
LIVE_OPT_IN_PASS_STATUS = "live_manager_opt_in_contracts_passed"
LIVE_OPT_IN_FAILED_STATUS = "live_manager_opt_in_contracts_failed"
LIVE_OPT_IN_INPUTS_MISSING_STATUS = "live_manager_opt_in_inputs_missing"

REQUIREMENT_LABELS = {
    "operator_authorization": "operator authorization",
    "credential_secret_policy": "credential and secret policy",
    "tau2_lifecycle_ownership": "tau2 lifecycle ownership",
    "sandbox_isolation": "sandbox and isolation",
    "rollback_recovery": "rollback and recovery",
    "audit_logging": "audit logging",
    "packet_chain": "state-packet chain",
    "phase7_disabled_by_construction": "Phase 7 disabled-by-construction readiness scoring",
}


@dataclasses.dataclass(frozen=True)
class LiveReadinessGateResult:
    requirement: str
    gate: str
    passed: bool
    blocker: str | None
    source_links: list[str]

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class LiveReadinessDecision:
    decision_id: str
    proposal_id: str
    scenario: str
    run_id: str
    structurally_complete: bool
    accepted: bool
    status: str
    live_ready: bool
    live_execution_available: bool
    executed: bool
    reason: str
    blockers: list[dict[str, Any]]
    gate_results: list[LiveReadinessGateResult]
    source_links: list[str]
    schema_version: str = LIVE_READINESS_DECISION_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "scenario": self.scenario,
            "run_id": self.run_id,
            "structurally_complete": self.structurally_complete,
            "accepted": self.accepted,
            "status": self.status,
            "live_ready": self.live_ready,
            "live_execution_available": self.live_execution_available,
            "executed": self.executed,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "gate_results": [result.to_json_dict() for result in self.gate_results],
            "source_links": list(self.source_links),
        }



def _contains_secret_like_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_secret_like_value(nested) for nested in value.values())
    if isinstance(value, list):
        return any(_contains_secret_like_value(item) for item in value)
    if isinstance(value, str):
        return SECRET_VALUE_PATTERN.search(value) is not None
    return False

def vendor_status(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--", "vendor/tau2-bench"],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def _gate(requirement: str, gate: str, passed: bool, blocker: str | None, source_links: list[str] | None = None) -> LiveReadinessGateResult:
    return LiveReadinessGateResult(requirement=requirement, gate=gate, passed=passed, blocker=None if passed else blocker, source_links=source_links or [])


def _artifact_source(proposal: LiveManagerOptInProposal, *names: str) -> list[str]:
    return [proposal.artifact_paths[name] for name in names if name in proposal.artifact_paths]


def validate_live_readiness_proposal(proposal: LiveManagerOptInProposal, *, repo_root: Path, decision_id: str) -> LiveReadinessDecision:
    """Validate a proposal without enabling or executing live control."""
    results: list[LiveReadinessGateResult] = []

    op = proposal.operator_authorization
    results.extend(
        [
            _gate("operator_authorization", "operator_acknowledgement_present", op.get("operator_acknowledged") is True and op.get("operator_acknowledgment") == LIVE_OPT_IN_DISABLED_ACK, "operator acknowledgement for proposal-only/no-live execution is missing."),
            _gate("operator_authorization", "experiment_id_present", bool(op.get("experiment_id")), "explicit experiment ID is required."),
            _gate("operator_authorization", "run_scope_present", op.get("run_scope") == LIVE_SCOPE_CONTRACT_ONLY, "explicit proposal-only run scope is required."),
            _gate("operator_authorization", "rollback_acknowledgement_present", op.get("rollback_acknowledged") is True, "rollback acknowledgement is required."),
            _gate("operator_authorization", "audit_log_acknowledgement_present", op.get("audit_log_acknowledged") is True, "audit-log acknowledgement is required."),
        ]
    )

    credentials = proposal.credential_policy
    results.extend(
        [
            _gate("credential_secret_policy", "no_secrets_in_request_payloads", credentials.get("no_secrets_in_request_payloads") is True and not _contains_secret_like_value(proposal.to_json_dict()), "request payloads and proposal artifacts must not contain secret-like material."),
            _gate("credential_secret_policy", "no_api_keys_in_artifacts", credentials.get("no_api_keys_in_artifacts") is True, "API keys must not be written to artifacts."),
            _gate("credential_secret_policy", "no_environment_variable_leakage", credentials.get("no_environment_variable_leakage") is True, "environment-variable leakage must be forbidden."),
            _gate("credential_secret_policy", "credential_references_are_handles", credentials.get("credential_references_are_handles") is True and credentials.get("raw_credential_values_present") is False, "future credential references must be handles, not raw values."),
            _gate("credential_secret_policy", "credential_vault_supported", credentials.get("credential_vault_supported") is True, "missing credential vault support keeps live readiness false."),
        ]
    )

    ownership = proposal.ownership_boundary
    results.extend(
        [
            _gate("tau2_lifecycle_ownership", "ownership_boundary_acknowledged", ownership.get("boundary_acknowledged") is True, "explicit ownership boundary is required."),
            _gate("tau2_lifecycle_ownership", "tau2_ownership_statement_present", bool(ownership.get("tau2_owns")), "statement of what tau2 owns is required."),
            _gate("tau2_lifecycle_ownership", "activegraph_ownership_statement_present", bool(ownership.get("activegraph_owns")), "statement of what ActiveGraph owns is required."),
            _gate("tau2_lifecycle_ownership", "no_ambiguous_control_ownership", ownership.get("ambiguous_control_ownership") is False and ownership.get("activegraph_controls_tau2") is False, "ambiguous or ActiveGraph-owned tau2 control is forbidden."),
            _gate("tau2_lifecycle_ownership", "validated_ownership_plan", ownership.get("validated_ownership_plan") is True, "future live control cannot proceed without a validated ownership plan."),
        ]
    )

    sandbox = proposal.sandbox_isolation
    dirty_vendor = proposal.simulation_overrides.get("dirty_vendor_tree") is True or bool(vendor_status(repo_root))
    results.extend(
        [
            _gate("sandbox_isolation", "sandbox_mode_required_and_declared", sandbox.get("sandbox_mode_required") is True and sandbox.get("sandbox_mode_declared") is True, "future live execution must require and declare sandbox mode."),
            _gate("sandbox_isolation", "output_directory_isolated", sandbox.get("output_directory_isolated") is True, "output directory isolation is required."),
            _gate("sandbox_isolation", "vendor_tau2_bench_unchanged", sandbox.get("vendor_tau2_bench_mutation_allowed") is False and sandbox.get("vendor_tau2_bench_unchanged") is True and not dirty_vendor, "vendor/tau2-bench must remain unchanged."),
            _gate("sandbox_isolation", "network_access_declared_and_allowed", sandbox.get("network_access_declared") is False or sandbox.get("network_access_allowed") is True, "network access must be explicitly declared and allowed."),
            _gate("sandbox_isolation", "model_backed_run_separately_gated", sandbox.get("model_backed_run_requested") is False or sandbox.get("model_backed_run_separately_gated") is True, "model-backed runs require a separate future gate."),
        ]
    )

    rollback = proposal.rollback_recovery
    results.extend(
        [
            _gate("rollback_recovery", "rollback_plan_present", rollback.get("rollback_plan_present") is True, "rollback plan is required.", _artifact_source(proposal, "replay_plan.json", "fork_plan.json")),
            _gate("rollback_recovery", "recovery_point_present", rollback.get("recovery_point_present") is True, "recovery point is required."),
            _gate("rollback_recovery", "replay_plan_present", rollback.get("replay_plan_present") is True, "replay plan is required.", _artifact_source(proposal, "replay_plan.json")),
            _gate("rollback_recovery", "fork_plan_present", rollback.get("fork_plan_present") is True, "fork plan is required.", _artifact_source(proposal, "fork_plan.json")),
            _gate("rollback_recovery", "state_packet_chain_present", rollback.get("state_packet_chain_present") is True, "state-packet chain is required.", _artifact_source(proposal, "state_packets.jsonl", "state_packet_index.json")),
            _gate("rollback_recovery", "rollback_simulation_dry_run_only", rollback.get("rollback_simulation_mode") == "dry_run_only" and rollback.get("rollback_executes") is False, "rollback simulation may be dry-run only in Phase 7."),
        ]
    )

    audit = proposal.audit_logging
    results.extend(
        [
            _gate("audit_logging", "immutable_decision_log_present", audit.get("immutable_decision_log_present") is True, "immutable decision log plan is required."),
            _gate("audit_logging", "provenance_present", audit.get("provenance_present") is True and bool(proposal.provenance), "provenance is required."),
            _gate("audit_logging", "operator_request_ids_present", audit.get("operator_request_ids_present") is True and bool(op.get("operator_id")) and bool(op.get("request_id")), "operator/request IDs are required."),
            _gate("audit_logging", "safety_gate_results_present", audit.get("safety_gate_results_present") is True, "safety-gate result logging is required."),
            _gate("audit_logging", "hash_chain_references_present", audit.get("hash_chain_references_present") is True, "hash-chain references are required.", _artifact_source(proposal, "state_packets.jsonl", "state_packet_index.json")),
        ]
    )

    packet_validation = proposal.validation.get("state_packet_chain", {})
    invalid_packet = proposal.simulation_overrides.get("invalid_packet_chain") is True
    results.append(_gate("packet_chain", "state_packet_chain_valid", packet_validation.get("ok") is True and packet_validation.get("hash_chain_valid") is not False and not invalid_packet, "valid state-packet chain is required.", _artifact_source(proposal, "state_packets.jsonl", "state_packet_index.json")))

    capabilities = proposal.requested_capabilities
    results.extend(
        [
            _gate("phase7_disabled_by_construction", "live_execution_not_requested", capabilities.get("live_execution_requested") is False, "live execution requested before enablement is refused closed."),
            _gate("phase7_disabled_by_construction", "tau2_control_flow_not_requested", capabilities.get("tau2_control_flow_requested") is False, "tau2 control flow remains unavailable."),
            _gate("phase7_disabled_by_construction", "model_api_call_not_requested", capabilities.get("model_api_call_requested") is False and capabilities.get("llm_api_services_requested") is False, "model/API calls require a separate future gate."),
            _gate("phase7_disabled_by_construction", "live_ready_forced_false", False, "Phase 7 intentionally keeps live_ready false even for structurally complete proposals."),
        ]
    )

    structural_results = [result for result in results if result.gate not in {"credential_vault_supported", "live_ready_forced_false"}]
    structurally_complete = all(result.passed for result in structural_results)
    blockers = [
        {
            "requirement": result.requirement,
            "requirement_label": REQUIREMENT_LABELS[result.requirement],
            "gate": result.gate,
            "blocker": result.blocker,
            "source_links": result.source_links,
        }
        for result in results
        if not result.passed
    ]
    status = "structurally_complete_disabled" if structurally_complete else "rejected_fail_closed"
    reason = "Proposal is structurally complete, but Phase 7 forces live_ready=false and live execution unavailable." if structurally_complete else "Proposal failed one or more live-readiness gates and was refused closed."
    return LiveReadinessDecision(
        decision_id=decision_id,
        proposal_id=proposal.proposal_id,
        scenario=proposal.scenario,
        run_id=proposal.run_id,
        structurally_complete=structurally_complete,
        accepted=False,
        status=status,
        live_ready=False,
        live_execution_available=False,
        executed=False,
        reason=reason,
        blockers=blockers,
        gate_results=results,
        source_links=list(proposal.source_links),
    )


def build_live_readiness_report(*, run_id: str, proposals: list[LiveManagerOptInProposal], decisions: list[LiveReadinessDecision]) -> dict[str, Any]:
    blocker_counts: dict[str, int] = {label: 0 for label in REQUIREMENT_LABELS}
    for decision in decisions:
        for blocker in decision.blockers:
            blocker_counts[blocker["requirement"]] += 1
    return {
        "schema_version": LIVE_READINESS_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "phase": "phase_7_live_reactive_manager_opt_in_contracts",
        "live_ready": False,
        "live_execution_available": False,
        "proposal_count": len(proposals),
        "decision_count": len(decisions),
        "accepted_decision_count": sum(1 for decision in decisions if decision.accepted),
        "rejected_decision_count": sum(1 for decision in decisions if not decision.accepted),
        "structurally_complete_disabled_count": sum(1 for decision in decisions if decision.structurally_complete),
        "executed_decision_count": sum(1 for decision in decisions if decision.executed),
        "requirements": REQUIREMENT_LABELS,
        "blocker_counts_by_requirement": blocker_counts,
        "scenario_results": [
            {
                "scenario": decision.scenario,
                "status": decision.status,
                "structurally_complete": decision.structurally_complete,
                "live_ready": decision.live_ready,
                "blocker_count": len(decision.blockers),
                "blockers": decision.blockers,
            }
            for decision in decisions
        ],
        "disabled_by_construction": True,
        "no_tau2_control_flow_executed": True,
        "no_state_packets_fed_back_into_tau2": True,
        "no_llm_api_calls_made": True,
    }
