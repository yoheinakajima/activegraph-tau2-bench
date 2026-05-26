#!/usr/bin/env python3
"""No-LLM baseline smoke harness for tau2-bench vendored checkout."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / "vendor" / "tau2-bench"
RUNS_DIR = REPO_ROOT / "runs"


def run_cmd(cmd: list[str], cwd: pathlib.Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    summary: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "llm_calls": False,
        "status": "started",
        "checks": [],
    }

    summary["checks"].append({"name": "repo_root", "ok": REPO_ROOT.exists(), "path": str(REPO_ROOT)})

    if not VENDOR_DIR.exists():
        summary["status"] = "blocked"
        summary["reason"] = "vendor/tau2-bench not present"
        summary["hint"] = "Run: git clone https://github.com/sierra-research/tau2-bench vendor/tau2-bench"
        log_lines.append("tau2-bench vendor directory missing; smoke test cannot execute benchmark internals.")
    else:
        summary["checks"].append({"name": "vendor_present", "ok": True, "path": str(VENDOR_DIR)})

        rc, out, err = run_cmd(["git", "rev-parse", "HEAD"], cwd=VENDOR_DIR)
        summary["checks"].append({"name": "vendor_git_head", "ok": rc == 0, "stdout": out.strip(), "stderr": err.strip()})
        log_lines.append("git rev-parse HEAD")
        log_lines.append(out.strip() or err.strip())

        pyproject = VENDOR_DIR / "pyproject.toml"
        setup_py = VENDOR_DIR / "setup.py"
        summary["checks"].append({
            "name": "packaging_files",
            "ok": pyproject.exists() or setup_py.exists(),
            "pyproject": pyproject.exists(),
            "setup_py": setup_py.exists(),
        })

        rc, out, err = run_cmd([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=VENDOR_DIR)
        summary["checks"].append({
            "name": "pytest_collect_only",
            "ok": rc == 0,
            "returncode": rc,
            "stdout_tail": "\n".join(out.splitlines()[-20:]),
            "stderr_tail": "\n".join(err.splitlines()[-20:]),
        })
        log_lines.append("pytest --collect-only -q")
        log_lines.append(out[-4000:] if out else err[-4000:])
        summary["status"] = "ok" if rc == 0 else "partial"

    final_state = {
        "smoke": summary,
        "output_dir": str(out_dir),
    }

    write(out_dir / "raw.log", "\n".join(log_lines) + "\n")
    write(out_dir / "final_state.json", json.dumps(final_state, indent=2) + "\n")

    md = [
        "# tau2-bench baseline smoke summary",
        "",
        f"- Timestamp (UTC): `{timestamp}`",
        f"- LLM/API calls used: `False`",
        f"- Status: `{summary['status']}`",
    ]
    if summary.get("reason"):
        md.append(f"- Reason: `{summary['reason']}`")
    if summary.get("hint"):
        md.append(f"- Hint: `{summary['hint']}`")
    write(out_dir / "summary.md", "\n".join(md) + "\n")

    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
