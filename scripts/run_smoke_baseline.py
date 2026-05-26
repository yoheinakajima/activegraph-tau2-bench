#!/usr/bin/env python3
"""No-LLM baseline smoke harness for tau2-bench vendored checkout."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
RUNS_DIR = REPO_ROOT / "runs"

ALLOWED_STATES = {
    "upstream_missing",
    "install_failed",
    "import_failed",
    "data_check_failed",
    "source_inspection_only_passed",
    "no_llm_smoke_passed",
}


def run_cmd(cmd: list[str], cwd: pathlib.Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def short(txt: str, n: int = 3000) -> str:
    return txt[-n:] if txt else ""


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    checks: list[dict[str, Any]] = []
    state = "source_inspection_only_passed"

    checks.append({"name": "repo_root", "ok": REPO_ROOT.exists(), "path": str(REPO_ROOT)})

    if not VENDOR_DIR.exists():
        state = "upstream_missing"
        checks.append({"name": "vendor_present", "ok": False, "path": str(VENDOR_DIR)})
        log_lines.append("vendor/tau2-bench missing; cannot run source-backed smoke.")
    else:
        checks.append({"name": "vendor_present", "ok": True, "path": str(VENDOR_DIR)})

        rc, out, err = run_cmd(["git", "rev-parse", "HEAD"], cwd=VENDOR_DIR)
        checks.append({"name": "vendor_git_head", "ok": rc == 0, "stdout": out.strip(), "stderr": err.strip()})
        log_lines.append("$ git -C vendor/tau2-bench rev-parse HEAD")
        log_lines.append(out.strip() or err.strip())

        pyproject = VENDOR_DIR / "pyproject.toml"
        checks.append({"name": "pyproject_present", "ok": pyproject.exists(), "path": str(pyproject)})

        uv = shutil.which("uv")
        if uv is None:
            checks.append({"name": "uv_available", "ok": False})
            state = "install_failed"
        else:
            checks.append({"name": "uv_available", "ok": True, "path": uv})
            rc, out, err = run_cmd([uv, "run", "tau2", "--help"], cwd=VENDOR_DIR)
            checks.append({"name": "tau2_help", "ok": rc == 0, "returncode": rc, "stdout_tail": short(out), "stderr_tail": short(err)})
            log_lines += ["$ uv run tau2 --help", short(out) or short(err)]
            if rc != 0:
                state = "install_failed"
            else:
                rc, out, err = run_cmd([uv, "run", "tau2", "check-data"], cwd=VENDOR_DIR)
                checks.append({"name": "tau2_check_data", "ok": rc == 0, "returncode": rc, "stdout_tail": short(out), "stderr_tail": short(err)})
                log_lines += ["$ uv run tau2 check-data", short(out) or short(err)]
                if rc != 0:
                    state = "data_check_failed"
                else:
                    rc, out, err = run_cmd([uv, "run", "tau2", "intro"], cwd=VENDOR_DIR)
                    checks.append({"name": "tau2_intro", "ok": rc == 0, "returncode": rc, "stdout_tail": short(out), "stderr_tail": short(err)})
                    log_lines += ["$ uv run tau2 intro", short(out) or short(err)]
                    state = "no_llm_smoke_passed" if rc == 0 else "source_inspection_only_passed"

    if state not in ALLOWED_STATES:
        raise RuntimeError(f"Unexpected state: {state}")

    final_state = {
        "timestamp_utc": timestamp,
        "state": state,
        "llm_api_calls": False,
        "checks": checks,
        "output_dir": str(out_dir),
    }

    write(out_dir / "raw.log", "\n".join(log_lines).strip() + "\n")
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")

    summary = [
        "# tau2-bench baseline smoke summary",
        "",
        f"- Timestamp (UTC): `{timestamp}`",
        "- LLM/API calls used: `False`",
        f"- Final state: `{state}`",
        f"- Output directory: `{out_dir}`",
    ]
    write(out_dir / "summary.md", "\n".join(summary) + "\n")

    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
