#!/usr/bin/env python3
"""Bootstrap tau2 CLI with runtime trace-only monkeypatches installed."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.write_intent_observer import PassiveWriteIntentObserver  # noqa: E402
from experiments.tau2_runtime_trace.runtime_trace import (  # noqa: E402
    RuntimeTraceWriter,
    Tau2RuntimeTracer,
    inspect_hook_targets,
    write_final_state,
    write_hook_map,
    write_summary,
)


def main() -> int:
    run_dir_value = os.environ.get("TAU2_RUNTIME_TRACE_RUN_DIR")
    if not run_dir_value:
        print("TAU2_RUNTIME_TRACE_RUN_DIR is required", file=sys.stderr)
        return 2
    run_dir = pathlib.Path(run_dir_value)
    run_dir.mkdir(parents=True, exist_ok=True)
    writer = RuntimeTraceWriter(run_dir, phase="runtime_traced_baseline")
    write_intent_observer = None
    if os.environ.get("TAU2_WRITE_INTENT_OBSERVER_ENABLED") == "1":
        write_intent_observer = PassiveWriteIntentObserver(run_dir, run_id=writer.run_id)
    status = os.environ.get("TAU2_RUNTIME_TRACE_PENDING_STATUS", "tau2_runtime_traced_baseline_failed")
    validated: list[str] = []
    deferred: list[str] = []
    rc = 1
    try:
        inspected = inspect_hook_targets()
        with Tau2RuntimeTracer(writer, write_intent_observer=write_intent_observer) as tracer:
            validated = list(tracer.installed_hooks)
            deferred = list(tracer.deferred_hooks)
            writer.record(
                component="tau2_runtime_trace.bootstrap",
                event_type="trace_bootstrap_start",
                payload={"argv": sys.argv[1:], "validated_hooks": validated, "deferred_hooks": deferred},
            )
            from tau2.cli import main as tau2_main

            sys.argv = ["tau2", *sys.argv[1:]]
            tau2_main()
            rc = 0
            status = "tau2_runtime_traced_baseline_passed"
            writer.record(component="tau2_runtime_trace.bootstrap", event_type="trace_bootstrap_end", payload={"status": status, "returncode": rc})
    except SystemExit as exc:
        rc = int(exc.code or 0) if isinstance(exc.code, int) else 1
        status = "tau2_runtime_traced_baseline_passed" if rc == 0 else "tau2_runtime_traced_baseline_failed"
        writer.record(component="tau2_runtime_trace.bootstrap", event_type="trace_bootstrap_end", payload={"status": status, "returncode": rc, "system_exit": repr(exc)})
    except Exception as exc:
        status = "tau2_runtime_traced_baseline_failed"
        writer.errors.append({"error": repr(exc), "traceback": traceback.format_exc()})
        writer.record(component="tau2_runtime_trace.bootstrap", event_type="trace_bootstrap_end", payload={"status": status, "returncode": rc, "error": repr(exc)})
    finally:
        inspected = locals().get("inspected") or inspect_hook_targets()
        write_hook_map(run_dir, inspected, validated, deferred)
        observer_extra = {"write_intent_observer_enabled": write_intent_observer is not None}
        if write_intent_observer is not None:
            observer_state = write_intent_observer.final_state(status)
            (run_dir / "observer_final_state.json").write_text(json.dumps(observer_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            write_intent_observer.close()
            observer_extra["write_intent_observer_artifacts"] = observer_state["artifacts"]
        write_final_state(run_dir, status, writer, extra={"tau2_executed": True, "returncode": rc, "paid_llm_api_calls_made": True, **observer_extra})
        write_summary(
            run_dir,
            status,
            writer,
            validated=validated,
            deferred=deferred,
            command="python experiments/tau2_runtime_trace/traced_tau2_cli.py " + " ".join(sys.argv[1:]),
            paid_llm_api_calls_made=True,
        )
        writer.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
