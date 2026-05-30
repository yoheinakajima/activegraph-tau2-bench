#!/usr/bin/env python3
"""Phase 8 review-only live-readiness audit smoke.

This command regenerates the fixture-backed Phase 7 artifact chain, then adds
audit-log integrity, credential handle-only policy, and sandbox-policy reports.
It never enables live execution, imports or runs tau2 benchmark episodes,
controls tau2 lifecycle/task state, feeds state packets back into tau2, calls
LLM/API services, reads environment secrets, or stores raw secrets.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import traceback
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.reactive_manager.live_opt_in import build_representative_live_opt_in_proposals  # noqa: E402
from experiments.reactive_manager.live_readiness import build_live_readiness_report, validate_live_readiness_proposal  # noqa: E402
from experiments.reactive_manager.live_readiness_audit import (  # noqa: E402
    LIVE_READINESS_AUDIT_FAILED_STATUS,
    LIVE_READINESS_AUDIT_INPUTS_MISSING_STATUS,
    LIVE_READINESS_AUDIT_PASS_STATUS,
    PHASE8_ARTIFACTS,
    build_live_readiness_audit_artifacts,
    find_missing_required_inputs,
    required_phase7_artifacts,
)
from experiments.reactive_manager.planner import write_json, write_jsonl  # noqa: E402
from experiments.state_packets.packets import STATE_PACKET_SCHEMA_VERSION  # noqa: E402
from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION  # noqa: E402
from scripts.run_live_manager_opt_in_contracts import write_phase6_contract_artifacts  # noqa: E402
from scripts.run_reactive_manager_contracts import artifact_paths, base_provenance, build_phase5_artifacts  # noqa: E402
from scripts.run_reactive_manager_dry_run import git_vendor_status  # noqa: E402
from scripts.run_trace_smoke import NO_LLM_STATUS, RUNS_DIR, VENDOR_DIR, rel, write  # noqa: E402

COMMAND = "python scripts/run_live_readiness_audit.py"
TRACE_MODE = "fixture_backed_live_readiness_audit_review_only_no_execution"


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    artifact_lines = "\n".join(f"- `{artifact}`" for artifact in final_state["artifacts"])
    blocker_lines = "\n".join(f"- {blocker}" for blocker in final_state["blocker_summary"])
    content = f"""# tau2-bench Phase 8 live-readiness audit

Status: `{final_state['state']}`

Run directory: `{final_state['output_dir']}`

## Readiness result

- live_ready: `{final_state['live_ready']}`
- live execution available: `{final_state['live_execution_available']}`
- live execution unavailable/fail-closed: `{final_state['live_execution_unavailable_fail_closed']}`
- credential_live_ready: `{final_state['credential_policy_summary']['credential_live_ready']}`
- vault_runtime_available: `{final_state['credential_policy_summary']['vault_runtime_available']}`
- live_sandbox_ready: `{final_state['sandbox_policy_summary']['live_sandbox_ready']}`
- tau2 control flow executed: `{final_state['tau2_control_flow_executed']}`
- LLM/API calls made: `{final_state['llm_api_calls_made']}`

## Audit integrity

- audit records: {final_state['audit_record_count']}
- hash-chain valid: `{final_state['audit_hash_chain_valid']}`
- source links valid: `{final_state['audit_source_links_valid']}`

## Credential policy

- valid inert handle accepted: `{final_state['credential_policy_summary']['valid_handle_accepted']}`
- raw secret-like values rejected: `{final_state['credential_policy_summary']['raw_secret_like_values_rejected']}`
- no raw secrets written: `{final_state['credential_policy_summary']['no_raw_secrets_written']}`

## Sandbox policy

- valid review policy passed: `{final_state['sandbox_policy_summary']['valid_review_policy_passed']}`
- invalid policies rejected: {final_state['sandbox_policy_summary']['invalid_policy_rejected_count']}
- unsafe network/model/live-tau2 settings rejected: `{final_state['sandbox_policy_summary']['network_model_live_unsafe_settings_rejected']}`
- vendor/tau2-bench modified: `{final_state['sandbox_policy_summary']['vendor_tau2_bench_modified']}`

## Blocker summary

{blocker_lines}

## Artifacts

{artifact_lines}

## Boundary

Phase 8 is review-only. It validates audit, credential, and sandbox policies while intentionally keeping `live_ready=false`; live reactive-manager execution remains unavailable and fail-closed.
"""
    write(out_dir / "summary.md", content)


def _write_phase7_artifacts(out_dir: pathlib.Path, run_id: str, timestamp: str, log_lines: list[str]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[Any], list[Any]]:
    generated = build_phase5_artifacts(out_dir, run_id, timestamp, log_lines)
    if not generated["ok"]:
        return generated, {}, {}, [], []
    phase6_report = write_phase6_contract_artifacts(out_dir, run_id, generated, log_lines)
    proposals = build_representative_live_opt_in_proposals(
        run_id=run_id,
        artifact_paths=artifact_paths(out_dir),
        provenance=base_provenance(generated),
        validation=generated["combined_validation"],
    )
    decisions = []
    for index, proposal in enumerate(proposals, start=1):
        decision = validate_live_readiness_proposal(proposal, repo_root=REPO_ROOT, decision_id=f"live-opt-in-decision-{index:06d}")
        decisions.append(decision)
        log_lines.append(f"[LIVE-OPT-IN] {decision.decision_id} scenario={proposal.scenario} status={decision.status} structurally_complete={decision.structurally_complete} live_ready={decision.live_ready} executed={decision.executed}")
    proposal_bundle = {
        "schema_version": "activegraph_live_reactive_manager_opt_in_proposal_bundle.v1",
        "run_id": run_id,
        "phase": "phase_7_live_reactive_manager_opt_in_contracts",
        "proposal_count": len(proposals),
        "proposals": [proposal.to_json_dict() for proposal in proposals],
    }
    write_json(out_dir / "live_manager_proposal.json", proposal_bundle)
    write_jsonl(out_dir / "live_opt_in_decisions.jsonl", [decision.to_json_dict() for decision in decisions])
    readiness_report = build_live_readiness_report(run_id=run_id, proposals=proposals, decisions=decisions)
    write_json(out_dir / "live_readiness_report.json", readiness_report)
    return generated, phase6_report, readiness_report, proposals, decisions


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"live-readiness-audit-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 8 review-only live-readiness audit smoke",
        f"timestamp_utc={timestamp}",
        f"command={COMMAND}",
        "boundary=review-only reports; live_ready=false; no live manager; no tau2 control; no tau2 run; no LLM/API calls; no real credentials",
    ]

    generated, phase6_report, readiness_report, proposals, decisions = _write_phase7_artifacts(out_dir, run_id, timestamp, log_lines)
    if not generated.get("ok"):
        final_state = {
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "state": LIVE_READINESS_AUDIT_INPUTS_MISSING_STATUS,
            "errors": generated.get("errors", []),
            "output_dir": rel(out_dir),
            "command": COMMAND,
            "live_ready": False,
            "live_execution_available": False,
            "tau2_control_flow_executed": False,
            "llm_api_calls_made": False,
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
        write(out_dir / "raw.log", "\n".join(log_lines + final_state["errors"]) + "\n")
        print(out_dir)
        print(final_state["state"])
        return 1

    missing_inputs = find_missing_required_inputs(out_dir)
    if missing_inputs:
        final_state = {
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "state": LIVE_READINESS_AUDIT_INPUTS_MISSING_STATUS,
            "missing_required_inputs": missing_inputs,
            "output_dir": rel(out_dir),
            "command": COMMAND,
            "live_ready": False,
            "live_execution_available": False,
            "tau2_control_flow_executed": False,
            "llm_api_calls_made": False,
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
        write(out_dir / "raw.log", "\n".join(log_lines + [f"missing_inputs={missing_inputs}"]) + "\n")
        print(out_dir)
        print(final_state["state"])
        return 1

    vendor_status = git_vendor_status()
    artifacts = build_live_readiness_audit_artifacts(
        out_dir=out_dir,
        run_id=run_id,
        timestamp=timestamp,
        repo_root=REPO_ROOT,
        vendor_status=vendor_status,
        phase7_readiness_report=readiness_report,
        phase6_contract_report=phase6_report,
    )
    write_jsonl(out_dir / "audit_log.jsonl", artifacts["audit_records"])
    write_json(out_dir / "audit_integrity_report.json", artifacts["audit_integrity_report"])
    write_json(out_dir / "credential_policy_report.json", artifacts["credential_policy_report"])
    write_json(out_dir / "sandbox_policy_report.json", artifacts["sandbox_policy_report"])
    write_json(out_dir / "live_readiness_audit_report.json", artifacts["live_readiness_audit_report"])

    missing_phase8 = [name for name in PHASE8_ARTIFACTS if not (out_dir / name).is_file()]
    smoke_ok = artifacts["ok"] and not missing_phase8 and readiness_report.get("live_ready") is False and not vendor_status
    audit_report = artifacts["live_readiness_audit_report"]
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": LIVE_READINESS_AUDIT_PASS_STATUS if smoke_ok else LIVE_READINESS_AUDIT_FAILED_STATUS,
        "schema_version": SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "event_schema_fields": EVENT_FIELDS,
        "trace_mode": TRACE_MODE,
        "vendor_dir": rel(VENDOR_DIR),
        "command": COMMAND,
        "output_dir": rel(out_dir),
        "event_count": len(generated["events"]),
        "state_packet_count": len(generated["state_packets"]),
        "manager_decision_count": len(generated["manager_decisions"]),
        "phase6_contract_decision_count": phase6_report.get("scenario_count"),
        "proposal_count": len(proposals),
        "live_opt_in_decision_count": len(decisions),
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
        "tau2_benchmark_episodes_imported_or_run": False,
        "no_llm_status": NO_LLM_STATUS,
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "missing_required_inputs": missing_inputs,
        "missing_phase8_artifacts": missing_phase8,
        "audit_record_count": audit_report["audit_record_count"],
        "audit_hash_chain_valid": audit_report["audit_hash_chain_valid"],
        "audit_source_links_valid": audit_report["audit_source_links_valid"],
        "credential_policy_summary": audit_report["credential_policy"],
        "sandbox_policy_summary": audit_report["sandbox_policy"],
        "readiness_result": audit_report["readiness_result"],
        "blocker_summary": audit_report["blocker_summary"],
        "live_readiness_audit_report_path": rel(out_dir / "live_readiness_audit_report.json"),
        "audit_log_path": rel(out_dir / "audit_log.jsonl"),
        "audit_integrity_report_path": rel(out_dir / "audit_integrity_report.json"),
        "credential_policy_report_path": rel(out_dir / "credential_policy_report.json"),
        "sandbox_policy_report_path": rel(out_dir / "sandbox_policy_report.json"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "artifacts": required_phase7_artifacts() + PHASE8_ARTIFACTS + ["summary.md", "final_state.json", "raw.log"],
        "limitations": [
            "Review-only audit/readiness validation; live reactive-manager execution is intentionally unavailable.",
            "Credential vault runtime is intentionally absent; only inert credential://future-vault/<name> handles are accepted.",
            "Sandbox policy is simulated and reports decisions only; it does not create a future live execution sandbox.",
            "No tau2 lifecycle/task-state ownership is transferred to ActiveGraph.",
            "Fixture-backed local artifacts only; no model-backed benchmark episodes or LLM/API calls.",
        ],
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
    write_summary(out_dir, final_state)
    log_lines.extend(
        [
            f"[PHASE8-AUDIT] records={final_state['audit_record_count']} hash_chain_valid={final_state['audit_hash_chain_valid']} source_links_valid={final_state['audit_source_links_valid']}",
            f"[PHASE8-CREDENTIAL] vault_runtime_available={final_state['credential_policy_summary']['vault_runtime_available']} credential_live_ready={final_state['credential_policy_summary']['credential_live_ready']} raw_secret_like_values_rejected={final_state['credential_policy_summary']['raw_secret_like_values_rejected']}",
            f"[PHASE8-SANDBOX] live_sandbox_ready={final_state['sandbox_policy_summary']['live_sandbox_ready']} invalid_policy_rejected_count={final_state['sandbox_policy_summary']['invalid_policy_rejected_count']} vendor_modified={final_state['sandbox_policy_summary']['vendor_tau2_bench_modified']}",
            f"state={final_state['state']}",
            f"vendor_status={vendor_status or 'clean'}",
        ]
    )
    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")

    print(out_dir)
    print(final_state["state"])
    return 0 if final_state["state"] == LIVE_READINESS_AUDIT_PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - write traceback artifact for unexpected smoke errors.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("live_readiness_audit_error")
        raise
