#!/usr/bin/env python3
"""Cheap repository health checks for the local tau2-bench readiness repo."""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_VENDOR_COMMIT = "fcc9ed68df33c93ff0b8c946865f267d7c99fb06"
PASS_STATUS = "repo_health_passed"
FAIL_STATUS = "repo_health_failed"

REQUIRED_FILES = [
    "README.md",
    ".gitignore",
    "vendor/tau2-bench.UPSTREAM_COMMIT",
    "scripts/run_all_smokes.py",
    "docs/source_map.md",
    "docs/trace_only.md",
    "docs/activegraph_trace_only.md",
    "docs/state_packets.md",
    "docs/reactive_manager_dry_run.md",
    "docs/reactive_manager_contracts.md",
    "docs/live_reactive_manager_opt_in.md",
    "docs/live_readiness_audit.md",
    "docs/external_audit_vault_readiness.md",
    "docs/operator_incident_readiness.md",
    "docs/human_review_package.md",
    "docs/auditor_handoff_retention.md",
    "docs/milestone_report.md",
    "docs/phase_matrix.md",
    "docs/operations.md",
]

VENDOR_KEY_PATHS = [
    "vendor/tau2-bench/README.md",
    "vendor/tau2-bench/pyproject.toml",
    "vendor/tau2-bench/uv.lock",
    "vendor/tau2-bench/src/tau2",
    "vendor/tau2-bench/tests",
]

COMPILE_DIRS = ["scripts", "experiments"]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def check_python_version() -> CheckResult:
    version = sys.version_info
    passed = version >= (3, 12)
    detail = f"python={version.major}.{version.minor}.{version.micro} executable={sys.executable}"
    return CheckResult("python_version", passed, detail)


def check_required_files() -> CheckResult:
    missing = [path for path in REQUIRED_FILES if not (REPO_ROOT / path).is_file()]
    return CheckResult(
        "required_files",
        not missing,
        "all required files present" if not missing else f"missing: {', '.join(missing)}",
    )


def check_vendor_commit() -> CheckResult:
    marker = REPO_ROOT / "vendor/tau2-bench.UPSTREAM_COMMIT"
    if not marker.is_file():
        return CheckResult("vendor_commit", False, "vendor/tau2-bench.UPSTREAM_COMMIT is missing")
    observed = marker.read_text(encoding="utf-8").strip()
    passed = observed == EXPECTED_VENDOR_COMMIT
    detail = f"observed={observed} expected={EXPECTED_VENDOR_COMMIT}"
    return CheckResult("vendor_commit", passed, detail)


def check_vendor_key_paths() -> CheckResult:
    missing = [path for path in VENDOR_KEY_PATHS if not (REPO_ROOT / path).exists()]
    return CheckResult(
        "vendor_key_paths",
        not missing,
        "all key vendor paths present" if not missing else f"missing: {', '.join(missing)}",
    )


def check_python_sources_compile() -> CheckResult:
    failures: list[str] = []
    checked = 0
    for directory in COMPILE_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            checked += 1
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, rel(path), "exec")
            except SyntaxError as exc:
                failures.append(f"{rel(path)}:{exc.lineno}:{exc.msg}")
    return CheckResult(
        "python_sources_compile",
        not failures,
        f"compiled {checked} files" if not failures else "; ".join(failures),
    )


def check_gitignore_runs() -> CheckResult:
    gitignore = REPO_ROOT / ".gitignore"
    if not gitignore.is_file():
        return CheckResult("gitignore_runs", False, ".gitignore is missing")
    lines = {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
    required = {"runs/*", "!runs/.gitkeep"}
    missing = sorted(required - lines)
    return CheckResult(
        "gitignore_runs",
        not missing,
        "runs artifacts are ignored with .gitkeep preserved" if not missing else f"missing ignore rules: {', '.join(missing)}",
    )


def check_no_generated_runs_staged() -> CheckResult:
    completed = run_git(["diff", "--cached", "--name-only", "--", "runs"])
    if completed.returncode != 0:
        return CheckResult("no_generated_runs_staged", False, completed.stdout.strip())
    staged = [line for line in completed.stdout.splitlines() if line and line != "runs/.gitkeep"]
    return CheckResult(
        "no_generated_runs_staged",
        not staged,
        "no generated run artifacts are staged" if not staged else f"staged runs: {', '.join(staged)}",
    )


def check_vendor_git_status() -> CheckResult:
    completed = run_git(["status", "--short", "--", "vendor/tau2-bench", "vendor/tau2-bench.UPSTREAM_COMMIT"])
    if completed.returncode != 0:
        return CheckResult("vendor_git_status", False, completed.stdout.strip())
    status = completed.stdout.strip()
    return CheckResult(
        "vendor_git_status",
        status == "",
        "vendor tree is clean" if status == "" else status,
    )


def check_run_smokes() -> CheckResult:
    completed = subprocess.run(
        [sys.executable, "scripts/run_all_smokes.py"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = completed.stdout.strip()
    tail = "\n".join(output.splitlines()[-5:]) if output else "no output"
    passed = completed.returncode == 0 and "aggregate_status=all_smokes_passed" in output
    return CheckResult("run_all_smokes", passed, tail)


def print_results(results: list[CheckResult]) -> None:
    width = max(len("check"), *(len(result.name) for result in results))
    print(f"{'check':<{width}}  status  detail")
    print(f"{'-' * width}  ------  ------")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{result.name:<{width}}  {status:<6}  {result.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cheap repository health checks.")
    parser.add_argument("--run-smokes", action="store_true", help="also run python scripts/run_all_smokes.py")
    args = parser.parse_args()

    results = [
        check_python_version(),
        check_required_files(),
        check_vendor_commit(),
        check_vendor_key_paths(),
        check_python_sources_compile(),
        check_gitignore_runs(),
        check_no_generated_runs_staged(),
        check_vendor_git_status(),
    ]
    if args.run_smokes:
        results.append(check_run_smokes())

    print_results(results)
    passed = all(result.passed for result in results)
    print(f"repo_health_status={PASS_STATUS if passed else FAIL_STATUS}")
    print("live_ready=false")
    print("live_execution_available=false")
    print("tau2_control_flow_executed=false")
    print("llm_api_calls_made=false")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
