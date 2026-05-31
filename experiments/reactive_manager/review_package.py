"""Build deterministic Phase 11 human-review package artifacts."""
from __future__ import annotations

import json
import pathlib
from collections import Counter
from typing import Any

from experiments.reactive_manager.human_review import (
    BLOCKER_CATEGORIES,
    HUMAN_REVIEW_PACKAGE_PASS_STATUS,
    HUMAN_REVIEW_PACKAGE_SCHEMA_VERSION,
    NON_APPROVAL_STATEMENT,
    PHASE11_ARTIFACTS,
    REQUIRED_PHASE10_CHAIN_ARTIFACTS,
    REVIEW_PACKET_SECTIONS,
    REVIEWER_CHECKLIST_ITEMS,
)
from experiments.reactive_manager.planner import write_json


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _artifact_entry(out_dir: pathlib.Path, name: str) -> dict[str, Any]:
    path = out_dir / name
    return {
        "artifact": name,
        "path": str(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
    }


def _blocker_item(code: str, source_reports: list[str], status: str = "unresolved") -> dict[str, Any]:
    return {"blocker": code, "status": status, "source_reports": source_reports}


def build_blocker_matrix(
    *,
    operator_report: dict[str, Any],
    live_audit_report: dict[str, Any],
    external_report: dict[str, Any],
    credential_report: dict[str, Any],
    sandbox_report: dict[str, Any],
    audit_integrity_report: dict[str, Any],
    state_packet_index: dict[str, Any],
) -> dict[str, Any]:
    """Build a non-empty matrix of unresolved live-readiness blockers."""
    operator_blockers = operator_report.get("operator_authorization", {}).get("observed_blockers", [])
    incident_blockers = operator_report.get("incident_response", {}).get("observed_blockers", [])
    external_blockers = external_report.get("blocker_summary", [])
    audit_blockers = live_audit_report.get("blocker_summary", [])
    matrix = {
        "operator authorization": [
            _blocker_item("operator_authorization_structural_only_not_approval", ["operator_incident_readiness_report.json", "operator_authorization_decisions.jsonl"]),
            *[_blocker_item(str(blocker), ["operator_authorization_decisions.jsonl"]) for blocker in operator_blockers],
        ],
        "incident response": [
            _blocker_item("incident_response_plan_only_not_executable", ["operator_incident_readiness_report.json", "incident_response_decisions.jsonl"]),
            *[_blocker_item(str(blocker), ["incident_response_decisions.jsonl"]) for blocker in incident_blockers],
        ],
        "credential/vault readiness": [
            _blocker_item("credential_live_ready_false", ["credential_policy_report.json", "vault_integration_contracts.json", "external_readiness_report.json"]),
            _blocker_item("vault_runtime_unavailable_handle_only_mock_only", ["credential_policy_report.json", "vault_integration_contracts.json"]),
        ],
        "sandbox readiness": [
            _blocker_item("live_sandbox_ready_false", ["sandbox_policy_report.json", "live_readiness_audit_report.json"]),
            _blocker_item("future_live_sandbox_enforcement_absent", ["sandbox_policy_report.json"]),
        ],
        "external audit-store readiness": [
            _blocker_item("external_audit_store_live_ready_false", ["external_audit_store_contracts.json", "external_readiness_report.json"]),
            _blocker_item("no_real_immutable_external_audit_service", ["external_readiness_report.json"]),
        ],
        "live execution gate": [
            _blocker_item("live_ready_false", ["live_readiness_report.json", "live_readiness_audit_report.json", "external_readiness_report.json", "operator_incident_readiness_report.json"]),
            _blocker_item("live_execution_unavailable_fail_closed", ["contract_report.json", "live_readiness_report.json", "operator_incident_readiness_report.json"]),
        ],
        "tau2 ownership/control boundary": [
            _blocker_item("activegraph_must_not_control_tau2_lifecycle_or_task_state", ["final_state.json", "operator_incident_readiness_report.json"]),
            _blocker_item("state_packets_not_fed_back_into_tau2", ["state_packet_index.json", "final_state.json"]),
        ],
        "rollback/recovery": [
            _blocker_item("rollback_execution_unavailable", ["incident_response_decisions.jsonl", "operator_incident_readiness_report.json"]),
            _blocker_item("rollback_recovery_plan_only", ["incident_response_plans.json"]),
        ],
        "audit/evidence": [
            _blocker_item("audit_hash_chain_must_remain_valid", ["audit_integrity_report.json"], "validated" if audit_integrity_report.get("hash_chain_valid") is True else "unresolved"),
            _blocker_item("state_packet_hash_chain_must_remain_valid", ["state_packet_index.json"], "validated" if state_packet_index.get("validation", {}).get("hash_chain_valid") is True else "unresolved"),
            _blocker_item("source_evidence_required_for_future_review", ["source_evidence_index.json"]),
        ],
        "unresolved future implementation prerequisites": [
            *[_blocker_item(str(blocker), ["live_readiness_audit_report.json"]) for blocker in audit_blockers],
            *[_blocker_item(str(blocker), ["external_readiness_report.json"]) for blocker in external_blockers],
            _blocker_item("separate_future_live_manager_design_and_approval_required", ["human_review_package.json", "reviewer_checklist.md"]),
        ],
    }
    for category in BLOCKER_CATEGORIES:
        matrix.setdefault(category, [])
    return {
        "schema_version": "activegraph_human_review_blocker_matrix.v1",
        "categories": matrix,
        "category_count": len(matrix),
        "blocker_count": sum(len(items) for items in matrix.values()),
        "source_report_count": len({report for items in matrix.values() for item in items for report in item["source_reports"]}),
        "credential_policy_snapshot": {
            "credential_live_ready": credential_report.get("credential_live_ready"),
            "vault_runtime_available": credential_report.get("vault_runtime_available"),
            "raw_secret_like_values_rejected": credential_report.get("raw_secret_like_values_rejected"),
        },
        "sandbox_policy_snapshot": {
            "live_sandbox_ready": sandbox_report.get("live_sandbox_ready"),
            "vendor_tau2_bench_modified": sandbox_report.get("vendor_tau2_bench_modified"),
            "network_model_live_unsafe_settings_rejected": sandbox_report.get("network_model_live_unsafe_settings_rejected"),
        },
    }


def build_evidence_index(out_dir: pathlib.Path, artifact_names: list[str], readiness_reports: dict[str, str]) -> dict[str, Any]:
    entries = [_artifact_entry(out_dir, name) for name in artifact_names]
    phase_groups = {
        "trace/state/manager": [
            "events.jsonl",
            "activegraph_trace.json",
            "state_packets.jsonl",
            "state_packet_index.json",
            "manager_plan.json",
            "manager_decisions.jsonl",
            "replay_plan.json",
            "fork_plan.json",
            "diff_report.json",
        ],
        "execution contracts and live opt-in": [
            "contract_decisions.jsonl",
            "contract_report.json",
            "live_opt_in_decisions.jsonl",
            "live_readiness_report.json",
            "live_manager_proposal.json",
        ],
        "audit credential sandbox": [
            "audit_log.jsonl",
            "audit_integrity_report.json",
            "credential_policy_report.json",
            "sandbox_policy_report.json",
            "live_readiness_audit_report.json",
        ],
        "external audit vault": [
            "external_audit_store_contracts.json",
            "vault_integration_contracts.json",
            "external_readiness_report.json",
        ],
        "operator incident": [
            "operator_authorization_requests.json",
            "operator_authorization_decisions.jsonl",
            "incident_response_plans.json",
            "incident_response_decisions.jsonl",
            "operator_incident_readiness_report.json",
        ],
    }
    return {
        "schema_version": "activegraph_human_review_source_evidence_index.v1",
        "artifacts": entries,
        "phase_groups": phase_groups,
        "readiness_reports": readiness_reports,
        "missing_artifacts": [entry["artifact"] for entry in entries if not entry["exists"]],
    }


def _decision_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(decision.get("status")) for decision in decisions)
    blockers = sorted({str(blocker) for decision in decisions for blocker in decision.get("blockers", [])})
    return {
        "decision_count": len(decisions),
        "accepted_decision_count": sum(1 for decision in decisions if decision.get("accepted") is True),
        "status_counts": dict(sorted(statuses.items())),
        "observed_blockers": blockers,
    }


def _markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_reviewer_checklist(package: dict[str, Any]) -> str:
    lines = [
        "# Phase 11 reviewer checklist",
        "",
        "All boxes are human-review prompts only; checking them does not approve execution.",
        "",
    ]
    for item in REVIEWER_CHECKLIST_ITEMS:
        lines.append(f"- [ ] {item}")
    lines.extend(
        [
            "",
            "## Recorded package state",
            "",
            f"- live_ready: `{package['live_ready']}`",
            f"- live execution available: `{package['live_execution_available']}`",
            f"- tau2 control flow executed: `{package['tau2_control_flow_executed']}`",
            f"- LLM/API calls made: `{package['llm_api_calls_made']}`",
            f"- vendor/tau2-bench modified: `{package['vendor_tau2_bench_modified']}`",
            f"- non-approval statement: {package['non_approval_statement']}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_review_packet(package: dict[str, Any]) -> str:
    blocker_lines = []
    for category, items in package["blocker_matrix"]["categories"].items():
        blocker_lines.append(f"- **{category}**: {len(items)} item(s)")
    evidence_lines = [f"- `{entry['artifact']}` ({'present' if entry['exists'] else 'missing'})" for entry in package["evidence_index"]["artifacts"]]
    future_prereqs = [item["blocker"] for item in package["blocker_matrix"]["categories"]["unresolved future implementation prerequisites"]]
    content = f"""# Phase 11 human-review packet

## Executive summary

Status: `{package['status']}`. This package summarizes Phase 10 readiness artifacts for human review only and does not approve live execution.

## Current readiness status

- live_ready: `{package['live_ready']}`
- readiness result: `{package['readiness_reports']['operator_incident_readiness']['status']}`
- phase: `{package['phase']}`

## Live execution status

- live execution available: `{package['live_execution_available']}`
- fail-closed: `{package['readiness_reports']['operator_incident_readiness']['live_execution_unavailable_fail_closed']}`

## tau2 control-flow status

- tau2 control flow executed: `{package['tau2_control_flow_executed']}`
- state packets fed back into tau2: `False`

## LLM/API-call status

- LLM/API calls made: `{package['llm_api_calls_made']}`
- API keys required: `False`

## Vendor immutability status

- vendor/tau2-bench modified: `{package['vendor_tau2_bench_modified']}`

## Trace/state/manager artifact chain

{_markdown_list(package['artifact_chain']['required_artifacts'])}

## Operator authorization decisions

- decisions: `{package['operator_authorization_summary']['decision_count']}`
- accepted decisions: `{package['operator_authorization_summary']['accepted_decision_count']}`
- structural-only disabled decisions remain non-approvals.

## Incident-response decisions

- decisions: `{package['incident_response_summary']['decision_count']}`
- accepted decisions: `{package['incident_response_summary']['accepted_decision_count']}`
- rollback executed: `False`

## Audit-log integrity

- audit hash chain valid: `{package['audit_summary']['audit_hash_chain_valid']}`
- state packet hash chain valid: `{package['audit_summary']['state_packet_hash_chain_valid']}`

## Credential/vault readiness

- credential live ready: `{package['credential_summary']['credential_live_ready']}`
- vault runtime available: `{package['credential_summary']['vault_runtime_available']}`
- handle-only/mock-only: `True`

## Sandbox readiness

- live sandbox ready: `{package['sandbox_summary']['live_sandbox_ready']}`
- unsafe network/model/live settings rejected: `{package['sandbox_summary']['network_model_live_unsafe_settings_rejected']}`

## External audit/vault readiness

- external audit store live ready: `{package['external_readiness_summary']['external_audit_store_live_ready']}`
- vault integration live ready: `{package['external_readiness_summary']['vault_integration_live_ready']}`

## Open blockers

{chr(10).join(blocker_lines)}

## Evidence artifacts

{chr(10).join(evidence_lines)}

## Future live-manager prerequisites

{_markdown_list(future_prereqs)}

## Explicit non-approval statement

{package['non_approval_statement']}
"""
    return content


def render_summary(package: dict[str, Any]) -> str:
    return f"""# Phase 11 human-review package summary

Status: `{package['status']}`

Run directory: `{package['provenance']['output_dir']}`

- live_ready: `{package['live_ready']}`
- live execution available: `{package['live_execution_available']}`
- live execution unavailable/fail-closed: `True`
- tau2 control flow executed: `{package['tau2_control_flow_executed']}`
- LLM/API calls made: `{package['llm_api_calls_made']}`
- vendor/tau2-bench modified: `{package['vendor_tau2_bench_modified']}`
- blocker categories: `{package['blocker_matrix']['category_count']}`
- blockers: `{package['blocker_matrix']['blocker_count']}`
- evidence artifacts: `{len(package['evidence_index']['artifacts'])}`

{package['non_approval_statement']}
"""


def build_human_review_package(*, out_dir: pathlib.Path, run_id: str, generated_at: str, command: str, source_phase10_run_dir: str) -> dict[str, Any]:
    final_state = read_json(out_dir / "final_state.json")
    live_readiness_report = read_json(out_dir / "live_readiness_report.json")
    live_audit_report = read_json(out_dir / "live_readiness_audit_report.json")
    external_report = read_json(out_dir / "external_readiness_report.json")
    operator_report = read_json(out_dir / "operator_incident_readiness_report.json")
    audit_integrity_report = read_json(out_dir / "audit_integrity_report.json")
    credential_report = read_json(out_dir / "credential_policy_report.json")
    sandbox_report = read_json(out_dir / "sandbox_policy_report.json")
    state_packet_index = read_json(out_dir / "state_packet_index.json")
    external_audit_contracts = read_json(out_dir / "external_audit_store_contracts.json")
    vault_contracts = read_json(out_dir / "vault_integration_contracts.json")
    operator_decisions = read_jsonl(out_dir / "operator_authorization_decisions.jsonl")
    incident_decisions = read_jsonl(out_dir / "incident_response_decisions.jsonl")

    readiness_reports = {
        "live_readiness": {
            "artifact": "live_readiness_report.json",
            "status": live_readiness_report.get("status"),
            "live_ready": live_readiness_report.get("live_ready"),
            "live_execution_available": live_readiness_report.get("live_execution_available"),
        },
        "live_readiness_audit": {
            "artifact": "live_readiness_audit_report.json",
            "status": live_audit_report.get("status"),
            "live_ready": live_audit_report.get("live_ready"),
            "live_execution_available": live_audit_report.get("live_execution_available"),
            "live_execution_unavailable_fail_closed": live_audit_report.get("live_execution_unavailable_fail_closed"),
        },
        "external_readiness": {
            "artifact": "external_readiness_report.json",
            "status": external_report.get("status"),
            "live_ready": external_report.get("live_ready"),
            "live_execution_available": external_report.get("live_execution_available"),
        },
        "operator_incident_readiness": {
            "artifact": "operator_incident_readiness_report.json",
            "status": operator_report.get("status"),
            "live_ready": operator_report.get("live_ready"),
            "live_execution_available": operator_report.get("live_execution_available"),
            "live_execution_unavailable_fail_closed": operator_report.get("live_execution_unavailable_fail_closed"),
        },
    }
    blocker_matrix = build_blocker_matrix(
        operator_report=operator_report,
        live_audit_report=live_audit_report,
        external_report=external_report,
        credential_report=credential_report,
        sandbox_report=sandbox_report,
        audit_integrity_report=audit_integrity_report,
        state_packet_index=state_packet_index,
    )
    evidence_index = build_evidence_index(out_dir, REQUIRED_PHASE10_CHAIN_ARTIFACTS, {key: value["artifact"] for key, value in readiness_reports.items()})
    package = {
        "schema_version": HUMAN_REVIEW_PACKAGE_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "phase": "phase_11_design_only_human_review_package",
        "status": HUMAN_REVIEW_PACKAGE_PASS_STATUS,
        "live_ready": False,
        "live_execution_available": False,
        "tau2_control_flow_executed": False,
        "llm_api_calls_made": False,
        "vendor_tau2_bench_modified": bool(final_state.get("vendor_tau2_bench_modified")),
        "artifact_chain": {
            "source_phase10_run_dir": source_phase10_run_dir,
            "required_artifacts": REQUIRED_PHASE10_CHAIN_ARTIFACTS,
            "missing_required_artifacts": evidence_index["missing_artifacts"],
            "phase11_artifacts": PHASE11_ARTIFACTS,
        },
        "readiness_reports": readiness_reports,
        "operator_authorization_summary": {
            **_decision_summary(operator_decisions),
            "structural_only": True,
            "operator_authorization_live_ready": operator_report.get("operator_authorization_live_ready"),
            "source_artifacts": ["operator_authorization_requests.json", "operator_authorization_decisions.jsonl", "operator_incident_readiness_report.json"],
        },
        "incident_response_summary": {
            **_decision_summary(incident_decisions),
            "plan_only": True,
            "incident_response_live_ready": operator_report.get("incident_response_live_ready"),
            "rollback_execution_available": operator_report.get("rollback_execution_available"),
            "rollback_executed": operator_report.get("rollback_executed"),
            "source_artifacts": ["incident_response_plans.json", "incident_response_decisions.jsonl", "operator_incident_readiness_report.json"],
        },
        "audit_summary": {
            "audit_hash_chain_valid": audit_integrity_report.get("hash_chain_valid"),
            "audit_source_links_valid": audit_integrity_report.get("source_links_valid"),
            "audit_record_count": audit_integrity_report.get("record_count"),
            "state_packet_hash_chain_valid": state_packet_index.get("validation", {}).get("hash_chain_valid"),
            "state_packet_count": state_packet_index.get("packet_count"),
        },
        "credential_summary": {
            "credential_live_ready": credential_report.get("credential_live_ready"),
            "vault_runtime_available": credential_report.get("vault_runtime_available"),
            "valid_handle_accepted": credential_report.get("valid_handle_accepted"),
            "raw_secret_like_values_rejected": credential_report.get("raw_secret_like_values_rejected"),
            "no_raw_secrets_written": credential_report.get("no_raw_secrets_written"),
            "handle_only_mock_only": True,
        },
        "sandbox_summary": {
            "live_sandbox_ready": sandbox_report.get("live_sandbox_ready"),
            "valid_review_policy_passed": sandbox_report.get("valid_review_policy_passed"),
            "network_model_live_unsafe_settings_rejected": sandbox_report.get("network_model_live_unsafe_settings_rejected"),
            "vendor_tau2_bench_modified": sandbox_report.get("vendor_tau2_bench_modified"),
        },
        "external_readiness_summary": {
            "external_audit_store_live_ready": external_audit_contracts.get("external_audit_store_live_ready"),
            "vault_integration_live_ready": vault_contracts.get("vault_integration_live_ready"),
            "live_ready": external_report.get("live_ready"),
            "status": external_report.get("status"),
        },
        "blocker_matrix": blocker_matrix,
        "evidence_index": evidence_index,
        "reviewer_checklist": REVIEWER_CHECKLIST_ITEMS,
        "non_approval_statement": NON_APPROVAL_STATEMENT,
        "provenance": {
            "command": command,
            "output_dir": str(out_dir),
            "source_phase10_run_dir": source_phase10_run_dir,
            "review_packet_sections": REVIEW_PACKET_SECTIONS,
            "design_only": True,
            "no_live_execution_code_path_added": True,
            "no_tau2_benchmark_episodes_imported_or_run": True,
            "no_llm_api_services_called": True,
            "no_real_credentials_handled": True,
            "no_raw_secrets_stored": True,
        },
    }
    return package


def write_human_review_artifacts(out_dir: pathlib.Path, package: dict[str, Any]) -> None:
    write_json(out_dir / "human_review_package.json", package)
    write_json(out_dir / "source_evidence_index.json", package["evidence_index"])
    write_json(out_dir / "blocker_matrix.json", package["blocker_matrix"])
    (out_dir / "human_review_packet.md").write_text(render_review_packet(package), encoding="utf-8")
    (out_dir / "reviewer_checklist.md").write_text(render_reviewer_checklist(package), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_summary(package), encoding="utf-8")
