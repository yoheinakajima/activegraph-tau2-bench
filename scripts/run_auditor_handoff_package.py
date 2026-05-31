#!/usr/bin/env python3
"""Phase 12 design-only external-auditor handoff package smoke.

This command regenerates the Phase 11 human-review artifact chain and emits an
advisory retention-ready auditor handoff. It does not execute tau2 control flow,
import or run tau2 benchmark episodes, call LLM/API services, handle real
credentials, store raw secrets, approve execution, or enable live
reactive-manager behavior.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import shutil
import subprocess
import sys
import traceback
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.reactive_manager.auditor_handoff import (  # noqa: E402
    AUDITOR_HANDOFF_FAILED_STATUS,
    AUDITOR_HANDOFF_INPUTS_MISSING_STATUS,
    AUDITOR_HANDOFF_PASS_STATUS,
    AUDITOR_PACKET_SECTIONS,
    build_auditor_handoff_package,
    build_required_artifacts,
    write_auditor_handoff_artifacts,
)
from experiments.reactive_manager.human_review import (  # noqa: E402
    HUMAN_REVIEW_PACKAGE_PASS_STATUS,
    PHASE11_ARTIFACTS,
    REQUIRED_PHASE10_CHAIN_ARTIFACTS,
)
from experiments.reactive_manager.planner import write_json  # noqa: E402
from scripts.run_all_smokes import parse_child_output  # noqa: E402
from scripts.run_reactive_manager_dry_run import git_vendor_status  # noqa: E402
from scripts.run_trace_smoke import RUNS_DIR, rel, write  # noqa: E402

COMMAND = "python scripts/run_auditor_handoff_package.py"
PHASE11_COMMAND = [sys.executable, "scripts/run_human_review_package.py"]


def _copy_artifact_chain(source_dir: pathlib.Path, out_dir: pathlib.Path, artifact_names: list[str]) -> list[str]:
    missing: list[str] = []
    for name in artifact_names:
        source = source_dir / name
        if not source.is_file():
            missing.append(name)
            continue
        shutil.copy2(source, out_dir / name)
    final_state_source = source_dir / "final_state.json"
    if final_state_source.is_file():
        shutil.copy2(final_state_source, out_dir / "phase11_final_state.json")
        shutil.copy2(final_state_source, out_dir / "final_state.json")
    else:
        missing.append("final_state.json")
    return missing


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
        "non_approval_statement": "Auditor handoff package failed or had missing inputs; it does not approve execution.",
    }
    write_json(out_dir / "final_state.json", final_state)
    write(out_dir / "raw.log", "\n".join(log_lines + errors) + "\n")
    print(out_dir)
    print(state)
    return 1


def _validate_outputs(package: dict[str, Any], manifests: dict[str, Any], out_dir: pathlib.Path) -> list[str]:
    errors: list[str] = []
    if package.get("live_ready") is not False:
        errors.append("auditor_handoff_package live_ready was not false")
    if package.get("live_execution_available") is not False:
        errors.append("auditor_handoff_package live_execution_available was not false")
    if package.get("tau2_control_flow_executed") is not False:
        errors.append("auditor_handoff_package tau2_control_flow_executed was not false")
    if package.get("llm_api_calls_made") is not False:
        errors.append("auditor_handoff_package llm_api_calls_made was not false")
    if package.get("vendor_tau2_bench_modified") is not False:
        errors.append("auditor_handoff_package vendor_tau2_bench_modified was not false")
    statement = package.get("non_approval_statement", "")
    if "does not approve" not in statement or "live_ready remains false" not in statement:
        errors.append("non_approval_statement missing no-approval/live_ready wording")
    if package.get("blocker_summary", {}).get("blocker_count", 0) <= 0:
        errors.append("blocker_summary was empty")
    if not package.get("unresolved_prerequisites"):
        errors.append("unresolved_prerequisites was empty")
    if not package.get("auditor_question_set"):
        errors.append("auditor_question_set was empty")
    required_groups = set(manifests["retention_manifest"].get("required_groups", []))
    populated_groups = {group for group, entries in manifests["retention_manifest"].get("retention_groups", {}).items() if entries}
    missing_groups = sorted(required_groups - populated_groups)
    if missing_groups:
        errors.append(f"retention_manifest missing required groups: {missing_groups}")
    if manifests["retention_manifest"].get("missing_required_groups"):
        errors.append(f"retention_manifest reported missing groups: {manifests['retention_manifest']['missing_required_groups']}")
    if manifests["hash_manifest"].get("missing_artifacts"):
        errors.append(f"artifact_hash_manifest missing artifacts: {manifests['hash_manifest']['missing_artifacts']}")
    for entry in manifests["hash_manifest"].get("artifacts", []):
        if entry["artifact"] == "artifact_hash_manifest.json":
            if entry.get("self_hash_excluded") is not True:
                errors.append("artifact_hash_manifest self entry missing self_hash_excluded")
        elif entry.get("exists") is not True or not entry.get("sha256") or entry.get("byte_size", 0) <= 0:
            errors.append(f"artifact_hash_manifest invalid entry: {entry['artifact']}")
    if manifests["evidence_index"].get("missing_review_areas"):
        errors.append(f"evidence_bundle_index missing review areas: {manifests['evidence_index']['missing_review_areas']}")
    question_text = (out_dir / "auditor_questions.md").read_text(encoding="utf-8") if (out_dir / "auditor_questions.md").is_file() else ""
    for required in [
        "What evidence proves live_ready=false?",
        "What evidence proves no LLM/API calls were made?",
        "What blockers prevent live readiness?",
        "Which artifacts should be retained for later comparison?",
    ]:
        if required not in question_text:
            errors.append(f"auditor_questions missing question: {required}")
    packet_text = (out_dir / "auditor_handoff_packet.md").read_text(encoding="utf-8") if (out_dir / "auditor_handoff_packet.md").is_file() else ""
    for section in AUDITOR_PACKET_SECTIONS:
        if f"## {section}" not in packet_text:
            errors.append(f"auditor_handoff_packet missing section: {section}")
    return errors


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")
    run_id = f"auditor-handoff-package-{timestamp}"
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "tau2-bench Phase 12 design-only external-auditor handoff package smoke",
        f"timestamp_utc={timestamp}",
        f"run_id={run_id}",
        f"command={COMMAND}",
        "boundary=advisory auditor handoff and retention manifest only; live_ready=false; no live manager; no tau2 control; no tau2 run; no LLM/API calls; no real credentials; no execution approval",
    ]

    completed = subprocess.run(
        PHASE11_COMMAND,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    phase11_output = completed.stdout
    phase11_dir_text, phase11_status = parse_child_output(phase11_output)
    log_lines.extend(
        [
            "===== python scripts/run_human_review_package.py =====",
            f"returncode={completed.returncode}",
            f"parsed_output_dir={phase11_dir_text}",
            f"parsed_status={phase11_status}",
            phase11_output.rstrip(),
        ]
    )
    if completed.returncode != 0 or phase11_status != HUMAN_REVIEW_PACKAGE_PASS_STATUS or phase11_dir_text is None:
        return _write_failure(
            out_dir,
            log_lines,
            timestamp,
            run_id,
            AUDITOR_HANDOFF_INPUTS_MISSING_STATUS,
            ["Phase 11 human-review package did not pass; auditor handoff inputs unavailable."],
        )

    source_phase11_dir = pathlib.Path(phase11_dir_text)
    if not source_phase11_dir.is_absolute():
        source_phase11_dir = REPO_ROOT / source_phase11_dir
    phase11_chain = REQUIRED_PHASE10_CHAIN_ARTIFACTS + PHASE11_ARTIFACTS
    missing = _copy_artifact_chain(source_phase11_dir, out_dir, phase11_chain)
    if missing:
        return _write_failure(out_dir, log_lines, timestamp, run_id, AUDITOR_HANDOFF_INPUTS_MISSING_STATUS, [f"missing_phase11_artifacts={missing}"])

    required_artifacts = build_required_artifacts(REQUIRED_PHASE10_CHAIN_ARTIFACTS, PHASE11_ARTIFACTS)
    package = build_auditor_handoff_package(
        out_dir=out_dir,
        run_id=run_id,
        generated_at=timestamp,
        command=COMMAND,
        source_human_review_run_dir=rel(source_phase11_dir),
        required_artifacts=required_artifacts,
        vendor_modified=bool(git_vendor_status()),
    )
    final_state: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "state": AUDITOR_HANDOFF_PASS_STATUS,
        "command": COMMAND,
        "output_dir": rel(out_dir),
        "source_human_review_run_dir": rel(source_phase11_dir),
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "tau2_control_flow_executed": False,
        "state_packets_fed_back_into_tau2": False,
        "llm_api_calls_made": False,
        "tau2_benchmark_episodes_imported_or_run": False,
        "vendor_tau2_bench_modified": bool(git_vendor_status()),
        "artifacts": required_artifacts,
        "auditor_handoff_package_path": rel(out_dir / "auditor_handoff_package.json"),
        "auditor_handoff_packet_path": rel(out_dir / "auditor_handoff_packet.md"),
        "retention_manifest_path": rel(out_dir / "retention_manifest.json"),
        "artifact_hash_manifest_path": rel(out_dir / "artifact_hash_manifest.json"),
        "evidence_bundle_index_path": rel(out_dir / "evidence_bundle_index.json"),
        "auditor_questions_path": rel(out_dir / "auditor_questions.md"),
        "handoff_summary_path": rel(out_dir / "handoff_summary.md"),
        "summary_path": rel(out_dir / "summary.md"),
        "raw_log_path": rel(out_dir / "raw.log"),
        "handoff_packet_sections": AUDITOR_PACKET_SECTIONS,
        "auditor_question_count": len(package["auditor_question_set"]),
        "blocker_category_count": package["blocker_summary"]["category_count"],
        "blocker_count": package["blocker_summary"]["blocker_count"],
        "readiness_result": {
            "live_ready": False,
            "review_only": True,
            "design_only": True,
            "disabled_by_construction": True,
            "fail_closed": True,
            "auditor_handoff_only": True,
            "approves_execution": False,
        },
        "non_approval_statement": package["non_approval_statement"],
        "validation_errors": [],
        "limitations": [
            "Auditor handoff artifacts are advisory/reporting only and cannot approve execution.",
            "Live reactive-manager execution remains unavailable and fail-closed.",
            "The package summarizes local fixture-backed artifacts only; it does not run tau2 episodes or call LLM/API services.",
            "Credential and vault readiness remains handle-only/mock-only with no real credential handling.",
            "Future live-manager work requires a separate reviewed implementation phase.",
        ],
    }
    write_json(out_dir / "final_state.json", final_state)
    log_lines.extend(
        [
            f"[PHASE12] planned_status={AUDITOR_HANDOFF_PASS_STATUS} live_ready={package['live_ready']} live_execution_available={package['live_execution_available']}",
            f"[PHASE12] blockers={package['blocker_summary']['blocker_count']} questions={len(package['auditor_question_set'])}",
            f"[PHASE12] non_approval_statement={package['non_approval_statement']}",
            f"state={AUDITOR_HANDOFF_PASS_STATUS}",
            f"vendor_status={git_vendor_status() or 'clean'}",
        ]
    )
    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")
    manifests = write_auditor_handoff_artifacts(out_dir=out_dir, package=package, required_artifacts=required_artifacts, run_id=run_id, generated_at=timestamp)
    validation_errors = _validate_outputs(package, manifests, out_dir)
    state = AUDITOR_HANDOFF_PASS_STATUS if not validation_errors else AUDITOR_HANDOFF_FAILED_STATUS
    if validation_errors:
        package["status"] = state
        write_json(out_dir / "auditor_handoff_package.json", package)
        final_state["state"] = state
        final_state["validation_errors"] = validation_errors
        write_json(out_dir / "final_state.json", final_state)
    print(out_dir)
    print(state)
    return 0 if state == AUDITOR_HANDOFF_PASS_STATUS else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001 - write traceback artifact for unexpected smoke errors.
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")
        out_dir = RUNS_DIR / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        write(out_dir / "raw.log", traceback.format_exc())
        print(out_dir)
        print("auditor_handoff_package_error")
        raise
