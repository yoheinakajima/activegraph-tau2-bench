"""Phase 10 operator authorization and incident-response readiness report builder."""
from __future__ import annotations

from typing import Any

OPERATOR_INCIDENT_READINESS_REPORT_SCHEMA_VERSION = "activegraph_operator_incident_readiness_report.v1"
OPERATOR_INCIDENT_READINESS_PASS_STATUS = "operator_incident_readiness_passed"
OPERATOR_INCIDENT_READINESS_FAILED_STATUS = "operator_incident_readiness_failed"
OPERATOR_INCIDENT_READINESS_INPUTS_MISSING_STATUS = "operator_incident_readiness_inputs_missing"

PHASE10_ARTIFACTS = [
    "operator_authorization_requests.json",
    "operator_authorization_decisions.jsonl",
    "incident_response_plans.json",
    "incident_response_decisions.jsonl",
    "operator_incident_readiness_report.json",
]


def build_operator_incident_readiness_report(*, run_id: str, external_readiness_report: dict[str, Any], operator_contracts: dict[str, Any], incident_contracts: dict[str, Any]) -> dict[str, Any]:
    """Combine Phase 9 readiness with Phase 10 design-only operator/incident contracts."""
    blocker_summary: list[str] = []
    if external_readiness_report.get("live_ready") is not False:
        blocker_summary.append("Phase 9 external readiness unexpectedly set live_ready true.")
    if external_readiness_report.get("live_execution_available") is not False:
        blocker_summary.append("Phase 9 external readiness unexpectedly made live execution available.")
    if not operator_contracts.get("contracts_ok"):
        blocker_summary.append("Operator authorization mock contracts did not pass.")
    if operator_contracts.get("operator_authorization_live_ready") is not False:
        blocker_summary.append("Operator authorization unexpectedly became live-ready.")
    if not incident_contracts.get("contracts_ok"):
        blocker_summary.append("Incident-response mock contracts did not pass.")
    if incident_contracts.get("incident_response_live_ready") is not False:
        blocker_summary.append("Incident response unexpectedly became live-ready.")

    ok = not blocker_summary
    return {
        "schema_version": OPERATOR_INCIDENT_READINESS_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "phase": "phase_10_design_only_operator_authorization_and_incident_response_readiness",
        "status": OPERATOR_INCIDENT_READINESS_PASS_STATUS if ok else OPERATOR_INCIDENT_READINESS_FAILED_STATUS,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "operator_authorization_live_ready": False,
        "incident_response_live_ready": False,
        "rollback_execution_available": False,
        "rollback_executed": False,
        "readiness_result": {
            "live_ready": False,
            "operator_authorization_live_ready": False,
            "incident_response_live_ready": False,
            "review_only": True,
            "design_only": True,
            "disabled_by_construction": True,
            "fail_closed": True,
        },
        "operator_authorization": {
            "contracts_ok": operator_contracts.get("contracts_ok"),
            "structurally_complete_disabled_count": operator_contracts.get("structurally_complete_disabled_count"),
            "accepted_decision_count": operator_contracts.get("accepted_decision_count"),
            "rejected_decision_count": operator_contracts.get("rejected_decision_count"),
            "observed_blockers": operator_contracts.get("observed_blockers", []),
        },
        "incident_response": {
            "contracts_ok": incident_contracts.get("contracts_ok"),
            "structurally_complete_plan_only_count": incident_contracts.get("structurally_complete_plan_only_count"),
            "accepted_decision_count": incident_contracts.get("accepted_decision_count"),
            "rejected_decision_count": incident_contracts.get("rejected_decision_count"),
            "observed_blockers": incident_contracts.get("observed_blockers", []),
            "rollback_execution_available": incident_contracts.get("rollback_execution_available"),
            "rollback_executed": incident_contracts.get("rollback_executed"),
        },
        "blocker_summary": blocker_summary
        or [
            "live_ready remains false because Phase 10 is design-only/readiness-only.",
            "operator_authorization_live_ready remains false because approvals are structural mock contracts only.",
            "incident_response_live_ready remains false because rollback/recovery plans are not executable.",
            "live execution and rollback execution remain unavailable and fail-closed pending a separately reviewed future live-manager phase.",
        ],
        "no_tau2_control_flow_executed": True,
        "no_state_packets_fed_back_into_tau2": True,
        "no_llm_api_calls_made": True,
        "no_tau2_benchmark_episodes_imported_or_run": True,
        "no_live_execution_code_path_added": True,
        "no_raw_secrets_written": True,
        "source_reports": {
            "external_readiness_report": "external_readiness_report.json",
            "operator_authorization_requests": "operator_authorization_requests.json",
            "operator_authorization_decisions": "operator_authorization_decisions.jsonl",
            "incident_response_plans": "incident_response_plans.json",
            "incident_response_decisions": "incident_response_decisions.jsonl",
        },
    }
