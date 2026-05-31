"""Build deterministic Phase 12 external-auditor handoff artifacts.

Phase 12 is design-only and advisory. It packages Phase 11 human-review outputs
for external auditor or internal review-board inspection. It never enables live
execution, imports tau2, executes tau2 control flow, calls LLM/API services,
handles real credentials, stores raw secrets, or approves future execution.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from experiments.reactive_manager.human_review import NON_APPROVAL_STATEMENT as PHASE11_NON_APPROVAL_STATEMENT
from experiments.reactive_manager.planner import write_json
from experiments.reactive_manager.retention_manifest import (
    PHASE12_ARTIFACTS,
    RETENTION_GROUPS,
    build_artifact_hash_manifest,
    build_evidence_bundle_index,
    build_retention_manifest,
)

AUDITOR_HANDOFF_SCHEMA_VERSION = "activegraph_auditor_handoff_package.v1"
AUDITOR_HANDOFF_PASS_STATUS = "auditor_handoff_package_passed"
AUDITOR_HANDOFF_FAILED_STATUS = "auditor_handoff_package_failed"
AUDITOR_HANDOFF_INPUTS_MISSING_STATUS = "auditor_handoff_inputs_missing"
PHASE12 = "phase_12_design_only_external_auditor_handoff_and_retention_manifest"

AUDITOR_PACKET_SECTIONS = [
    "Executive summary",
    "Scope and non-goals",
    "Current readiness status",
    "Evidence bundle overview",
    "Artifact integrity summary",
    "Retention categories",
    "Blocker summary",
    "Auditor question set",
    "Required future approvals",
    "Explicit non-approval statement",
]

NON_APPROVAL_STATEMENT = (
    "This Phase 12 external-auditor handoff and retention-manifest package is "
    "advisory/reporting only. It does not approve, authorize, enable, or execute "
    "live reactive-manager behavior; live_ready remains false and live execution "
    "remains unavailable/fail-closed."
)

AUDITOR_QUESTIONS = [
    {
        "question": "What evidence proves live_ready=false?",
        "evidence_groups": ["live opt-in readiness", "audit / credential / sandbox readiness", "operator authorization and incident response", "human review"],
        "source_artifacts": ["live_readiness_report.json", "live_readiness_audit_report.json", "operator_incident_readiness_report.json", "human_review_package.json"],
    },
    {
        "question": "What evidence proves live execution is unavailable/fail-closed?",
        "evidence_groups": ["execution contracts", "live opt-in readiness", "human review"],
        "source_artifacts": ["contract_report.json", "live_readiness_report.json", "human_review_packet.md"],
    },
    {
        "question": "What evidence proves no tau2 control flow executed?",
        "evidence_groups": ["trace and projection", "state packets and hash chain", "human review", "auditor handoff"],
        "source_artifacts": ["final_state.json", "human_review_package.json", "auditor_handoff_package.json"],
    },
    {
        "question": "What evidence proves no LLM/API calls were made?",
        "evidence_groups": ["human review", "auditor handoff"],
        "source_artifacts": ["human_review_package.json", "final_state.json", "auditor_handoff_package.json"],
    },
    {
        "question": "What evidence proves no raw secrets were stored?",
        "evidence_groups": ["audit / credential / sandbox readiness", "external audit/vault readiness", "human review", "auditor handoff"],
        "source_artifacts": ["credential_policy_report.json", "vault_integration_contracts.json", "retention_manifest.json"],
    },
    {
        "question": "What evidence proves vendor/tau2-bench was unchanged?",
        "evidence_groups": ["tau2 provenance", "audit / credential / sandbox readiness", "human review"],
        "source_artifacts": ["vendor/tau2-bench.UPSTREAM_COMMIT", "sandbox_policy_report.json", "human_review_package.json"],
    },
    {
        "question": "What blockers prevent live readiness?",
        "evidence_groups": ["human review", "operator authorization and incident response", "external audit/vault readiness"],
        "source_artifacts": ["blocker_matrix.json", "operator_incident_readiness_report.json", "external_readiness_report.json"],
    },
    {
        "question": "What future approvals would be required before live execution?",
        "evidence_groups": ["human review", "auditor handoff"],
        "source_artifacts": ["reviewer_checklist.md", "auditor_handoff_packet.md"],
    },
    {
        "question": "Which artifacts should be retained for later comparison?",
        "evidence_groups": ["auditor handoff"],
        "source_artifacts": ["retention_manifest.json", "artifact_hash_manifest.json"],
    },
    {
        "question": "Which evidence would an external auditor need to inspect first?",
        "evidence_groups": ["auditor handoff", "human review", "live opt-in readiness"],
        "source_artifacts": ["auditor_handoff_packet.md", "human_review_packet.md", "live_readiness_report.json"],
    },
]

REQUIRED_FUTURE_APPROVALS = [
    "Separate live-manager design review and implementation approval.",
    "Explicit operator authorization runtime approval with revocation and expiration semantics.",
    "External immutable audit-store integration approval and retention policy acceptance.",
    "Handle-only credential vault integration approval with no raw secret storage.",
    "Sandbox/network/model/tool boundary approval for any live execution environment.",
    "Rollback/recovery executor design approval and tested fail-closed procedures.",
    "No-regression approval proving state packets are never fed back into tau2 execution.",
]


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_required_artifacts(phase11_required: list[str], phase11_artifacts: list[str]) -> list[str]:
    artifacts = ["vendor/tau2-bench.UPSTREAM_COMMIT", *phase11_required, *phase11_artifacts, *PHASE12_ARTIFACTS]
    deduped: list[str] = []
    for artifact in artifacts:
        if artifact not in deduped:
            deduped.append(artifact)
    return deduped


def summarize_blockers(blocker_matrix: dict[str, Any]) -> dict[str, Any]:
    categories = blocker_matrix.get("categories", {})
    summary_categories: dict[str, Any] = {}
    for category in sorted(categories):
        items = categories[category]
        summary_categories[category] = {
            "blocker_count": len(items),
            "unresolved_count": sum(1 for item in items if item.get("status") == "unresolved"),
            "source_reports": sorted({source for item in items for source in item.get("source_reports", [])}),
            "blockers": [item.get("blocker") for item in items],
        }
    return {
        "source_artifact": "blocker_matrix.json",
        "blocker_count": blocker_matrix.get("blocker_count", sum(value["blocker_count"] for value in summary_categories.values())),
        "category_count": blocker_matrix.get("category_count", len(summary_categories)),
        "categories": summary_categories,
    }


def build_unresolved_prerequisites(blocker_summary: dict[str, Any]) -> list[dict[str, Any]]:
    prerequisites: list[dict[str, Any]] = []
    for category, value in blocker_summary["categories"].items():
        for blocker in value["blockers"]:
            prerequisites.append({"category": category, "blocker": blocker, "source_reports": value["source_reports"], "status": "unresolved_or_review_required"})
    return prerequisites


def build_auditor_handoff_package(
    *,
    out_dir: pathlib.Path,
    run_id: str,
    generated_at: str,
    command: str,
    source_human_review_run_dir: str,
    required_artifacts: list[str],
    vendor_modified: bool,
) -> dict[str, Any]:
    human_review_package = read_json(out_dir / "human_review_package.json")
    blocker_matrix = read_json(out_dir / "blocker_matrix.json")
    blocker_summary = summarize_blockers(blocker_matrix)
    return {
        "schema_version": AUDITOR_HANDOFF_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "phase": PHASE12,
        "status": AUDITOR_HANDOFF_PASS_STATUS,
        "live_ready": False,
        "live_execution_available": False,
        "tau2_control_flow_executed": False,
        "llm_api_calls_made": False,
        "vendor_tau2_bench_modified": vendor_modified,
        "source_human_review_package": {
            "run_dir": source_human_review_run_dir,
            "artifact": "human_review_package.json",
            "status": human_review_package.get("status"),
            "live_ready": human_review_package.get("live_ready"),
            "non_approval_statement": human_review_package.get("non_approval_statement", PHASE11_NON_APPROVAL_STATEMENT),
        },
        "evidence_bundle_index": "evidence_bundle_index.json",
        "retention_manifest": "retention_manifest.json",
        "artifact_hash_manifest": "artifact_hash_manifest.json",
        "blocker_summary": blocker_summary,
        "unresolved_prerequisites": build_unresolved_prerequisites(blocker_summary),
        "auditor_question_set": AUDITOR_QUESTIONS,
        "non_approval_statement": NON_APPROVAL_STATEMENT,
        "provenance": {
            "command": command,
            "output_dir": str(out_dir),
            "source_human_review_run_dir": source_human_review_run_dir,
            "required_artifacts": required_artifacts,
            "handoff_packet_sections": AUDITOR_PACKET_SECTIONS,
            "design_only": True,
            "advisory_only": True,
            "approves_execution": False,
            "no_live_execution_code_path_added": True,
            "no_tau2_benchmark_episodes_imported_or_run": True,
            "no_tau2_control_flow_executed": True,
            "state_packets_fed_back_into_tau2": False,
            "no_llm_api_services_called": True,
            "no_real_credentials_handled": True,
            "no_raw_secrets_stored": True,
        },
    }


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}\n"


def render_auditor_questions(package: dict[str, Any]) -> str:
    lines = ["# Auditor question set", "", "Each question maps to evidence groups and source artifacts. Answering these questions is review-only and does not approve live execution.", ""]
    for index, question in enumerate(package["auditor_question_set"], start=1):
        lines.extend(
            [
                f"## {index}. {question['question']}",
                "",
                "Evidence groups: " + ", ".join(f"`{group}`" for group in question["evidence_groups"]),
                "",
                "Source artifacts: " + ", ".join(f"`{artifact}`" for artifact in question["source_artifacts"]),
                "",
            ]
        )
    lines.extend(["## Non-approval boundary", "", package["non_approval_statement"], ""])
    return "\n".join(lines)


def render_auditor_handoff_packet(package: dict[str, Any], retention_manifest: dict[str, Any], evidence_index: dict[str, Any], hash_manifest: dict[str, Any] | None = None) -> str:
    blocker_summary = package["blocker_summary"]
    hash_count = hash_manifest.get("artifact_count", "pending") if hash_manifest else "pending"
    missing_hashes = hash_manifest.get("missing_artifacts", []) if hash_manifest else []
    sections = ["# Phase 12 external-auditor handoff packet", ""]
    sections.append(
        _section(
            "Executive summary",
            "Phase 12 packages the Phase 11 human-review artifact chain for an external auditor or internal review board. The handoff is deterministic, advisory, retention-ready, and explicitly non-approving.",
        )
    )
    sections.append(
        _section(
            "Scope and non-goals",
            "Scope: reference existing local artifacts, classify retention groups, hash evidence, summarize blockers, and provide auditor questions. Non-goals: no live reactive-manager execution, no ActiveGraph control of tau2 lifecycle or task state, no feedback of state packets into tau2, no tau2 behavior mutation, no vendored tau2 mutation, no model-backed tau2 benchmark episodes, no LLM/API calls, no API keys, no real credential handling, and no raw secret storage.",
        )
    )
    sections.append(
        _section(
            "Current readiness status",
            "`live_ready=false`; `live_execution_available=false`; live execution remains unavailable/fail-closed; `tau2_control_flow_executed=false`; `llm_api_calls_made=false`; `vendor_tau2_bench_modified=false` for a passing run.",
        )
    )
    overview_lines = []
    for area, entries in evidence_index["review_areas"].items():
        overview_lines.append(f"- `{area}`: {len(entries)} artifact(s)")
    sections.append(_section("Evidence bundle overview", "\n".join(overview_lines)))
    sections.append(
        _section(
            "Artifact integrity summary",
            f"Hash manifest: `artifact_hash_manifest.json`; hash algorithm: sha256; artifact entries: {hash_count}; missing artifacts: {missing_hashes}. The hash manifest lists itself with a self-hash exclusion to avoid recursive non-determinism.",
        )
    )
    retention_lines = [f"- `{group}`: {len(retention_manifest['retention_groups'].get(group, []))} artifact(s)" for group in RETENTION_GROUPS]
    sections.append(_section("Retention categories", "\n".join(retention_lines)))
    blocker_lines = [f"- `{category}`: {value['blocker_count']} blocker(s), {value['unresolved_count']} unresolved" for category, value in blocker_summary["categories"].items()]
    sections.append(_section("Blocker summary", "\n".join(blocker_lines)))
    question_lines = [f"- {item['question']} Evidence groups: {', '.join(item['evidence_groups'])}." for item in package["auditor_question_set"]]
    sections.append(_section("Auditor question set", "\n".join(question_lines)))
    approval_lines = [f"- {approval}" for approval in REQUIRED_FUTURE_APPROVALS]
    sections.append(_section("Required future approvals", "\n".join(approval_lines)))
    sections.append(_section("Explicit non-approval statement", package["non_approval_statement"]))
    return "\n".join(sections).rstrip() + "\n"


def render_handoff_summary(package: dict[str, Any], retention_manifest: dict[str, Any], evidence_index: dict[str, Any], hash_manifest: dict[str, Any] | None = None) -> str:
    hash_count = hash_manifest.get("artifact_count", "pending") if hash_manifest else "pending"
    return f"""# Phase 12 auditor handoff summary

Status: `{package['status']}`

Readiness: `live_ready={str(package['live_ready']).lower()}`; `live_execution_available={str(package['live_execution_available']).lower()}`; fail-closed and non-approving.

Artifacts hashed: `{hash_count}`

Retention groups populated: `{len([group for group, entries in retention_manifest['retention_groups'].items() if entries])}` of `{len(retention_manifest['retention_groups'])}`

Evidence review areas populated: `{len([area for area, entries in evidence_index['review_areas'].items() if entries])}` of `{len(evidence_index['review_areas'])}`

Blockers summarized: `{package['blocker_summary']['blocker_count']}` across `{package['blocker_summary']['category_count']}` categories.

Non-approval: {package['non_approval_statement']}
"""


def write_auditor_handoff_artifacts(
    *,
    out_dir: pathlib.Path,
    package: dict[str, Any],
    required_artifacts: list[str],
    run_id: str,
    generated_at: str,
) -> dict[str, Any]:
    evidence_index = build_evidence_bundle_index(artifacts=required_artifacts, run_id=run_id, generated_at=generated_at)
    retention_manifest = build_retention_manifest(artifacts=required_artifacts, run_id=run_id, generated_at=generated_at)
    write_json(out_dir / "evidence_bundle_index.json", evidence_index)
    write_json(out_dir / "retention_manifest.json", retention_manifest)
    write_json(out_dir / "auditor_handoff_package.json", package)
    (out_dir / "auditor_questions.md").write_text(render_auditor_questions(package), encoding="utf-8")
    for placeholder in ["auditor_handoff_packet.md", "handoff_summary.md", "summary.md", "artifact_hash_manifest.json"]:
        (out_dir / placeholder).write_text("pending deterministic Phase 12 artifact materialization\n", encoding="utf-8")
    expected_missing = [artifact for artifact in required_artifacts if not ((out_dir.parents[1] / artifact) if artifact.startswith("vendor/") else (out_dir / artifact)).is_file()]
    hash_manifest_summary = {"artifact_count": len(required_artifacts), "missing_artifacts": expected_missing}
    (out_dir / "auditor_handoff_packet.md").write_text(render_auditor_handoff_packet(package, retention_manifest, evidence_index, hash_manifest_summary), encoding="utf-8")
    (out_dir / "handoff_summary.md").write_text(render_handoff_summary(package, retention_manifest, evidence_index, hash_manifest_summary), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_handoff_summary(package, retention_manifest, evidence_index, hash_manifest_summary), encoding="utf-8")
    hash_manifest = build_artifact_hash_manifest(out_dir=out_dir, artifacts=required_artifacts, run_id=run_id, generated_at=generated_at)
    write_json(out_dir / "artifact_hash_manifest.json", hash_manifest)
    return {"evidence_index": evidence_index, "retention_manifest": retention_manifest, "hash_manifest": hash_manifest}
