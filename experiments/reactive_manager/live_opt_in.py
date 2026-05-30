"""Live reactive-manager opt-in proposal records.

Phase 7 models the extra authorization, isolation, ownership, rollback, and audit
requirements that a future live manager would need. These records are inert:
they are proposal data only and contain no code path that can execute tau2,
control tau2 lifecycle/task state, feed packets back into tau2, or call APIs.
"""
from __future__ import annotations

import copy
import dataclasses
from typing import Any

LIVE_OPT_IN_SCHEMA_VERSION = "activegraph_live_reactive_manager_opt_in_proposal.v1"
LIVE_OPT_IN_PHASE = "phase_7_live_reactive_manager_opt_in_contracts"
LIVE_OPT_IN_DISABLED_ACK = "phase7_live_manager_proposal_only_live_execution_disabled"
LIVE_SCOPE_CONTRACT_ONLY = "proposal_contract_validation_only"


@dataclasses.dataclass(frozen=True)
class LiveManagerOptInProposal:
    """A non-executable future-live-manager readiness proposal."""

    proposal_id: str
    scenario: str
    run_id: str
    operator_authorization: dict[str, Any]
    credential_policy: dict[str, Any]
    ownership_boundary: dict[str, Any]
    sandbox_isolation: dict[str, Any]
    rollback_recovery: dict[str, Any]
    audit_logging: dict[str, Any]
    requested_capabilities: dict[str, Any]
    artifact_paths: dict[str, str]
    provenance: dict[str, Any]
    validation: dict[str, Any]
    simulation_overrides: dict[str, Any]
    source_links: list[str]
    schema_version: str = LIVE_OPT_IN_SCHEMA_VERSION
    phase: str = LIVE_OPT_IN_PHASE

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _base_proposal_parts(*, run_id: str, artifact_paths: dict[str, str], provenance: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    source_links = [artifact_paths[name] for name in sorted(artifact_paths)]
    return {
        "run_id": run_id,
        "operator_authorization": {
            "operator_acknowledged": True,
            "operator_acknowledgment": LIVE_OPT_IN_DISABLED_ACK,
            "operator_id": "operator-fixture-phase7",
            "request_id": "live-opt-in-fixture-request",
            "experiment_id": "phase7-live-manager-opt-in-contracts",
            "run_scope": LIVE_SCOPE_CONTRACT_ONLY,
            "rollback_acknowledged": True,
            "audit_log_acknowledged": True,
        },
        "credential_policy": {
            "no_secrets_in_request_payloads": True,
            "no_api_keys_in_artifacts": True,
            "no_environment_variable_leakage": True,
            "credential_references_are_handles": True,
            "credential_references": ["credential-handle://future/vault/reference-only"],
            "credential_vault_supported": False,
            "credential_vault_support_required": True,
            "raw_credential_values_present": False,
        },
        "ownership_boundary": {
            "boundary_acknowledged": True,
            "tau2_owns": ["benchmark lifecycle", "task state", "tool dispatch", "evaluation", "persistence"],
            "activegraph_owns": ["trace observation", "state-packet serialization", "proposal readiness reporting"],
            "activegraph_controls_tau2": False,
            "state_packets_feed_back_into_tau2": False,
            "ambiguous_control_ownership": False,
            "validated_ownership_plan": True,
        },
        "sandbox_isolation": {
            "sandbox_mode_required": True,
            "sandbox_mode_declared": True,
            "output_directory_isolated": True,
            "vendor_tau2_bench_mutation_allowed": False,
            "vendor_tau2_bench_unchanged": True,
            "network_access_declared": False,
            "network_access_allowed": False,
            "model_backed_run_requested": False,
            "model_backed_run_separately_gated": False,
        },
        "rollback_recovery": {
            "rollback_plan_required": True,
            "rollback_plan_present": True,
            "recovery_point_present": True,
            "replay_plan_present": True,
            "fork_plan_present": True,
            "state_packet_chain_present": True,
            "rollback_simulation_mode": "dry_run_only",
            "rollback_executes": False,
        },
        "audit_logging": {
            "immutable_decision_log_required": True,
            "immutable_decision_log_present": True,
            "provenance_present": True,
            "operator_request_ids_present": True,
            "safety_gate_results_present": True,
            "hash_chain_references_present": True,
        },
        "requested_capabilities": {
            "live_execution_requested": False,
            "tau2_control_flow_requested": False,
            "state_packet_feedback_requested": False,
            "model_api_call_requested": False,
            "llm_api_services_requested": False,
        },
        "artifact_paths": copy.deepcopy(artifact_paths),
        "provenance": copy.deepcopy(provenance),
        "validation": copy.deepcopy(validation),
        "simulation_overrides": {
            "dirty_vendor_tree": False,
            "invalid_packet_chain": False,
        },
        "source_links": source_links,
    }


def build_representative_live_opt_in_proposals(*, run_id: str, artifact_paths: dict[str, str], provenance: dict[str, Any], validation: dict[str, Any]) -> list[LiveManagerOptInProposal]:
    """Build deterministic Phase 7 proposal fixtures for readiness gates."""

    base = _base_proposal_parts(run_id=run_id, artifact_paths=artifact_paths, provenance=provenance, validation=validation)

    def proposal(index: int, scenario: str, **updates: Any) -> LiveManagerOptInProposal:
        data = copy.deepcopy(base)
        data.update(updates)
        return LiveManagerOptInProposal(proposal_id=f"live-opt-in-proposal-{index:06d}", scenario=scenario, **data)

    missing_ack = copy.deepcopy(base["operator_authorization"])
    missing_ack.update({"operator_acknowledged": False, "operator_acknowledgment": None})

    missing_credentials = copy.deepcopy(base["credential_policy"])
    missing_credentials.update({"no_secrets_in_request_payloads": False, "credential_references_are_handles": False, "raw_credential_values_present": True})

    ambiguous_ownership = copy.deepcopy(base["ownership_boundary"])
    ambiguous_ownership.update({"boundary_acknowledged": False, "activegraph_controls_tau2": True, "ambiguous_control_ownership": True, "validated_ownership_plan": False})

    missing_rollback = copy.deepcopy(base["rollback_recovery"])
    missing_rollback.update({"rollback_plan_present": False, "recovery_point_present": False, "replay_plan_present": False, "fork_plan_present": False})

    missing_audit = copy.deepcopy(base["audit_logging"])
    missing_audit.update({"immutable_decision_log_present": False, "provenance_present": False, "operator_request_ids_present": False, "safety_gate_results_present": False})

    dirty_vendor = copy.deepcopy(base["simulation_overrides"])
    dirty_vendor["dirty_vendor_tree"] = True
    dirty_vendor_sandbox = copy.deepcopy(base["sandbox_isolation"])
    dirty_vendor_sandbox["vendor_tau2_bench_unchanged"] = False

    invalid_packet = copy.deepcopy(base["simulation_overrides"])
    invalid_packet["invalid_packet_chain"] = True
    invalid_packet_validation = copy.deepcopy(validation)
    invalid_packet_validation.setdefault("state_packet_chain", {})["ok"] = False
    invalid_packet_validation.setdefault("state_packet_chain", {})["hash_chain_valid"] = False
    invalid_packet_validation.setdefault("errors", []).append("simulated Phase 7 packet chain invalidity")

    unsafe_model_capabilities = copy.deepcopy(base["requested_capabilities"])
    unsafe_model_capabilities.update({"live_execution_requested": True, "model_api_call_requested": True, "llm_api_services_requested": True})
    unsafe_model_sandbox = copy.deepcopy(base["sandbox_isolation"])
    unsafe_model_sandbox.update({"model_backed_run_requested": True, "model_backed_run_separately_gated": False, "network_access_declared": True, "network_access_allowed": False})

    return [
        proposal(1, "complete_but_disabled_proposal"),
        proposal(2, "missing_operator_acknowledgement", operator_authorization=missing_ack),
        proposal(3, "missing_credential_isolation", credential_policy=missing_credentials),
        proposal(4, "ambiguous_tau2_ownership", ownership_boundary=ambiguous_ownership),
        proposal(5, "missing_rollback_plan", rollback_recovery=missing_rollback),
        proposal(6, "missing_audit_log_plan", audit_logging=missing_audit),
        proposal(7, "dirty_vendor_tree_simulated", sandbox_isolation=dirty_vendor_sandbox, simulation_overrides=dirty_vendor),
        proposal(8, "invalid_packet_chain_simulated", validation=invalid_packet_validation, simulation_overrides=invalid_packet),
        proposal(9, "unsafe_model_api_request", sandbox_isolation=unsafe_model_sandbox, requested_capabilities=unsafe_model_capabilities),
    ]
