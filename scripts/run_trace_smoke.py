#!/usr/bin/env python3
"""Phase 2 trace-only no-LLM smoke harness for the local tau2-bench vendor tree.

This command does not import tau2, run tau2 episodes, instantiate LLM agents, or
call paid APIs. It uses local source inspection plus a deterministic fixture to
prove the repository-owned JSONL event schema and artifact pipeline.
"""
from __future__ import annotations

import ast
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

from experiments.trace_only.fixtures import (  # noqa: E402
    FINAL_FIXTURE_STATE,
    FIXTURE_COMMAND,
    FIXTURE_DOMAIN,
    FIXTURE_SOURCE_PATHS,
    FIXTURE_TASK_ID,
    FIXTURE_TRANSCRIPT,
    INITIAL_FIXTURE_STATE,
)
from experiments.trace_only.schema import EVENT_FIELDS, SCHEMA_VERSION, state_hash  # noqa: E402
from experiments.trace_only.writer import TraceWriter  # noqa: E402

VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
UPSTREAM_COMMIT_FILE = REPO_ROOT / "vendor" / "tau2-bench.UPSTREAM_COMMIT"
RUNS_DIR = REPO_ROOT / "runs"
EXPECTED_UPSTREAM_COMMIT = "fcc9ed68df33c93ff0b8c946865f267d7c99fb06"
NO_LLM_STATUS = {
    "llm_api_calls": False,
    "requires_api_keys": False,
    "paid_llm_apis_called": False,
    "real_tau2_episode_run": False,
    "fixture_backed": True,
}
SYMBOL_CHECKS = {
    "cli": ["add_run_args", "main"],
    "runner_batch": ["run_domain", "run_single_task", "run_tasks"],
    "runner_simulation": ["run_simulation"],
    "orchestrator": ["BaseOrchestrator", "Orchestrator"],
    "environment": ["Environment"],
    "evaluator": ["evaluate_simulation"],
    "results": ["SimulationRun", "Results", "RewardInfo"],
}


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001 - provenance is best-effort in archives.
        return None
    return result.stdout.strip() or None


def inspect_source_symbols(log_lines: list[str]) -> tuple[list[dict[str, Any]], bool]:
    checks: list[dict[str, Any]] = []
    all_ok = True
    for component, source_path in FIXTURE_SOURCE_PATHS.items():
        path = REPO_ROOT / source_path
        required = SYMBOL_CHECKS.get(component, [])
        check: dict[str, Any] = {
            "component": component,
            "path": source_path,
            "required_symbols": required,
            "exists": path.exists(),
            "ok": False,
        }
        if not path.exists():
            check["missing_symbols"] = required
            all_ok = False
            log_lines.append(f"[FAIL] source path missing component={component} path={source_path}")
            checks.append(check)
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            found = {
                node.name
                for node in tree.body
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            }
            missing = sorted(set(required) - found)
            check.update(
                {
                    "found_symbols": sorted(found & set(required)),
                    "missing_symbols": missing,
                    "ok": not missing,
                }
            )
            all_ok = all_ok and not missing
            status = "PASS" if not missing else "FAIL"
            log_lines.append(
                f"[{status}] source symbols component={component} path={source_path} missing={missing}"
            )
        except Exception as exc:  # noqa: BLE001 - smoke failures should be captured.
            check["error"] = str(exc)
            all_ok = False
            log_lines.append(
                f"[FAIL] source parse component={component} path={source_path} error={exc!r}"
            )
        checks.append(check)
    return checks, all_ok


def load_upstream_commit() -> str:
    if not UPSTREAM_COMMIT_FILE.exists():
        return ""
    return UPSTREAM_COMMIT_FILE.read_text(encoding="utf-8").strip()


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    emitted_types = "\n".join(
        f"- `{event_type}`" for event_type in final_state["event_types_emitted"]
    )
    source_lines = "\n".join(
        f"- `{check['component']}`: `{check['path']}` (`ok={check['ok']}`)"
        for check in final_state["source_symbol_checks"]
    )
    content = f"""# tau2-bench Phase 2 trace-only smoke summary

- Timestamp (UTC): `{final_state['timestamp_utc']}`
- Run ID: `{final_state['run_id']}`
- Final state: `{final_state['state']}`
- Trace mode: `fixture_backed_baseline_trace_only`
- Real tau2 episode run: `{final_state['no_llm_status']['real_tau2_episode_run']}`
- LLM/API calls used: `{final_state['no_llm_status']['llm_api_calls']}`
- API keys required: `{final_state['no_llm_status']['requires_api_keys']}`
- Paid LLM APIs called: `{final_state['no_llm_status']['paid_llm_apis_called']}`
- Events written: `{final_state['event_count']}`
- Output directory: `{final_state['output_dir']}`

## Boundary

This Phase 2 smoke run is trace-only. It does not integrate ActiveGraph, create
state packets, implement reactive manager behavior, mutate tau2-bench behavior,
run `tau2 run`, import `tau2`, instantiate model-backed agents, or call external
LLM APIs. It validates local tau2 source hook candidates by AST inspection and
emits deterministic fixture-backed lifecycle events to prove the JSONL logging
pipeline.

## Artifacts

- `events.jsonl` - append-only trace events using schema `{SCHEMA_VERSION}`
- `final_state.json` - machine-readable smoke result and provenance
- `summary.md` - this human-readable summary
- `raw.log` - command/check log

## Source paths inspected

{source_lines}

## Event types emitted

{emitted_types}
"""
    write(out_dir / "summary.md", content)


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"trace-smoke-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines = [
        "tau2-bench Phase 2 trace-only no-LLM smoke",
        f"timestamp_utc={timestamp}",
        f"command={FIXTURE_COMMAND}",
        "boundary=no imports of tau2; no tau2 run; no API keys; no paid LLM APIs",
    ]

    upstream_commit = load_upstream_commit()
    wrapper_commit = git_commit()
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
            "event_count": 0,
            "event_types_emitted": [],
            "source_symbol_checks": [],
        }
        write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
        write(out_dir / "raw.log", "\n".join(log_lines + ["[FAIL] upstream vendor missing or wrong commit"]) + "\n")
        write_summary(out_dir, final_state)
        print(out_dir)
        print(state)
        return 1

    source_checks, source_ok = inspect_source_symbols(log_lines)
    writer = TraceWriter(out_dir / "events.jsonl", run_id=run_id)
    event_types: list[str] = []

    def emit(**kwargs: Any) -> str:
        event = writer.emit(**kwargs)
        event_types.append(event.event_type)
        log_lines.append(
            f"[EVENT] {event.event_id} component={event.component} type={event.event_type}"
        )
        return event.event_id

    root_event_id = emit(
        component="runner",
        event_type="run.started",
        payload={
            "schema_version": SCHEMA_VERSION,
            "command": FIXTURE_COMMAND,
            "tau2_upstream_commit": upstream_commit,
            "wrapper_repo_commit": wrapper_commit,
            "no_llm_status": NO_LLM_STATUS,
            "trace_mode": "fixture_backed_baseline_trace_only",
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
        payload={"trial_index": 0, "seed": 300, "source_path": FIXTURE_SOURCE_PATHS["runner_simulation"]},
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
    emit(
        component="results",
        event_type="results.persisted",
        task_id=FIXTURE_TASK_ID,
        payload={
            "source_path": FIXTURE_SOURCE_PATHS["results"],
            "artifacts": ["events.jsonl", "summary.md", "final_state.json", "raw.log"],
        },
        parent_event_id=eval_event_id,
    )
    emit(
        component="runner",
        event_type="run.completed",
        payload={"state": "trace_smoke_passed" if source_ok else "source_inspection_failed"},
        parent_event_id=root_event_id,
    )

    state = "trace_smoke_passed" if source_ok else "source_inspection_failed"
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": state,
        "schema_version": SCHEMA_VERSION,
        "event_schema_fields": EVENT_FIELDS,
        "event_count": len(event_types),
        "event_types_emitted": event_types,
        "task_id": FIXTURE_TASK_ID,
        "trace_mode": "fixture_backed_baseline_trace_only",
        "vendor_dir": rel(VENDOR_DIR),
        "tau2_upstream_commit": upstream_commit,
        "wrapper_repo_commit": wrapper_commit,
        "command": FIXTURE_COMMAND,
        "output_dir": rel(out_dir),
        "events_path": rel(out_dir / "events.jsonl"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "no_llm_status": NO_LLM_STATUS,
        "initial_state_hash": initial_hash,
        "final_state_hash": final_hash,
        "source_symbol_checks": source_checks,
        "limitations": [
            "Fixture-backed trace only; no real tau2 episode was executed.",
            "No ActiveGraph integration, state packets, or reactive manager behavior.",
            "No tau2 behavior mutation and no imports from the vendored tau2 package.",
        ],
    }
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")
    write_summary(out_dir, final_state)
    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")

    print(out_dir)
    print(state)
    return 0 if state == "trace_smoke_passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - preserve traceback in generated artifacts when possible.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("trace_smoke_error")
        raise
