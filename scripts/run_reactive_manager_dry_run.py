#!/usr/bin/env python3
"""Phase 5 dry-run-only reactive-manager replay planning smoke.

This command generates the same fixture-backed Phase 4 trace/graph/packet
artifacts, then reads them back to compute replay, fork, and diff plans. The
manager is explicitly observational and plan-only: it never imports tau2, never
runs a tau2 benchmark episode, never controls lifecycle/task state, never feeds
packets back into execution, and never calls LLM/API services.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys
import traceback
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.activegraph_trace.store import UNAVAILABLE_STATUS, build_trace_store, status_for_store  # noqa: E402
from experiments.reactive_manager.planner import (  # noqa: E402
    INPUTS_MISSING_STATUS,
    PASS_STATUS,
    VALIDATION_FAILED_STATUS,
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
from experiments.state_packets.packets import (  # noqa: E402
    EXPECTED_FIXTURE_PACKET_COUNT,
    STATE_PACKET_SCHEMA_VERSION,
    build_packet_index,
    build_state_packets,
    validate_state_packets,
    write_jsonl as write_packet_jsonl,
)
from experiments.trace_only.fixtures import (  # noqa: E402
    FINAL_FIXTURE_STATE,
    FIXTURE_DOMAIN,
    FIXTURE_SOURCE_PATHS,
    FIXTURE_TASK_ID,
    FIXTURE_TRANSCRIPT,
    INITIAL_FIXTURE_STATE,
)
from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION, state_hash  # noqa: E402
from experiments.trace_only.writer import TraceWriter  # noqa: E402
from scripts.run_trace_smoke import (  # noqa: E402
    EXPECTED_UPSTREAM_COMMIT,
    NO_LLM_STATUS,
    RUNS_DIR,
    SYMBOL_CHECKS,
    VENDOR_DIR,
    git_commit,
    inspect_source_symbols,
    load_upstream_commit,
    rel,
    write,
)

COMMAND = "python scripts/run_reactive_manager_dry_run.py"
TRACE_MODE = "fixture_backed_reactive_manager_dry_run_plan_only"


def git_vendor_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--", "vendor/tau2-bench"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def emit_fixture_artifacts(
    *,
    out_dir: pathlib.Path,
    run_id: str,
    timestamp: str,
    log_lines: list[str],
) -> dict[str, Any]:
    upstream_commit = load_upstream_commit()
    wrapper_commit = git_commit()
    store = build_trace_store()
    activegraph_availability_status = "activegraph_runtime_importable" if store.runtime_available else UNAVAILABLE_STATUS
    log_lines.append(
        f"activegraph_adapter mode={store.adapter_mode} runtime_available={store.runtime_available} runtime_module={store.runtime_module}"
    )

    if not VENDOR_DIR.exists() or upstream_commit != EXPECTED_UPSTREAM_COMMIT:
        return {
            "ok": False,
            "state": INPUTS_MISSING_STATUS,
            "errors": ["upstream vendor missing or wrong commit"],
            "upstream_commit": upstream_commit,
            "wrapper_commit": wrapper_commit,
            "activegraph_adapter": {
                "mode": store.adapter_mode,
                "runtime_available": store.runtime_available,
                "runtime_module": store.runtime_module,
            },
            "activegraph_availability_status": activegraph_availability_status,
        }

    source_checks, source_ok = inspect_source_symbols(log_lines)
    writer = TraceWriter(out_dir / "events.jsonl", run_id=run_id)
    events: list[dict[str, Any]] = []
    event_types: list[str] = []

    def emit(**kwargs: Any) -> str:
        event = writer.emit(**kwargs)
        store.ingest(event)
        event_dict = event.to_json_dict()
        events.append(event_dict)
        event_types.append(event.event_type)
        log_lines.append(f"[EVENT] {event.event_id} component={event.component} type={event.event_type} activegraph_ingested=true")
        return event.event_id

    root_event_id = emit(
        component="runner",
        event_type="run.started",
        payload={
            "schema_version": SCHEMA_VERSION,
            "command": COMMAND,
            "tau2_upstream_commit": upstream_commit,
            "wrapper_repo_commit": wrapper_commit,
            "no_llm_status": NO_LLM_STATUS,
            "trace_mode": TRACE_MODE,
            "activegraph": {
                "adapter_mode": store.adapter_mode,
                "runtime_available": store.runtime_available,
                "runtime_module": store.runtime_module,
                "availability_status": activegraph_availability_status,
                "trace_only": True,
                "state_packets_enabled": True,
                "state_packets_observational_only": True,
                "reactive_manager_enabled": False,
                "reactive_manager_dry_run_plan_only": True,
                "controls_tau2_execution": False,
            },
        },
    )
    cli_event_id = emit(
        component="cli",
        event_type="cli.config_inspected",
        payload={"source_path": FIXTURE_SOURCE_PATHS["cli"], "symbols_checked": SYMBOL_CHECKS["cli"], "domain": FIXTURE_DOMAIN, "max_steps": len(FIXTURE_TRANSCRIPT)},
        parent_event_id=root_event_id,
    )
    batch_event_id = emit(
        component="runner.batch",
        event_type="batch.started",
        payload={"source_path": FIXTURE_SOURCE_PATHS["runner_batch"], "domain": FIXTURE_DOMAIN, "num_tasks": 1, "fixture_backed": True},
        parent_event_id=cli_event_id,
    )
    task_event_id = emit(
        component="runner.batch",
        event_type="task.started",
        task_id=FIXTURE_TASK_ID,
        payload={"trial_index": 0, "seed": 300, "source_path": FIXTURE_SOURCE_PATHS["runner_simulation"]},
        parent_event_id=batch_event_id,
    )
    initial_hash = state_hash(INITIAL_FIXTURE_STATE)
    orchestrator_event_id = emit(
        component="orchestrator",
        event_type="orchestrator.initialized",
        task_id=FIXTURE_TASK_ID,
        state_hash=initial_hash,
        payload={"source_path": FIXTURE_SOURCE_PATHS["orchestrator"], "initial_state_summary": "fixture state only; no tau2 state mutated"},
        parent_event_id=task_event_id,
    )
    emit(
        component="environment",
        event_type="state.snapshot",
        task_id=FIXTURE_TASK_ID,
        state_hash=initial_hash,
        payload={"snapshot_name": "initial", "state": INITIAL_FIXTURE_STATE},
        parent_event_id=orchestrator_event_id,
    )

    latest_parent = orchestrator_event_id
    for turn in FIXTURE_TRANSCRIPT:
        turn_event_id = emit(
            component="orchestrator",
            event_type="turn.started",
            task_id=FIXTURE_TASK_ID,
            turn_index=turn["turn_index"],
            message_role=turn["role"],
            payload={"content_summary": turn["content_summary"]},
            parent_event_id=latest_parent,
        )
        emit(
            component="message",
            event_type="message.observed",
            task_id=FIXTURE_TASK_ID,
            turn_index=turn["turn_index"],
            message_role=turn["role"],
            payload={"content_summary": turn["content_summary"], "content_redacted": True},
            parent_event_id=turn_event_id,
        )
        if "tool_call" in turn:
            tool_call = turn["tool_call"]
            tool_request_id = emit(
                component="environment",
                event_type="tool.dispatch_requested",
                task_id=FIXTURE_TASK_ID,
                turn_index=turn["turn_index"],
                tool_name=tool_call["name"],
                payload={"source_path": FIXTURE_SOURCE_PATHS["environment"], "arguments": tool_call["arguments"]},
                parent_event_id=turn_event_id,
            )
            emit(
                component="environment",
                event_type="tool.dispatch_completed",
                task_id=FIXTURE_TASK_ID,
                turn_index=turn["turn_index"],
                tool_name=tool_call["name"],
                payload={"result_summary": tool_call["result"], "fixture_backed": True},
                parent_event_id=tool_request_id,
            )
        latest_parent = turn_event_id

    final_hash = state_hash(FINAL_FIXTURE_STATE)
    emit(
        component="environment",
        event_type="state.snapshot",
        task_id=FIXTURE_TASK_ID,
        state_hash=final_hash,
        payload={"snapshot_name": "final", "state": FINAL_FIXTURE_STATE},
        parent_event_id=latest_parent,
    )
    eval_event_id = emit(
        component="evaluator",
        event_type="evaluation.completed",
        task_id=FIXTURE_TASK_ID,
        state_hash=final_hash,
        payload={"source_path": FIXTURE_SOURCE_PATHS["evaluator"], "reward": 1.0, "evaluation_mode": "fixture_no_llm"},
        parent_event_id=latest_parent,
    )
    results_event_id = emit(
        component="results",
        event_type="results.persisted",
        task_id=FIXTURE_TASK_ID,
        payload={
            "source_path": FIXTURE_SOURCE_PATHS["results"],
            "artifacts": [
                "events.jsonl",
                "activegraph_trace.json",
                "state_packets.jsonl",
                "state_packet_index.json",
                "manager_plan.json",
                "manager_decisions.jsonl",
                "replay_plan.json",
                "fork_plan.json",
                "diff_report.json",
                "summary.md",
                "final_state.json",
                "raw.log",
            ],
        },
        parent_event_id=eval_event_id,
    )
    activegraph_state = status_for_store(store) if source_ok else "source_inspection_failed"
    emit(
        component="runner",
        event_type="run.completed",
        payload={
            "state": activegraph_state,
            "phase_5_state": PASS_STATUS if source_ok else "source_inspection_failed",
            "activegraph_adapter_mode": store.adapter_mode,
            "activegraph_runtime_available": store.runtime_available,
            "state_packets_observational_only": True,
            "reactive_manager_enabled": False,
            "reactive_manager_dry_run_plan_only": True,
            "controls_tau2_execution": False,
            "results_event_id": results_event_id,
        },
        parent_event_id=root_event_id,
    )

    provenance = {
        "tau2_upstream_commit": upstream_commit,
        "wrapper_repo_commit": wrapper_commit,
        "command": COMMAND,
        "run_id": run_id,
        "trace_mode": TRACE_MODE,
        "activegraph_adapter_mode": store.adapter_mode,
        "activegraph_runtime_available": store.runtime_available,
        "activegraph_runtime_module": store.runtime_module,
        "activegraph_availability_status": activegraph_availability_status,
        "no_llm_status": NO_LLM_STATUS,
    }
    activegraph_export = store.export(provenance=provenance)
    write(out_dir / "activegraph_trace.json", json.dumps(activegraph_export, indent=2) + "\n")
    state_packets = build_state_packets(
        events,
        activegraph_trace=activegraph_export,
        tau2_upstream_commit=upstream_commit,
        wrapper_repo_commit=wrapper_commit,
        command=COMMAND,
        no_llm_status=NO_LLM_STATUS,
    )
    state_packet_validation = validate_state_packets(
        state_packets,
        events=events,
        activegraph_trace=activegraph_export,
        tau2_upstream_commit=upstream_commit,
        wrapper_repo_commit=wrapper_commit,
        no_llm_status=NO_LLM_STATUS,
        expected_packet_count=EXPECTED_FIXTURE_PACKET_COUNT,
    )
    packet_index = build_packet_index(
        state_packets,
        validation=state_packet_validation,
        activegraph_trace_path=rel(out_dir / "activegraph_trace.json"),
        events_path=rel(out_dir / "events.jsonl"),
    )
    write_packet_jsonl(out_dir / "state_packets.jsonl", state_packets)
    write(out_dir / "state_packet_index.json", json.dumps(packet_index, indent=2) + "\n")
    return {
        "ok": source_ok and state_packet_validation["ok"],
        "state": "fixture_artifacts_ready" if source_ok and state_packet_validation["ok"] else VALIDATION_FAILED_STATUS,
        "errors": [] if source_ok else ["source inspection failed"],
        "events": events,
        "activegraph_trace": activegraph_export,
        "state_packets": state_packets,
        "state_packet_index": packet_index,
        "state_packet_validation": state_packet_validation,
        "event_types": event_types,
        "source_checks": source_checks,
        "activegraph_trace_status": activegraph_state,
        "activegraph_adapter": activegraph_export["adapter"],
        "activegraph_availability_status": activegraph_availability_status,
        "activegraph_counts": activegraph_export["counts"],
        "initial_state_hash": initial_hash,
        "final_state_hash": final_hash,
        "upstream_commit": upstream_commit,
        "wrapper_commit": wrapper_commit,
    }


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    artifact_lines = "\n".join(f"- `{artifact}`" for artifact in final_state["artifacts"])
    replay = final_state["replay_plan_summary"]
    fork = final_state["fork_plan_summary"]
    diff = final_state["diff_report_summary"]
    content = f"""# tau2-bench Phase 5 reactive-manager dry-run summary

- Timestamp (UTC): `{final_state['timestamp_utc']}`
- Run ID: `{final_state['run_id']}`
- Final state: `{final_state['state']}`
- Trace mode: `{final_state['trace_mode']}`
- Events written: `{final_state['event_count']}`
- State packets written: `{final_state['state_packet_count']}`
- Manager decisions written: `{final_state['manager_decision_count']}`
- Replay steps planned: `{replay['step_count']}`
- Fork points planned: `{fork['fork_point_count']}`
- Diff comparisons planned: `{diff['comparison_count']}`
- Dry-run decisions valid: `{final_state['manager_validation']['all_decisions_dry_run_unexecuted']}`
- Real tau2 episode run: `{final_state['no_llm_status']['real_tau2_episode_run']}`
- LLM/API calls used: `{final_state['no_llm_status']['llm_api_calls']}`
- Paid LLM APIs called: `{final_state['no_llm_status']['paid_llm_apis_called']}`
- Vendor tau2-bench modified: `{final_state['vendor_tau2_bench_modified']}`
- Output directory: `{final_state['output_dir']}`

## Boundary

This Phase 5 smoke is a dry-run-only planning prototype. It reads fixture-backed
`events.jsonl`, `activegraph_trace.json`, `state_packets.jsonl`, and
`state_packet_index.json` artifacts and writes replay, fork, diff, and manager
decision plans. It does not execute replay/fork steps, does not let ActiveGraph
control tau2 lifecycle or task state, does not feed packets back into tau2, does
not mutate the vendored tau2 tree, and does not call LLM/API services.

## Artifacts

{artifact_lines}

## Replay plan summary

- Steps: `{replay['step_count']}`
- First step: `{replay['first_step']}`
- Last step: `{replay['last_step']}`

## Fork plan summary

- Fork points: `{fork['fork_point_count']}`
- Fork point IDs: `{', '.join(fork['fork_point_ids'])}`

## Diff report summary

- Comparisons: `{diff['comparison_count']}`
- Deterministic report hash: `{diff['deterministic_report_hash']}`

## Validation

```json
{json.dumps(final_state['manager_validation'], indent=2)}
```
"""
    write(out_dir / "summary.md", content)


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"reactive-manager-dry-run-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 5 reactive-manager dry-run planning smoke",
        f"timestamp_utc={timestamp}",
        f"command={COMMAND}",
        "boundary=dry-run plan only; no live manager; no tau2 control; no tau2 run; no paid LLM APIs",
    ]

    generated = emit_fixture_artifacts(out_dir=out_dir, run_id=run_id, timestamp=timestamp, log_lines=log_lines)
    if not generated["ok"]:
        final_state = {
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "state": generated["state"],
            "errors": generated["errors"],
            "command": COMMAND,
            "output_dir": rel(out_dir),
            "no_llm_status": NO_LLM_STATUS,
            "artifacts": ["final_state.json", "raw.log", "summary.md"],
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
        write(out_dir / "raw.log", "\n".join(log_lines + generated["errors"]) + "\n")
        print(out_dir)
        print(generated["state"])
        return 1

    required = ["events.jsonl", "activegraph_trace.json", "state_packets.jsonl", "state_packet_index.json"]
    missing = [name for name in required if not (out_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"reactive manager inputs missing: {missing}")

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
    combined_errors = (
        trace_validation["errors"]
        + activegraph_validation["errors"]
        + packet_chain_validation["errors"]
        + manager_validation["errors"]
    )
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

    vendor_status = git_vendor_status()
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": PASS_STATUS if combined_validation["ok"] and not vendor_status else VALIDATION_FAILED_STATUS,
        "schema_version": SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "event_schema_fields": EVENT_FIELDS,
        "event_count": len(events),
        "event_types_emitted": [event["event_type"] for event in events],
        "task_id": FIXTURE_TASK_ID,
        "trace_mode": TRACE_MODE,
        "vendor_dir": rel(VENDOR_DIR),
        "tau2_upstream_commit": generated["upstream_commit"],
        "wrapper_repo_commit": generated["wrapper_commit"],
        "command": COMMAND,
        "output_dir": rel(out_dir),
        "events_path": rel(out_dir / "events.jsonl"),
        "activegraph_trace_path": rel(out_dir / "activegraph_trace.json"),
        "state_packets_path": rel(out_dir / "state_packets.jsonl"),
        "state_packet_index_path": rel(out_dir / "state_packet_index.json"),
        "manager_plan_path": rel(out_dir / "manager_plan.json"),
        "manager_decisions_path": rel(out_dir / "manager_decisions.jsonl"),
        "replay_plan_path": rel(out_dir / "replay_plan.json"),
        "fork_plan_path": rel(out_dir / "fork_plan.json"),
        "diff_report_path": rel(out_dir / "diff_report.json"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "no_llm_status": NO_LLM_STATUS,
        "activegraph_availability_status": generated["activegraph_availability_status"],
        "activegraph_adapter": generated["activegraph_adapter"],
        "activegraph_counts": generated["activegraph_counts"],
        "activegraph_trace_status": generated["activegraph_trace_status"],
        "initial_state_hash": generated["initial_state_hash"],
        "final_state_hash": generated["final_state_hash"],
        "state_packet_count": len(state_packets),
        "state_packet_validation": generated["state_packet_validation"],
        "state_packet_index_validation": state_packet_index.get("validation"),
        "manager_decision_count": len(manager_decisions),
        "manager_validation": combined_validation,
        "replay_plan_summary": {
            "step_count": replay_plan["step_count"],
            "first_step": replay_plan["steps"][0]["step_id"],
            "last_step": replay_plan["steps"][-1]["step_id"],
        },
        "fork_plan_summary": {
            "fork_point_count": fork_plan["fork_point_count"],
            "fork_point_ids": [point["fork_point_id"] for point in fork_plan["fork_points"]],
        },
        "diff_report_summary": {
            "comparison_count": diff_report["comparison_count"],
            "deterministic_report_hash": diff_report["deterministic_report_hash"],
        },
        "vendor_tau2_bench_modified": bool(vendor_status),
        "vendor_tau2_bench_status": vendor_status,
        "source_symbol_checks": generated["source_checks"],
        "artifacts": [
            "events.jsonl",
            "activegraph_trace.json",
            "state_packets.jsonl",
            "state_packet_index.json",
            "manager_plan.json",
            "manager_decisions.jsonl",
            "replay_plan.json",
            "fork_plan.json",
            "diff_report.json",
            "summary.md",
            "final_state.json",
            "raw.log",
        ],
        "limitations": [
            "Fixture-backed trace only; no real tau2 episode was executed.",
            "Reactive-manager behavior is dry-run, observational, and plan-only.",
            "Replay, fork, and diff artifacts are proposed plans, not executed operations.",
            "State packets are not fed back into tau2 execution or task state.",
            "No tau2 behavior mutation and no imports from the vendored tau2 package.",
        ],
    }
    if vendor_status:
        final_state["manager_validation"]["errors"].append("vendor/tau2-bench has modifications")
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
    write_summary(out_dir, final_state)
    write(out_dir / "raw.log", "\n".join(log_lines + [f"state={final_state['state']}", f"vendor_status={vendor_status or 'clean'}"]) + "\n")

    print(out_dir)
    print(final_state["state"])
    return 0 if final_state["state"] == PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - preserve traceback in generated artifacts when possible.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("reactive_manager_dry_run_error")
        raise
