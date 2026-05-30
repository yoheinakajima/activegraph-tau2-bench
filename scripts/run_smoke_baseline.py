#!/usr/bin/env python3
"""No-LLM baseline smoke harness for the locally vendored tau2-bench tree.

This script intentionally avoids importing or running tau2. It performs only
standard-library source and data checks so it never requires API keys and never
calls paid LLM APIs.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import sys
import tomllib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
UPSTREAM_COMMIT_FILE = REPO_ROOT / "vendor" / "tau2-bench.UPSTREAM_COMMIT"
RUNS_DIR = REPO_ROOT / "runs"
EXPECTED_UPSTREAM_COMMIT = "fcc9ed68df33c93ff0b8c946865f267d7c99fb06"

ALLOWED_STATES = {
    "upstream_missing",
    "source_inspection_failed",
    "no_llm_smoke_passed",
}

REQUIRED_PATHS = [
    VENDOR_DIR / "pyproject.toml",
    VENDOR_DIR / "src" / "tau2" / "cli.py",
    VENDOR_DIR / "src" / "tau2" / "run.py",
    VENDOR_DIR / "src" / "tau2" / "runner" / "batch.py",
    VENDOR_DIR / "src" / "tau2" / "runner" / "simulation.py",
    VENDOR_DIR / "src" / "tau2" / "orchestrator" / "orchestrator.py",
    VENDOR_DIR / "src" / "tau2" / "agent" / "base" / "participant.py",
    VENDOR_DIR / "src" / "tau2" / "agent" / "base_agent.py",
    VENDOR_DIR / "src" / "tau2" / "user" / "user_simulator.py",
    VENDOR_DIR / "src" / "tau2" / "user" / "user_simulator_base.py",
    VENDOR_DIR / "src" / "tau2" / "environment" / "environment.py",
    VENDOR_DIR / "src" / "tau2" / "environment" / "toolkit.py",
    VENDOR_DIR / "src" / "tau2" / "evaluator" / "evaluator.py",
    VENDOR_DIR / "src" / "tau2" / "data_model" / "tasks.py",
    VENDOR_DIR / "src" / "tau2" / "data_model" / "simulation.py",
    VENDOR_DIR / "src" / "tau2" / "registry.py",
]

AST_SYMBOLS: dict[pathlib.Path, set[str]] = {
    VENDOR_DIR / "src" / "tau2" / "cli.py": {"main", "add_run_args"},
    VENDOR_DIR / "src" / "tau2" / "runner" / "batch.py": {
        "run_domain",
        "run_tasks",
        "run_single_task",
    },
    VENDOR_DIR / "src" / "tau2" / "runner" / "simulation.py": {"run_simulation"},
    VENDOR_DIR / "src" / "tau2" / "orchestrator" / "orchestrator.py": {
        "BaseOrchestrator",
        "Orchestrator",
    },
    VENDOR_DIR / "src" / "tau2" / "agent" / "base" / "participant.py": {
        "HalfDuplexParticipant",
    },
    VENDOR_DIR / "src" / "tau2" / "agent" / "base_agent.py": {"HalfDuplexAgent"},
    VENDOR_DIR / "src" / "tau2" / "user" / "user_simulator.py": {
        "UserSimulator",
        "DummyUser",
    },
    VENDOR_DIR / "src" / "tau2" / "environment" / "environment.py": {"Environment"},
    VENDOR_DIR / "src" / "tau2" / "environment" / "toolkit.py": {
        "ToolKitBase",
        "ToolSignature",
        "get_tool_signatures",
    },
    VENDOR_DIR / "src" / "tau2" / "evaluator" / "evaluator.py": {
        "EvaluationType",
        "evaluate_simulation",
    },
    VENDOR_DIR / "src" / "tau2" / "data_model" / "tasks.py": {
        "Task",
        "EvaluationCriteria",
        "RewardType",
    },
    VENDOR_DIR / "src" / "tau2" / "data_model" / "simulation.py": {
        "SimulationRun",
        "Results",
        "RewardInfo",
    },
}

DOMAIN_DATA_FILES = [
    VENDOR_DIR / "data" / "tau2" / "domains" / "mock" / "tasks.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "mock" / "db.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "mock" / "policy.md",
    VENDOR_DIR / "data" / "tau2" / "domains" / "airline" / "tasks.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "airline" / "db.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "airline" / "policy.md",
    VENDOR_DIR / "data" / "tau2" / "domains" / "retail" / "tasks.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "retail" / "db.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "retail" / "policy.md",
    VENDOR_DIR / "data" / "tau2" / "domains" / "banking_knowledge" / "tasks.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "banking_knowledge" / "db.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "telecom" / "tasks.json",
    VENDOR_DIR / "data" / "tau2" / "domains" / "telecom" / "db.toml",
    VENDOR_DIR / "data" / "tau2" / "domains" / "telecom" / "user_db.toml",
    VENDOR_DIR / "data" / "tau2" / "domains" / "telecom" / "main_policy.md",
]


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def record(
    checks: list[dict[str, Any]],
    log_lines: list[str],
    name: str,
    ok: bool,
    **details: Any,
) -> None:
    entry = {"name": name, "ok": ok, **details}
    checks.append(entry)
    status = "PASS" if ok else "FAIL"
    detail_text = " ".join(f"{key}={value!r}" for key, value in details.items())
    log_lines.append(f"[{status}] {name}" + (f" {detail_text}" if detail_text else ""))


def top_level_symbols(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def validate_json_or_toml(path: pathlib.Path) -> tuple[bool, int | None, str | None]:
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            return path.read_text(encoding="utf-8").strip() != "", None, None
    except Exception as exc:  # noqa: BLE001 - record smoke failure details.
        return False, None, str(exc)
    if isinstance(data, list):
        return True, len(data), None
    if isinstance(data, dict):
        return True, len(data), None
    return True, None, None


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = [
        "tau2-bench Phase 1.5 no-LLM smoke",
        f"timestamp_utc={timestamp}",
        "boundary=no imports of tau2; no tau2 run; no API keys; no paid LLM APIs",
    ]
    checks: list[dict[str, Any]] = []

    record(checks, log_lines, "repo_root_present", REPO_ROOT.exists(), path=rel(REPO_ROOT))

    if not VENDOR_DIR.exists():
        state = "upstream_missing"
        record(checks, log_lines, "vendor_present", False, path=rel(VENDOR_DIR))
    else:
        record(checks, log_lines, "vendor_present", True, path=rel(VENDOR_DIR))
        commit_text = (
            UPSTREAM_COMMIT_FILE.read_text(encoding="utf-8").strip()
            if UPSTREAM_COMMIT_FILE.exists()
            else ""
        )
        record(
            checks,
            log_lines,
            "upstream_commit_marker",
            commit_text == EXPECTED_UPSTREAM_COMMIT,
            path=rel(UPSTREAM_COMMIT_FILE),
            expected=EXPECTED_UPSTREAM_COMMIT,
            actual=commit_text,
        )

        for path in REQUIRED_PATHS:
            record(checks, log_lines, "required_path", path.exists(), path=rel(path))

        for path, required_symbols in AST_SYMBOLS.items():
            try:
                found = top_level_symbols(path)
                missing = sorted(required_symbols - found)
                record(
                    checks,
                    log_lines,
                    "ast_symbols",
                    not missing,
                    path=rel(path),
                    required=sorted(required_symbols),
                    missing=missing,
                )
            except Exception as exc:  # noqa: BLE001 - record smoke failure details.
                record(
                    checks,
                    log_lines,
                    "ast_symbols",
                    False,
                    path=rel(path),
                    error=str(exc),
                )

        registry_text = (VENDOR_DIR / "src" / "tau2" / "registry.py").read_text(
            encoding="utf-8"
        )
        for domain in ["mock", "airline", "retail", "telecom", "banking_knowledge"]:
            record(
                checks,
                log_lines,
                "registry_domain_registration",
                f'"{domain}"' in registry_text,
                domain=domain,
            )

        for path in DOMAIN_DATA_FILES:
            if not path.exists():
                record(checks, log_lines, "domain_data_file", False, path=rel(path))
                continue
            ok, item_count, error = validate_json_or_toml(path)
            record(
                checks,
                log_lines,
                "domain_data_file",
                ok,
                path=rel(path),
                item_count=item_count,
                error=error,
            )

        state = (
            "no_llm_smoke_passed"
            if all(check["ok"] for check in checks)
            else "source_inspection_failed"
        )

    if state not in ALLOWED_STATES:
        raise RuntimeError(f"Unexpected state: {state}")

    final_state = {
        "timestamp_utc": timestamp,
        "state": state,
        "llm_api_calls": False,
        "requires_api_keys": False,
        "paid_llm_apis_called": False,
        "vendor_dir": rel(VENDOR_DIR),
        "expected_upstream_commit": EXPECTED_UPSTREAM_COMMIT,
        "output_dir": rel(out_dir),
        "checks": checks,
    }

    write(out_dir / "raw.log", "\n".join(log_lines).strip() + "\n")
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")

    passed = sum(1 for check in checks if check["ok"])
    failed = len(checks) - passed
    summary = [
        "# tau2-bench Phase 1.5 no-LLM smoke summary",
        "",
        f"- Timestamp (UTC): `{timestamp}`",
        "- LLM/API calls used: `False`",
        "- API keys required: `False`",
        f"- Final state: `{state}`",
        f"- Checks passed: `{passed}`",
        f"- Checks failed: `{failed}`",
        f"- Output directory: `{rel(out_dir)}`",
        "",
        "## Boundary",
        "",
        "This smoke run inspected local source/data files only. It did not import `tau2`, run `tau2 run`, instantiate LLM agents, or call external APIs.",
    ]
    write(out_dir / "summary.md", "\n".join(summary) + "\n")

    print(out_dir)
    print(state)
    return 0 if state == "no_llm_smoke_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
