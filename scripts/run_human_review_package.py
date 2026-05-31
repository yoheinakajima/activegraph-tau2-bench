#!/usr/bin/env python3
"""Phase 11 design-only human-review package smoke.

This command regenerates the Phase 10 artifact chain through the existing
operator/incident readiness smoke, copies those local artifacts into a Phase 11
run directory, and emits advisory human-review packets. It does not execute tau2
control flow, import or run tau2 benchmark episodes, call LLM/API services,
handle real credentials, store raw secrets, approve execution, or enable live
reactive-manager behavior.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
import traceback
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.reactive_manager.human_review import (  # noqa: E402
    HUMAN_REVIEW_PACKAGE_FAILED_STATUS,
    HUMAN_REVIEW_PACKAGE_INPUTS_MISSING_STATUS,
    HUMAN_REVIEW_PACKAGE_PASS_STATUS,
    PHASE11_ARTIFACTS,
    REQUIRED_PHASE10_CHAIN_ARTIFACTS,
)
from experiments.reactive_manager.operator_readiness import OPERATOR_INCIDENT_READINESS_PASS_STATUS  # noqa: E402
from experiments.reactive_manager.planner import write_json  # noqa: E402
from experiments.reactive_manager.review_package import build_human_review_package, write_human_review_artifacts  # noqa: E402
from scripts.run_all_smokes import parse_child_output  # noqa: E402
from scripts.run_reactive_manager_dry_run import git_vendor_status  # noqa: E402
from scripts.run_trace_smoke import RUNS_DIR, rel, write  # noqa: E402

COMMAND = "python scripts/run_human_review_package.py"
PHASE10_COMMAND = [sys.executable, "scripts/run_operator_incident_readiness.py"]


def _write_failure(out_dir: pathlib.Path, log_lines: list[str], timestamp: str, run_id: str, state: str, errors: list[str]) -> int:
    final_state = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": state,
        "errors": errors,
        "output_dir": rel(out_dir),
        "command": COMMAND,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "tau2_control_flow_executed": False,
        "llm_api_calls_made": False,
        "vendor_tau2_bench_modified": bool(git_vendor_status()),
        "non_approval_statement": "Human review package failed or had missing inputs; it does not approve execution.",
    }
    write_json(out_dir / "final_state.json", final_state)
    write(out_dir / "raw.log", "\n".join(log_lines + errors) + "\n")
    print(out_dir)
    print(state)
    return 1


def _copy_phase10_chain(source_dir: pathlib.Path, out_dir: pathlib.Path) -> list[str]:
    missing: list[str] = []
    for name in REQUIRED_PHASE10_CHAIN_ARTIFACTS:
        source = source_dir / name
        if not source.is_file():
            missing.append(name)
            continue
        shutil.copy2(source, out_dir / name)
    final_state_source = source_dir / "final_state.json"
    if final_state_source.is_file():
        shutil.copy2(final_state_source, out_dir / "phase10_final_state.json")
        shutil.copy2(final_state_source, out_dir / "final_state.json")
    else:
        missing.append("final_state.json")
    return missing


def _validate_package(package: dict[str, Any], out_dir: pathlib.Path) -> list[str]:
    errors: list[str] = []
    if package.get("live_ready") is not False:
        errors.append("human_review_package live_ready was not false")
    if package.get("live_execution_available") is not False:
        errors.append("human_review_package live_execution_available was not false")
    if package.get("tau2_control_flow_executed") is not False:
        errors.append("human_review_package tau2_control_flow_executed was not false")
    if package.get("llm_api_calls_made") is not False:
        errors.append("human_review_package llm_api_calls_made was not false")
    if package.get("vendor_tau2_bench_modified") is not False:
        errors.append("human_review_package vendor_tau2_bench_modified was not false")
    statement = package.get("non_approval_statement", "")
    if "does not approve" not in statement or "live_ready remains false" not in statement:
        errors.append("non_approval_statement missing no-approval/live_ready wording")
    if package.get("blocker_matrix", {}).get("blocker_count", 0) <= 0:
        errors.append("blocker_matrix was empty")
    if package.get("evidence_index", {}).get("missing_artifacts"):
        errors.append(f"evidence_index missing artifacts: {package['evidence_index']['missing_artifacts']}")
    checklist_text = (out_dir / "reviewer_checklist.md").read_text(encoding="utf-8") if (out_dir / "reviewer_checklist.md").is_file() else ""
    for required in [
        "Confirm no tau2 control flow executed",
        "Confirm no LLM/API calls made",
        "Confirm this package does not approve execution",
    ]:
        if required not in checklist_text:
            errors.append(f"reviewer_checklist missing item: {required}")
    return errors


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")
    run_id = f"human-review-package-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 11 design-only human-review package smoke",
        f"timestamp_utc={timestamp}",
        f"run_id={run_id}",
        f"command={COMMAND}",
        "boundary=advisory human-review package only; live_ready=false; no live manager; no tau2 control; no tau2 run; no LLM/API calls; no real credentials; no execution approval",
    ]

    completed = subprocess.run(
        PHASE10_COMMAND,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    phase10_output = completed.stdout
    phase10_dir_text, phase10_status = parse_child_output(phase10_output)
    log_lines.extend(
        [
            "===== python scripts/run_operator_incident_readiness.py =====",
            f"returncode={completed.returncode}",
            f"parsed_output_dir={phase10_dir_text}",
            f"parsed_status={phase10_status}",
            phase10_output.rstrip(),
        ]
    )
    if completed.returncode != 0 or phase10_status != OPERATOR_INCIDENT_READINESS_PASS_STATUS or phase10_dir_text is None:
        return _write_failure(
            out_dir,
            log_lines,
            timestamp,
            run_id,
            HUMAN_REVIEW_PACKAGE_INPUTS_MISSING_STATUS,
            ["Phase 10 operator/incident readiness did not pass; human-review package inputs unavailable."],
        )

    source_phase10_dir = pathlib.Path(phase10_dir_text)
    if not source_phase10_dir.is_absolute():
        source_phase10_dir = REPO_ROOT / source_phase10_dir
    missing = _copy_phase10_chain(source_phase10_dir, out_dir)
    if missing:
        return _write_failure(out_dir, log_lines, timestamp, run_id, HUMAN_REVIEW_PACKAGE_INPUTS_MISSING_STATUS, [f"missing_phase10_artifacts={missing}"])

    package = build_human_review_package(
        out_dir=out_dir,
        run_id=run_id,
        generated_at=timestamp,
        command=COMMAND,
        source_phase10_run_dir=rel(source_phase10_dir),
    )
    write_human_review_artifacts(out_dir, package)
    validation_errors = _validate_package(package, out_dir)
    state = HUMAN_REVIEW_PACKAGE_PASS_STATUS if not validation_errors else HUMAN_REVIEW_PACKAGE_FAILED_STATUS
    package["status"] = state
    if validation_errors:
        write_human_review_artifacts(out_dir, package)

    final_state: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": state,
        "command": COMMAND,
        "output_dir": rel(out_dir),
        "source_phase10_run_dir": rel(source_phase10_dir),
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
        "tau2_benchmark_episodes_imported_or_run": False,
        "vendor_tau2_bench_modified": bool(git_vendor_status()),
        "artifacts": REQUIRED_PHASE10_CHAIN_ARTIFACTS + PHASE11_ARTIFACTS + ["summary.md", "final_state.json", "raw.log"],
        "review_package_path": rel(out_dir / "human_review_package.json"),
        "review_packet_path": rel(out_dir / "human_review_packet.md"),
        "reviewer_checklist_path": rel(out_dir / "reviewer_checklist.md"),
        "source_evidence_index_path": rel(out_dir / "source_evidence_index.json"),
        "blocker_matrix_path": rel(out_dir / "blocker_matrix.json"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "review_packet_sections": package["provenance"]["review_packet_sections"],
        "checklist_item_count": len(package["reviewer_checklist"]),
        "blocker_category_count": package["blocker_matrix"]["category_count"],
        "blocker_count": package["blocker_matrix"]["blocker_count"],
        "evidence_artifact_count": len(package["evidence_index"]["artifacts"]),
        "readiness_result": {
            "live_ready": False,
            "review_only": True,
            "design_only": True,
            "disabled_by_construction": True,
            "fail_closed": True,
            "human_review_only": True,
            "approves_execution": False,
        },
        "non_approval_statement": package["non_approval_statement"],
        "validation_errors": validation_errors,
        "limitations": [
            "Human-review artifacts are advisory/reporting only and cannot approve execution.",
            "Live reactive-manager execution remains unavailable and fail-closed.",
            "The package summarizes local fixture-backed artifacts only; it does not run tau2 episodes or call LLM/API services.",
            "Credential and vault readiness remains handle-only/mock-only with no real credential handling.",
            "Future live-manager work requires a separate reviewed implementation phase.",
        ],
    }
    write_json(out_dir / "final_state.json", final_state)
    log_lines.extend(
        [
            f"[PHASE11] status={state} live_ready={package['live_ready']} live_execution_available={package['live_execution_available']}",
            f"[PHASE11] blockers={package['blocker_matrix']['blocker_count']} evidence_artifacts={len(package['evidence_index']['artifacts'])}",
            f"[PHASE11] non_approval_statement={package['non_approval_statement']}",
            f"state={state}",
            f"vendor_status={git_vendor_status() or 'clean'}",
        ]
    )
    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")
    print(out_dir)
    print(state)
    return 0 if state == HUMAN_REVIEW_PACKAGE_PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - write traceback artifact for unexpected smoke errors.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("human_review_package_error")
        raise
