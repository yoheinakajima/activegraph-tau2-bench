#!/usr/bin/env python3
"""Explicit opt-in model-backed tau2 baseline runner with runtime trace hooks."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUNS_DIR = REPO_ROOT / "runs"
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
TAU2_DATA_DIR = VENDOR_DIR / "data"
TRACE_BOOTSTRAP = REPO_ROOT / "experiments" / "tau2_runtime_trace" / "traced_tau2_cli.py"

REFUSED_MISSING_ACK_STATUS = "tau2_runtime_traced_baseline_refused_missing_ack"
REFUSED_MISSING_MODEL_STATUS = "tau2_runtime_traced_baseline_refused_missing_model"
PASSED_STATUS = "tau2_runtime_traced_baseline_passed"
FAILED_STATUS = "tau2_runtime_traced_baseline_failed"
REFUSED_NON_MOCK_DOMAIN_STATUS = "tau2_runtime_traced_baseline_refused_non_mock_domain"
ENV_MISSING_STATUS = "tau2_runtime_traced_baseline_refused_missing_provider_env"
REFUSED_INVALID_TASK_ID_STATUS = "tau2_runtime_traced_baseline_refused_invalid_task_id"
READY_STATUS = "tau2_runtime_traced_baseline_ready_not_run"

DEFAULT_DOMAIN = "mock"
DEFAULT_MAX_STEPS = 2
DEFAULT_NUM_TASKS = 1
DEFAULT_TASK_ID = "create_task_1"
DEFAULT_CONCURRENCY = 1
DEFAULT_TIMEOUT_SECONDS = 900

API_KEY_ENV_BY_PROVIDER = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "claude": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "vertex_ai": ["GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT"],
    "azure": ["AZURE_OPENAI_API_KEY"],
    "azure_openai": ["AZURE_OPENAI_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "together_ai": ["TOGETHER_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "fireworks_ai": ["FIREWORKS_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "perplexity": ["PERPLEXITYAI_API_KEY", "PERPLEXITY_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
}
API_KEY_LIKE_NAMES = sorted({name for names in API_KEY_ENV_BY_PROVIDER.values() for name in names})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an explicit paid opt-in tau2 baseline with runtime trace-only instrumentation.")
    parser.add_argument("--provider", help="LiteLLM/tau2 provider prefix, for example openai or anthropic.")
    parser.add_argument("--model", help="Model name. Combined as <provider>/<model> unless already prefixed.")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="tau2 domain to run. Defaults to mock.")
    parser.add_argument(
        "--task-id",
        help=(
            "Single tau2 task ID or zero-based numeric index. "
            f"If omitted with no --num-tasks, defaults to {DEFAULT_TASK_ID}."
        ),
    )
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help=f"Maximum tau2 text-mode steps. Default: {DEFAULT_MAX_STEPS}.")
    parser.add_argument(
        "--num-tasks",
        type=int,
        help=(
            "Number of tasks to let tau2 select when --task-id is omitted. "
            f"If both task selectors are omitted, the wrapper defaults to --task-id {DEFAULT_TASK_ID}."
        ),
    )
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help=f"tau2 --max-concurrency. Default: {DEFAULT_CONCURRENCY}.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help=f"Wrapper subprocess timeout. Default: {DEFAULT_TIMEOUT_SECONDS}.")
    parser.add_argument("--allow-non-mock-domain", action="store_true", help="Second explicit override required for any domain other than mock.")
    parser.add_argument("--yes-i-understand-this-may-call-paid-apis", action="store_true", help="Required acknowledgement that this command may call paid model APIs.")
    parser.add_argument("--enable-write-intent-observer", action="store_true", help="Also emit passive write-intent observer artifacts from runtime tool dispatch hooks. Observational only; no control.")
    return parser.parse_args()


def timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def shell_join(command: list[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in command)


def provider_model_name(provider: str, model: str) -> str:
    cleaned_provider = provider.strip().strip("/")
    cleaned_model = model.strip()
    if cleaned_model.startswith(f"{cleaned_provider}/"):
        return cleaned_model
    return f"{cleaned_provider}/{cleaned_model}"


def api_key_presence() -> dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in API_KEY_LIKE_NAMES}


def provider_env_status(provider: str | None, presence: dict[str, bool]) -> dict[str, Any]:
    if not provider:
        return {"known_provider": False, "required_env_vars": [], "satisfied": False}
    normalized = provider.strip().lower()
    required = API_KEY_ENV_BY_PROVIDER.get(normalized)
    if required is None:
        return {"known_provider": False, "required_env_vars": [], "satisfied": any(presence.values()), "reason": "unknown provider; requiring at least one API-key-like environment variable"}
    return {"known_provider": True, "required_env_vars": required, "satisfied": any(presence.get(name, False) for name in required)}


def load_domain_task_ids(domain: str) -> list[str]:
    task_file = TAU2_DATA_DIR / "tau2" / "domains" / domain / "tasks.json"
    if not task_file.is_file():
        raise ValueError(f"cannot resolve numeric --task-id because {rel(task_file)} does not exist")
    tasks = json.loads(task_file.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError(f"cannot resolve numeric --task-id because {rel(task_file)} is not a task list")
    task_ids = [task.get("id") for task in tasks if isinstance(task, dict) and isinstance(task.get("id"), str)]
    if not task_ids:
        raise ValueError(f"cannot resolve numeric --task-id because {rel(task_file)} contains no task IDs")
    return task_ids


def resolve_task_id_arg(task_id: str | None, domain: str) -> tuple[str | None, str | None]:
    if task_id is None:
        return None, None
    cleaned = str(task_id).strip()
    if not cleaned.isdigit():
        return cleaned, None
    task_ids = load_domain_task_ids(domain)
    index = int(cleaned)
    if index < 0 or index >= len(task_ids):
        raise ValueError(f"numeric --task-id {cleaned} is out of range for domain {domain!r}; valid indexes are 0..{len(task_ids) - 1}")
    return task_ids[index], f"numeric --task-id {cleaned} resolved to {task_ids[index]!r}"


def apply_task_selection(args: argparse.Namespace) -> tuple[str, str | None]:
    """Normalize wrapper task selection before building the tau2 command."""
    if args.task_id is not None:
        original_task_id = str(args.task_id).strip()
        args.task_id, note = resolve_task_id_arg(args.task_id, args.domain)
        return ("numeric_task_index" if original_task_id.isdigit() else "explicit_task_id"), note
    if args.num_tasks is not None:
        return "num_tasks", None
    args.task_id = DEFAULT_TASK_ID
    return "default_task_id", f"no task selector supplied; defaulted to {DEFAULT_TASK_ID!r}"


def build_tau2_command(args: argparse.Namespace, tau2_output_dir: pathlib.Path) -> list[str]:
    llm_name = provider_model_name(args.provider, args.model)
    command = [
        sys.executable,
        str(TRACE_BOOTSTRAP),
        "run",
        "--domain",
        args.domain,
        "--agent",
        "llm_agent",
        "--agent-llm",
        llm_name,
        "--user",
        "user_simulator",
        "--user-llm",
        llm_name,
        "--num-trials",
        "1",
        "--max-steps",
        str(args.max_steps),
        "--max-concurrency",
        str(args.concurrency),
        "--save-to",
        str(tau2_output_dir),
        "--log-level",
        "INFO",
    ]
    if args.task_id is not None:
        command.extend(["--task-ids", str(args.task_id)])
    else:
        command.extend(["--num-tasks", str(args.num_tasks)])
    return command


def copy_tau2_artifacts(tau2_output_dir: pathlib.Path, artifacts_dir: pathlib.Path) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    if not tau2_output_dir.exists():
        return copied
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(tau2_output_dir.rglob("*")):
        if path.is_file():
            dest = artifacts_dir / path.relative_to(tau2_output_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied.append({"source": rel(path), "copy": rel(dest)})
    return copied


def task_selection_state(args: argparse.Namespace, task_selection_mode: str | None, task_id_resolution_note: str | None) -> dict[str, Any]:
    return {
        "task_id": args.task_id,
        "task_id_resolution_note": task_id_resolution_note,
        "task_selection_mode": task_selection_mode,
        "num_tasks": args.num_tasks,
    }


def update_runtime_final_state(out_dir: pathlib.Path, extra: dict[str, Any]) -> None:
    path = out_dir / "runtime_trace_final_state.json"
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {}
    payload.update(extra)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_refusal_artifacts(out_dir: pathlib.Path, status: str, reason: str, args: argparse.Namespace, command: list[str] | None, api_presence: dict[str, bool], provider_env: dict[str, Any], task_selection_mode: str | None, task_id_resolution_note: str | None) -> None:
    from experiments.tau2_runtime_trace.runtime_trace import RuntimeTraceWriter, inspect_hook_targets, write_final_state, write_hook_map, write_summary

    writer = RuntimeTraceWriter(out_dir, phase="runtime_traced_baseline_refusal")
    inspected = inspect_hook_targets()
    writer.record(component="tau2_runtime_trace.wrapper", event_type="traced_baseline_refused", payload={"status": status, "reason": reason, "provider": args.provider, "model_present": bool(args.model)})
    write_hook_map(out_dir, inspected, [], list(inspected.keys()))
    write_final_state(
        out_dir,
        status,
        writer,
        extra={
            "reason": reason,
            "tau2_executed": False,
            "api_key_presence": api_presence,
            "provider_env": provider_env,
            "tau2_command": command,
            "tau2_command_display": shell_join(command) if command else None,
            **task_selection_state(args, task_selection_mode, task_id_resolution_note),
        },
    )
    write_summary(out_dir, status, writer, validated=[], deferred=list(inspected.keys()), command=shell_join(command) if command else "not built/refused")
    writer.close()


def write_wrapper_summary(out_dir: pathlib.Path, status: str, reason: str | None, args: argparse.Namespace, command: list[str] | None, api_presence: dict[str, bool], provider_env: dict[str, Any], copied_artifacts: list[dict[str, str]], returncode: int | None) -> None:
    lines = [
        "# tau2 runtime traced baseline wrapper",
        "",
        f"- status: `{status}`",
        f"- reason: {reason or 'n/a'}",
        f"- provider: `{args.provider}`",
        f"- model: `{args.model}`",
        f"- paid API acknowledgement: `{bool(args.yes_i_understand_this_may_call_paid_apis)}`",
        f"- tau2 executed: `{returncode is not None}`",
        f"- returncode: `{returncode}`",
        f"- command: `{shell_join(command) if command else 'not built'}`",
        f"- passive write-intent observer enabled: `{bool(args.enable_write_intent_observer)}`",
        "",
        "## API key-like environment variable presence",
        "",
    ]
    lines.extend(f"- `{name}`: `{present}`" for name, present in api_presence.items())
    lines.extend(["", f"Provider env status: `{provider_env}`", "", "No API key values are printed or stored by this wrapper.", "", "## Copied tau2 artifacts", ""])
    lines.extend(f"- `{item['copy']}` copied from `{item['source']}`" for item in copied_artifacts) if copied_artifacts else lines.append("- none")
    (out_dir / "wrapper_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = RUNS_DIR / timestamp()
    out_dir.mkdir(parents=True, exist_ok=False)
    raw_log = out_dir / "raw.log"
    tau2_output_dir = out_dir / "tau2_output"
    artifacts_dir = out_dir / "tau2_artifacts"
    api_presence = api_key_presence()
    provider_env = provider_env_status(args.provider, api_presence)
    status = READY_STATUS
    reason: str | None = None
    command: list[str] | None = None
    copied_artifacts: list[dict[str, str]] = []
    returncode: int | None = None
    task_id_resolution_note: str | None = None
    task_selection_mode: str | None = None

    if not args.provider or not args.model:
        status = REFUSED_MISSING_MODEL_STATUS
        reason = "provider and model are both required"
    elif not args.yes_i_understand_this_may_call_paid_apis:
        status = REFUSED_MISSING_ACK_STATUS
        reason = "missing explicit paid-API acknowledgement flag"
    elif args.domain != DEFAULT_DOMAIN and not args.allow_non_mock_domain:
        status = REFUSED_NON_MOCK_DOMAIN_STATUS
        reason = "non-mock domain requires --allow-non-mock-domain"
    elif args.max_steps < 1:
        status = FAILED_STATUS
        reason = "--max-steps must be at least 1"
    elif args.concurrency != DEFAULT_CONCURRENCY:
        status = FAILED_STATUS
        reason = "runtime traced spike only permits concurrency=1"
    elif args.num_tasks is not None and args.num_tasks < 1:
        status = FAILED_STATUS
        reason = "--num-tasks must be at least 1"
    else:
        try:
            task_selection_mode, task_id_resolution_note = apply_task_selection(args)
            command = build_tau2_command(args, tau2_output_dir)
        except ValueError as exc:
            status = REFUSED_INVALID_TASK_ID_STATUS
            reason = str(exc)
        if status == READY_STATUS and not provider_env.get("satisfied", False):
            status = ENV_MISSING_STATUS
            reason = "required provider API-key-like environment variables are not present"
        elif status == READY_STATUS:
            env = os.environ.copy()
            env["TAU2_DATA_DIR"] = str(TAU2_DATA_DIR)
            env["PYTHONUNBUFFERED"] = "1"
            env["TAU2_RUNTIME_TRACE_RUN_DIR"] = str(out_dir)
            env["TAU2_RUNTIME_TRACE_PENDING_STATUS"] = FAILED_STATUS
            if args.enable_write_intent_observer:
                env["TAU2_WRITE_INTENT_OBSERVER_ENABLED"] = "1"
            env.setdefault("PYTHONPATH", str(REPO_ROOT))
            env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + str(VENDOR_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
            env.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
            with raw_log.open("w", encoding="utf-8") as handle:
                handle.write(f"status_start={READY_STATUS}\n")
                handle.write(f"cwd={rel(VENDOR_DIR)}\n")
                handle.write(f"command={shell_join(command)}\n")
                handle.write("api_key_values_printed=false\n\n")
                handle.flush()
                completed = subprocess.run(command, cwd=VENDOR_DIR, env=env, check=False, text=True, stdout=handle, stderr=subprocess.STDOUT, timeout=args.timeout_seconds)
            returncode = completed.returncode
            copied_artifacts = copy_tau2_artifacts(tau2_output_dir, artifacts_dir)
            status = PASSED_STATUS if completed.returncode == 0 else FAILED_STATUS
            reason = "tau2 completed successfully" if completed.returncode == 0 else "tau2 exited non-zero"
            update_runtime_final_state(
                out_dir,
                {
                    "status": status,
                    "reason": reason,
                    "returncode": returncode,
                    "tau2_command": command,
                    "tau2_command_display": shell_join(command),
                    "tau2_output_path": rel(tau2_output_dir),
                    "copied_tau2_artifacts": copied_artifacts,
                    **task_selection_state(args, task_selection_mode, task_id_resolution_note),
                },
            )

    if returncode is None:
        if command is None and args.provider and args.model and status != REFUSED_INVALID_TASK_ID_STATUS:
            try:
                if task_selection_mode is None:
                    task_selection_mode, task_id_resolution_note = apply_task_selection(args)
                command = build_tau2_command(args, tau2_output_dir)
            except ValueError as exc:
                status = REFUSED_INVALID_TASK_ID_STATUS
                reason = str(exc)
        raw_log.write_text(f"status={status}\nreason={reason}\noutput_dir={rel(out_dir)}\ntau2_executed=false\napi_key_values_printed=false\n", encoding="utf-8")
        write_refusal_artifacts(out_dir, status, reason or "refused", args, command, api_presence, provider_env, task_selection_mode, task_id_resolution_note)

    write_wrapper_summary(out_dir, status, reason, args, command, api_presence, provider_env, copied_artifacts, returncode)
    print(rel(out_dir))
    print(status)
    return 1 if status == FAILED_STATUS else 0


if __name__ == "__main__":
    sys.exit(main())
