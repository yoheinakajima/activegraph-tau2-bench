"""Phase 8 review-only live-readiness audit orchestration.

This module combines Phase 7 proposal/readiness artifacts with deterministic
audit-log integrity, handle-only credential policy checks, and sandbox-policy
validation. It produces reports only and intentionally keeps live execution
unavailable and fail-closed.
"""
from __future__ import annotations

import pathlib
from typing import Any

from experiments.reactive_manager.audit_log import build_audit_records, validate_audit_records
from experiments.reactive_manager.credential_vault import build_credential_policy_report
from experiments.reactive_manager.sandbox_policy import build_sandbox_policy_report

LIVE_READINESS_AUDIT_REPORT_SCHEMA_VERSION = "activegraph_live_readiness_audit_report.v1"
LIVE_READINESS_AUDIT_PASS_STATUS = "live_readiness_audit_passed"
LIVE_READINESS_AUDIT_FAILED_STATUS = "live_readiness_audit_failed"
LIVE_READINESS_AUDIT_INPUTS_MISSING_STATUS = "live_readiness_audit_inputs_missing"

PHASE8_ARTIFACTS = [
    "audit_log.jsonl",
    "audit_integrity_report.json",
    "credential_policy_report.json",
    "sandbox_policy_report.json",
    "live_readiness_audit_report.json",
]


def required_phase7_artifacts() -> list[str]:
    return [
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
    ]


def find_missing_required_inputs(out_dir: pathlib.Path) -> list[str]:
    return [name for name in required_phase7_artifacts() if not (out_dir / name).is_file()]


def build_live_readiness_audit_artifacts(*, out_dir: pathlib.Path, run_id: str, timestamp: str, repo_root: pathlib.Path, vendor_status: str, phase7_readiness_report: dict[str, Any], phase6_contract_report: dict[str, Any]) -> dict[str, Any]:
    """Build in-memory Phase 8 artifacts; caller owns persistence order."""
    audit_records = build_audit_records(out_dir=out_dir, run_id=run_id, timestamp=timestamp)
    audit_integrity_report = validate_audit_records(out_dir=out_dir, records=audit_records)
    credential_policy_report = build_credential_policy_report()
    sandbox_policy_report = build_sandbox_policy_report(repo_root=repo_root, out_dir=out_dir, vendor_status=vendor_status)

    blocker_summary: list[str] = []
    if phase7_readiness_report.get("live_ready") is not False:
        blocker_summary.append("Phase 7 readiness report unexpectedly set live_ready true.")
    if phase7_readiness_report.get("live_execution_available") is not False:
        blocker_summary.append("Phase 7 readiness report unexpectedly made live execution available.")
    if phase6_contract_report.get("live_execution_available") is not False:
        blocker_summary.append("Phase 6 contract report unexpectedly made live execution available.")
    if not audit_integrity_report["hash_chain_valid"]:
        blocker_summary.append("Audit hash chain validation failed.")
    if not credential_policy_report["valid_handle_accepted"] or not credential_policy_report["raw_secret_like_values_rejected"]:
        blocker_summary.append("Credential policy did not enforce handle-only references.")
    if credential_policy_report["vault_runtime_available"] is not False:
        blocker_summary.append("Credential vault runtime unexpectedly available.")
    if not sandbox_policy_report["valid_review_policy_passed"] or not sandbox_policy_report["network_model_live_unsafe_settings_rejected"]:
        blocker_summary.append("Sandbox policy did not reject unsafe settings.")
    if sandbox_policy_report["vendor_tau2_bench_modified"]:
        blocker_summary.append("vendor/tau2-bench is modified.")

    readiness_result = {
        "live_ready": False,
        "live_execution_available": False,
        "credential_live_ready": False,
        "live_sandbox_ready": False,
        "audit_hash_chain_valid": audit_integrity_report["hash_chain_valid"],
        "review_only": True,
        "disabled_by_construction": True,
    }
    report_ok = (
        not blocker_summary
        and phase7_readiness_report.get("live_ready") is False
        and phase7_readiness_report.get("live_execution_available") is False
        and phase6_contract_report.get("live_execution_available") is False
        and audit_integrity_report["hash_chain_valid"] is True
        and audit_integrity_report["source_links_valid"] is True
        and credential_policy_report["valid_handle_accepted"] is True
        and credential_policy_report["raw_secret_like_values_rejected"] is True
        and credential_policy_report["vault_runtime_available"] is False
        and credential_policy_report["credential_live_ready"] is False
        and sandbox_policy_report["valid_review_policy_passed"] is True
        and sandbox_policy_report["invalid_policy_rejected_count"] == 2
        and sandbox_policy_report["network_model_live_unsafe_settings_rejected"] is True
        and sandbox_policy_report["live_sandbox_ready"] is False
        and sandbox_policy_report["vendor_tau2_bench_modified"] is False
    )
    live_readiness_audit_report = {
        "schema_version": LIVE_READINESS_AUDIT_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "phase": "phase_8_review_only_live_readiness_audit",
        "status": LIVE_READINESS_AUDIT_PASS_STATUS if report_ok else LIVE_READINESS_AUDIT_FAILED_STATUS,
        "readiness_result": readiness_result,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "audit_record_count": audit_integrity_report["record_count"],
        "audit_hash_chain_valid": audit_integrity_report["hash_chain_valid"],
        "audit_source_links_valid": audit_integrity_report["source_links_valid"],
        "credential_policy": {
            "vault_runtime_available": credential_policy_report["vault_runtime_available"],
            "credential_live_ready": credential_policy_report["credential_live_ready"],
            "valid_handle_accepted": credential_policy_report["valid_handle_accepted"],
            "raw_secret_like_values_rejected": credential_policy_report["raw_secret_like_values_rejected"],
            "no_raw_secrets_written": credential_policy_report["no_raw_secrets_written"],
        },
        "sandbox_policy": {
            "live_sandbox_ready": sandbox_policy_report["live_sandbox_ready"],
            "valid_review_policy_passed": sandbox_policy_report["valid_review_policy_passed"],
            "invalid_policy_rejected_count": sandbox_policy_report["invalid_policy_rejected_count"],
            "network_model_live_unsafe_settings_rejected": sandbox_policy_report["network_model_live_unsafe_settings_rejected"],
            "artifact_boundaries_enforced": sandbox_policy_report["artifact_boundaries_enforced"],
            "vendor_tau2_bench_modified": sandbox_policy_report["vendor_tau2_bench_modified"],
        },
        "blocker_summary": blocker_summary
        or [
            "live_ready remains false because Phase 8 is review-only.",
            "credential_live_ready remains false because the credential vault runtime is unavailable.",
            "live_sandbox_ready remains false because future live sandbox enforcement requirements are absent.",
        ],
        "no_tau2_control_flow_executed": True,
        "no_state_packets_fed_back_into_tau2": True,
        "no_llm_api_calls_made": True,
        "no_tau2_benchmark_episodes_imported_or_run": True,
        "no_live_execution_code_path_added": True,
        "source_reports": {
            "live_readiness_report": "live_readiness_report.json",
            "contract_report": "contract_report.json",
            "audit_integrity_report": "audit_integrity_report.json",
            "credential_policy_report": "credential_policy_report.json",
            "sandbox_policy_report": "sandbox_policy_report.json",
        },
    }
    return {
        "audit_records": audit_records,
        "audit_integrity_report": audit_integrity_report,
        "credential_policy_report": credential_policy_report,
        "sandbox_policy_report": sandbox_policy_report,
        "live_readiness_audit_report": live_readiness_audit_report,
        "ok": report_ok,
    }
