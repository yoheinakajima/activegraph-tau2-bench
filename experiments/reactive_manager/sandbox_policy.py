"""Review-only sandbox-policy validation for future live-readiness gates."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

SANDBOX_POLICY_REPORT_SCHEMA_VERSION = "activegraph_sandbox_policy_report.v1"


@dataclass(frozen=True)
class SandboxPolicy:
    policy_id: str
    output_dir: str
    output_dir_isolated: bool
    vendor_tau2_bench_mutation_allowed: bool
    vendor_tau2_bench_modified: bool
    network_access_declared: bool
    network_access_allowed: bool
    model_api_call_requested: bool
    model_api_call_separately_gated: bool
    live_tau2_execution_requested: bool
    artifact_only_read_paths: list[str] = field(default_factory=list)
    artifact_only_write_paths: list[str] = field(default_factory=list)
    future_live_requirements_present: bool = False

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "output_dir": self.output_dir,
            "output_dir_isolated": self.output_dir_isolated,
            "vendor_tau2_bench_mutation_allowed": self.vendor_tau2_bench_mutation_allowed,
            "vendor_tau2_bench_modified": self.vendor_tau2_bench_modified,
            "network_access_declared": self.network_access_declared,
            "network_access_allowed": self.network_access_allowed,
            "model_api_call_requested": self.model_api_call_requested,
            "model_api_call_separately_gated": self.model_api_call_separately_gated,
            "live_tau2_execution_requested": self.live_tau2_execution_requested,
            "artifact_only_read_paths": list(self.artifact_only_read_paths),
            "artifact_only_write_paths": list(self.artifact_only_write_paths),
            "future_live_requirements_present": self.future_live_requirements_present,
        }


def _is_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_sandbox_policy(policy: SandboxPolicy, *, repo_root: pathlib.Path, out_dir: pathlib.Path) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    def gate(name: str, passed: bool, blocker: str) -> None:
        gates.append({"gate": name, "passed": passed, "blocker": None if passed else blocker})

    output_path = repo_root / policy.output_dir
    runs_root = repo_root / "runs"
    gate("output_directory_isolated", policy.output_dir_isolated and _is_under(output_path, runs_root), "writes must remain inside isolated runs/<timestamp> output directory")
    gate("vendor_tau2_bench_not_mutated", not policy.vendor_tau2_bench_mutation_allowed and not policy.vendor_tau2_bench_modified, "vendor/tau2-bench must remain read-only and clean")
    gate("network_disabled_or_explicitly_allowed", (not policy.network_access_declared and not policy.network_access_allowed) or (policy.network_access_declared and policy.network_access_allowed), "network access must be absent or explicitly declared and allowed")
    gate("model_api_calls_separately_gated", not policy.model_api_call_requested and not policy.model_api_call_separately_gated, "model/API calls are not allowed in Phase 8")
    gate("live_tau2_execution_disabled", not policy.live_tau2_execution_requested, "live tau2 execution is unavailable")
    artifact_read_ok = all(path.startswith("runs/") or path in {"vendor/tau2-bench.UPSTREAM_COMMIT"} for path in policy.artifact_only_read_paths)
    artifact_write_ok = all(path.startswith(str(out_dir.relative_to(repo_root))) for path in policy.artifact_only_write_paths)
    gate("artifact_only_boundaries", artifact_read_ok and artifact_write_ok, "read/write paths must stay artifact-only for this review phase")

    policy_passed = all(item["passed"] for item in gates)
    return {
        "policy": policy.to_json_dict(),
        "policy_passed": policy_passed,
        "live_sandbox_ready": policy_passed and policy.future_live_requirements_present,
        "gates": gates,
        "blockers": [item for item in gates if not item["passed"]],
    }


def build_sandbox_policy_report(*, repo_root: pathlib.Path, out_dir: pathlib.Path, vendor_status: str) -> dict[str, Any]:
    rel_out = str(out_dir.relative_to(repo_root))
    valid_review_policy = SandboxPolicy(
        policy_id="sandbox-policy-valid-review-only",
        output_dir=rel_out,
        output_dir_isolated=True,
        vendor_tau2_bench_mutation_allowed=False,
        vendor_tau2_bench_modified=bool(vendor_status),
        network_access_declared=False,
        network_access_allowed=False,
        model_api_call_requested=False,
        model_api_call_separately_gated=False,
        live_tau2_execution_requested=False,
        artifact_only_read_paths=[f"{rel_out}/live_readiness_report.json", f"{rel_out}/live_manager_proposal.json", "vendor/tau2-bench.UPSTREAM_COMMIT"],
        artifact_only_write_paths=[f"{rel_out}/audit_log.jsonl", f"{rel_out}/sandbox_policy_report.json"],
        future_live_requirements_present=False,
    )
    invalid_network_model_live_policy = SandboxPolicy(
        policy_id="sandbox-policy-invalid-network-model-live",
        output_dir=rel_out,
        output_dir_isolated=True,
        vendor_tau2_bench_mutation_allowed=False,
        vendor_tau2_bench_modified=bool(vendor_status),
        network_access_declared=True,
        network_access_allowed=False,
        model_api_call_requested=True,
        model_api_call_separately_gated=False,
        live_tau2_execution_requested=True,
        artifact_only_read_paths=[f"{rel_out}/live_readiness_report.json"],
        artifact_only_write_paths=[f"{rel_out}/sandbox_policy_report.json"],
        future_live_requirements_present=False,
    )
    invalid_boundary_policy = SandboxPolicy(
        policy_id="sandbox-policy-invalid-boundaries",
        output_dir="vendor/tau2-bench",
        output_dir_isolated=False,
        vendor_tau2_bench_mutation_allowed=True,
        vendor_tau2_bench_modified=True,
        network_access_declared=False,
        network_access_allowed=False,
        model_api_call_requested=False,
        model_api_call_separately_gated=False,
        live_tau2_execution_requested=False,
        artifact_only_read_paths=["vendor/tau2-bench/src"],
        artifact_only_write_paths=["vendor/tau2-bench/forbidden.json"],
        future_live_requirements_present=False,
    )
    validations = [
        validate_sandbox_policy(policy, repo_root=repo_root, out_dir=out_dir)
        for policy in [valid_review_policy, invalid_network_model_live_policy, invalid_boundary_policy]
    ]
    valid_review = validations[0]
    return {
        "schema_version": SANDBOX_POLICY_REPORT_SCHEMA_VERSION,
        "policy_count": len(validations),
        "valid_review_policy_passed": valid_review["policy_passed"],
        "invalid_policy_rejected_count": sum(1 for item in validations[1:] if not item["policy_passed"]),
        "live_sandbox_ready": False,
        "future_live_requirements_present": False,
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "validations": validations,
        "network_model_live_unsafe_settings_rejected": not validations[1]["policy_passed"],
        "artifact_boundaries_enforced": not validations[2]["policy_passed"],
        "live_ready_blocker": "future live sandbox enforcement requirements are absent in Phase 8",
    }
