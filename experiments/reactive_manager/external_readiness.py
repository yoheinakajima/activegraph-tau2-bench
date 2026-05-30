"""Phase 9 external audit-store and vault-integration readiness report builder."""
from __future__ import annotations

from typing import Any

EXTERNAL_READINESS_REPORT_SCHEMA_VERSION = "activegraph_external_readiness_report.v1"
EXTERNAL_READINESS_PASS_STATUS = "external_readiness_contracts_passed"
EXTERNAL_READINESS_FAILED_STATUS = "external_readiness_contracts_failed"
EXTERNAL_READINESS_INPUTS_MISSING_STATUS = "external_readiness_inputs_missing"

PHASE9_ARTIFACTS = [
    "external_audit_store_contracts.json",
    "external_audit_store_decisions.jsonl",
    "vault_integration_contracts.json",
    "vault_integration_decisions.jsonl",
    "external_readiness_report.json",
]


def build_external_readiness_report(*, run_id: str, phase8_report: dict[str, Any], external_audit_contracts: dict[str, Any], vault_contracts: dict[str, Any]) -> dict[str, Any]:
    """Combine Phase 8, external audit-store, and vault readiness contracts."""
    blocker_summary: list[str] = []
    if phase8_report.get("live_ready") is not False:
        blocker_summary.append("Phase 8 report unexpectedly set live_ready true.")
    if phase8_report.get("live_execution_available") is not False:
        blocker_summary.append("Phase 8 report unexpectedly made live execution available.")
    if not external_audit_contracts.get("contracts_ok"):
        blocker_summary.append("External audit-store mock contracts did not pass.")
    if external_audit_contracts.get("external_audit_store_live_ready") is not False:
        blocker_summary.append("External audit-store readiness unexpectedly became live-ready.")
    if not vault_contracts.get("contracts_ok"):
        blocker_summary.append("Vault integration mock contracts did not pass.")
    if vault_contracts.get("vault_integration_live_ready") is not False:
        blocker_summary.append("Vault integration readiness unexpectedly became live-ready.")

    ok = not blocker_summary
    return {
        "schema_version": EXTERNAL_READINESS_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "phase": "phase_9_design_only_external_audit_store_and_vault_readiness",
        "status": EXTERNAL_READINESS_PASS_STATUS if ok else EXTERNAL_READINESS_FAILED_STATUS,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "external_audit_store_live_ready": False,
        "vault_integration_live_ready": False,
        "readiness_result": {
            "live_ready": False,
            "external_audit_store_live_ready": False,
            "vault_integration_live_ready": False,
            "review_only": True,
            "design_only": True,
            "disabled_by_construction": True,
        },
        "external_audit_store": {
            "contracts_ok": external_audit_contracts.get("contracts_ok"),
            "append_only_required": external_audit_contracts.get("append_only_required"),
            "read_back_verification_required": external_audit_contracts.get("read_back_verification_required"),
            "external_immutability_required": external_audit_contracts.get("external_immutability_required"),
            "hash_chain_anchoring_required": external_audit_contracts.get("hash_chain_anchoring_required"),
            "source_artifact_anchoring_required": external_audit_contracts.get("source_artifact_anchoring_required"),
            "observed_rejected_reasons": external_audit_contracts.get("observed_rejected_reasons", []),
        },
        "vault_integration": {
            "contracts_ok": vault_contracts.get("contracts_ok"),
            "vault_runtime_available": vault_contracts.get("vault_runtime_available"),
            "accepted_handle_schema": vault_contracts.get("accepted_handle_schema"),
            "raw_credential_values_allowed": vault_contracts.get("raw_credential_values_allowed"),
            "environment_variable_lookup_allowed": vault_contracts.get("environment_variable_lookup_allowed"),
            "filesystem_secret_reads_allowed": vault_contracts.get("filesystem_secret_reads_allowed"),
            "raw_material_written_to_artifacts": vault_contracts.get("raw_material_written_to_artifacts"),
            "observed_rejected_reasons": vault_contracts.get("observed_rejected_reasons", []),
        },
        "blocker_summary": blocker_summary
        or [
            "live_ready remains false because Phase 9 is design-only/readiness-only.",
            "external_audit_store_live_ready remains false because no real immutable external service exists.",
            "vault_integration_live_ready remains false because no real vault runtime or secret resolution exists.",
            "live execution remains unavailable and fail-closed pending a separately reviewed future live-manager phase.",
        ],
        "no_tau2_control_flow_executed": True,
        "no_state_packets_fed_back_into_tau2": True,
        "no_llm_api_calls_made": True,
        "no_tau2_benchmark_episodes_imported_or_run": True,
        "no_live_execution_code_path_added": True,
        "source_reports": {
            "live_readiness_audit_report": "live_readiness_audit_report.json",
            "external_audit_store_contracts": "external_audit_store_contracts.json",
            "vault_integration_contracts": "vault_integration_contracts.json",
        },
    }
