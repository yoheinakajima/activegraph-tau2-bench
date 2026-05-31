"""Phase 12 retention and hash manifest helpers.

These helpers only inspect local Phase 11 artifacts and local files. They do not
import tau2, execute tau2 control flow, call LLM/API services, read credentials,
or enable live reactive-manager execution.
"""
from __future__ import annotations

import hashlib
import pathlib
from typing import Any

RETENTION_MANIFEST_SCHEMA_VERSION = "activegraph_retention_manifest.v1"
ARTIFACT_HASH_MANIFEST_SCHEMA_VERSION = "activegraph_artifact_hash_manifest.v1"
EVIDENCE_BUNDLE_INDEX_SCHEMA_VERSION = "activegraph_evidence_bundle_index.v1"

RETENTION_GROUPS = [
    "source_provenance",
    "trace_events",
    "activegraph_projection",
    "state_packets",
    "manager_plans",
    "safety_contracts",
    "live_readiness",
    "audit_logs",
    "credential_and_sandbox",
    "external_readiness",
    "operator_incident",
    "human_review",
    "auditor_handoff",
]

REVIEW_AREAS = [
    "tau2 provenance",
    "trace and projection",
    "state packets and hash chain",
    "manager dry-run planning",
    "execution contracts",
    "live opt-in readiness",
    "audit / credential / sandbox readiness",
    "external audit/vault readiness",
    "operator authorization and incident response",
    "human review",
    "auditor handoff",
]

ARTIFACT_CLASSIFICATIONS: dict[str, dict[str, Any]] = {
    "vendor/tau2-bench.UPSTREAM_COMMIT": {
        "group": "source_provenance",
        "source_phase": "phase_1_5_local_vendored_tau2_bench_smoke",
        "retention_reason": "Pins the vendored tau2-bench upstream commit for later immutability comparison.",
        "review_area": "tau2 provenance",
        "required_for_future_live_review": True,
    },
    "events.jsonl": {
        "group": "trace_events",
        "source_phase": "phase_2_trace_only_observability",
        "retention_reason": "Preserves fixture-backed trace events used by every downstream design-only artifact.",
        "review_area": "trace and projection",
        "required_for_future_live_review": True,
    },
    "activegraph_trace.json": {
        "group": "activegraph_projection",
        "source_phase": "phase_3_activegraph_trace_only_adapter_smoke",
        "retention_reason": "Captures the trace-only ActiveGraph projection without control over tau2 lifecycle or state.",
        "review_area": "trace and projection",
        "required_for_future_live_review": True,
    },
    "state_packets.jsonl": {
        "group": "state_packets",
        "source_phase": "phase_4_activegraph_state_packet_serialization",
        "retention_reason": "Retains serialized state packets for hash-chain and no-feedback review.",
        "review_area": "state packets and hash chain",
        "required_for_future_live_review": True,
    },
    "state_packet_index.json": {
        "group": "state_packets",
        "source_phase": "phase_4_activegraph_state_packet_serialization",
        "retention_reason": "Indexes state-packet hash-chain validation evidence.",
        "review_area": "state packets and hash chain",
        "required_for_future_live_review": True,
    },
    "manager_plan.json": {
        "group": "manager_plans",
        "source_phase": "phase_5_dry_run_reactive_manager_replay_fork_diff_planning",
        "retention_reason": "Records design-only manager planning inputs and decisions without execution.",
        "review_area": "manager dry-run planning",
        "required_for_future_live_review": True,
    },
    "manager_decisions.jsonl": {
        "group": "manager_plans",
        "source_phase": "phase_5_dry_run_reactive_manager_replay_fork_diff_planning",
        "retention_reason": "Preserves dry-run manager decisions for future comparison.",
        "review_area": "manager dry-run planning",
        "required_for_future_live_review": True,
    },
    "replay_plan.json": {
        "group": "manager_plans",
        "source_phase": "phase_5_dry_run_reactive_manager_replay_fork_diff_planning",
        "retention_reason": "Documents replay planning only; no replay execution is enabled.",
        "review_area": "manager dry-run planning",
        "required_for_future_live_review": True,
    },
    "fork_plan.json": {
        "group": "manager_plans",
        "source_phase": "phase_5_dry_run_reactive_manager_replay_fork_diff_planning",
        "retention_reason": "Documents safe fork-point planning only; no fork execution is enabled.",
        "review_area": "manager dry-run planning",
        "required_for_future_live_review": True,
    },
    "diff_report.json": {
        "group": "manager_plans",
        "source_phase": "phase_5_dry_run_reactive_manager_replay_fork_diff_planning",
        "retention_reason": "Retains design-only diff analysis for later no-regression review.",
        "review_area": "manager dry-run planning",
        "required_for_future_live_review": True,
    },
    "contract_decisions.jsonl": {
        "group": "safety_contracts",
        "source_phase": "phase_6_guarded_reactive_manager_execution_contracts",
        "retention_reason": "Preserves fail-closed contract decisions for execution-gate review.",
        "review_area": "execution contracts",
        "required_for_future_live_review": True,
    },
    "contract_report.json": {
        "group": "safety_contracts",
        "source_phase": "phase_6_guarded_reactive_manager_execution_contracts",
        "retention_reason": "Summarizes guarded execution contracts while live execution remains unavailable.",
        "review_area": "execution contracts",
        "required_for_future_live_review": True,
    },
    "live_opt_in_decisions.jsonl": {
        "group": "live_readiness",
        "source_phase": "phase_7_live_reactive_manager_opt_in_contracts",
        "retention_reason": "Preserves opt-in contract decisions showing live opt-in remains disabled.",
        "review_area": "live opt-in readiness",
        "required_for_future_live_review": True,
    },
    "live_readiness_report.json": {
        "group": "live_readiness",
        "source_phase": "phase_7_live_reactive_manager_opt_in_contracts",
        "retention_reason": "Records live_ready=false and live execution unavailable/fail-closed evidence.",
        "review_area": "live opt-in readiness",
        "required_for_future_live_review": True,
    },
    "live_manager_proposal.json": {
        "group": "live_readiness",
        "source_phase": "phase_7_live_reactive_manager_opt_in_contracts",
        "retention_reason": "Captures a non-executable proposal for future live-manager review.",
        "review_area": "live opt-in readiness",
        "required_for_future_live_review": True,
    },
    "audit_log.jsonl": {
        "group": "audit_logs",
        "source_phase": "phase_8_live_readiness_audit_contracts",
        "retention_reason": "Preserves audit records and source links for integrity review.",
        "review_area": "audit / credential / sandbox readiness",
        "required_for_future_live_review": True,
    },
    "audit_integrity_report.json": {
        "group": "audit_logs",
        "source_phase": "phase_8_live_readiness_audit_contracts",
        "retention_reason": "Records audit hash-chain validation and source-link validation.",
        "review_area": "audit / credential / sandbox readiness",
        "required_for_future_live_review": True,
    },
    "credential_policy_report.json": {
        "group": "credential_and_sandbox",
        "source_phase": "phase_8_live_readiness_audit_contracts",
        "retention_reason": "Documents handle-only/mock-only credential policy and no raw secret storage.",
        "review_area": "audit / credential / sandbox readiness",
        "required_for_future_live_review": True,
    },
    "sandbox_policy_report.json": {
        "group": "credential_and_sandbox",
        "source_phase": "phase_8_live_readiness_audit_contracts",
        "retention_reason": "Documents sandbox policy constraints and vendor immutability checks.",
        "review_area": "audit / credential / sandbox readiness",
        "required_for_future_live_review": True,
    },
    "live_readiness_audit_report.json": {
        "group": "live_readiness",
        "source_phase": "phase_8_live_readiness_audit_contracts",
        "retention_reason": "Aggregates live-readiness audit blockers and fail-closed status.",
        "review_area": "audit / credential / sandbox readiness",
        "required_for_future_live_review": True,
    },
    "external_audit_store_contracts.json": {
        "group": "external_readiness",
        "source_phase": "phase_9_external_audit_store_and_vault_integration_readiness_contracts",
        "retention_reason": "Documents external audit-store contract readiness without real service integration.",
        "review_area": "external audit/vault readiness",
        "required_for_future_live_review": True,
    },
    "vault_integration_contracts.json": {
        "group": "external_readiness",
        "source_phase": "phase_9_external_audit_store_and_vault_integration_readiness_contracts",
        "retention_reason": "Documents vault integration contracts without raw credential handling.",
        "review_area": "external audit/vault readiness",
        "required_for_future_live_review": True,
    },
    "external_readiness_report.json": {
        "group": "external_readiness",
        "source_phase": "phase_9_external_audit_store_and_vault_integration_readiness_contracts",
        "retention_reason": "Summarizes unresolved external audit-store and vault readiness blockers.",
        "review_area": "external audit/vault readiness",
        "required_for_future_live_review": True,
    },
    "operator_authorization_requests.json": {
        "group": "operator_incident",
        "source_phase": "phase_10_operator_authorization_and_incident_response_readiness_contracts",
        "retention_reason": "Preserves structural-only operator authorization requests for review.",
        "review_area": "operator authorization and incident response",
        "required_for_future_live_review": True,
    },
    "operator_authorization_decisions.jsonl": {
        "group": "operator_incident",
        "source_phase": "phase_10_operator_authorization_and_incident_response_readiness_contracts",
        "retention_reason": "Preserves structural-only operator authorization decisions; these are not approvals.",
        "review_area": "operator authorization and incident response",
        "required_for_future_live_review": True,
    },
    "incident_response_plans.json": {
        "group": "operator_incident",
        "source_phase": "phase_10_operator_authorization_and_incident_response_readiness_contracts",
        "retention_reason": "Documents plan-only incident response and rollback/recovery artifacts.",
        "review_area": "operator authorization and incident response",
        "required_for_future_live_review": True,
    },
    "incident_response_decisions.jsonl": {
        "group": "operator_incident",
        "source_phase": "phase_10_operator_authorization_and_incident_response_readiness_contracts",
        "retention_reason": "Preserves incident-response decisions; rollback execution remains unavailable.",
        "review_area": "operator authorization and incident response",
        "required_for_future_live_review": True,
    },
    "operator_incident_readiness_report.json": {
        "group": "operator_incident",
        "source_phase": "phase_10_operator_authorization_and_incident_response_readiness_contracts",
        "retention_reason": "Summarizes operator authorization and incident-response readiness blockers.",
        "review_area": "operator authorization and incident response",
        "required_for_future_live_review": True,
    },
    "human_review_package.json": {
        "group": "human_review",
        "source_phase": "phase_11_human_review_package_generation",
        "retention_reason": "Preserves the advisory human-review package consumed by auditor handoff.",
        "review_area": "human review",
        "required_for_future_live_review": True,
    },
    "human_review_packet.md": {
        "group": "human_review",
        "source_phase": "phase_11_human_review_package_generation",
        "retention_reason": "Preserves the human-readable review packet and non-approval statement.",
        "review_area": "human review",
        "required_for_future_live_review": True,
    },
    "reviewer_checklist.md": {
        "group": "human_review",
        "source_phase": "phase_11_human_review_package_generation",
        "retention_reason": "Retains checklist prompts for future live-readiness comparison.",
        "review_area": "human review",
        "required_for_future_live_review": True,
    },
    "source_evidence_index.json": {
        "group": "human_review",
        "source_phase": "phase_11_human_review_package_generation",
        "retention_reason": "Preserves source-linked human-review evidence index.",
        "review_area": "human review",
        "required_for_future_live_review": True,
    },
    "blocker_matrix.json": {
        "group": "human_review",
        "source_phase": "phase_11_human_review_package_generation",
        "retention_reason": "Preserves unresolved blocker matrix consumed by auditor handoff.",
        "review_area": "human review",
        "required_for_future_live_review": True,
    },
}

PHASE12_ARTIFACTS = [
    "auditor_handoff_package.json",
    "auditor_handoff_packet.md",
    "retention_manifest.json",
    "artifact_hash_manifest.json",
    "evidence_bundle_index.json",
    "auditor_questions.md",
    "handoff_summary.md",
    "summary.md",
    "final_state.json",
    "raw.log",
]

for artifact in PHASE12_ARTIFACTS:
    ARTIFACT_CLASSIFICATIONS[artifact] = {
        "group": "auditor_handoff",
        "source_phase": "phase_12_design_only_external_auditor_handoff_and_retention_manifest",
        "retention_reason": "Retains Phase 12 external-auditor handoff, retention, hash, evidence, question, or run-state output.",
        "review_area": "auditor handoff",
        "required_for_future_live_review": artifact not in {"raw.log"},
    }


def classification_for(artifact: str) -> dict[str, Any]:
    """Return deterministic retention metadata for an artifact."""
    return ARTIFACT_CLASSIFICATIONS.get(
        artifact,
        {
            "group": "auditor_handoff",
            "source_phase": "phase_12_design_only_external_auditor_handoff_and_retention_manifest",
            "retention_reason": "Retained because it is referenced by the auditor handoff package.",
            "review_area": "auditor handoff",
            "required_for_future_live_review": False,
        },
    )


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_hash_manifest(
    *,
    out_dir: pathlib.Path,
    artifacts: list[str],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build stable sha256/size records for referenced artifacts.

    The manifest records its own file with ``self_hash_excluded`` because a file
    cannot contain its final own cryptographic hash without becoming
    self-referential. All other entries contain stable sha256 hashes of bytes on
    disk at manifest generation time.
    """
    entries: list[dict[str, Any]] = []
    for artifact in artifacts:
        info = classification_for(artifact)
        path = out_dir / artifact if not artifact.startswith("vendor/") else out_dir.parents[1] / artifact
        exists = path.is_file()
        entry = {
            "artifact": artifact,
            "sha256": None if artifact == "artifact_hash_manifest.json" else (sha256_file(path) if exists else None),
            "byte_size": path.stat().st_size if exists else 0,
            "exists": exists,
            "group": info["group"],
            "source_phase": info["source_phase"],
        }
        if artifact == "artifact_hash_manifest.json":
            entry["self_hash_excluded"] = True
            entry["self_hash_exclusion_reason"] = "Self-hash is excluded to avoid a non-deterministic recursive manifest."
        entries.append(entry)
    return {
        "schema_version": ARTIFACT_HASH_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "hash_algorithm": "sha256",
        "self_hash_policy": "artifact_hash_manifest.json is listed but self-hash is excluded; all other existing artifacts include stable byte hashes.",
        "artifacts": entries,
        "artifact_count": len(entries),
        "missing_artifacts": [entry["artifact"] for entry in entries if not entry["exists"]],
    }


def build_retention_manifest(*, artifacts: list[str], run_id: str, generated_at: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for artifact in artifacts:
        info = classification_for(artifact)
        entries.append(
            {
                "artifact": artifact,
                "group": info["group"],
                "retention_reason": info["retention_reason"],
                "contains_secrets": False,
                "generated_by_phase": info["source_phase"],
                "required_for_future_live_review": bool(info["required_for_future_live_review"]),
                "hash_reference": f"artifact_hash_manifest.json#{artifact}",
            }
        )
    groups = {group: [entry["artifact"] for entry in entries if entry["group"] == group] for group in RETENTION_GROUPS}
    return {
        "schema_version": RETENTION_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "contains_secrets": False,
        "retention_groups": groups,
        "entries": entries,
        "required_groups": RETENTION_GROUPS,
        "missing_required_groups": [group for group, names in groups.items() if not names],
        "entry_count": len(entries),
        "non_approval_statement": "Retention classification is advisory/reporting only and does not approve live execution.",
    }


def build_evidence_bundle_index(*, artifacts: list[str], run_id: str, generated_at: str) -> dict[str, Any]:
    groups = {area: [] for area in REVIEW_AREAS}
    for artifact in artifacts:
        info = classification_for(artifact)
        groups.setdefault(info["review_area"], []).append(
            {
                "artifact": artifact,
                "group": info["group"],
                "source_phase": info["source_phase"],
                "retention_reason": info["retention_reason"],
            }
        )
    return {
        "schema_version": EVIDENCE_BUNDLE_INDEX_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "review_areas": groups,
        "required_review_areas": REVIEW_AREAS,
        "missing_review_areas": [area for area, entries in groups.items() if not entries],
        "artifact_count": sum(len(entries) for entries in groups.values()),
    }
