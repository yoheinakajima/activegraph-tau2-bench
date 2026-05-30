#!/usr/bin/env python3
"""Phase 6 guarded reactive-manager execution contract smoke.

This command regenerates fixture-backed Phase 5 artifacts, builds representative
execution contract requests, and validates fail-closed safety gates. It never
imports or runs tau2 benchmark episodes, never controls tau2 lifecycle/task
state, never feeds packets back into tau2, and never calls LLM/API services.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import sys
import traceback
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.reactive_manager.contracts import (  # noqa: E402
    CONTRACT_REPORT_SCHEMA_VERSION,
    FAILED_STATUS,
    INPUTS_MISSING_STATUS,
    LIVE_CONTROL_MODE,
    PASS_STATUS,
    PLAN_ONLY_MODE,
    ReactiveManagerExecutionRequest,
    ReactiveManagerSafetyPolicy,
)
from experiments.reactive_manager.executor_contract import DisabledLiveExecutor, DryRunExecutor  # noqa: E402
from experiments.reactive_manager.planner import (  # noqa: E402
    build_diff_report,
    build_fork_plan,
    build_manager_decisions,
    build_manager_plan,
    build_replay_plan,
    load_json,
    load_jsonl,
    validate_activegraph_trace,
    validate_packet_chain,
    validate_plans_and_decisions,
    validate_trace_events,
    write_json,
    write_jsonl,
)
from experiments.state_packets.packets import EXPECTED_FIXTURE_PACKET_COUNT, STATE_PACKET_SCHEMA_VERSION  # noqa: E402
from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION  # noqa: E402
from scripts.run_reactive_manager_dry_run import emit_fixture_artifacts, git_vendor_status  # noqa: E402
from scripts.run_trace_smoke import NO_LLM_STATUS, RUNS_DIR, VENDOR_DIR, rel, write  # noqa: E402

COMMAND = "python scripts/run_reactive_manager_contracts.py"
TRACE_MODE = "fixture_backed_reactive_manager_execution_contracts_plan_only"
REQUIRED_ARTIFACTS = [
    "events.jsonl",
    "activegraph_trace.json",
    "state_packets.jsonl",
    "state_packet_index.json",
    "manager_plan.json",
    "manager_decisions.jsonl",
    "replay_plan.json",
    "fork_plan.json",
    "diff_report.json",
]


def build_phase5_artifacts(out_dir: pathlib.Path, run_id: str, timestamp: str, log_lines: list[str]) -> dict[str, Any]:
    generated = emit_fixture_artifacts(out_dir=out_dir, run_id=run_id, timestamp=timestamp, log_lines=log_lines)
    if not generated["ok"]:
        return generated

    missing = [name for name in REQUIRED_ARTIFACTS[:4] if not (out_dir / name).exists()]
    if missing:
        return {"ok": False, "state": INPUTS_MISSING_STATUS, "errors": [f"missing generated inputs: {missing}"]}

    events = load_jsonl(out_dir / "events.jsonl")
    activegraph_trace = load_json(out_dir / "activegraph_trace.json")
    state_packets = load_jsonl(out_dir / "state_packets.jsonl")
    state_packet_index = load_json(out_dir / "state_packet_index.json")

    trace_validation = validate_trace_events(events, expected_count=EXPECTED_FIXTURE_PACKET_COUNT)
    activegraph_validation = validate_activegraph_trace(activegraph_trace, events)
    packet_chain_validation = validate_packet_chain(state_packets, events, expected_count=EXPECTED_FIXTURE_PACKET_COUNT)
    replay_plan = build_replay_plan(events, state_packets, run_id=run_id)
    fork_plan = build_fork_plan(events, state_packets, run_id=run_id)
    diff_report = build_diff_report(events, state_packets, activegraph_trace, fork_plan, run_id=run_id)
    manager_decisions = build_manager_decisions(
        fork_plan,
        replay_plan,
        diff_report,
        run_id=run_id,
        timestamp=dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
    )
    manager_validation = validate_plans_and_decisions(
        replay_plan,
        fork_plan,
        diff_report,
        manager_decisions,
        events,
        state_packets,
        NO_LLM_STATUS,
    )
    combined_errors = trace_validation["errors"] + activegraph_validation["errors"] + packet_chain_validation["errors"] + manager_validation["errors"]
    combined_validation = {
        "ok": not combined_errors,
        "errors": combined_errors,
        "trace_events": trace_validation,
        "activegraph_trace": activegraph_validation,
        "state_packet_chain": packet_chain_validation,
        "manager_plan": manager_validation,
        "all_decisions_dry_run_unexecuted": manager_validation["all_decisions_dry_run_unexecuted"],
        "no_tau2_control_claimed": manager_validation["no_live_tau2_episode_validated"],
        "no_llm_api_calls_validated": manager_validation["no_llm_api_calls_validated"],
    }
    manager_plan = build_manager_plan(
        run_id=run_id,
        validation=combined_validation,
        replay_plan=replay_plan,
        fork_plan=fork_plan,
        diff_report=diff_report,
        decision_count=len(manager_decisions),
    )
    write_json(out_dir / "replay_plan.json", replay_plan)
    write_json(out_dir / "fork_plan.json", fork_plan)
    write_json(out_dir / "diff_report.json", diff_report)
    write_jsonl(out_dir / "manager_decisions.jsonl", manager_decisions)
    write_json(out_dir / "manager_plan.json", manager_plan)

    generated.update(
        {
            "ok": generated["ok"] and combined_validation["ok"],
            "state": "phase5_artifacts_ready" if combined_validation["ok"] else FAILED_STATUS,
            "errors": combined_errors,
            "events": events,
            "activegraph_trace": activegraph_trace,
            "state_packets": state_packets,
            "state_packet_index": state_packet_index,
            "trace_validation": trace_validation,
            "activegraph_validation": activegraph_validation,
            "packet_chain_validation": packet_chain_validation,
            "manager_validation": manager_validation,
            "combined_validation": combined_validation,
            "replay_plan": replay_plan,
            "fork_plan": fork_plan,
            "diff_report": diff_report,
            "manager_decisions": manager_decisions,
            "manager_plan": manager_plan,
        }
    )
    return generated


def artifact_paths(out_dir: pathlib.Path) -> dict[str, str]:
    return {name: rel(out_dir / name) for name in REQUIRED_ARTIFACTS}


def base_provenance(generated: dict[str, Any]) -> dict[str, Any]:
    return {
        "events": {"artifact": "events.jsonl", "count": len(generated["events"])},
        "activegraph_trace": {"artifact": "activegraph_trace.json", "counts": generated["activegraph_trace"].get("counts", {})},
        "state_packets": {"artifact": "state_packets.jsonl", "count": len(generated["state_packets"])},
        "state_packet_index": {"artifact": "state_packet_index.json", "validation": generated["state_packet_index"].get("validation", {})},
        "manager_plan": {"artifact": "manager_plan.json", "counts": generated["manager_plan"].get("counts", {})},
        "replay_plan": {"artifact": "replay_plan.json", "step_count": generated["replay_plan"].get("step_count")},
        "fork_plan": {"artifact": "fork_plan.json", "fork_point_count": generated["fork_plan"].get("fork_point_count")},
        "diff_report": {"artifact": "diff_report.json", "comparison_count": generated["diff_report"].get("comparison_count")},
        "no_llm_status": copy.deepcopy(NO_LLM_STATUS),
    }


def build_requests(out_dir: pathlib.Path, run_id: str, generated: dict[str, Any]) -> list[ReactiveManagerExecutionRequest]:
    paths = artifact_paths(out_dir)
    validation = copy.deepcopy(generated["combined_validation"])
    provenance = base_provenance(generated)
    safe_payload = {
        "controls_tau2_execution": False,
        "feeds_packets_back_into_tau2": False,
        "model_backed_episode_execution": False,
        "calls_llm_or_api_services": False,
        "requested_boundary": "contract_validation_only",
    }

    requests = [
        ReactiveManagerExecutionRequest(
            request_id="contract-request-000001",
            scenario="valid_dry_run_request",
            run_id=run_id,
            execution_mode=PLAN_ONLY_MODE,
            dry_run=True,
            explicit_opt_in=True,
            operator_acknowledgment="phase6_plan_only_no_live_execution",
            requested_action="validate plan-only reactive-manager contract",
            artifact_paths=copy.deepcopy(paths),
            provenance=copy.deepcopy(provenance),
            validation=copy.deepcopy(validation),
            payload=copy.deepcopy(safe_payload),
        ),
        ReactiveManagerExecutionRequest(
            request_id="contract-request-000002",
            scenario="invalid_live_control_request",
            run_id=run_id,
            execution_mode=LIVE_CONTROL_MODE,
            dry_run=False,
            explicit_opt_in=True,
            operator_acknowledgment="future_live_control_requested",
            requested_action="attempt live tau2 control",
            artifact_paths=copy.deepcopy(paths),
            provenance=copy.deepcopy(provenance),
            validation=copy.deepcopy(validation),
            payload={**safe_payload, "controls_tau2_execution": True},
        ),
        ReactiveManagerExecutionRequest(
            request_id="contract-request-000003",
            scenario="invalid_missing_provenance",
            run_id=run_id,
            execution_mode=PLAN_ONLY_MODE,
            dry_run=True,
            explicit_opt_in=True,
            operator_acknowledgment="phase6_plan_only_no_live_execution",
            requested_action="validate request without complete provenance",
            artifact_paths=copy.deepcopy(paths),
            provenance={"no_llm_status": copy.deepcopy(NO_LLM_STATUS)},
            validation=copy.deepcopy(validation),
            payload=copy.deepcopy(safe_payload),
        ),
        ReactiveManagerExecutionRequest(
            request_id="contract-request-000004",
            scenario="invalid_packet_hash_chain",
            run_id=run_id,
            execution_mode=PLAN_ONLY_MODE,
            dry_run=True,
            explicit_opt_in=True,
            operator_acknowledgment="phase6_plan_only_no_live_execution",
            requested_action="validate request with simulated packet validation failure",
            artifact_paths=copy.deepcopy(paths),
            provenance=copy.deepcopy(provenance),
            validation=_with_broken_packet_validation(validation),
            payload=copy.deepcopy(safe_payload),
        ),
        ReactiveManagerExecutionRequest(
            request_id="contract-request-000005",
            scenario="invalid_secret_payload",
            run_id=run_id,
            execution_mode=PLAN_ONLY_MODE,
            dry_run=True,
            explicit_opt_in=True,
            operator_acknowledgment="phase6_plan_only_no_live_execution",
            requested_action="validate request with forbidden secret-like payload",
            artifact_paths=copy.deepcopy(paths),
            provenance=copy.deepcopy(provenance),
            validation=copy.deepcopy(validation),
            payload={**safe_payload, "api_key": "sk-phase6-contract-test-secret"},
        ),
    ]
    return requests


def _with_broken_packet_validation(validation: dict[str, Any]) -> dict[str, Any]:
    broken = copy.deepcopy(validation)
    broken["ok"] = False
    broken.setdefault("errors", []).append("simulated state packet hash-chain validation failure")
    broken.setdefault("state_packet_chain", {})["ok"] = False
    broken.setdefault("state_packet_chain", {})["hash_chain_valid"] = False
    broken.setdefault("state_packet_chain", {}).setdefault("errors", []).append("simulated packet_hash mismatch")
    return broken


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    scenarios = "\n".join(
        f"- `{item['scenario']}`: `{item['status']}` accepted={item['accepted']} executed={item['executed']}" for item in final_state["contract_scenarios"]
    )
    artifacts = "\n".join(f"- `{artifact}`" for artifact in final_state["artifacts"])
    content = f"""# tau2-bench Phase 6 reactive-manager execution contracts

Status: `{final_state['state']}`

Run directory: `{final_state['output_dir']}`

## Contract results

- accepted decisions: {final_state['accepted_decision_count']}
- rejected decisions: {final_state['rejected_decision_count']}
- live execution available: `{final_state['live_execution_available']}`
- tau2 control flow executed: `{final_state['tau2_control_flow_executed']}`
- LLM/API calls made: `{final_state['llm_api_calls_made']}`

## Scenarios

{scenarios}

## Artifacts

{artifacts}

## Boundary

Phase 6 is a contract and safety-gate smoke only. Live reactive-manager execution is unavailable and every non-dry-run or live-control request is refused closed.
"""
    write(out_dir / "summary.md", content)


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"reactive-manager-contracts-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 6 reactive-manager execution contract smoke",
        f"timestamp_utc={timestamp}",
        f"command={COMMAND}",
        "boundary=contracts and fail-closed stubs only; no live manager; no tau2 control; no tau2 run; no paid LLM APIs",
    ]

    generated = build_phase5_artifacts(out_dir, run_id, timestamp, log_lines)
    if not generated["ok"]:
        final_state = {
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "state": generated.get("state", INPUTS_MISSING_STATUS),
            "errors": generated.get("errors", []),
            "command": COMMAND,
            "output_dir": rel(out_dir),
            "no_llm_status": NO_LLM_STATUS,
            "artifacts": ["final_state.json", "raw.log", "summary.md"],
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
        write(out_dir / "raw.log", "\n".join(log_lines + final_state["errors"]) + "\n")
        print(out_dir)
        print(final_state["state"])
        return 1

    missing = [name for name in REQUIRED_ARTIFACTS if not (out_dir / name).exists()]
    policy = ReactiveManagerSafetyPolicy()
    requests = build_requests(out_dir, run_id, generated)
    dry_executor = DryRunExecutor(policy=policy, repo_root=REPO_ROOT)
    disabled_live_executor = DisabledLiveExecutor(policy=policy, repo_root=REPO_ROOT)
    decisions = []
    for index, request in enumerate(requests, start=1):
        executor = dry_executor if request.dry_run and request.execution_mode == PLAN_ONLY_MODE else disabled_live_executor
        decision = executor.decide(request, decision_id=f"contract-decision-{index:06d}")
        decisions.append(decision.to_json_dict())
        log_lines.append(f"[CONTRACT] {decision.decision_id} scenario={request.scenario} status={decision.status} accepted={decision.accepted} executed={decision.executed}")

    write_jsonl(out_dir / "contract_decisions.jsonl", decisions)
    accepted_count = sum(1 for decision in decisions if decision["accepted"])
    rejected_count = sum(1 for decision in decisions if not decision["accepted"])
    scenario_status = {decision["scenario"]: decision for decision in decisions}
    expected_contracts_ok = (
        accepted_count == 1
        and rejected_count == 4
        and scenario_status["valid_dry_run_request"]["accepted"] is True
        and all(not scenario_status[name]["accepted"] for name in scenario_status if name != "valid_dry_run_request")
        and all(decision["executed"] is False for decision in decisions)
        and not missing
    )
    vendor_status = git_vendor_status()
    contract_report = {
        "schema_version": CONTRACT_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "status": PASS_STATUS if expected_contracts_ok and not vendor_status else FAILED_STATUS,
        "policy": policy.to_json_dict(),
        "scenario_count": len(decisions),
        "accepted_decision_count": accepted_count,
        "rejected_decision_count": rejected_count,
        "scenarios": decisions,
        "required_artifacts": {name: rel(out_dir / name) for name in REQUIRED_ARTIFACTS},
        "missing_required_artifacts": missing,
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "live_execution_available": False,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
    }
    write_json(out_dir / "contract_report.json", contract_report)

    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": contract_report["status"],
        "schema_version": SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "event_schema_fields": EVENT_FIELDS,
        "trace_mode": TRACE_MODE,
        "vendor_dir": rel(VENDOR_DIR),
        "command": COMMAND,
        "output_dir": rel(out_dir),
        "event_count": len(generated["events"]),
        "state_packet_count": len(generated["state_packets"]),
        "replay_step_count": generated["replay_plan"].get("step_count"),
        "fork_point_count": generated["fork_plan"].get("fork_point_count"),
        "diff_comparison_count": generated["diff_report"].get("comparison_count"),
        "manager_decision_count": len(generated["manager_decisions"]),
        "contract_decision_count": len(decisions),
        "accepted_decision_count": accepted_count,
        "rejected_decision_count": rejected_count,
        "contract_scenarios": [
            {
                "scenario": decision["scenario"],
                "status": decision["status"],
                "accepted": decision["accepted"],
                "executed": decision["executed"],
                "refusal_reasons": decision["refusal_reasons"],
            }
            for decision in decisions
        ],
        "no_llm_status": NO_LLM_STATUS,
        "live_execution_available": False,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "contract_report_path": rel(out_dir / "contract_report.json"),
        "contract_decisions_path": rel(out_dir / "contract_decisions.jsonl"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "artifacts": REQUIRED_ARTIFACTS + ["contract_decisions.jsonl", "contract_report.json", "summary.md", "final_state.json", "raw.log"],
        "limitations": [
            "Contracts and fail-closed stubs only; live reactive-manager execution is intentionally unavailable.",
            "No tau2 lifecycle, task-state, replay, fork, or diff execution is implemented.",
            "State packets remain observational and are not fed back into tau2.",
            "Fixture-backed local artifacts only; no model-backed benchmark episodes or LLM/API calls.",
        ],
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
    write_summary(out_dir, final_state)
    write(out_dir / "raw.log", "\n".join(log_lines + [f"state={final_state['state']}", f"vendor_status={vendor_status or 'clean'}"]) + "\n")

    print(out_dir)
    print(final_state["state"])
    return 0 if final_state["state"] == PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - write traceback artifact for unexpected smoke errors.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("reactive_manager_contracts_error")
        raise
