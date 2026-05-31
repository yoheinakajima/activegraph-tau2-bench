#!/usr/bin/env python3
"""Compare fixture-backed trace smoke output with an extracted real tau2 baseline trace.

This command is an offline artifact comparator only. It reads already-produced
JSON/JSONL files, writes comparison artifacts, and does not import or execute
tau2, call LLM/API services, require API keys, or mutate the vendored tau2 tree.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EVENT_FIELDS = [
    "event_id",
    "timestamp",
    "run_id",
    "phase",
    "component",
    "event_type",
    "task_id",
    "turn_index",
    "tool_name",
    "message_role",
    "state_hash",
    "payload",
    "parent_event_id",
]
STATUS_PASSED = "trace_comparison_passed"
STATUS_EXPECTED_GAPS = "trace_comparison_completed_with_expected_gaps"
STATUS_FAILED = "trace_comparison_failed"
STATUS_INPUTS_MISSING = "trace_comparison_inputs_missing"


class ComparisonInputError(RuntimeError):
    """Raised when required offline comparison artifacts are missing or invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare fixture trace smoke artifacts against a post-run extracted tau2 baseline trace."
    )
    parser.add_argument("--fixture-run-dir", required=True, type=pathlib.Path, help="Fixture trace smoke run directory containing events.jsonl.")
    parser.add_argument("--baseline-run-dir", required=True, type=pathlib.Path, help="Completed tau2 baseline run directory containing extracted_trace/.")
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Optional output directory. Defaults to <baseline-run-dir>/trace_comparison/.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_optional(path: pathlib.Path) -> Any | None:
    if not path.is_file():
        return None
    return load_json(path)


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ComparisonInputError(f"{rel(path)} line {line_number} is not a JSON object")
        events.append(item)
    return events


def require_file(path: pathlib.Path, label: str) -> None:
    if not path.is_file():
        raise ComparisonInputError(f"missing required {label}: {rel(path)}")


def sorted_non_null(values: list[Any]) -> list[Any]:
    unique = {value for value in values if value is not None}
    return sorted(unique, key=lambda item: str(item))


def set_summary(values: list[Any]) -> dict[str, Any]:
    non_null = sorted_non_null(values)
    return {"count": len(non_null), "values": non_null}


def event_type_family(event_type: str) -> str:
    mapping = {
        "run.started": "run_started",
        "baseline.run.started": "run_started",
        "run.completed": "run_completed",
        "baseline.run.completed": "run_completed",
        "task.started": "task_started",
        "baseline.task.started": "task_started",
        "message.observed": "message_observed",
        "baseline.message.observed": "message_observed",
        "tool.dispatch_requested": "tool_requested",
        "baseline.tool.requested": "tool_requested",
        "tool.dispatch_completed": "tool_completed",
        "baseline.tool.completed": "tool_completed",
        "evaluation.completed": "evaluation_observed",
        "baseline.evaluation.observed": "evaluation_observed",
        "results.persisted": "results_persisted",
        "baseline.result.persisted": "results_persisted",
        "state.snapshot": "state_snapshot",
        "turn.started": "turn_started",
        "cli.config_inspected": "config_observed",
        "baseline.config.loaded": "config_observed",
        "batch.started": "batch_started",
        "orchestrator.initialized": "orchestrator_initialized",
    }
    return mapping.get(event_type, event_type)


def event_type_report(fixture_events: list[dict[str, Any]], baseline_events: list[dict[str, Any]]) -> dict[str, Any]:
    fixture_counter = collections.Counter(event.get("event_type") for event in fixture_events)
    baseline_counter = collections.Counter(event.get("event_type") for event in baseline_events)
    fixture_types = set(fixture_counter)
    baseline_types = set(baseline_counter)
    fixture_families = collections.Counter(event_type_family(str(event.get("event_type"))) for event in fixture_events)
    baseline_families = collections.Counter(event_type_family(str(event.get("event_type"))) for event in baseline_events)
    common_families = sorted(set(fixture_families) & set(baseline_families))
    return {
        "fixture_event_count": len(fixture_events),
        "baseline_event_count": len(baseline_events),
        "fixture_event_type_counts": dict(sorted(fixture_counter.items(), key=lambda item: str(item[0]))),
        "baseline_event_type_counts": dict(sorted(baseline_counter.items(), key=lambda item: str(item[0]))),
        "exact_event_types_common": sorted(fixture_types & baseline_types, key=str),
        "fixture_only_event_types": sorted(fixture_types - baseline_types, key=str),
        "baseline_only_event_types": sorted(baseline_types - fixture_types, key=str),
        "semantic_event_family_counts": {
            "fixture": dict(sorted(fixture_families.items())),
            "baseline": dict(sorted(baseline_families.items())),
            "common": common_families,
            "fixture_only": sorted(set(fixture_families) - set(baseline_families)),
            "baseline_only": sorted(set(baseline_families) - set(fixture_families)),
        },
        "interpretation": [
            "Exact event_type names differ because fixture events use trace-smoke names while extracted baseline events use baseline.* names.",
            "Semantic event families align for run lifecycle, task start, messages, tool request/completion, evaluation, results persistence, and config/provenance observations.",
            "Fixture-only turn/state/batch/orchestrator families are expected because the fixture emits synthetic trace smoke lifecycle details.",
        ],
    }


def schema_report(fixture_events: list[dict[str, Any]], baseline_events: list[dict[str, Any]], fixture_final: dict[str, Any] | None, baseline_final: dict[str, Any] | None) -> dict[str, Any]:
    fixture_fields = set().union(*(event.keys() for event in fixture_events)) if fixture_events else set()
    baseline_fields = set().union(*(event.keys() for event in baseline_events)) if baseline_events else set()
    expected_fields = set(EVENT_FIELDS)
    return {
        "expected_event_fields": EVENT_FIELDS,
        "fixture_fields": sorted(fixture_fields),
        "baseline_fields": sorted(baseline_fields),
        "common_fields": sorted(fixture_fields & baseline_fields),
        "fixture_missing_expected_fields": sorted(expected_fields - fixture_fields),
        "baseline_missing_expected_fields": sorted(expected_fields - baseline_fields),
        "fixture_extra_fields": sorted(fixture_fields - expected_fields),
        "baseline_extra_fields": sorted(baseline_fields - expected_fields),
        "schema_versions": {
            "fixture": (fixture_final or {}).get("schema_version"),
            "baseline": (baseline_final or {}).get("schema_version"),
        },
        "compatible_envelope": fixture_fields == expected_fields and baseline_fields == expected_fields,
        "interpretation": "Both traces use the repository-owned trace_event.v1 envelope when compatible_envelope is true; payload details remain source-specific.",
    }


def coverage_report(events: list[dict[str, Any]], final_state: dict[str, Any] | None) -> dict[str, Any]:
    payloads = [event.get("payload") for event in events if isinstance(event.get("payload"), dict)]
    reward_payloads = [payload for payload in payloads if "reward" in payload or "reward_info" in payload]
    evaluation_payloads = [payload for payload in payloads if "evaluation_mode" in payload or "reward_info" in payload]
    fixture_flags = [payload.get("fixture_backed") for payload in payloads if "fixture_backed" in payload]
    no_api_flags = {
        "payload_llm_api_calls_made_by_extractor_values": sorted_non_null([payload.get("llm_api_calls_made_by_extractor") for payload in payloads]),
        "payload_tau2_rerun_values": sorted_non_null([payload.get("tau2_rerun") for payload in payloads]),
    }
    return {
        "task_ids": set_summary([event.get("task_id") for event in events]),
        "turn_indexes": set_summary([event.get("turn_index") for event in events]),
        "message_roles": set_summary([event.get("message_role") for event in events]),
        "tool_names": set_summary([event.get("tool_name") for event in events]),
        "reward_or_evaluation_metadata": {
            "event_count": len(reward_payloads),
            "evaluation_event_count": len(evaluation_payloads),
            "keys_observed": sorted({key for payload in reward_payloads + evaluation_payloads for key in payload.keys()}),
        },
        "fixture_backed_flags": {
            "payload_values": sorted_non_null(fixture_flags),
            "final_state_value": (final_state or {}).get("fixture_backed") or (final_state or {}).get("no_llm_status", {}).get("fixture_backed"),
        },
        "no_rerun_no_api_guarantees": {
            **no_api_flags,
            "final_state_tau2_rerun": (final_state or {}).get("tau2_rerun"),
            "final_state_llm_api_calls_made_by_extractor": (final_state or {}).get("llm_api_calls_made_by_extractor"),
            "final_state_no_llm_status": (final_state or {}).get("no_llm_status"),
            "requires_api_keys": (final_state or {}).get("requires_api_keys"),
        },
    }


def artifact_provenance(
    fixture_run_dir: pathlib.Path,
    baseline_run_dir: pathlib.Path,
    fixture_events_path: pathlib.Path,
    baseline_events_path: pathlib.Path,
    baseline_artifact_index: dict[str, Any] | None,
) -> dict[str, Any]:
    fixture_files = [
        fixture_run_dir / "events.jsonl",
        fixture_run_dir / "summary.md",
        fixture_run_dir / "final_state.json",
        fixture_run_dir / "raw.log",
    ]
    return {
        "fixture_artifacts": [
            {"path": rel(path), "available": path.is_file(), "sha256": content_hash(path) if path.is_file() else None}
            for path in fixture_files
        ],
        "baseline_trace_artifacts": [
            {"path": rel(path), "available": path.is_file(), "sha256": content_hash(path) if path.is_file() else None}
            for path in [
                baseline_events_path,
                baseline_run_dir / "extracted_trace" / "baseline_trace_final_state.json",
                baseline_run_dir / "extracted_trace" / "baseline_artifact_index.json",
                baseline_run_dir / "extracted_trace" / "baseline_trace_summary.md",
            ]
        ],
        "baseline_source_artifact_index": baseline_artifact_index,
        "interpretation": "Fixture artifacts are synthetic smoke outputs; baseline trace artifacts are post-run extraction outputs derived from a completed model-backed run without rerunning tau2.",
    }


def build_gaps(
    schema: dict[str, Any],
    event_types: dict[str, Any],
    fixture_coverage: dict[str, Any],
    baseline_coverage: dict[str, Any],
    baseline_final: dict[str, Any] | None,
) -> dict[str, Any]:
    expected_differences: list[str] = []
    future_gaps: list[str] = []
    successes: list[str] = []

    if schema["compatible_envelope"]:
        successes.append("Fixture and baseline traces share the full trace_event.v1 envelope field set.")
    else:
        future_gaps.append("One or both traces are missing expected envelope fields; inspect schema_field_alignment.json.")

    common_families = event_types["semantic_event_family_counts"]["common"]
    if {"run_started", "run_completed", "task_started", "message_observed", "tool_requested", "tool_completed", "evaluation_observed", "results_persisted"}.issubset(common_families):
        successes.append("Core lifecycle, message, tool, evaluation, and result semantic event families are present in both traces.")

    if event_types["fixture_only_event_types"] or event_types["baseline_only_event_types"]:
        expected_differences.append("Exact event_type names and counts differ because the fixture is synthetic and the baseline trace is extracted from tau2 results artifacts.")

    if fixture_coverage["task_ids"]["values"] != baseline_coverage["task_ids"]["values"]:
        expected_differences.append("Task IDs differ: fixture uses a smoke task id while the baseline uses the real mock-domain task id.")

    if fixture_coverage["turn_indexes"]["values"] != baseline_coverage["turn_indexes"]["values"]:
        expected_differences.append("Turn-index coverage differs because tau2 results serialize message turn_idx values rather than the fixture's synthetic turn lifecycle.")

    baseline_limitations = list((baseline_final or {}).get("limitations", []))
    for limitation in baseline_limitations:
        if "tick-level" in limitation or "effect_timeline" in limitation or "speech_environment" in limitation:
            future_gaps.append(limitation)
        if "reward_info" in limitation:
            future_gaps.append(limitation)

    if not baseline_coverage["tool_names"]["values"]:
        future_gaps.append("Baseline tool completion events do not currently preserve tool_name on the completion message; correlate by tool_call_id in payload until richer instrumentation is added.")

    if baseline_coverage["no_rerun_no_api_guarantees"]["final_state_tau2_rerun"] is False:
        successes.append("Baseline extraction declares tau2_rerun=false.")
    if baseline_coverage["no_rerun_no_api_guarantees"]["final_state_llm_api_calls_made_by_extractor"] is False:
        successes.append("Baseline extraction declares llm_api_calls_made_by_extractor=false.")

    return {
        "schema_compatibility_successes": successes,
        "expected_differences": expected_differences,
        "real_baseline_limitations": sorted(set(baseline_limitations)),
        "future_instrumentation_gaps": sorted(set(future_gaps)),
        "posture": "Mismatches are informational by default; fixture-vs-real differences are expected unless required inputs or envelope compatibility fail.",
    }


def write_summary(path: pathlib.Path, report: dict[str, Any], gaps: dict[str, Any]) -> None:
    lines = [
        "# Fixture vs real tau2 baseline trace comparison",
        "",
        f"- status: `{report['status']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- fixture_run_dir: `{report['inputs']['fixture_run_dir']}`",
        f"- baseline_run_dir: `{report['inputs']['baseline_run_dir']}`",
        f"- fixture_event_count: `{report['event_counts']['fixture']}`",
        f"- baseline_event_count: `{report['event_counts']['baseline']}`",
        f"- schema_compatible_envelope: `{report['schema_alignment']['compatible_envelope']}`",
        f"- tau2_rerun_performed_by_comparison: `{report['no_rerun_no_api_guarantees']['tau2_rerun_performed_by_comparison']}`",
        f"- llm_api_calls_made_by_comparison: `{report['no_rerun_no_api_guarantees']['llm_api_calls_made_by_comparison']}`",
        f"- requires_api_keys: `{report['no_rerun_no_api_guarantees']['requires_api_keys']}`",
        "",
        "## Event-type alignment",
        "",
        f"- exact common event types: `{len(report['event_type_alignment']['exact_event_types_common'])}`",
        f"- common semantic event families: `{', '.join(report['event_type_alignment']['semantic_event_family_counts']['common'])}`",
        f"- fixture-only event types: `{', '.join(report['event_type_alignment']['fixture_only_event_types'])}`",
        f"- baseline-only event types: `{', '.join(report['event_type_alignment']['baseline_only_event_types'])}`",
        "",
        "## Coverage summary",
        "",
        f"- fixture task ids: `{report['coverage']['fixture']['task_ids']['values']}`",
        f"- baseline task ids: `{report['coverage']['baseline']['task_ids']['values']}`",
        f"- fixture turn indexes: `{report['coverage']['fixture']['turn_indexes']['values']}`",
        f"- baseline turn indexes: `{report['coverage']['baseline']['turn_indexes']['values']}`",
        f"- fixture message roles: `{report['coverage']['fixture']['message_roles']['values']}`",
        f"- baseline message roles: `{report['coverage']['baseline']['message_roles']['values']}`",
        f"- fixture tool names: `{report['coverage']['fixture']['tool_names']['values']}`",
        f"- baseline tool names: `{report['coverage']['baseline']['tool_names']['values']}`",
        "",
        "## Schema compatibility successes",
        "",
    ]
    lines.extend(f"- {item}" for item in gaps["schema_compatibility_successes"])
    lines.extend(["", "## Expected differences", ""])
    lines.extend(f"- {item}" for item in gaps["expected_differences"])
    lines.extend(["", "## Real-baseline limitations", ""])
    lines.extend(f"- {item}" for item in gaps["real_baseline_limitations"])
    lines.extend(["", "## Future instrumentation gaps", ""])
    lines.extend(f"- {item}" for item in gaps["future_instrumentation_gaps"])
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This comparison reads existing fixture and extracted baseline artifacts only. It does not run tau2, does not run a model-backed episode, does not call LLM/API services, does not require API keys, and does not mutate `vendor/tau2-bench`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    fixture_run_dir = args.fixture_run_dir.resolve()
    baseline_run_dir = args.baseline_run_dir.resolve()
    output_dir = (args.output_dir.resolve() if args.output_dir else baseline_run_dir / "trace_comparison")

    fixture_events_path = fixture_run_dir / "events.jsonl"
    fixture_final_path = fixture_run_dir / "final_state.json"
    fixture_summary_path = fixture_run_dir / "summary.md"
    baseline_extracted_dir = baseline_run_dir / "extracted_trace"
    baseline_events_path = baseline_extracted_dir / "baseline_trace.jsonl"
    baseline_final_path = baseline_extracted_dir / "baseline_trace_final_state.json"
    baseline_index_path = baseline_extracted_dir / "baseline_artifact_index.json"

    try:
        require_file(fixture_events_path, "fixture events.jsonl")
        require_file(baseline_events_path, "baseline extracted_trace/baseline_trace.jsonl")
        require_file(baseline_final_path, "baseline extracted_trace/baseline_trace_final_state.json")
        require_file(baseline_index_path, "baseline extracted_trace/baseline_artifact_index.json")

        fixture_events = load_jsonl(fixture_events_path)
        baseline_events = load_jsonl(baseline_events_path)
        fixture_final = load_json_optional(fixture_final_path)
        baseline_final = load_json(baseline_final_path)
        baseline_artifact_index = load_json(baseline_index_path)
    except Exception as exc:  # noqa: BLE001 - convert input/parsing failures into comparison artifacts when possible.
        output_dir.mkdir(parents=True, exist_ok=True)
        final_state = {
            "status": STATUS_INPUTS_MISSING,
            "generated_at_utc": utc_now(),
            "fixture_run_dir": rel(fixture_run_dir),
            "baseline_run_dir": rel(baseline_run_dir),
            "error": str(exc),
            "tau2_rerun_performed_by_comparison": False,
            "llm_api_calls_made_by_comparison": False,
            "requires_api_keys": False,
        }
        write_json(output_dir / "final_state.json", final_state)
        (output_dir / "raw.log").write_text(f"[ERROR] {exc}\n", encoding="utf-8")
        print(f"comparison_status={STATUS_INPUTS_MISSING}")
        print(f"error={exc}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    schema = schema_report(fixture_events, baseline_events, fixture_final, baseline_final)
    event_types = event_type_report(fixture_events, baseline_events)
    fixture_coverage = coverage_report(fixture_events, fixture_final)
    baseline_coverage = coverage_report(baseline_events, baseline_final)
    provenance = artifact_provenance(
        fixture_run_dir,
        baseline_run_dir,
        fixture_events_path,
        baseline_events_path,
        baseline_artifact_index,
    )
    gaps = build_gaps(schema, event_types, fixture_coverage, baseline_coverage, baseline_final)

    status = STATUS_PASSED
    if not schema["compatible_envelope"]:
        status = STATUS_FAILED
    elif gaps["expected_differences"] or gaps["real_baseline_limitations"] or gaps["future_instrumentation_gaps"]:
        status = STATUS_EXPECTED_GAPS

    output_files = [
        output_dir / "trace_comparison_report.json",
        output_dir / "trace_comparison_summary.md",
        output_dir / "event_type_alignment.json",
        output_dir / "schema_field_alignment.json",
        output_dir / "coverage_gaps.json",
        output_dir / "final_state.json",
        output_dir / "raw.log",
    ]

    report = {
        "status": status,
        "generated_at_utc": utc_now(),
        "inputs": {
            "fixture_run_dir": rel(fixture_run_dir),
            "fixture_events_path": rel(fixture_events_path),
            "fixture_final_state_path": rel(fixture_final_path) if fixture_final_path.is_file() else None,
            "fixture_summary_path": rel(fixture_summary_path) if fixture_summary_path.is_file() else None,
            "baseline_run_dir": rel(baseline_run_dir),
            "baseline_events_path": rel(baseline_events_path),
            "baseline_final_state_path": rel(baseline_final_path),
            "baseline_artifact_index_path": rel(baseline_index_path),
        },
        "event_counts": {"fixture": len(fixture_events), "baseline": len(baseline_events)},
        "schema_alignment": schema,
        "event_type_alignment": event_types,
        "coverage": {"fixture": fixture_coverage, "baseline": baseline_coverage},
        "artifact_provenance": provenance,
        "coverage_gaps": gaps,
        "fixture_backed_vs_real_baseline": {
            "fixture": "fixture_backed synthetic no-LLM trace smoke output",
            "baseline": "real model-backed tau2 baseline trace extracted after completion",
            "mismatch_posture": "expected and informational",
        },
        "available_vs_unavailable_details": {
            "available": [
                "trace_event.v1 envelope fields",
                "event type names and semantic families",
                "event counts",
                "task_id, turn_index, message_role, and tool_name coverage",
                "fixture evaluation reward and baseline reward_info where serialized",
                "baseline artifact provenance index",
                "no-rerun/no-API flags from comparison and extraction artifacts",
            ],
            "unavailable_or_limited": gaps["future_instrumentation_gaps"],
        },
        "no_rerun_no_api_guarantees": {
            "tau2_rerun_performed_by_comparison": False,
            "model_backed_episode_run_by_comparison": False,
            "llm_api_calls_made_by_comparison": False,
            "requires_api_keys": False,
            "vendor_tau2_bench_mutated_by_comparison": False,
        },
        "output_files": [rel(path) for path in output_files],
    }
    final_state = {
        "status": status,
        "generated_at_utc": report["generated_at_utc"],
        "fixture_run_dir": rel(fixture_run_dir),
        "baseline_run_dir": rel(baseline_run_dir),
        "output_dir": rel(output_dir),
        "fixture_event_count": len(fixture_events),
        "baseline_event_count": len(baseline_events),
        "schema_compatible_envelope": schema["compatible_envelope"],
        "common_semantic_event_families": event_types["semantic_event_family_counts"]["common"],
        "expected_difference_count": len(gaps["expected_differences"]),
        "real_baseline_limitation_count": len(gaps["real_baseline_limitations"]),
        "future_instrumentation_gap_count": len(gaps["future_instrumentation_gaps"]),
        "tau2_rerun_performed_by_comparison": False,
        "llm_api_calls_made_by_comparison": False,
        "requires_api_keys": False,
        "vendor_tau2_bench_mutated_by_comparison": False,
        "output_files": [rel(path) for path in output_files],
    }

    write_json(output_dir / "event_type_alignment.json", event_types)
    write_json(output_dir / "schema_field_alignment.json", schema)
    write_json(output_dir / "coverage_gaps.json", gaps)
    write_json(output_dir / "trace_comparison_report.json", report)
    write_json(output_dir / "final_state.json", final_state)
    write_summary(output_dir / "trace_comparison_summary.md", report, gaps)
    (output_dir / "raw.log").write_text(
        "\n".join(
            [
                f"[INFO] comparison_status={status}",
                f"[INFO] fixture_run_dir={rel(fixture_run_dir)}",
                f"[INFO] baseline_run_dir={rel(baseline_run_dir)}",
                f"[INFO] fixture_events={len(fixture_events)} baseline_events={len(baseline_events)}",
                "[INFO] tau2_rerun_performed_by_comparison=False",
                "[INFO] llm_api_calls_made_by_comparison=False",
                "[INFO] requires_api_keys=False",
                "[INFO] vendor_tau2_bench_mutated_by_comparison=False",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"comparison_status={status}")
    print(f"comparison_output_dir={rel(output_dir)}")
    print(f"fixture_event_count={len(fixture_events)}")
    print(f"baseline_event_count={len(baseline_events)}")
    return 0 if status in {STATUS_PASSED, STATUS_EXPECTED_GAPS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
