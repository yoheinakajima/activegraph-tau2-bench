#!/usr/bin/env python3
"""Explicit opt-in prompt/control variant runner for airline task 8."""
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
PROMPT_VARIANT_BOOTSTRAP = REPO_ROOT / "experiments" / "tau2_prompt_variant" / "prompt_variant_tau2_cli.py"

DOMAIN = "airline"
TASK_ID = "8"
DEFAULT_CONCURRENCY = 1
DEFAULT_TIMEOUT_SECONDS = 1800
PROMPT_VARIANT = (
    "Treat this as a new booking request unless the user explicitly says they are modifying an existing booking. "
    "Preserve all named passengers unless the user explicitly removes one. "
    "If booking a reservation for multiple passengers, include every eligible named passenger in the booking."
)

REFUSED_MISSING_MODEL_STATUS = "airline_task8_prompt_variant_refused_missing_model"
REFUSED_MISSING_ACK_STATUS = "airline_task8_prompt_variant_refused_missing_ack"
REFUSED_MISSING_PROVIDER_ENV_STATUS = "airline_task8_prompt_variant_refused_missing_provider_env"
FAILED_STATUS = "airline_task8_prompt_variant_failed"
PASSED_STATUS = "airline_task8_prompt_variant_passed"
READY_STATUS = "airline_task8_prompt_variant_ready_not_run"

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
SOURCE_INSPECTION = {
    "tau2_cli_flags": "vendor/tau2-bench/src/tau2/cli.py exposes --agent-llm-args/--user-llm-args but no agent prompt or instruction append flag.",
    "tau2_agent_prompt_target": "vendor/tau2-bench/src/tau2/agent/llm_agent.py defines LLMAgent.system_prompt from AGENT_INSTRUCTION plus domain policy.",
    "repo_adapter": "experiments/tau2_prompt_variant/prompt_variant_tau2_cli.py appends the prompt variant with a process-local property wrapper outside vendor/tau2-bench.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run airline task 8 with a repo-owned, opt-in agent prompt/control variant. "
            "This command may call paid provider APIs only with explicit acknowledgement."
        )
    )
    parser.add_argument("--provider", required=False, help="LiteLLM/tau2 provider prefix, for example openai.")
    parser.add_argument("--model", required=False, help="Model name, for example gpt-4.1-mini. Combined as <provider>/<model> unless already prefixed.")
    parser.add_argument("--max-steps", type=int, default=30, help="Maximum tau2 text-mode steps. Default: 30.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help=f"Wrapper subprocess timeout. Default: {DEFAULT_TIMEOUT_SECONDS}.")
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
        return {
            "known_provider": False,
            "required_env_vars": [],
            "satisfied": any(presence.values()),
            "reason": "unknown provider; requiring at least one API-key-like environment variable",
        }
    return {"known_provider": True, "required_env_vars": required, "satisfied": any(presence.get(name, False) for name in required)}


def build_tau2_command(args: argparse.Namespace, tau2_output_dir: pathlib.Path) -> list[str]:
    llm_name = provider_model_name(args.provider, args.model)
    return [
        sys.executable,
        str(PROMPT_VARIANT_BOOTSTRAP),
        "run",
        "--domain",
        DOMAIN,
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
        str(DEFAULT_CONCURRENCY),
        "--task-ids",
        TASK_ID,
        "--save-to",
        str(tau2_output_dir),
        "--log-level",
        "INFO",
    ]


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


def write_prompt_variant_artifacts(out_dir: pathlib.Path) -> None:
    payload = {
        "domain": DOMAIN,
        "task_id": TASK_ID,
        "prompt_variant": PROMPT_VARIANT,
        "prompt_variant_target": "tau2.agent.llm_agent.LLMAgent.system_prompt",
        "adapter": rel(PROMPT_VARIANT_BOOTSTRAP),
        "vendor_tau2_bench_mutated": False,
        "activegraph_control": False,
        "source_inspection": SOURCE_INSPECTION,
    }
    (out_dir / "prompt_variant.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "prompt_variant.txt").write_text(PROMPT_VARIANT + "\n", encoding="utf-8")


def write_refusal_trace(out_dir: pathlib.Path, status: str, reason: str, args: argparse.Namespace, command: list[str] | None, api_presence: dict[str, bool], provider_env: dict[str, Any]) -> None:
    from experiments.tau2_runtime_trace.runtime_trace import RuntimeTraceWriter, inspect_hook_targets, write_final_state, write_hook_map, write_summary

    writer = RuntimeTraceWriter(out_dir, phase="airline_task8_prompt_variant_refusal")
    inspected = inspect_hook_targets()
    writer.record(
        component="airline_task8_prompt_variant.wrapper",
        event_type="prompt_variant_refused",
        payload={"status": status, "reason": reason, "provider": args.provider, "model_present": bool(args.model), "prompt_variant": PROMPT_VARIANT},
    )
    write_hook_map(out_dir, inspected, [], list(inspected.keys()))
    write_final_state(
        out_dir,
        status,
        writer,
        extra={
            "reason": reason,
            "domain": DOMAIN,
            "task_id": TASK_ID,
            "tau2_executed": False,
            "paid_llm_api_calls_made": False,
            "api_key_presence": api_presence,
            "provider_env": provider_env,
            "tau2_command": command,
            "tau2_command_display": shell_join(command) if command else None,
            "prompt_variant": PROMPT_VARIANT,
            "vendor_tau2_bench_mutated": False,
            "activegraph_control": False,
        },
    )
    write_summary(out_dir, status, writer, validated=[], deferred=list(inspected.keys()), command=shell_join(command) if command else "not built/refused", paid_llm_api_calls_made=False)
    writer.close()


def write_wrapper_summary(out_dir: pathlib.Path, status: str, reason: str | None, args: argparse.Namespace, command: list[str] | None, api_presence: dict[str, bool], provider_env: dict[str, Any], copied_artifacts: list[dict[str, str]], returncode: int | None) -> None:
    lines = [
        "# Airline task 8 prompt variant wrapper",
        "",
        f"- status: `{status}`",
        f"- reason: {reason or 'n/a'}",
        f"- domain: `{DOMAIN}`",
        f"- task id: `{TASK_ID}`",
        f"- provider: `{args.provider}`",
        f"- model: `{args.model}`",
        f"- max steps: `{args.max_steps}`",
        f"- concurrency: `{DEFAULT_CONCURRENCY}`",
        f"- paid API acknowledgement: `{bool(args.yes_i_understand_this_may_call_paid_apis)}`",
        f"- tau2 executed: `{returncode is not None}`",
        f"- paid LLM/API calls made: `{returncode is not None}`",
        f"- returncode: `{returncode}`",
        f"- command: `{shell_join(command) if command else 'not built'}`",
        f"- prompt/control variant: `{PROMPT_VARIANT}`",
        "- adapter mutates vendor/tau2-bench: `False`",
        "- ActiveGraph control added: `False`",
        "",
        "## API key-like environment variable presence",
        "",
    ]
    lines.extend(f"- `{name}`: `{present}`" for name, present in api_presence.items())
    lines.extend(["", f"Provider env status: `{provider_env}`", "", "No API key values are printed or stored by this wrapper.", "", "## Source inspection", ""])
    lines.extend(f"- {key}: {value}" for key, value in SOURCE_INSPECTION.items())
    lines.extend(["", "## Copied tau2 artifacts", ""])
    if copied_artifacts:
        lines.extend(f"- `{item['copy']}` copied from `{item['source']}`" for item in copied_artifacts)
    else:
        lines.append("- none")
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

    write_prompt_variant_artifacts(out_dir)

    if not args.provider or not args.model:
        status = REFUSED_MISSING_MODEL_STATUS
        reason = "provider and model are both required"
    elif not args.yes_i_understand_this_may_call_paid_apis:
        status = REFUSED_MISSING_ACK_STATUS
        reason = "missing explicit paid-API acknowledgement flag"
        command = build_tau2_command(args, tau2_output_dir)
    elif args.max_steps < 1:
        status = FAILED_STATUS
        reason = "--max-steps must be at least 1"
        command = build_tau2_command(args, tau2_output_dir)
    else:
        command = build_tau2_command(args, tau2_output_dir)
        if not provider_env.get("satisfied", False):
            status = REFUSED_MISSING_PROVIDER_ENV_STATUS
            reason = "required provider API-key-like environment variables are not present"
        else:
            env = os.environ.copy()
            env["TAU2_DATA_DIR"] = str(TAU2_DATA_DIR)
            env["PYTHONUNBUFFERED"] = "1"
            env["TAU2_RUNTIME_TRACE_RUN_DIR"] = str(out_dir)
            env["TAU2_RUNTIME_TRACE_PENDING_STATUS"] = FAILED_STATUS
            env["TAU2_PROMPT_VARIANT_STATUS_PREFIX"] = "airline_task8_prompt_variant"
            env["TAU2_AGENT_PROMPT_VARIANT_TEXT"] = PROMPT_VARIANT
            env.setdefault("PYTHONPATH", str(REPO_ROOT))
            env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + str(VENDOR_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
            env.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
            with raw_log.open("w", encoding="utf-8") as handle:
                handle.write(f"status_start={READY_STATUS}\n")
                handle.write(f"cwd={rel(VENDOR_DIR)}\n")
                handle.write(f"command={shell_join(command)}\n")
                handle.write(f"prompt_variant={PROMPT_VARIANT}\n")
                handle.write("api_key_values_printed=false\n\n")
                handle.flush()
                completed = subprocess.run(command, cwd=VENDOR_DIR, env=env, check=False, text=True, stdout=handle, stderr=subprocess.STDOUT, timeout=args.timeout_seconds)
            returncode = completed.returncode
            copied_artifacts = copy_tau2_artifacts(tau2_output_dir, artifacts_dir)
            status = PASSED_STATUS if completed.returncode == 0 else FAILED_STATUS
            reason = "tau2 completed successfully" if completed.returncode == 0 else "tau2 exited non-zero"

    if returncode is None:
        raw_log.write_text(
            f"status={status}\nreason={reason}\noutput_dir={rel(out_dir)}\ntau2_executed=false\npaid_llm_api_calls_made=false\napi_key_values_printed=false\n",
            encoding="utf-8",
        )
        write_refusal_trace(out_dir, status, reason or "refused", args, command, api_presence, provider_env)

    write_wrapper_summary(out_dir, status, reason, args, command, api_presence, provider_env, copied_artifacts, returncode)
    print(rel(out_dir))
    print(status)
    return 1 if status == FAILED_STATUS else 0


if __name__ == "__main__":
    sys.exit(main())
