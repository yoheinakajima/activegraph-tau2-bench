#!/usr/bin/env python3
"""Explicit opt-in model-backed tau2 baseline runner."""
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
RUNS_DIR = REPO_ROOT / "runs"
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
TAU2_DATA_DIR = VENDOR_DIR / "data"

READY_NOT_RUN_STATUS = "tau2_model_baseline_ready_not_run"
REFUSED_MISSING_ACK_STATUS = "tau2_model_baseline_refused_missing_ack"
REFUSED_MISSING_MODEL_STATUS = "tau2_model_baseline_refused_missing_model"
REFUSED_NON_MOCK_DOMAIN_STATUS = "tau2_model_baseline_refused_non_mock_domain"
ENV_MISSING_STATUS = "tau2_model_baseline_env_missing"
PASSED_STATUS = "tau2_model_baseline_passed"
FAILED_STATUS = "tau2_model_baseline_failed"

DEFAULT_DOMAIN = "mock"
DEFAULT_MAX_STEPS = 5
DEFAULT_NUM_TASKS = 1
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

API_KEY_LIKE_NAMES = sorted(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "AZURE_OPENAI_API_KEY",
        "XAI_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "GROQ_API_KEY",
        "TOGETHER_API_KEY",
        "FIREWORKS_API_KEY",
        "PERPLEXITYAI_API_KEY",
        "PERPLEXITY_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        *[name for names in API_KEY_ENV_BY_PROVIDER.values() for name in names],
    }
)

SOURCE_INSPECTION_FILES = [
    "vendor/tau2-bench/docs/cli-reference.md",
    "vendor/tau2-bench/docs/running_simulations.md",
    "vendor/tau2-bench/src/tau2/cli.py",
    "vendor/tau2-bench/src/tau2/run.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicit opt-in, model-backed tau2 baseline episode. "
            "This may call paid provider APIs only when all guardrails are acknowledged."
        )
    )
    parser.add_argument("--provider", help="LiteLLM/tau2 provider prefix, for example openai or anthropic.")
    parser.add_argument("--model", help="Model name, for example gpt-4.1-mini. Combined as <provider>/<model> for tau2.")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="tau2 domain to run. Defaults to mock.")
    parser.add_argument("--task-id", help="Single tau2 task ID or index to run. If omitted, tau2 receives --num-tasks 1.")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help=f"Maximum tau2 text-mode steps. Default: {DEFAULT_MAX_STEPS}.")
    parser.add_argument("--num-tasks", type=int, default=DEFAULT_NUM_TASKS, help=f"Number of tasks when --task-id is omitted. Default: {DEFAULT_NUM_TASKS}.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help=f"tau2 --max-concurrency. Default: {DEFAULT_CONCURRENCY}.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help=f"Wrapper subprocess timeout. Default: {DEFAULT_TIMEOUT_SECONDS}.")
    parser.add_argument(
        "--allow-non-mock-domain",
        action="store_true",
        help="Second explicit override required before running any domain other than mock.",
    )
    parser.add_argument(
        "--yes-i-understand-this-may-call-paid-apis",
        action="store_true",
        help="Required acknowledgement that this command may call paid model APIs.",
    )
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
        any_key_present = any(presence.values())
        return {
            "known_provider": False,
            "required_env_vars": [],
            "satisfied": any_key_present,
            "reason": "unknown provider; requiring at least one API-key-like environment variable",
        }
    return {
        "known_provider": True,
        "required_env_vars": required,
        "satisfied": any(presence.get(name, False) for name in required),
    }


def build_tau2_command(args: argparse.Namespace, tau2_output_dir: pathlib.Path) -> list[str]:
    llm_name = provider_model_name(args.provider, args.model)
    command = [
        "uv",
        "run",
        "tau2",
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
        if not path.is_file():
            continue
        relative = path.relative_to(tau2_output_dir)
        destination = artifacts_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append({"source": rel(path), "copy": rel(destination)})
    return copied


def write_artifacts(
    out_dir: pathlib.Path,
    *,
    status: str,
    args: argparse.Namespace,
    command: list[str] | None,
    api_presence: dict[str, bool],
    provider_env: dict[str, Any],
    tau2_output_dir: pathlib.Path,
    copied_artifacts: list[dict[str, str]] | None = None,
    returncode: int | None = None,
    reason: str | None = None,
) -> None:
    final_state = {
        "status": status,
        "reason": reason,
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "paid_api_acknowledged": bool(args.yes_i_understand_this_may_call_paid_apis),
        "provider": args.provider,
        "model": args.model,
        "tau2_model_name": provider_model_name(args.provider, args.model) if args.provider and args.model else None,
        "domain": args.domain,
        "task_id": args.task_id,
        "num_tasks": args.num_tasks,
        "max_steps": args.max_steps,
        "concurrency": args.concurrency,
        "allow_non_mock_domain": bool(args.allow_non_mock_domain),
        "api_key_presence": api_presence,
        "provider_env": provider_env,
        "tau2_command": command,
        "tau2_command_display": shell_join(command) if command else None,
        "tau2_cwd": rel(VENDOR_DIR),
        "tau2_data_dir": rel(TAU2_DATA_DIR),
        "tau2_output_path": rel(tau2_output_dir),
        "copied_tau2_artifacts": copied_artifacts or [],
        "returncode": returncode,
        "source_inspection_files": SOURCE_INSPECTION_FILES,
    }
    (out_dir / "final_state.json").write_text(json.dumps(final_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary_lines = [
        "# tau2 model baseline run",
        "",
        f"- status: `{status}`",
        f"- reason: {reason or 'n/a'}",
        f"- paid API acknowledgement: `{bool(args.yes_i_understand_this_may_call_paid_apis)}`",
        f"- provider: `{args.provider}`",
        f"- model: `{args.model}`",
        f"- tau2 model name: `{final_state['tau2_model_name']}`",
        f"- domain: `{args.domain}`",
        f"- task_id: `{args.task_id}`",
        f"- num_tasks: `{args.num_tasks}`",
        f"- max_steps: `{args.max_steps}`",
        f"- concurrency: `{args.concurrency}`",
        f"- tau2 output path: `{rel(tau2_output_dir)}`",
        f"- returncode: `{returncode}`",
        "",
        "## tau2 command",
        "",
        "```bash",
        f"cd {rel(VENDOR_DIR)} && {shell_join(command) if command else '(not built)' }",
        "```",
        "",
        "## API key-like environment variable presence",
        "",
    ]
    for name, present in api_presence.items():
        summary_lines.append(f"- `{name}`: `{present}`")
    summary_lines.extend(
        [
            "",
            "No API key values are printed or stored by this wrapper.",
            "",
            "## Copied tau2 artifacts",
            "",
        ]
    )
    if copied_artifacts:
        summary_lines.extend(f"- `{item['copy']}` copied from `{item['source']}`" for item in copied_artifacts)
    else:
        summary_lines.append("- none")
    (out_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


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
    command: list[str] | None = None
    status = READY_NOT_RUN_STATUS
    reason: str | None = None
    returncode: int | None = None
    copied_artifacts: list[dict[str, str]] = []

    if not args.yes_i_understand_this_may_call_paid_apis:
        status = REFUSED_MISSING_ACK_STATUS
        reason = "missing explicit paid-API acknowledgement flag"
    elif not args.provider or not args.model:
        status = REFUSED_MISSING_MODEL_STATUS
        reason = "provider and model are both required"
    elif args.domain != DEFAULT_DOMAIN and not args.allow_non_mock_domain:
        status = REFUSED_NON_MOCK_DOMAIN_STATUS
        reason = "non-mock domain requires --allow-non-mock-domain"
    elif args.max_steps < 1:
        status = FAILED_STATUS
        reason = "--max-steps must be at least 1"
    elif args.concurrency != DEFAULT_CONCURRENCY:
        status = FAILED_STATUS
        reason = "this first baseline wrapper only permits concurrency=1"
    elif args.num_tasks != DEFAULT_NUM_TASKS and args.task_id is None:
        status = FAILED_STATUS
        reason = "this first baseline wrapper only permits one task"
    else:
        command = build_tau2_command(args, tau2_output_dir)
        if not provider_env.get("satisfied", False):
            status = ENV_MISSING_STATUS
            reason = "required provider API-key-like environment variables are not present"
        else:
            env = os.environ.copy()
            env["TAU2_DATA_DIR"] = str(TAU2_DATA_DIR)
            env["PYTHONUNBUFFERED"] = "1"
            env.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
            with raw_log.open("w", encoding="utf-8") as handle:
                handle.write(f"status_start={READY_NOT_RUN_STATUS}\n")
                handle.write(f"cwd={rel(VENDOR_DIR)}\n")
                handle.write(f"command={shell_join(command)}\n")
                handle.write("api_key_values_printed=false\n\n")
                handle.flush()
                completed = subprocess.run(
                    command,
                    cwd=VENDOR_DIR,
                    env=env,
                    check=False,
                    text=True,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    timeout=args.timeout_seconds,
                )
            returncode = completed.returncode
            copied_artifacts = copy_tau2_artifacts(tau2_output_dir, artifacts_dir)
            status = PASSED_STATUS if completed.returncode == 0 else FAILED_STATUS
            reason = "tau2 completed successfully" if completed.returncode == 0 else "tau2 exited non-zero"

    if not raw_log.exists():
        raw_lines = [
            f"status={status}",
            f"reason={reason}",
            f"output_dir={rel(out_dir)}",
            "tau2_executed=false",
        ]
        if command:
            raw_lines.append(f"command={shell_join(command)}")
        raw_lines.append("api_key_values_printed=false")
        raw_log.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    write_artifacts(
        out_dir,
        status=status,
        args=args,
        command=command,
        api_presence=api_presence,
        provider_env=provider_env,
        tau2_output_dir=tau2_output_dir,
        copied_artifacts=copied_artifacts,
        returncode=returncode,
        reason=reason,
    )
    print(rel(out_dir))
    print(status)
    return 1 if status == FAILED_STATUS else 0


if __name__ == "__main__":
    sys.exit(main())
