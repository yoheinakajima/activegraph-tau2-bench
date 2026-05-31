"""Phase 11 design-only human-review package constants and helpers.

The Phase 11 package is advisory/reporting only. It summarizes existing Phase 10
operator authorization and incident-response readiness artifacts without enabling
live execution, executing tau2 control flow, calling LLM/API services, handling
real credentials, or approving future execution.
"""
from __future__ import annotations

HUMAN_REVIEW_PACKAGE_SCHEMA_VERSION = "activegraph_human_review_package.v1"
HUMAN_REVIEW_PACKAGE_PASS_STATUS = "human_review_package_passed"
HUMAN_REVIEW_PACKAGE_FAILED_STATUS = "human_review_package_failed"
HUMAN_REVIEW_PACKAGE_INPUTS_MISSING_STATUS = "human_review_package_inputs_missing"

PHASE11_ARTIFACTS = [
    "human_review_package.json",
    "human_review_packet.md",
    "reviewer_checklist.md",
    "source_evidence_index.json",
    "blocker_matrix.json",
]

REQUIRED_PHASE10_CHAIN_ARTIFACTS = [
    "events.jsonl",
    "activegraph_trace.json",
    "state_packets.jsonl",
    "state_packet_index.json",
    "manager_plan.json",
    "manager_decisions.jsonl",
    "replay_plan.json",
    "fork_plan.json",
    "diff_report.json",
    "contract_decisions.jsonl",
    "contract_report.json",
    "live_opt_in_decisions.jsonl",
    "live_readiness_report.json",
    "live_manager_proposal.json",
    "audit_log.jsonl",
    "audit_integrity_report.json",
    "credential_policy_report.json",
    "sandbox_policy_report.json",
    "live_readiness_audit_report.json",
    "external_audit_store_contracts.json",
    "vault_integration_contracts.json",
    "external_readiness_report.json",
    "operator_authorization_requests.json",
    "operator_authorization_decisions.jsonl",
    "incident_response_plans.json",
    "incident_response_decisions.jsonl",
    "operator_incident_readiness_report.json",
]

OPTIONAL_PHASE10_CHAIN_ARTIFACTS = [
    "external_audit_store_decisions.jsonl",
    "vault_integration_decisions.jsonl",
]

REVIEW_PACKET_SECTIONS = [
    "Executive summary",
    "Current readiness status",
    "Live execution status",
    "tau2 control-flow status",
    "LLM/API-call status",
    "Vendor immutability status",
    "Trace/state/manager artifact chain",
    "Operator authorization decisions",
    "Incident-response decisions",
    "Audit-log integrity",
    "Credential/vault readiness",
    "Sandbox readiness",
    "External audit/vault readiness",
    "Open blockers",
    "Evidence artifacts",
    "Future live-manager prerequisites",
    "Explicit non-approval statement",
]

REVIEWER_CHECKLIST_ITEMS = [
    "Confirm live_ready=false",
    "Confirm live execution unavailable/fail-closed",
    "Confirm no tau2 control flow executed",
    "Confirm no LLM/API calls made",
    "Confirm no vendor mutation",
    "Confirm no secrets in artifacts",
    "Confirm credential vault is handle-only/mock-only",
    "Confirm audit hash chain validation",
    "Confirm state packet hash chain validation",
    "Confirm operator authorization is structural only",
    "Confirm incident response is plan-only",
    "Confirm future live-manager blockers are unresolved",
    "Confirm this package does not approve execution",
]

BLOCKER_CATEGORIES = [
    "operator authorization",
    "incident response",
    "credential/vault readiness",
    "sandbox readiness",
    "external audit-store readiness",
    "live execution gate",
    "tau2 ownership/control boundary",
    "rollback/recovery",
    "audit/evidence",
    "unresolved future implementation prerequisites",
]

NON_APPROVAL_STATEMENT = (
    "This Phase 11 human-review package is advisory/reporting only. It does not "
    "approve, authorize, enable, or execute live reactive-manager behavior; "
    "live_ready remains false and live execution remains unavailable/fail-closed."
)
