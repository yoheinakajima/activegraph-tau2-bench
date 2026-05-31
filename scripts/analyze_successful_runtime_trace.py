#!/usr/bin/env python3
"""Compatibility wrapper for runtime-traced tau2 baseline outcome analysis.

Historically this command only described a successful create_task run.  The
implementation now delegates to analyze_runtime_trace_outcome.py so the report
language and schema are outcome-neutral and safe for successful, no-write, and
partial-progress traces.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import analyze_runtime_trace_outcome as outcome  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compatibility alias for offline runtime-traced tau2 baseline outcome analysis."
    )
    parser.add_argument("--successful-runtime-run-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--short-runtime-run-dir",
        required=False,
        type=pathlib.Path,
        help="Accepted for backward compatibility; outcome analysis compares against --successful-runtime-run-dir as the reference success run.",
    )
    parser.add_argument("--postrun-baseline-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Defaults to <successful-runtime-run-dir>/runtime_outcome_analysis/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    delegated = argparse.Namespace(
        runtime_run_dir=args.successful_runtime_run_dir,
        reference_success_run_dir=args.successful_runtime_run_dir,
        postrun_baseline_dir=args.postrun_baseline_dir,
        output_dir=args.output_dir,
    )
    output_dir = delegated.output_dir.resolve() if delegated.output_dir is not None else delegated.runtime_run_dir.resolve() / "runtime_outcome_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = outcome.build_report(delegated, output_dir)
    except Exception as exc:  # noqa: BLE001 - keep wrapper behavior diagnosable like the primary command.
        final_state = {
            "status": outcome.STATUS_INPUTS_MISSING,
            "generated_at_utc": outcome.utc_now(),
            "title": "runtime-traced tau2 baseline analysis",
            "error": str(exc),
            "compatibility_wrapper": "scripts/analyze_successful_runtime_trace.py",
            "analysis_boundaries": {
                "tau2_rerun_performed_by_analysis": False,
                "model_backed_episode_run_by_analysis": False,
                "llm_api_calls_made_by_analysis": False,
                "requires_api_keys": False,
                "vendor_tau2_bench_mutated_by_analysis": False,
                "activegraph_control_added": False,
            },
        }
        outcome.write_json(output_dir / "final_state.json", final_state)
        (output_dir / "raw.log").write_text(
            f"runtime-traced tau2 baseline analysis\ncompatibility_wrapper=true\nstatus={outcome.STATUS_INPUTS_MISSING}\nerror={exc}\n",
            encoding="utf-8",
        )
        print(f"analysis_status={outcome.STATUS_INPUTS_MISSING}")
        print(f"error={exc}", file=sys.stderr)
        return 2

    report["compatibility_wrapper"] = "scripts/analyze_successful_runtime_trace.py"
    outcome.write_json(output_dir / "runtime_outcome_analysis.json", report)
    (output_dir / "runtime_outcome_summary.md").write_text(outcome.markdown_summary(report), encoding="utf-8")
    outcome.write_json(output_dir / "completion_or_failure_path.json", report["completion_or_failure_path"])
    outcome.write_json(output_dir / "metric_classification.json", report["metric_classification"])
    final_state = outcome.final_state_from_report(report)
    final_state["compatibility_wrapper"] = "scripts/analyze_successful_runtime_trace.py"
    outcome.write_json(output_dir / "final_state.json", final_state)
    (output_dir / "raw.log").write_text(
        "\n".join(
            [
                "runtime-traced tau2 baseline analysis",
                "compatibility_wrapper=true",
                f"generated_at_utc={report['generated_at_utc']}",
                f"status={report['status']}",
                f"task_outcome={report['task_outcome']}",
                "offline_analysis=true",
                "tau2_rerun_performed_by_analysis=false",
                "model_backed_episode_run_by_analysis=false",
                "llm_api_calls_made_by_analysis=false",
                "requires_api_keys=false",
                "vendor_tau2_bench_mutated_by_analysis=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(outcome.rel(output_dir))
    print(report["status"])
    print(f"task_outcome={report['task_outcome']}")
    return 0 if report["status"] in {outcome.STATUS_PASSED, outcome.STATUS_WITH_GAPS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
