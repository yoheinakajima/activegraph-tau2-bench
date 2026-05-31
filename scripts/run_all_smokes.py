#!/usr/bin/env python3
"""Compact smoke aggregator for all local no-LLM smoke commands."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "runs"
PASS_STATUS = "all_smokes_passed"
FAILED_STATUS = "all_smokes_failed"

SMOKES = [
    {
        "name": "baseline",
        "command": [sys.executable, "scripts/run_smoke_baseline.py"],
        "display_command": "python scripts/run_smoke_baseline.py",
        "expected_statuses": ["no_llm_smoke_passed"],
    },
    {
        "name": "trace",
        "command": [sys.executable, "scripts/run_trace_smoke.py"],
        "display_command": "python scripts/run_trace_smoke.py",
        "expected_statuses": ["trace_smoke_passed"],
    },
    {
        "name": "activegraph_trace",
        "command": [sys.executable, "scripts/run_activegraph_trace_smoke.py"],
        "display_command": "python scripts/run_activegraph_trace_smoke.py",
        "expected_statuses": ["activegraph_trace_mock_passed", "activegraph_trace_runtime_passed"],
    },
    {
        "name": "state_packet",
        "command": [sys.executable, "scripts/run_state_packet_smoke.py"],
        "display_command": "python scripts/run_state_packet_smoke.py",
        "expected_statuses": ["state_packet_smoke_passed"],
    },
    {
        "name": "reactive_manager_dry_run",
        "command": [sys.executable, "scripts/run_reactive_manager_dry_run.py"],
        "display_command": "python scripts/run_reactive_manager_dry_run.py",
        "expected_statuses": ["reactive_manager_dry_run_passed"],
    },
    {
        "name": "reactive_manager_contracts",
        "command": [sys.executable, "scripts/run_reactive_manager_contracts.py"],
        "display_command": "python scripts/run_reactive_manager_contracts.py",
        "expected_statuses": ["reactive_manager_contracts_passed"],
    },
    {
        "name": "live_manager_opt_in_contracts",
        "command": [sys.executable, "scripts/run_live_manager_opt_in_contracts.py"],
        "display_command": "python scripts/run_live_manager_opt_in_contracts.py",
        "expected_statuses": ["live_manager_opt_in_contracts_passed"],
    },
    {
        "name": "live_readiness_audit",
        "command": [sys.executable, "scripts/run_live_readiness_audit.py"],
        "display_command": "python scripts/run_live_readiness_audit.py",
        "expected_statuses": ["live_readiness_audit_passed"],
    },
    {
        "name": "external_readiness_contracts",
        "command": [sys.executable, "scripts/run_external_readiness_contracts.py"],
        "display_command": "python scripts/run_external_readiness_contracts.py",
        "expected_statuses": ["external_readiness_contracts_passed"],
    },
    {
        "name": "operator_incident_readiness",
        "command": [sys.executable, "scripts/run_operator_incident_readiness.py"],
        "display_command": "python scripts/run_operator_incident_readiness.py",
        "expected_statuses": ["operator_incident_readiness_passed"],
    },
    {
        "name": "human_review_package",
        "command": [sys.executable, "scripts/run_human_review_package.py"],
        "display_command": "python scripts/run_human_review_package.py",
        "expected_statuses": ["human_review_package_passed"],
    },
    {
        "name": "auditor_handoff_package",
        "command": [sys.executable, "scripts/run_auditor_handoff_package.py"],
        "display_command": "python scripts/run_auditor_handoff_package.py",
        "expected_statuses": ["auditor_handoff_package_passed"],
    },
    {
        "name": "tau2_real",
        "command": [sys.executable, "scripts/run_tau2_real_smoke.py"],
        "display_command": "python scripts/run_tau2_real_smoke.py",
        "expected_statuses": [
            "tau2_real_smoke_source_only_passed",
            "tau2_real_smoke_import_passed",
            "tau2_real_smoke_cli_passed",
            "tau2_real_smoke_data_check_passed",
            "tau2_real_smoke_tests_passed",
            "tau2_real_smoke_passed",
        ],
        "warning_statuses": ["tau2_real_smoke_source_only_passed"],
    },
]


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_child_output(output: str) -> tuple[str | None, str | None]:
    nonempty = [line.strip() for line in output.splitlines() if line.strip()]
    output_dir = None
    status = None
    for line in nonempty:
        candidate = pathlib.Path(line)
        if line.startswith(str(RUNS_DIR)) or line.startswith("runs/"):
            output_dir = line
        elif line.endswith("_passed") or line.endswith("_failed") or line.endswith("_missing") or line.endswith("_error") or line == "source_inspection_failed":
            status = line
    if output_dir is None and len(nonempty) >= 2:
        output_dir = nonempty[-2]
    if status is None and nonempty:
        status = nonempty[-1]
    return output_dir, status


def write(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    rows = "\n".join(
        f"| {result['name']} | `{result['status']}` | {result['returncode']} | `{result['output_dir']}` |"
        for result in final_state["results"]
    )
    content = f"""# tau2-bench aggregate smoke summary

Status: `{final_state['state']}`

Run directory: `{final_state['output_dir']}`

| Smoke | Status | Return code | Output directory |
| --- | --- | ---: | --- |
{rows}

Expected aggregate status: `{PASS_STATUS}`

Boundary: this aggregator invokes local no-LLM smoke commands and records their outputs. It does not execute paid model calls or model-backed tau2 benchmark episodes. The `tau2_real` smoke may report `tau2_real_smoke_source_only_passed` as a warning-level minimum when local dependency installation is unavailable; stronger import/CLI/data/test/pass statuses indicate progressively more real vendored tau2 behavior ran.
"""
    write(out_dir / "aggregate_summary.md", content)


def print_table(results: list[dict[str, Any]], aggregate_state: str, output_dir: str) -> None:
    name_width = max(len("smoke"), *(len(result["name"]) for result in results))
    status_width = max(len("status"), *(len(str(result["status"])) for result in results))
    print(f"{'smoke':<{name_width}}  {'status':<{status_width}}  rc  output_dir")
    print(f"{'-' * name_width}  {'-' * status_width}  --  ----------")
    for result in results:
        print(f"{result['name']:<{name_width}}  {str(result['status']):<{status_width}}  {result['returncode']:>2}  {result['output_dir']}")
    print(f"aggregate_status={aggregate_state}")
    print(f"aggregate_output_dir={output_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all local smoke commands and print a compact status table.")
    parser.add_argument("--verbose", action="store_true", help="print full child-script output while running")
    args = parser.parse_args()

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")
    run_id = f"all-smokes-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_sections: list[str] = [
        "tau2-bench aggregate smoke run",
        f"timestamp_utc={timestamp}",
        f"run_id={run_id}",
    ]
    results: list[dict[str, Any]] = []
    last_child_start_second = None
    for smoke in SMOKES:
        while int(time.time()) == last_child_start_second:
            time.sleep(0.05)
        last_child_start_second = int(time.time())
        completed = subprocess.run(
            smoke["command"],
            cwd=REPO_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = completed.stdout
        if args.verbose and output:
            print(f"\n### {smoke['display_command']} ###")
            print(output, end="" if output.endswith("\n") else "\n")
        output_dir, status = parse_child_output(output)
        expected = status in smoke["expected_statuses"]
        result = {
            "name": smoke["name"],
            "command": smoke["display_command"],
            "returncode": completed.returncode,
            "output_dir": output_dir,
            "status": status,
            "expected_statuses": smoke["expected_statuses"],
            "warning_statuses": smoke.get("warning_statuses", []),
            "expected_status_observed": expected,
            "warning_status_observed": status in smoke.get("warning_statuses", []),
            "passed": completed.returncode == 0 and expected and output_dir is not None,
        }
        results.append(result)
        raw_sections.append(
            "\n".join(
                [
                    f"\n===== {smoke['display_command']} =====",
                    f"returncode={completed.returncode}",
                    f"parsed_output_dir={output_dir}",
                    f"parsed_status={status}",
                    output.rstrip(),
                ]
            )
        )

    aggregate_ok = all(result["passed"] for result in results)
    aggregate_state = PASS_STATUS if aggregate_ok else FAILED_STATUS
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": aggregate_state,
        "command": "python scripts/run_all_smokes.py",
        "output_dir": rel(out_dir),
        "aggregate_raw_log_path": rel(out_dir / "aggregate_raw.log"),
        "aggregate_summary_path": rel(out_dir / "aggregate_summary.md"),
        "results": results,
        "expected_status_missing_count": sum(1 for result in results if not result["expected_status_observed"]),
        "failed_smoke_count": sum(1 for result in results if not result["passed"]),
        "warning_smoke_count": sum(1 for result in results if result.get("warning_status_observed")),
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "tau2_control_flow_executed": False,
        "llm_api_calls_made": False,
        "no_live_execution_code_path_added": True,
    }
    write(out_dir / "aggregate_raw.log", "\n".join(raw_sections).rstrip() + "\n")
    write(out_dir / "aggregate_final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
    write_summary(out_dir, final_state)
    print_table(results, aggregate_state, rel(out_dir))
    return 0 if aggregate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
