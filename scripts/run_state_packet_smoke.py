#!/usr/bin/env python3
"""Phase 4 ActiveGraph state-packet no-LLM smoke harness.

This command derives deterministic, serialized state packets beside the Phase 3
ActiveGraph trace-only projection. Packets are observational artifacts only and
never control tau2 lifecycle, task state, tools, evaluation, or replay.
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

from experiments.activegraph_trace.store import (  # noqa: E402
    UNAVAILABLE_STATUS,
    build_trace_store,
    status_for_store,
)
from experiments.state_packets.packets import (  # noqa: E402
    EXPECTED_FIXTURE_PACKET_COUNT,
    STATE_PACKET_SCHEMA_VERSION,
    build_packet_index,
    build_state_packets,
    validate_state_packets,
    write_jsonl,
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

COMMAND = "python scripts/run_state_packet_smoke.py"
TRACE_MODE = "fixture_backed_activegraph_state_packet_observation_only"
PASS_STATUS = "state_packet_smoke_passed"


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    """Write a human-readable Phase 4 smoke summary."""
    artifact_lines = "\n".join(f"- `{artifact}`" for artifact in final_state["artifacts"])
    packet_type_lines = "\n".join(
        f"- `{packet_type}`: `{count}`"
        for packet_type, count in final_state["state_packet_validation"]["packet_types"].items()
    )
    validation = final_state["state_packet_validation"]
    content = f"""# tau2-bench Phase 4 ActiveGraph state-packet smoke summary

- Timestamp (UTC): `{final_state['timestamp_utc']}`
- Run ID: `{final_state['run_id']}`
- Final state: `{final_state['state']}`
- Trace mode: `{final_state['trace_mode']}`
- ActiveGraph adapter mode: `{final_state['activegraph_adapter']['mode']}`
- ActiveGraph runtime available: `{final_state['activegraph_adapter']['runtime_available']}`
- Real tau2 episode run: `{final_state['no_llm_status']['real_tau2_episode_run']}`
- LLM/API calls used: `{final_state['no_llm_status']['llm_api_calls']}`
- API keys required: `{final_state['no_llm_status']['requires_api_keys']}`
- Paid LLM APIs called: `{final_state['no_llm_status']['paid_llm_apis_called']}`
- Events written: `{final_state['event_count']}`
- State packets written: `{final_state['state_packet_count']}`
- Expected fixture packets: `{validation['expected_packet_count']}`
- Hash chain valid: `{validation['hash_chain_valid']}`
- Packet ordering valid: `{validation['ordering_valid']}`
- ActiveGraph projection preserved: `{validation['activegraph_projection_preserved']}`
- Output directory: `{final_state['output_dir']}`

## Boundary

This Phase 4 smoke run serializes state packets derived from the existing
`events.jsonl` TraceEvent stream and the preserved `activegraph_trace.json`
projection. The packets are explicit artifacts for later replay/fork/diff work.
They do **not** implement ActiveGraph reactive manager behavior, do not let
ActiveGraph control tau2 lifecycle or task state, do not mutate tau2-bench, do
not run `tau2 run`, and do not call paid LLM APIs.

## Artifacts

{artifact_lines}

## Packet types emitted

{packet_type_lines}

## Validation

```json
{json.dumps(validation, indent=2)}
```
"""
    write(out_dir / "summary.md", content)


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"state-packet-smoke-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines = [
        "tau2-bench Phase 4 ActiveGraph state-packet no-LLM smoke",
        f"timestamp_utc={timestamp}",
        f"command={COMMAND}",
        "boundary=serialized state packets only; no reactive manager; no tau2 control; no tau2 run; no paid LLM APIs",
    ]

    upstream_commit = load_upstream_commit()
    wrapper_commit = git_commit()
    store = build_trace_store()
    activegraph_availability_status = (
        "activegraph_runtime_importable" if store.runtime_available else UNAVAILABLE_STATUS
    )
    log_lines.append(
        f"activegraph_adapter mode={store.adapter_mode} runtime_available={store.runtime_available} runtime_module={store.runtime_module}"
    )

    if not VENDOR_DIR.exists() or upstream_commit != EXPECTED_UPSTREAM_COMMIT:
        state = "upstream_missing"
        final_state = {
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "state": state,
            "vendor_dir": rel(VENDOR_DIR),
            "expected_upstream_commit": EXPECTED_UPSTREAM_COMMIT,
            "actual_upstream_commit": upstream_commit,
            "output_dir": rel(out_dir),
            "no_llm_status": NO_LLM_STATUS,
            "activegraph_availability_status": activegraph_availability_status,
            "activegraph_adapter": {
                "mode": store.adapter_mode,
                "runtime_available": store.runtime_available,
                "runtime_module": store.runtime_module,
            },
            "event_count": 0,
            "state_packet_count": 0,
            "state_packet_validation": {"ok": False, "errors": ["upstream vendor missing or wrong commit"]},
            "artifacts": ["final_state.json", "raw.log", "summary.md"],
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
        write(
            out_dir / "raw.log",
            "\n".join(log_lines + ["[FAIL] upstream vendor missing or wrong commit"]) + "\n",
        )
        write_summary(out_dir, final_state)
        print(out_dir)
        print(state)
        return 1

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
        log_lines.append(
            f"[EVENT] {event.event_id} component={event.component} type={event.event_type} activegraph_ingested=true"
        )
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
                "controls_tau2_execution": False,
            },
        },
    )
    cli_event_id = emit(
        component="cli",
        event_type="cli.config_inspected",
        payload={
            "source_path": FIXTURE_SOURCE_PATHS["cli"],
            "symbols_checked": SYMBOL_CHECKS["cli"],
            "domain": FIXTURE_DOMAIN,
            "max_steps": len(FIXTURE_TRANSCRIPT),
        },
        parent_event_id=root_event_id,
    )
    batch_event_id = emit(
        component="runner.batch",
        event_type="batch.started",
        payload={
            "source_path": FIXTURE_SOURCE_PATHS["runner_batch"],
            "domain": FIXTURE_DOMAIN,
            "num_tasks": 1,
            "fixture_backed": True,
        },
        parent_event_id=cli_event_id,
    )
    task_event_id = emit(
        component="runner.batch",
        event_type="task.started",
        task_id=FIXTURE_TASK_ID,
        payload={
            "trial_index": 0,
            "seed": 300,
            "source_path": FIXTURE_SOURCE_PATHS["runner_simulation"],
        },
        parent_event_id=batch_event_id,
    )
    initial_hash = state_hash(INITIAL_FIXTURE_STATE)
    orchestrator_event_id = emit(
        component="orchestrator",
        event_type="orchestrator.initialized",
        task_id=FIXTURE_TASK_ID,
        state_hash=initial_hash,
        payload={
            "source_path": FIXTURE_SOURCE_PATHS["orchestrator"],
            "initial_state_summary": "fixture state only; no tau2 state mutated",
        },
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
                payload={
                    "source_path": FIXTURE_SOURCE_PATHS["environment"],
                    "arguments": tool_call["arguments"],
                },
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
        payload={
            "source_path": FIXTURE_SOURCE_PATHS["evaluator"],
            "reward": 1.0,
            "evaluation_mode": "fixture_no_llm",
        },
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
            "phase_4_state": PASS_STATUS if source_ok else "source_inspection_failed",
            "activegraph_adapter_mode": store.adapter_mode,
            "activegraph_runtime_available": store.runtime_available,
            "state_packets_observational_only": True,
            "reactive_manager_enabled": False,
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
    validation = validate_state_packets(
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
        validation=validation,
        activegraph_trace_path=rel(out_dir / "activegraph_trace.json"),
        events_path=rel(out_dir / "events.jsonl"),
    )
    write_jsonl(out_dir / "state_packets.jsonl", state_packets)
    write(out_dir / "state_packet_index.json", json.dumps(packet_index, indent=2) + "\n")

    state = PASS_STATUS if source_ok and validation["ok"] else "state_packet_smoke_failed"
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": state,
        "schema_version": SCHEMA_VERSION,
        "state_packet_schema_version": STATE_PACKET_SCHEMA_VERSION,
        "event_schema_fields": EVENT_FIELDS,
        "event_count": len(event_types),
        "event_types_emitted": event_types,
        "task_id": FIXTURE_TASK_ID,
        "trace_mode": TRACE_MODE,
        "vendor_dir": rel(VENDOR_DIR),
        "tau2_upstream_commit": upstream_commit,
        "wrapper_repo_commit": wrapper_commit,
        "command": COMMAND,
        "output_dir": rel(out_dir),
        "events_path": rel(out_dir / "events.jsonl"),
        "activegraph_trace_path": rel(out_dir / "activegraph_trace.json"),
        "state_packets_path": rel(out_dir / "state_packets.jsonl"),
        "state_packet_index_path": rel(out_dir / "state_packet_index.json"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "no_llm_status": NO_LLM_STATUS,
        "activegraph_availability_status": activegraph_availability_status,
        "activegraph_adapter": activegraph_export["adapter"],
        "activegraph_counts": activegraph_export["counts"],
        "activegraph_trace_status": activegraph_state,
        "initial_state_hash": initial_hash,
        "final_state_hash": final_hash,
        "state_packet_count": len(state_packets),
        "state_packet_validation": validation,
        "first_packet_hash": packet_index["first_packet_hash"],
        "last_packet_hash": packet_index["last_packet_hash"],
        "source_symbol_checks": source_checks,
        "artifacts": [
            "events.jsonl",
            "activegraph_trace.json",
            "state_packets.jsonl",
            "state_packet_index.json",
            "summary.md",
            "final_state.json",
            "raw.log",
        ],
        "limitations": [
            "Fixture-backed trace only; no real tau2 episode was executed.",
            "ActiveGraph is used only as append-only trace projection plus serialized state packets.",
            "State packets are derived artifacts and do not control tau2 execution or task state.",
            "No ActiveGraph reactive manager behavior is implemented.",
            "No tau2 behavior mutation and no imports from the vendored tau2 package.",
        ],
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
    write_summary(out_dir, final_state)
    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")

    print(out_dir)
    print(state)
    return 0 if state == PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - preserve traceback in generated artifacts when possible.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("state_packet_smoke_error")
        raise
