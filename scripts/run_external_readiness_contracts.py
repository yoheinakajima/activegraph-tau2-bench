#!/usr/bin/env python3
"""Phase 9 design-only external audit-store and vault readiness smoke.

This command regenerates the fixture-backed Phase 8 artifact chain, then adds
mock-contract reports for a future external audit store and credential vault
integration. It never enables live execution, imports or runs tau2 benchmark
episodes, controls tau2 lifecycle/task state, feeds state packets back into
tau2, calls LLM/API services, reads real credentials, or stores raw secrets.
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

from experiments.reactive_manager.external_audit_store import build_external_audit_store_contracts  # noqa: E402
from experiments.reactive_manager.external_readiness import (  # noqa: E402
    EXTERNAL_READINESS_FAILED_STATUS,
    EXTERNAL_READINESS_INPUTS_MISSING_STATUS,
    EXTERNAL_READINESS_PASS_STATUS,
    PHASE9_ARTIFACTS,
    build_external_readiness_report,
)
from experiments.reactive_manager.live_readiness_audit import (  # noqa: E402
    PHASE8_ARTIFACTS,
    build_live_readiness_audit_artifacts,
    find_missing_required_inputs,
    required_phase7_artifacts,
)
from experiments.reactive_manager.planner import write_json, write_jsonl  # noqa: E402
from experiments.reactive_manager.vault_integration import build_vault_integration_contracts  # noqa: E402
from experiments.state_packets.packets import STATE_PACKET_SCHEMA_VERSION  # noqa: E402
from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION  # noqa: E402
from scripts.run_live_readiness_audit import TRACE_MODE, _write_phase7_artifacts  # noqa: E402
from scripts.run_reactive_manager_dry_run import git_vendor_status  # noqa: E402
from scripts.run_trace_smoke import NO_LLM_STATUS, RUNS_DIR, VENDOR_DIR, rel, write  # noqa: E402

COMMAND = "python scripts/run_external_readiness_contracts.py"


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    artifact_lines = "\n".join(f"- `{artifact}`" for artifact in final_state["artifacts"])
    blocker_lines = "\n".join(f"- {blocker}" for blocker in final_state["blocker_summary"])
    external_rejections = "\n".join(f"- `{reason}`" for reason in final_state["external_audit_store_summary"]["observed_rejected_reasons"])
    vault_rejections = "\n".join(f"- `{reason}`" for reason in final_state["vault_integration_summary"]["observed_rejected_reasons"])
    content = f"""# tau2-bench Phase 9 external audit-store and vault readiness

Status: `{final_state['state']}`

Run directory: `{final_state['output_dir']}`

## Readiness result

- live_ready: `{final_state['live_ready']}`
- live execution available: `{final_state['live_execution_available']}`
- live execution unavailable/fail-closed: `{final_state['live_execution_unavailable_fail_closed']}`
- external_audit_store_live_ready: `{final_state['external_audit_store_live_ready']}`
- vault_integration_live_ready: `{final_state['vault_integration_live_ready']}`
- tau2 control flow executed: `{final_state['tau2_control_flow_executed']}`
- LLM/API calls made: `{final_state['llm_api_calls_made']}`

## External audit-store contracts

- contracts_ok: `{final_state['external_audit_store_summary']['contracts_ok']}`
- append-only required: `{final_state['external_audit_store_summary']['append_only_required']}`
- read-back verification required: `{final_state['external_audit_store_summary']['read_back_verification_required']}`
- hash-chain anchoring required: `{final_state['external_audit_store_summary']['hash_chain_anchoring_required']}`
- source artifact anchoring required: `{final_state['external_audit_store_summary']['source_artifact_anchoring_required']}`

Rejected reasons covered:

{external_rejections}

## Vault integration contracts

- contracts_ok: `{final_state['vault_integration_summary']['contracts_ok']}`
- vault runtime available: `{final_state['vault_integration_summary']['vault_runtime_available']}`
- accepted handle schema: `{final_state['vault_integration_summary']['accepted_handle_schema']}`
- raw credential values allowed: `{final_state['vault_integration_summary']['raw_credential_values_allowed']}`
- environment-variable lookup allowed: `{final_state['vault_integration_summary']['environment_variable_lookup_allowed']}`
- filesystem secret reads allowed: `{final_state['vault_integration_summary']['filesystem_secret_reads_allowed']}`
- raw material written to artifacts: `{final_state['vault_integration_summary']['raw_material_written_to_artifacts']}`

Rejected reasons covered:

{vault_rejections}

## Blocker summary

{blocker_lines}

## Artifacts

{artifact_lines}

## Boundary

Phase 9 is design-only. It validates mock contracts for future external audit storage and future vault integration while intentionally keeping `live_ready=false`; live reactive-manager execution remains unavailable and fail-closed.
"""
    write(out_dir / "summary.md", content)


def _write_failure(out_dir: pathlib.Path, log_lines: list[str], timestamp: str, run_id: str, state: str, errors: list[str]) -> int:
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": state,
        "errors": errors,
        "output_dir": rel(out_dir),
        "command": COMMAND,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "external_audit_store_live_ready": False,
        "vault_integration_live_ready": False,
        "tau2_control_flow_executed": False,
        "llm_api_calls_made": False,
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
    write(out_dir / "raw.log", "\n".join(log_lines + errors) + "\n")
    print(out_dir)
    print(state)
    return 1


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"external-readiness-contracts-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 9 design-only external audit-store and vault readiness smoke",
        f"timestamp_utc={timestamp}",
        f"command={COMMAND}",
        "boundary=design-only mock contracts; live_ready=false; no live manager; no tau2 control; no tau2 run; no LLM/API calls; no real credentials",
    ]

    generated, phase6_report, phase7_readiness_report, proposals, decisions = _write_phase7_artifacts(out_dir, run_id, timestamp, log_lines)
    if not generated.get("ok"):
        return _write_failure(out_dir, log_lines, timestamp, run_id, EXTERNAL_READINESS_INPUTS_MISSING_STATUS, generated.get("errors", []))

    missing_inputs = find_missing_required_inputs(out_dir)
    if missing_inputs:
        return _write_failure(out_dir, log_lines, timestamp, run_id, EXTERNAL_READINESS_INPUTS_MISSING_STATUS, [f"missing_inputs={missing_inputs}"])

    vendor_status = git_vendor_status()
    phase8_artifacts = build_live_readiness_audit_artifacts(
        out_dir=out_dir,
        run_id=run_id,
        timestamp=timestamp,
        repo_root=REPO_ROOT,
        vendor_status=vendor_status,
        phase7_readiness_report=phase7_readiness_report,
        phase6_contract_report=phase6_report,
    )
    write_jsonl(out_dir / "audit_log.jsonl", phase8_artifacts["audit_records"])
    write_json(out_dir / "audit_integrity_report.json", phase8_artifacts["audit_integrity_report"])
    write_json(out_dir / "credential_policy_report.json", phase8_artifacts["credential_policy_report"])
    write_json(out_dir / "sandbox_policy_report.json", phase8_artifacts["sandbox_policy_report"])
    write_json(out_dir / "live_readiness_audit_report.json", phase8_artifacts["live_readiness_audit_report"])

    missing_phase8 = [name for name in PHASE8_ARTIFACTS if not (out_dir / name).is_file()]
    if not phase8_artifacts["ok"] or missing_phase8:
        return _write_failure(out_dir, log_lines, timestamp, run_id, EXTERNAL_READINESS_FAILED_STATUS, [f"phase8_artifacts_ok={phase8_artifacts['ok']}", f"missing_phase8={missing_phase8}"])

    external_audit_contracts = build_external_audit_store_contracts(
        audit_records=phase8_artifacts["audit_records"],
        required_source_artifacts=required_phase7_artifacts(),
    )
    vault_contracts = build_vault_integration_contracts()
    external_readiness_report = build_external_readiness_report(
        run_id=run_id,
        phase8_report=phase8_artifacts["live_readiness_audit_report"],
        external_audit_contracts=external_audit_contracts,
        vault_contracts=vault_contracts,
    )
    write_json(out_dir / "external_audit_store_contracts.json", external_audit_contracts)
    write_jsonl(out_dir / "external_audit_store_decisions.jsonl", external_audit_contracts["decisions"])
    write_json(out_dir / "vault_integration_contracts.json", vault_contracts)
    write_jsonl(out_dir / "vault_integration_decisions.jsonl", vault_contracts["decisions"])
    write_json(out_dir / "external_readiness_report.json", external_readiness_report)

    missing_phase9 = [name for name in PHASE9_ARTIFACTS if not (out_dir / name).is_file()]
    smoke_ok = (
        external_readiness_report["status"] == EXTERNAL_READINESS_PASS_STATUS
        and not missing_phase9
        and not vendor_status
        and phase7_readiness_report.get("live_ready") is False
        and phase8_artifacts["live_readiness_audit_report"].get("live_ready") is False
        and external_audit_contracts.get("external_audit_store_live_ready") is False
        and vault_contracts.get("vault_integration_live_ready") is False
    )
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": EXTERNAL_READINESS_PASS_STATUS if smoke_ok else EXTERNAL_READINESS_FAILED_STATUS,
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
        "external_audit_store_live_ready": False,
        "vault_integration_live_ready": False,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
        "tau2_benchmark_episodes_imported_or_run": False,
        "no_llm_status": NO_LLM_STATUS,
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "missing_required_inputs": missing_inputs,
        "missing_phase8_artifacts": missing_phase8,
        "missing_phase9_artifacts": missing_phase9,
        "external_audit_store_summary": external_readiness_report["external_audit_store"],
        "vault_integration_summary": external_readiness_report["vault_integration"],
        "readiness_result": external_readiness_report["readiness_result"],
        "blocker_summary": external_readiness_report["blocker_summary"],
        "external_readiness_report_path": rel(out_dir / "external_readiness_report.json"),
        "external_audit_store_contracts_path": rel(out_dir / "external_audit_store_contracts.json"),
        "vault_integration_contracts_path": rel(out_dir / "vault_integration_contracts.json"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "artifacts": required_phase7_artifacts() + PHASE8_ARTIFACTS + PHASE9_ARTIFACTS + ["summary.md", "final_state.json", "raw.log"],
        "limitations": [
            "Design-only external audit-store readiness; no real external service is implemented.",
            "Design-only vault integration readiness; no real vault runtime or credential resolution is implemented.",
            "Review-only artifacts; live reactive-manager execution is intentionally unavailable and fail-closed.",
            "No tau2 lifecycle/task-state ownership is transferred to ActiveGraph.",
            "Fixture-backed local artifacts only; no model-backed benchmark episodes or LLM/API calls.",
        ],
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
    write_summary(out_dir, final_state)
    log_lines.extend(
        [
            f"[PHASE9-EXTERNAL-AUDIT] contracts_ok={external_audit_contracts['contracts_ok']} live_ready={external_audit_contracts['external_audit_store_live_ready']} rejected={external_audit_contracts['observed_rejected_reasons']}",
            f"[PHASE9-VAULT] contracts_ok={vault_contracts['contracts_ok']} live_ready={vault_contracts['vault_integration_live_ready']} rejected={vault_contracts['observed_rejected_reasons']}",
            f"[PHASE9-READINESS] status={external_readiness_report['status']} live_ready={external_readiness_report['live_ready']} fail_closed={external_readiness_report['live_execution_unavailable_fail_closed']}",
            f"state={final_state['state']}",
            f"vendor_status={vendor_status or 'clean'}",
        ]
    )
    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")

    print(out_dir)
    print(final_state["state"])
    return 0 if final_state["state"] == EXTERNAL_READINESS_PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - write traceback artifact for unexpected smoke errors.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("external_readiness_contracts_error")
        raise
