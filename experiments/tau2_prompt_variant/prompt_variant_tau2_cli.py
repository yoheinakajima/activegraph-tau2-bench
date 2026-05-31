#!/usr/bin/env python3
"""Bootstrap tau2 CLI with runtime tracing and an opt-in agent prompt variant.

This module intentionally lives outside vendor/tau2-bench. It applies a
process-local monkeypatch to the standard LLMAgent system prompt before tau2
constructs the agent, then delegates to the upstream tau2 CLI. It does not
mutate vendored source or feed ActiveGraph state back into tau2 execution.
"""
from __future__ import annotations

import os
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.tau2_runtime_trace.runtime_trace import (  # noqa: E402
    RuntimeTraceWriter,
    Tau2RuntimeTracer,
    ensure_vendor_import_path,
    inspect_hook_targets,
    write_final_state,
    write_hook_map,
    write_summary,
)

PROMPT_VARIANT_ENV = "TAU2_AGENT_PROMPT_VARIANT_TEXT"
STATUS_ENV = "TAU2_PROMPT_VARIANT_STATUS_PREFIX"
DEFAULT_STATUS_PREFIX = "airline_task8_prompt_variant"


def install_prompt_variant(writer: RuntimeTraceWriter) -> str:
    """Append the opt-in prompt variant to LLMAgent.system_prompt at runtime."""
    prompt_variant = os.environ.get(PROMPT_VARIANT_ENV, "").strip()
    if not prompt_variant:
        raise RuntimeError(f"{PROMPT_VARIANT_ENV} is required")

    ensure_vendor_import_path()
    from tau2.agent import llm_agent as llm_agent_module

    original_property = llm_agent_module.LLMAgent.system_prompt
    original_getter = original_property.fget
    if original_getter is None:
        raise RuntimeError("LLMAgent.system_prompt has no getter to wrap")

    def variant_system_prompt(self):  # noqa: ANN001 - signature must match property getter
        base_prompt = original_getter(self)
        return f"{base_prompt}\n\n<control_variant>\n{prompt_variant}\n</control_variant>"

    llm_agent_module.LLMAgent.system_prompt = property(variant_system_prompt)
    writer.record(
        component="tau2_prompt_variant.bootstrap",
        event_type="agent_prompt_variant_installed",
        payload={
            "target": "tau2.agent.llm_agent.LLMAgent.system_prompt",
            "prompt_variant": prompt_variant,
            "vendor_source_mutated": False,
        },
    )
    return prompt_variant


def main() -> int:
    run_dir_value = os.environ.get("TAU2_RUNTIME_TRACE_RUN_DIR")
    if not run_dir_value:
        print("TAU2_RUNTIME_TRACE_RUN_DIR is required", file=sys.stderr)
        return 2
    run_dir = pathlib.Path(run_dir_value)
    run_dir.mkdir(parents=True, exist_ok=True)
    status_prefix = os.environ.get(STATUS_ENV, DEFAULT_STATUS_PREFIX)
    failed_status = f"{status_prefix}_failed"
    passed_status = f"{status_prefix}_passed"
    writer = RuntimeTraceWriter(run_dir, phase="airline_task8_prompt_variant")
    status = os.environ.get("TAU2_RUNTIME_TRACE_PENDING_STATUS", failed_status)
    validated: list[str] = []
    deferred: list[str] = []
    prompt_variant = ""
    rc = 1
    try:
        inspected = inspect_hook_targets()
        prompt_variant = install_prompt_variant(writer)
        with Tau2RuntimeTracer(writer) as tracer:
            validated = list(tracer.installed_hooks)
            deferred = list(tracer.deferred_hooks)
            writer.record(
                component="tau2_prompt_variant.bootstrap",
                event_type="trace_bootstrap_start",
                payload={
                    "argv": sys.argv[1:],
                    "validated_hooks": validated,
                    "deferred_hooks": deferred,
                    "prompt_variant": prompt_variant,
                },
            )
            from tau2.cli import main as tau2_main

            sys.argv = ["tau2", *sys.argv[1:]]
            tau2_main()
            rc = 0
            status = passed_status
            writer.record(
                component="tau2_prompt_variant.bootstrap",
                event_type="trace_bootstrap_end",
                payload={"status": status, "returncode": rc},
            )
    except SystemExit as exc:
        rc = int(exc.code or 0) if isinstance(exc.code, int) else 1
        status = passed_status if rc == 0 else failed_status
        writer.record(
            component="tau2_prompt_variant.bootstrap",
            event_type="trace_bootstrap_end",
            payload={"status": status, "returncode": rc, "system_exit": repr(exc)},
        )
    except Exception as exc:  # pragma: no cover - defensive wrapper for artifact capture
        status = failed_status
        writer.errors.append({"error": repr(exc), "traceback": traceback.format_exc()})
        writer.record(
            component="tau2_prompt_variant.bootstrap",
            event_type="trace_bootstrap_end",
            payload={"status": status, "returncode": rc, "error": repr(exc)},
        )
    finally:
        inspected = locals().get("inspected") or inspect_hook_targets()
        write_hook_map(run_dir, inspected, validated, deferred)
        write_final_state(
            run_dir,
            status,
            writer,
            extra={
                "tau2_executed": True,
                "returncode": rc,
                "paid_llm_api_calls_made": True,
                "prompt_variant": prompt_variant,
                "prompt_variant_target": "tau2.agent.llm_agent.LLMAgent.system_prompt",
                "vendor_tau2_bench_mutated": False,
                "activegraph_control": False,
            },
        )
        write_summary(
            run_dir,
            status,
            writer,
            validated=validated,
            deferred=deferred,
            command="python experiments/tau2_prompt_variant/prompt_variant_tau2_cli.py " + " ".join(sys.argv[1:]),
            paid_llm_api_calls_made=True,
        )
        writer.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
