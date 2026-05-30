#!/usr/bin/env python3
"""Phase 7 live-reactive-manager opt-in contract smoke.

This command regenerates the fixture-backed Phase 6 artifact chain, builds
representative future-live opt-in proposals, and validates live-readiness gates.
It is design/validation only: it never enables live execution, imports or runs
tau2 benchmark episodes, controls tau2 lifecycle/task state, feeds state packets
back into tau2, calls LLM/API services, or handles real credentials.
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
from experiments.reactive_manager.live_readiness import (  # noqa: E402
    LIVE_OPT_IN_FAILED_STATUS,
    LIVE_OPT_IN_INPUTS_MISSING_STATUS,
    LIVE_OPT_IN_PASS_STATUS,
    build_live_readiness_report,
    validate_live_readiness_proposal,
)
from experiments.reactive_manager.planner import write_json, write_jsonl  # noqa: E402
from experiments.state_packets.packets import STATE_PACKET_SCHEMA_VERSION  # noqa: E402
from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION  # noqa: E402
from scripts.run_reactive_manager_contracts import (  # noqa: E402
    REQUIRED_ARTIFACTS as PHASE6_REQUIRED_ARTIFACTS,
    artifact_paths,
    base_provenance,
    build_phase5_artifacts,
    build_requests,
)
from experiments.reactive_manager.contracts import ReactiveManagerSafetyPolicy  # noqa: E402
from experiments.reactive_manager.executor_contract import DisabledLiveExecutor, DryRunExecutor  # noqa: E402
from scripts.run_reactive_manager_dry_run import git_vendor_status  # noqa: E402
from scripts.run_trace_smoke import NO_LLM_STATUS, RUNS_DIR, VENDOR_DIR, rel, write  # noqa: E402

COMMAND = "python scripts/run_live_manager_opt_in_contracts.py"
TRACE_MODE = "fixture_backed_live_reactive_manager_opt_in_contracts_no_execution"
PHASE6_CONTRACT_ARTIFACTS = ["contract_decisions.jsonl", "contract_report.json"]
LIVE_ARTIFACTS = ["live_opt_in_decisions.jsonl", "live_readiness_report.json", "live_manager_proposal.json"]
ALL_REQUIRED_ARTIFACTS = PHASE6_REQUIRED_ARTIFACTS + PHASE6_CONTRACT_ARTIFACTS + LIVE_ARTIFACTS


def write_phase6_contract_artifacts(out_dir: pathlib.Path, run_id: str, generated: dict[str, Any], log_lines: list[str]) -> dict[str, Any]:
    """Preserve/regenerate Phase 6 contract artifacts in the Phase 7 run dir."""
    policy = ReactiveManagerSafetyPolicy()
    requests = build_requests(out_dir, run_id, generated)
    dry_executor = DryRunExecutor(policy=policy, repo_root=REPO_ROOT)
    disabled_live_executor = DisabledLiveExecutor(policy=policy, repo_root=REPO_ROOT)
    decisions = []
    for index, request in enumerate(requests, start=1):
        executor = dry_executor if request.dry_run and request.execution_mode == "plan_only" else disabled_live_executor
        decision = executor.decide(request, decision_id=f"contract-decision-{index:06d}")
        decisions.append(decision.to_json_dict())
        log_lines.append(f"[PHASE6-CONTRACT] {decision.decision_id} scenario={request.scenario} status={decision.status} accepted={decision.accepted} executed={decision.executed}")

    write_jsonl(out_dir / "contract_decisions.jsonl", decisions)
    accepted_count = sum(1 for decision in decisions if decision["accepted"])
    rejected_count = sum(1 for decision in decisions if not decision["accepted"])
    scenario_status = {decision["scenario"]: decision for decision in decisions}
    vendor_status = git_vendor_status()
    contract_ok = (
        accepted_count == 1
        and rejected_count == 4
        and scenario_status["valid_dry_run_request"]["accepted"] is True
        and all(decision["executed"] is False for decision in decisions)
        and not vendor_status
    )
    report = {
        "schema_version": "activegraph_reactive_manager_contract_report.v1",
        "run_id": run_id,
        "status": "reactive_manager_contracts_passed" if contract_ok else "reactive_manager_contracts_failed",
        "policy": policy.to_json_dict(),
        "scenario_count": len(decisions),
        "accepted_decision_count": accepted_count,
        "rejected_decision_count": rejected_count,
        "scenarios": decisions,
        "required_artifacts": {name: rel(out_dir / name) for name in PHASE6_REQUIRED_ARTIFACTS},
        "missing_required_artifacts": [name for name in PHASE6_REQUIRED_ARTIFACTS if not (out_dir / name).exists()],
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "live_execution_available": False,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
    }
    write_json(out_dir / "contract_report.json", report)
    return report


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    scenario_lines = "\n".join(
        f"- `{item['scenario']}`: `{item['status']}` structurally_complete={item['structurally_complete']} live_ready={item['live_ready']} blockers={item['blocker_count']}"
        for item in final_state["live_scenarios"]
    )
    artifact_lines = "\n".join(f"- `{artifact}`" for artifact in final_state["artifacts"])
    blocker_lines = "\n".join(f"- `{requirement}`: {count}" for requirement, count in final_state["blocker_counts_by_requirement"].items())
    content = f"""# tau2-bench Phase 7 live reactive-manager opt-in contracts

Status: `{final_state['state']}`

Run directory: `{final_state['output_dir']}`

## Readiness result

- live_ready: `{final_state['live_ready']}`
- live execution available: `{final_state['live_execution_available']}`
- accepted decisions: {final_state['accepted_decision_count']}
- rejected decisions: {final_state['rejected_decision_count']}
- structurally complete but disabled proposals: {final_state['structurally_complete_disabled_count']}
- tau2 control flow executed: `{final_state['tau2_control_flow_executed']}`
- LLM/API calls made: `{final_state['llm_api_calls_made']}`

## Proposals

{scenario_lines}

## Blockers by requirement

{blocker_lines}

## Artifacts

{artifact_lines}

## Boundary

Phase 7 is a proposal/readiness contract layer only. It intentionally keeps `live_ready=false`; live reactive-manager execution remains unavailable and fail-closed.
"""
    write(out_dir / "summary.md", content)


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"live-manager-opt-in-contracts-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 7 live reactive-manager opt-in contract smoke",
        f"timestamp_utc={timestamp}",
        f"command={COMMAND}",
        "boundary=proposal/readiness contracts only; live_ready=false; no live manager; no tau2 control; no tau2 run; no LLM/API calls",
    ]

    generated = build_phase5_artifacts(out_dir, run_id, timestamp, log_lines)
    if not generated["ok"]:
        final_state = {
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "state": LIVE_OPT_IN_INPUTS_MISSING_STATUS,
            "errors": generated.get("errors", []),
            "output_dir": rel(out_dir),
            "command": COMMAND,
            "live_ready": False,
            "live_execution_available": False,
            "tau2_control_flow_executed": False,
            "llm_api_calls_made": False,
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
        write(out_dir / "raw.log", "\n".join(log_lines + final_state["errors"]) + "\n")
        print(out_dir)
        print(final_state["state"])
        return 1

    phase6_report = write_phase6_contract_artifacts(out_dir, run_id, generated, log_lines)
    paths = artifact_paths(out_dir)
    provenance = base_provenance(generated)
    proposals = build_representative_live_opt_in_proposals(
        run_id=run_id,
        artifact_paths=paths,
        provenance=provenance,
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

    expected_scenarios = {
        "complete_but_disabled_proposal",
        "missing_operator_acknowledgement",
        "missing_credential_isolation",
        "ambiguous_tau2_ownership",
        "missing_rollback_plan",
        "missing_audit_log_plan",
        "dirty_vendor_tree_simulated",
        "invalid_packet_chain_simulated",
        "unsafe_model_api_request",
    }
    scenario_results = {decision.scenario: decision for decision in decisions}
    missing_artifacts = [name for name in ALL_REQUIRED_ARTIFACTS if not (out_dir / name).exists()]
    vendor_status = git_vendor_status()
    smoke_ok = (
        set(scenario_results) == expected_scenarios
        and readiness_report["live_ready"] is False
        and all(decision.live_ready is False for decision in decisions)
        and all(decision.executed is False for decision in decisions)
        and scenario_results["complete_but_disabled_proposal"].structurally_complete is True
        and scenario_results["complete_but_disabled_proposal"].status == "structurally_complete_disabled"
        and all(not scenario_results[name].structurally_complete for name in expected_scenarios if name != "complete_but_disabled_proposal")
        and phase6_report["status"] == "reactive_manager_contracts_passed"
        and not missing_artifacts
        and not vendor_status
    )

    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": LIVE_OPT_IN_PASS_STATUS if smoke_ok else LIVE_OPT_IN_FAILED_STATUS,
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
        "phase6_contract_decision_count": phase6_report["scenario_count"],
        "proposal_count": len(proposals),
        "live_opt_in_decision_count": len(decisions),
        "accepted_decision_count": readiness_report["accepted_decision_count"],
        "rejected_decision_count": readiness_report["rejected_decision_count"],
        "structurally_complete_disabled_count": readiness_report["structurally_complete_disabled_count"],
        "executed_decision_count": readiness_report["executed_decision_count"],
        "live_ready": False,
        "live_execution_available": False,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
        "no_llm_status": NO_LLM_STATUS,
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "missing_required_artifacts": missing_artifacts,
        "blocker_counts_by_requirement": readiness_report["blocker_counts_by_requirement"],
        "live_scenarios": readiness_report["scenario_results"],
        "live_readiness_report_path": rel(out_dir / "live_readiness_report.json"),
        "live_opt_in_decisions_path": rel(out_dir / "live_opt_in_decisions.jsonl"),
        "live_manager_proposal_path": rel(out_dir / "live_manager_proposal.json"),
        "contract_report_path": rel(out_dir / "contract_report.json"),
        "contract_decisions_path": rel(out_dir / "contract_decisions.jsonl"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "artifacts": ALL_REQUIRED_ARTIFACTS + ["summary.md", "final_state.json", "raw.log"],
        "limitations": [
            "Proposal/readiness validation only; live reactive-manager execution is intentionally unavailable.",
            "Credential vault support is intentionally absent, so live_ready remains false.",
            "No tau2 lifecycle/task-state ownership is transferred to ActiveGraph.",
            "No state packets are fed back into tau2 execution.",
            "Fixture-backed local artifacts only; no model-backed benchmark episodes or LLM/API calls.",
        ],
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
    write_summary(out_dir, final_state)
    write(out_dir / "raw.log", "\n".join(log_lines + [f"state={final_state['state']}", f"vendor_status={vendor_status or 'clean'}"]) + "\n")

    print(out_dir)
    print(final_state["state"])
    return 0 if final_state["state"] == LIVE_OPT_IN_PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - write traceback artifact for unexpected smoke errors.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("live_manager_opt_in_contracts_error")
        raise
