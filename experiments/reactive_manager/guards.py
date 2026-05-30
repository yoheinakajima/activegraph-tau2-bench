"""Fail-closed safety gates for Phase 6 reactive-manager contracts."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from experiments.reactive_manager.contracts import (
    LIVE_CONTROL_MODE,
    PLAN_ONLY_MODE,
    ContractValidationResult,
    ReactiveManagerExecutionRequest,
    ReactiveManagerGuardResult,
    ReactiveManagerSafetyPolicy,
)

SECRET_KEY_FRAGMENTS = ("api_key", "apikey", "secret", "token", "password", "credential")
SECRET_VALUE_PATTERN = re.compile(r"(?i)(sk-[A-Za-z0-9_-]{8,}|api[_-]?key|bearer\s+[A-Za-z0-9._-]{8,})")
REQUIRED_ARTIFACTS = (
    "events.jsonl",
    "activegraph_trace.json",
    "state_packets.jsonl",
    "state_packet_index.json",
    "manager_plan.json",
    "manager_decisions.jsonl",
    "replay_plan.json",
    "fork_plan.json",
    "diff_report.json",
)


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


def contains_secret_like_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if any(fragment in key_lower for fragment in SECRET_KEY_FRAGMENTS):
                if nested is not False and nested is not None:
                    return True
            if contains_secret_like_payload(nested):
                return True
    elif isinstance(value, list):
        return any(contains_secret_like_payload(item) for item in value)
    elif isinstance(value, str):
        return SECRET_VALUE_PATTERN.search(value) is not None
    return False


def _result(gate: str, passed: bool, reason: str, source_links: list[str] | None = None) -> ReactiveManagerGuardResult:
    return ReactiveManagerGuardResult(gate=gate, passed=passed, reason=reason, source_links=source_links or [])


def _artifact_sources(request: ReactiveManagerExecutionRequest, names: tuple[str, ...]) -> list[str]:
    return [request.artifact_paths[name] for name in names if name in request.artifact_paths]


def validate_execution_request(
    request: ReactiveManagerExecutionRequest,
    *,
    policy: ReactiveManagerSafetyPolicy,
    repo_root: Path,
) -> ContractValidationResult:
    """Validate all Phase 6 gates; any missing requirement fails closed."""
    results: list[ReactiveManagerGuardResult] = []

    results.append(
        _result(
            "execution_mode_allowlisted",
            request.execution_mode in policy.allowlisted_execution_modes,
            f"mode={request.execution_mode!r}; allowlist={list(policy.allowlisted_execution_modes)}",
        )
    )
    results.append(
        _result(
            "live_execution_unavailable",
            request.dry_run is True and request.execution_mode == PLAN_ONLY_MODE,
            "Phase 6 hard-codes live execution as unavailable; only plan-only dry-run requests may pass.",
        )
    )
    results.append(_result("explicit_opt_in", request.explicit_opt_in is True, "explicit opt-in flag must be true."))
    results.append(
        _result(
            "dry_run_required",
            request.dry_run is True,
            "dry_run must remain true in Phase 6; dry_run=false is reserved for a future phase.",
        )
    )
    ack_ok = request.operator_acknowledgment == "phase6_plan_only_no_live_execution"
    results.append(
        _result(
            "operator_acknowledgment",
            ack_ok,
            "operator acknowledgment must be the Phase 6 plan-only no-live-execution acknowledgment.",
        )
    )

    provenance = request.provenance
    results.append(_result("events_provenance", bool(provenance.get("events")), "events.jsonl provenance is required.", _artifact_sources(request, ("events.jsonl",))))
    results.append(
        _result(
            "graph_projection_provenance",
            bool(provenance.get("activegraph_trace")),
            "activegraph_trace.json provenance is required.",
            _artifact_sources(request, ("activegraph_trace.json",)),
        )
    )
    results.append(
        _result(
            "state_packet_provenance",
            bool(provenance.get("state_packets")) and bool(provenance.get("state_packet_index")),
            "state packet and packet-index provenance are required.",
            _artifact_sources(request, ("state_packets.jsonl", "state_packet_index.json")),
        )
    )

    missing_artifacts = [name for name in REQUIRED_ARTIFACTS if name not in request.artifact_paths]
    results.append(_result("required_artifacts_present", not missing_artifacts, f"missing_artifacts={missing_artifacts}"))

    packet_validation = request.validation.get("state_packet_chain", {})
    results.append(
        _result(
            "state_packet_hash_chain_valid",
            packet_validation.get("ok") is True and packet_validation.get("hash_chain_valid") is not False,
            "state packet chain validation must pass with a valid hash chain.",
            _artifact_sources(request, ("state_packets.jsonl", "state_packet_index.json")),
        )
    )
    manager_validation = request.validation.get("manager_plan", {})
    results.append(
        _result(
            "replay_fork_diff_plan_valid",
            manager_validation.get("ok") is True,
            "replay/fork/diff manager validation must pass before any execution-like boundary.",
            _artifact_sources(request, ("manager_plan.json", "replay_plan.json", "fork_plan.json", "diff_report.json")),
        )
    )
    pending_errors = request.validation.get("errors", [])
    results.append(_result("no_pending_validation_errors", not pending_errors, f"pending_errors={pending_errors}"))
    results.append(
        _result(
            "no_api_keys_or_secrets",
            not contains_secret_like_payload(request.to_json_dict()),
            "request payload and metadata must not contain API-key-like or secret-like material.",
        )
    )

    status = vendor_status(repo_root)
    results.append(_result("vendor_tau2_bench_unchanged", status == "", f"vendor_status={status or 'clean'}"))

    no_llm_status = request.provenance.get("no_llm_status", {})
    no_model_episode = no_llm_status.get("real_tau2_episode_run") is False and request.payload.get("model_backed_episode_execution") is not True
    results.append(_result("no_model_backed_episode_execution", no_model_episode, "model-backed tau2 benchmark episode execution is forbidden."))
    controls_tau2 = request.payload.get("controls_tau2_execution") is True or request.execution_mode == LIVE_CONTROL_MODE
    results.append(_result("no_tau2_control_flow", not controls_tau2, "ActiveGraph/reactive manager must not control tau2 lifecycle or task state in Phase 6."))

    errors = [f"{result.gate}: {result.reason}" for result in results if not result.passed]
    return ContractValidationResult(ok=not errors, errors=errors, guard_results=results)
