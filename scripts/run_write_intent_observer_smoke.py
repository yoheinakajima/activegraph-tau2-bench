#!/usr/bin/env python3
"""No-LLM smoke for the passive write-intent observer."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.write_intent_observer.fixtures import fixture_cases  # noqa: E402
from experiments.write_intent_observer.observer import PassiveWriteIntentObserver, validate_jsonl  # noqa: E402
from experiments.write_intent_observer.schema import BOUNDARY_FLAGS, SCHEMA_VERSION  # noqa: E402

RUNS_DIR = REPO_ROOT / "runs"
PASS_STATUS = "write_intent_observer_smoke_passed"
FAIL_STATUS = "write_intent_observer_smoke_failed"
COMMAND = "python scripts/run_write_intent_observer_smoke.py"


def timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S-%f")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def validate_results(out_dir: pathlib.Path, results: list[dict[str, Any]], raw_log: list[str]) -> list[str]:
    errors: list[str] = []
    for artifact in ("observer_events.jsonl", "constraint_ledger_snapshots.jsonl", "write_intent_diffs.jsonl"):
        path = out_dir / artifact
        try:
            count = validate_jsonl(path)
            raw_log.append(f"[OK] validated {artifact} jsonl_records={count}")
        except Exception as exc:  # noqa: BLE001 - smoke should report all validation errors.
            errors.append(f"{artifact} is invalid JSONL: {exc!r}")

    by_case = {result["case_id"]: result for result in results}
    required_cases = {
        "airline_task8_baseline_missing_kevin_wrong_payment",
        "airline_task8_prompt_variant_wrong_payment_missing_search",
        "successful_create_task_1",
        "failed_no_write_expected_absent",
        "db_mismatch_scoring_ambiguity",
    }
    missing_cases = sorted(required_cases - set(by_case))
    if missing_cases:
        errors.append(f"missing fixture cases: {missing_cases}")

    for result in results:
        expected = set(result.get("expected_warning_codes", []))
        actual = set(result.get("warning_codes", []))
        missing = expected - actual
        if missing:
            errors.append(f"{result['case_id']} missing expected warning codes: {sorted(missing)}")

    success = by_case.get("successful_create_task_1")
    if success and success.get("readiness_score", 0) < 0.9:
        errors.append("successful_create_task_1 should retain a high readiness score")
    if success and any(w.get("severity") in {"medium", "high"} for w in success.get("warnings", [])):
        errors.append("successful_create_task_1 should not emit medium/high warnings")

    boundary = BOUNDARY_FLAGS
    for key in ("activegraph_control_enabled", "blocks_tool_calls", "rewrites_tool_arguments", "repairs_or_rolls_back", "feeds_state_packets_back_to_tau2", "mutates_vendor_tau2_bench", "llm_or_api_calls_made"):
        if boundary[key] is not False:
            errors.append(f"observer boundary flag {key} must be false")
    if boundary["passive_observer_only"] is not True:
        errors.append("observer boundary flag passive_observer_only must be true")
    return errors


def write_summary(out_dir: pathlib.Path, status: str, final_state: dict[str, Any], validation_errors: list[str]) -> None:
    rows = []
    flagged = []
    for result in final_state["case_results"]:
        codes = ", ".join(result["warning_codes"]) or "none"
        rows.append(
            f"| {result['case_id']} | {result['write_intents_observed']} | {result['readiness_score']} | {codes} |"
        )
        if result["warning_codes"]:
            flagged.append(f"- `{result['case_id']}`: {codes}")
    taxonomy_rows = "\n".join(
        f"| {phase} | {count} |" for phase, count in sorted(final_state["warning_counts_by_phase"].items())
    ) or "| none | 0 |"
    content = f"""# Passive write-intent observer smoke

Status: `{status}`

Run directory: `{rel(out_dir)}`

Schema: `{SCHEMA_VERSION}`

Command: `{COMMAND}`

## Boundary

- Passive observer only: `{BOUNDARY_FLAGS['passive_observer_only']}`
- ActiveGraph control enabled: `{BOUNDARY_FLAGS['activegraph_control_enabled']}`
- Blocks tool calls: `{BOUNDARY_FLAGS['blocks_tool_calls']}`
- Rewrites tool arguments: `{BOUNDARY_FLAGS['rewrites_tool_arguments']}`
- Repairs or rolls back: `{BOUNDARY_FLAGS['repairs_or_rolls_back']}`
- Feeds state packets back to tau2: `{BOUNDARY_FLAGS['feeds_state_packets_back_to_tau2']}`
- Mutates vendor/tau2-bench: `{BOUNDARY_FLAGS['mutates_vendor_tau2_bench']}`
- LLM/API calls made: `{BOUNDARY_FLAGS['llm_or_api_calls_made']}`
- tau2 rerun: `false`

## Fixture coverage

| Case | Write intents observed | Readiness score | Warning codes |
| --- | ---: | ---: | --- |
{chr(10).join(rows)}

## Warning taxonomy counts

| Phase | Count |
| --- | ---: |
{taxonomy_rows}

## Flagged cases

{chr(10).join(flagged) if flagged else '- none'}

## Validation

- JSONL schema/load validation errors: `{len(validation_errors)}`
- No-control boundary validated: `{not validation_errors}`

```json
{json.dumps(validation_errors, indent=2)}
```

## Artifacts

- `observer_events.jsonl`
- `constraint_ledger_snapshots.jsonl`
- `write_intent_diffs.jsonl`
- `observer_summary.md`
- `observer_final_state.json`
- `raw.log`
"""
    write(out_dir / "observer_summary.md", content)


def main() -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = RUNS_DIR / timestamp()
    out_dir.mkdir(parents=True, exist_ok=False)
    raw_log = [
        "passive write-intent observer no-LLM smoke",
        f"command={COMMAND}",
        "tau2_rerun=false",
        "llm_or_api_calls_made=false",
        "activegraph_control_enabled=false",
    ]
    observer = PassiveWriteIntentObserver(out_dir, run_id=f"write-intent-observer-smoke-{out_dir.name}")
    results: list[dict[str, Any]] = []
    try:
        for case in fixture_cases():
            result = observer.observe_case(case)
            results.append(result)
            raw_log.append(f"[CASE] {result['case_id']} readiness={result['readiness_score']} warnings={','.join(result['warning_codes']) or 'none'}")
        validation_errors = validate_results(out_dir, results, raw_log)
        status = PASS_STATUS if not validation_errors else FAIL_STATUS
        final_state = observer.final_state(status)
        final_state.update(
            {
                "output_dir": rel(out_dir),
                "command": COMMAND,
                "fixture_case_ids": [result["case_id"] for result in results],
                "validation_errors": validation_errors,
                "tau2_rerun": False,
                "paid_llm_api_calls_made": False,
                "llm_or_api_calls_made": False,
                "vendor_tau2_bench_mutated": False,
            }
        )
    except Exception as exc:  # noqa: BLE001 - smoke should persist failure artifacts.
        status = FAIL_STATUS
        validation_errors = [repr(exc)]
        final_state = observer.final_state(status)
        final_state.update({"output_dir": rel(out_dir), "command": COMMAND, "validation_errors": validation_errors})
        raw_log.append(f"[FAIL] {exc!r}")
    finally:
        observer.close()

    write(out_dir / "observer_final_state.json", json.dumps(final_state, indent=2, sort_keys=True) + "\n")
    write_summary(out_dir, status, final_state, final_state.get("validation_errors", []))
    write(out_dir / "raw.log", "\n".join(raw_log + [f"status={status}", f"output_dir={rel(out_dir)}"]) + "\n")
    print(rel(out_dir))
    print(status)
    return 0 if status == PASS_STATUS else 1


if __name__ == "__main__":
    sys.exit(main())
