#!/usr/bin/env python3
"""Run a real local no-LLM smoke against the vendored tau2-bench package."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tomllib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "runs"
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
UPSTREAM_COMMIT_FILE = REPO_ROOT / "vendor" / "tau2-bench.UPSTREAM_COMMIT"
EXPECTED_UPSTREAM_COMMIT = "fcc9ed68df33c93ff0b8c946865f267d7c99fb06"
MOCK_DOMAIN_DIR = VENDOR_DIR / "data" / "tau2" / "domains" / "mock"

SOURCE_ONLY_STATUS = "tau2_real_smoke_source_only_passed"
IMPORT_STATUS = "tau2_real_smoke_import_passed"
CLI_STATUS = "tau2_real_smoke_cli_passed"
DATA_STATUS = "tau2_real_smoke_data_check_passed"
TESTS_STATUS = "tau2_real_smoke_tests_passed"
PASS_STATUS = "tau2_real_smoke_passed"
FAILED_STATUS = "tau2_real_smoke_failed"
ENV_MISSING_STATUS = "tau2_real_smoke_env_missing"
INSTALL_FAILED_STATUS = "tau2_real_smoke_install_failed"

NO_LLM_TESTS = [
    "tests/test_domains/test_mock/test_tools_mock.py",
    "tests/test_tasks.py",
    "tests/test_environment.py",
]

API_KEY_NAMES = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_OPENAI_API_KEY",
]


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class Recorder:
    def __init__(self, out_dir: pathlib.Path) -> None:
        self.out_dir = out_dir
        self.raw_log = out_dir / "raw.log"
        self.lines: list[str] = []

    def log(self, message: str) -> None:
        print(message)
        self.lines.append(message)

    def section(self, title: str) -> None:
        self.lines.append(f"\n===== {title} =====")

    def command(self, label: str, completed: subprocess.CompletedProcess[str]) -> None:
        self.section(label)
        self.lines.append(f"returncode={completed.returncode}")
        if completed.stdout:
            self.lines.append(completed.stdout.rstrip())

    def flush(self) -> None:
        self.raw_log.write_text("\n".join(self.lines).rstrip() + "\n", encoding="utf-8")


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["TAU2_DATA_DIR"] = str(VENDOR_DIR / "data")
    env["PYTHONUNBUFFERED"] = "1"
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    for key in API_KEY_NAMES:
        env.pop(key, None)
    return env


def run_command(
    command: list[str],
    *,
    cwd: pathlib.Path,
    env: dict[str, str],
    timeout: int = 120,
    output_file: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if output_file is not None:
        output_file.write_text(completed.stdout, encoding="utf-8")
    return completed


def parse_pyproject() -> dict[str, Any]:
    pyproject = VENDOR_DIR / "pyproject.toml"
    if not pyproject.exists():
        return {"exists": False}
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project", {})
    scripts = project.get("scripts", {})
    return {
        "exists": True,
        "requires_python": project.get("requires-python"),
        "cli_entrypoint": scripts.get("tau2"),
        "dependencies_count": len(project.get("dependencies", [])),
        "dev_dependencies": project.get("optional-dependencies", {}).get("dev", []),
    }


def python_satisfies(requirement: str | None) -> bool | None:
    if not requirement:
        return None
    current = sys.version_info
    if requirement.replace(" ", "") == ">=3.12,<3.14":
        return (current.major, current.minor) >= (3, 12) and (current.major, current.minor) < (3, 14)
    return None


def source_checks() -> tuple[list[dict[str, Any]], bool, bool]:
    checks = [
        ("vendor_dir", VENDOR_DIR, "dir"),
        ("upstream_commit_file", UPSTREAM_COMMIT_FILE, "file"),
        ("pyproject", VENDOR_DIR / "pyproject.toml", "file"),
        ("cli_py", VENDOR_DIR / "src" / "tau2" / "cli.py", "file"),
        ("mock_domain_dir", MOCK_DOMAIN_DIR, "dir"),
        ("mock_tasks", MOCK_DOMAIN_DIR / "tasks.json", "file"),
        ("mock_policy", MOCK_DOMAIN_DIR / "policy.md", "file"),
        ("mock_tools", VENDOR_DIR / "src" / "tau2" / "domains" / "mock" / "tools.py", "file"),
    ]
    results: list[dict[str, Any]] = []
    all_ok = True
    vendor_missing = False
    for name, path, kind in checks:
        exists = path.is_dir() if kind == "dir" else path.is_file()
        if not exists:
            all_ok = False
            if name == "vendor_dir":
                vendor_missing = True
        results.append({"name": name, "path": rel(path), "kind": kind, "exists": exists})
    commit = UPSTREAM_COMMIT_FILE.read_text(encoding="utf-8").strip() if UPSTREAM_COMMIT_FILE.exists() else None
    commit_matches = commit == EXPECTED_UPSTREAM_COMMIT
    if not commit_matches:
        all_ok = False
    results.append(
        {
            "name": "upstream_commit_matches_expected",
            "observed": commit,
            "expected": EXPECTED_UPSTREAM_COMMIT,
            "exists": commit_matches,
        }
    )
    return results, all_ok, vendor_missing


def file_domain_probe() -> dict[str, Any]:
    probe: dict[str, Any] = {
        "mode": "file",
        "domain_dir": rel(MOCK_DOMAIN_DIR),
        "tasks_path": rel(MOCK_DOMAIN_DIR / "tasks.json"),
        "policy_path": rel(MOCK_DOMAIN_DIR / "policy.md"),
        "tools_path": rel(VENDOR_DIR / "src" / "tau2" / "domains" / "mock" / "tools.py"),
    }
    tasks_path = MOCK_DOMAIN_DIR / "tasks.json"
    if tasks_path.exists():
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        probe["task_count"] = len(tasks)
        probe["task_ids_preview"] = [task.get("id") for task in tasks[:5]]
    else:
        probe["task_count"] = 0
        probe["task_ids_preview"] = []
    policy_path = MOCK_DOMAIN_DIR / "policy.md"
    probe["policy_exists"] = policy_path.exists()
    probe["policy_non_empty"] = policy_path.exists() and bool(policy_path.read_text(encoding="utf-8").strip())
    db_paths = [MOCK_DOMAIN_DIR / "db.json", MOCK_DOMAIN_DIR / "user_db.json"]
    probe["db_files"] = [{"path": rel(path), "exists": path.exists()} for path in db_paths]
    tools_path = VENDOR_DIR / "src" / "tau2" / "domains" / "mock" / "tools.py"
    probe["tools_exists"] = tools_path.exists()
    probe["tools_size_bytes"] = tools_path.stat().st_size if tools_path.exists() else 0
    return probe


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_summary(out_dir: pathlib.Path, final_state: dict[str, Any]) -> None:
    checks = final_state["checks"]
    status_rows = "\n".join(
        f"| {name} | `{value}` |" for name, value in [
            ("state", final_state["state"]),
            ("python", final_state["python"]["version"]),
            ("uv_available", final_state["environment"]["uv_available"]),
            ("uv_sync_succeeded", final_state["environment"]["uv_sync_succeeded"]),
            ("tau2_import_worked", checks["import"]["ok"]),
            ("tau2_cli_worked", checks["cli_help"]["ok"]),
            ("tau2_check_data_worked", checks["check_data"]["ok"]),
            ("tau2_intro_worked", checks["intro"]["ok"]),
            ("no_llm_tests_ran", checks["pytest_no_llm"]["ran"]),
            ("real_no_llm_episode_ran", final_state["episode"]["ran"]),
        ]
    )
    probe = final_state["domain_probe"]
    content = f"""# Real tau2 local smoke summary

Status: `{final_state['state']}`

Run directory: `{final_state['output_dir']}`

This smoke exercises the vendored tau2-bench source locally without API keys, paid LLM calls, or model-backed benchmark episodes.

## Key results

| Check | Result |
| --- | --- |
{status_rows}

## Command strategy

Install command: `{final_state['environment']['install_command'] or 'not run'}`

Execution prefix: `{final_state['environment']['execution_prefix'] or 'not available'}`

## Mock domain probe

- Tasks: `{probe.get('task_count', 0)}`
- Policy exists and non-empty: `{probe.get('policy_non_empty')}`
- DB files: `{probe.get('db_files')}`
- API-level probe: `{probe.get('api_probe_status')}`

## Episode status

`{final_state['episode']['status']}`

Reason: {final_state['episode']['reason']}

## Logs

- `raw.log`
- `final_state.json`
- `domain_probe.json`
- `tau2_cli_help.txt`
- `tau2_run_help.txt`
- `tau2_check_data.log`
- `tau2_intro.log`
- `pytest_collect.log`
- `pytest_no_llm.log`
"""
    (out_dir / "summary.md").write_text(content, encoding="utf-8")


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    recorder = Recorder(out_dir)
    env = base_env()

    source_results, source_ok, vendor_missing = source_checks()
    pyproject = parse_pyproject() if (VENDOR_DIR / "pyproject.toml").exists() else {"exists": False}
    domain_probe = file_domain_probe() if MOCK_DOMAIN_DIR.exists() else {"mode": "file", "task_count": 0}

    python_info = {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "satisfies_tau2_requirement": python_satisfies(pyproject.get("requires_python")),
        "tau2_requires_python": pyproject.get("requires_python"),
    }
    uv_path = shutil.which("uv")

    final_state: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "state": SOURCE_ONLY_STATUS,
        "output_dir": rel(out_dir),
        "raw_log_path": rel(out_dir / "raw.log"),
        "summary_path": rel(out_dir / "summary.md"),
        "final_state_path": rel(out_dir / "final_state.json"),
        "source_checks": source_results,
        "source_checks_passed": source_ok,
        "pyproject": pyproject,
        "python": python_info,
        "environment": {
            "uv_available": uv_path is not None,
            "uv_path": uv_path,
            "uv_sync_succeeded": False,
            "dependencies_installed": False,
            "install_command": None,
            "execution_prefix": None,
            "api_keys_removed_for_child_processes": API_KEY_NAMES,
            "tau2_data_dir": env["TAU2_DATA_DIR"],
        },
        "checks": {
            "import": {"ok": False, "returncode": None},
            "cli_available": {"ok": False, "returncode": None},
            "cli_help": {"ok": False, "returncode": None},
            "run_help": {"ok": False, "returncode": None},
            "check_data": {"ok": False, "returncode": None},
            "intro": {"ok": False, "returncode": None},
            "pytest_collect": {"ok": False, "returncode": None, "ran": False},
            "pytest_no_llm": {"ok": False, "returncode": None, "ran": False, "tests": NO_LLM_TESTS},
        },
        "domain_probe": domain_probe,
        "episode": {
            "ran": False,
            "status": "real_tau2_episode_not_available_without_llm",
            "reason": "Local source registers LLM-backed agent factories and a dummy user, but no dummy/non-LLM agent factory for tau2 run.",
        },
        "llm_api_calls_made": False,
        "model_backed_benchmark_episodes_ran": False,
    }

    recorder.log(rel(out_dir))
    if not source_ok:
        final_state["state"] = ENV_MISSING_STATUS if vendor_missing else FAILED_STATUS
        write_json(out_dir / "domain_probe.json", domain_probe)
        write_json(out_dir / "final_state.json", final_state)
        write_summary(out_dir, final_state)
        recorder.log(final_state["state"])
        recorder.flush()
        return 1

    command_prefix: list[str] | None = None
    if uv_path:
        install_command = [uv_path, "sync"]
        final_state["environment"]["install_command"] = "uv sync"
        try:
            completed = run_command(install_command, cwd=VENDOR_DIR, env=env, timeout=240)
        except subprocess.TimeoutExpired as exc:
            completed = subprocess.CompletedProcess(install_command, 124, stdout=f"uv sync timed out after {exc.timeout}s\n")
        recorder.command("uv sync --extra dev", completed)
        final_state["environment"]["uv_sync_returncode"] = completed.returncode
        if completed.returncode == 0:
            final_state["environment"]["uv_sync_succeeded"] = True
            final_state["environment"]["dependencies_installed"] = True
            command_prefix = [uv_path, "run"]
            final_state["environment"]["execution_prefix"] = "uv run"

    if command_prefix is None:
        src_path = str(VENDOR_DIR / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        command_prefix = [sys.executable, "-m"]
        final_state["environment"]["execution_prefix"] = f"{sys.executable} -m with PYTHONPATH={src_path}"

    import_cmd = command_prefix + ["python", "-c", "import tau2, tau2.cli; print('tau2_import_ok')"] if command_prefix[:2] == [uv_path, "run"] else [sys.executable, "-c", "import tau2, tau2.cli; print('tau2_import_ok')"]
    completed = run_command(import_cmd, cwd=VENDOR_DIR, env=env, timeout=60)
    recorder.command("tau2 import", completed)
    final_state["checks"]["import"] = {"ok": completed.returncode == 0, "returncode": completed.returncode}
    if completed.returncode != 0:
        final_state["state"] = SOURCE_ONLY_STATUS
        if uv_path and not final_state["environment"].get("uv_sync_succeeded"):
            final_state["environment"]["install_failure_degraded_to_source_only"] = True
        write_json(out_dir / "domain_probe.json", domain_probe)
        write_json(out_dir / "final_state.json", final_state)
        write_summary(out_dir, final_state)
        recorder.log(final_state["state"])
        recorder.flush()
        return 0
    final_state["state"] = IMPORT_STATUS

    api_probe_cmd = (
        command_prefix
        + [
            "python",
            "-c",
            (
                "import json; from tau2.run import get_options, get_tasks; "
                "from tau2.registry import registry; "
                "env=registry.get_env_constructor('mock')(); "
                "tasks=get_tasks('mock'); "
                "print(json.dumps({'domains': get_options().domains, 'agents': get_options().agents, "
                "'users': get_options().users, 'mock_task_count': len(tasks), "
                "'mock_first_task_id': tasks[0].id if tasks else None, "
                "'mock_tool_count': len(env.tools.get_tools())}))"
            ),
        ]
        if command_prefix[:2] == [uv_path, "run"]
        else [
            sys.executable,
            "-c",
            (
                "import json; from tau2.run import get_options, get_tasks; "
                "from tau2.registry import registry; "
                "env=registry.get_env_constructor('mock')(); "
                "tasks=get_tasks('mock'); "
                "print(json.dumps({'domains': get_options().domains, 'agents': get_options().agents, "
                "'users': get_options().users, 'mock_task_count': len(tasks), "
                "'mock_first_task_id': tasks[0].id if tasks else None, "
                "'mock_tool_count': len(env.tools.get_tools())}))"
            ),
        ]
    )
    completed = run_command(api_probe_cmd, cwd=VENDOR_DIR, env=env, timeout=60)
    recorder.command("tau2 api domain probe", completed)
    if completed.returncode == 0:
        try:
            api_data = json.loads(completed.stdout.strip().splitlines()[-1])
            domain_probe.update(api_data)
            domain_probe["api_probe_status"] = "api_probe_passed"
        except Exception as exc:  # noqa: BLE001
            domain_probe["api_probe_status"] = f"api_probe_parse_failed: {exc}"
    else:
        domain_probe["api_probe_status"] = "api_probe_failed"

    cli_base = command_prefix + ["tau2"] if command_prefix[:2] == [uv_path, "run"] else [sys.executable, "-m", "tau2.cli"]
    cli_available_cmd = cli_base + ["--help"]
    for key, args, filename in [
        ("cli_help", ["--help"], "tau2_cli_help.txt"),
        ("run_help", ["run", "--help"], "tau2_run_help.txt"),
        ("check_data", ["check-data"], "tau2_check_data.log"),
        ("intro", ["intro"], "tau2_intro.log"),
    ]:
        completed = run_command(cli_base + args, cwd=VENDOR_DIR, env=env, timeout=90, output_file=out_dir / filename)
        recorder.command(f"tau2 {' '.join(args)}", completed)
        final_state["checks"][key] = {"ok": completed.returncode == 0, "returncode": completed.returncode, "artifact": rel(out_dir / filename)}
        if completed.returncode != 0:
            final_state["state"] = FAILED_STATUS
            write_json(out_dir / "domain_probe.json", domain_probe)
            write_json(out_dir / "final_state.json", final_state)
            write_summary(out_dir, final_state)
            recorder.log(final_state["state"])
            recorder.flush()
            return 1
    final_state["checks"]["cli_available"] = {"ok": True, "returncode": 0}
    final_state["state"] = DATA_STATUS

    pytest_env = env.copy()
    venv_site = VENDOR_DIR / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    pytest_paths = [str(VENDOR_DIR / "src")]
    if venv_site.exists():
        pytest_paths.append(str(venv_site))
    pytest_env["PYTHONPATH"] = os.pathsep.join(pytest_paths + ([pytest_env["PYTHONPATH"]] if pytest_env.get("PYTHONPATH") else []))
    pytest_base = [sys.executable, "-m", "pytest"]
    final_state["environment"]["pytest_execution_prefix"] = f"{sys.executable} -m pytest with PYTHONPATH={pytest_env['PYTHONPATH']}"
    completed = run_command(pytest_base + ["--collect-only", "-q", *NO_LLM_TESTS], cwd=VENDOR_DIR, env=pytest_env, timeout=120, output_file=out_dir / "pytest_collect.log")
    recorder.command("pytest collect no-LLM subset", completed)
    final_state["checks"]["pytest_collect"] = {"ok": completed.returncode == 0, "returncode": completed.returncode, "ran": True, "artifact": rel(out_dir / "pytest_collect.log")}
    if completed.returncode != 0:
        final_state["state"] = FAILED_STATUS
        write_json(out_dir / "domain_probe.json", domain_probe)
        write_json(out_dir / "final_state.json", final_state)
        write_summary(out_dir, final_state)
        recorder.log(final_state["state"])
        recorder.flush()
        return 1

    completed = run_command(pytest_base + ["-q", *NO_LLM_TESTS], cwd=VENDOR_DIR, env=pytest_env, timeout=180, output_file=out_dir / "pytest_no_llm.log")
    recorder.command("pytest no-LLM subset", completed)
    final_state["checks"]["pytest_no_llm"] = {"ok": completed.returncode == 0, "returncode": completed.returncode, "ran": True, "tests": NO_LLM_TESTS, "artifact": rel(out_dir / "pytest_no_llm.log")}
    if completed.returncode != 0:
        final_state["state"] = FAILED_STATUS
        write_json(out_dir / "domain_probe.json", domain_probe)
        write_json(out_dir / "final_state.json", final_state)
        write_summary(out_dir, final_state)
        recorder.log(final_state["state"])
        recorder.flush()
        return 1

    final_state["state"] = PASS_STATUS
    final_state["status_history"] = [SOURCE_ONLY_STATUS, IMPORT_STATUS, CLI_STATUS, DATA_STATUS, TESTS_STATUS, PASS_STATUS]
    write_json(out_dir / "domain_probe.json", domain_probe)
    final_state["domain_probe"] = domain_probe
    write_json(out_dir / "final_state.json", final_state)
    write_summary(out_dir, final_state)
    recorder.log(final_state["state"])
    recorder.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
