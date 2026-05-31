#!/usr/bin/env python3
"""No-LLM dry smoke for tau2 runtime trace instrumentation."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.tau2_runtime_trace.runtime_trace import (  # noqa: E402
    RuntimeTraceWriter,
    Tau2RuntimeTracer,
    inspect_hook_targets,
    stable_hash,
    write_final_state,
    write_hook_map,
    write_summary,
)

RUNS_DIR = REPO_ROOT / "runs"
PASSED_STATUS = "tau2_runtime_trace_smoke_passed"
SKIPPED_LIVE_STATUS = "tau2_runtime_trace_smoke_completed_with_skipped_live_hooks"
FAILED_STATUS = "tau2_runtime_trace_smoke_failed"


def timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = RUNS_DIR / timestamp()
    out_dir.mkdir(parents=True, exist_ok=False)
    raw_log = out_dir / "raw.log"
    writer = RuntimeTraceWriter(out_dir, phase="runtime_trace_smoke")
    status = PASSED_STATUS
    validated: list[str] = []
    deferred: list[str] = []
    inspected = {}
    try:
        with raw_log.open("w", encoding="utf-8") as log:
            log.write("tau2_runtime_trace_smoke_start\n")
            log.write("paid_llm_api_calls_made=false\n")
            log.write("tau2_control_flow_executed=false\n")
            inspected = inspect_hook_targets()
            log.write(f"inspected_hooks={len(inspected)}\n")
            with Tau2RuntimeTracer(writer) as tracer:
                validated = list(tracer.installed_hooks)
                deferred = list(tracer.deferred_hooks)
                writer.record(
                    component="tau2_runtime_trace.smoke",
                    event_type="dry_hook_patch_context_entered",
                    state_hash=stable_hash({"validated": validated, "deferred": deferred}),
                    payload={
                        "mode": "no_llm_dry_validation",
                        "structurally_validated_hooks": validated,
                        "deferred_live_hooks": deferred,
                    },
                )
                writer.record(
                    component="tau2_runtime_trace.smoke",
                    event_type="sample_tool_dispatch_start",
                    task_id="dry_task",
                    turn_index=0,
                    tool_name="dry_tool",
                    state_hash=stable_hash({"before": True}),
                    payload={"arguments": {"example": "value"}, "runtime_only": True},
                )
                writer.record(
                    component="tau2_runtime_trace.smoke",
                    event_type="sample_tool_dispatch_end",
                    task_id="dry_task",
                    turn_index=0,
                    tool_name="dry_tool",
                    state_hash=stable_hash({"after": True}),
                    payload={"result": {"ok": True}, "state_hash_changed": True},
                )
            if deferred:
                status = SKIPPED_LIVE_STATUS
            log.write(f"validated_hooks={json.dumps(sorted(set(validated)))}\n")
            log.write(f"deferred_hooks={json.dumps(sorted(set(deferred)))}\n")
            log.write(f"status={status}\n")
    except Exception as exc:
        status = FAILED_STATUS
        writer.errors.append({"error": repr(exc), "traceback": traceback.format_exc()})
        raw_log.write_text(
            "tau2_runtime_trace_smoke_failed\n"
            f"error={exc!r}\n"
            f"traceback={traceback.format_exc()}\n",
            encoding="utf-8",
        )
    finally:
        write_hook_map(out_dir, inspected or inspect_hook_targets(), validated, deferred)
        write_final_state(
            out_dir,
            status,
            writer,
            extra={
                "tau2_executed": False,
                "dry_validation": True,
                "generated_files": [
                    "runtime_events.jsonl",
                    "runtime_trace_summary.md",
                    "runtime_trace_final_state.json",
                    "runtime_hook_map.json",
                    "raw.log",
                ],
            },
        )
        write_summary(out_dir, status, writer, validated=validated, deferred=deferred, command="python scripts/run_tau2_runtime_trace_smoke.py")
        writer.close()
    print(rel(out_dir))
    print(status)
    return 1 if status == FAILED_STATUS else 0


if __name__ == "__main__":
    sys.exit(main())
