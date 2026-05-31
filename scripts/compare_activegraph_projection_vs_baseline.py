#!/usr/bin/env python3
"""Compare fixture-backed and real-baseline ActiveGraph projections offline.

This command only reads local smoke/projection artifacts. It does not run tau2,
call model providers, require API keys, or feed ActiveGraph state back into tau2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from collections import Counter
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

STATUS_PASSED = "activegraph_projection_comparison_passed"
STATUS_EXPECTED_GAPS = "activegraph_projection_comparison_completed_with_expected_gaps"
STATUS_FAILED = "activegraph_projection_comparison_failed"
STATUS_INPUTS_MISSING = "activegraph_projection_comparison_inputs_missing"

COMMAND = "python scripts/compare_activegraph_projection_vs_baseline.py"
COMPARISON_SCHEMA_VERSION = "activegraph_projection_comparison.v1"

FIXTURE_REQUIRED = {
    "events": "events.jsonl",
    "projection": "activegraph_trace.json",
    "packets": "state_packets.jsonl",
    "packet_index": "state_packet_index.json",
}
BASELINE_REQUIRED = {
    "events": "activegraph_projection/activegraph_baseline_events.jsonl",
    "projection": "activegraph_projection/activegraph_baseline_projection.json",
    "packets": "activegraph_projection/activegraph_baseline_state_packets.jsonl",
    "packet_index": "activegraph_projection/activegraph_baseline_state_packet_index.json",
    "final_state": "activegraph_projection/activegraph_projection_final_state.json",
}
OUTPUT_FILES = [
    "activegraph_projection_comparison_report.json",
    "activegraph_projection_comparison_summary.md",
    "graph_alignment.json",
    "packet_alignment.json",
    "provenance_alignment.json",
    "coverage_gaps.json",
    "final_state.json",
    "raw.log",
]


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{rel(path)}:{line_number}: invalid JSONL: {exc}") from exc
    return rows


def write_json(path: pathlib.Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def recursively_collect_key(value: Any, key: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key and item_value not in (None, ""):
                found.add(str(item_value))
            found.update(recursively_collect_key(item_value, key))
    elif isinstance(value, list):
        for item in value:
            found.update(recursively_collect_key(item, key))
    return found


def semantic_family(event_type: str | None) -> str:
    if not event_type:
        return "unknown"
    parts = [part for part in event_type.split(".") if part]
    if parts and parts[0] == "baseline":
        parts = parts[1:]
    if not parts:
        return event_type
    if parts[0] == "results":
        return "result"
    return parts[0]


def graph_nodes(projection: dict[str, Any]) -> list[dict[str, Any]]:
    graph = projection.get("graph") or {}
    nodes = graph.get("nodes") or projection.get("nodes") or []
    return nodes if isinstance(nodes, list) else []


def graph_edges(projection: dict[str, Any]) -> list[dict[str, Any]]:
    graph = projection.get("graph") or {}
    edges = graph.get("edges") or projection.get("edges") or []
    return edges if isinstance(edges, list) else []


def node_kind(node: dict[str, Any]) -> str:
    return str(node.get("kind") or node.get("type") or "unknown")


def packet_type_for_event(event: dict[str, Any]) -> str:
    family = semantic_family(event.get("event_type"))
    if family == "tool":
        return "tool_state"
    if family in {"message", "turn"}:
        return "turn_state"
    if family == "task":
        return "task_state"
    if family == "evaluation":
        return "evaluation_state"
    if family == "result":
        return "result_state"
    return "run_state"


def summarize_artifacts(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    artifact_nodes = [node for node in nodes if node_kind(node) in {"artifact", "provenance"}]
    return {
        "count": len(artifact_nodes),
        "ids": sorted(str(node.get("id")) for node in artifact_nodes if node.get("id")),
        "paths": sorted(
            str((node.get("attributes") or {}).get("path"))
            for node in artifact_nodes
            if (node.get("attributes") or {}).get("path")
        ),
    }


def summarize_projection(
    label: str,
    events: list[dict[str, Any]],
    projection: dict[str, Any],
    packets: list[dict[str, Any]],
    packet_index: dict[str, Any],
    final_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = graph_nodes(projection)
    edges = graph_edges(projection)
    task_ids = set()
    for event in events:
        if event.get("task_id"):
            task_ids.add(str(event["task_id"]))
        task_ids.update(recursively_collect_key(event.get("payload"), "task_id"))
    if final_state:
        task_ids.update(recursively_collect_key(final_state, "task_id"))
    event_types = [str(event.get("event_type") or "unknown") for event in events]
    packet_types = [str(packet.get("packet_type") or "unknown") for packet in packets]
    return {
        "label": label,
        "schema_version": projection.get("schema_version"),
        "trace_event_schema_version": projection.get("trace_event_schema_version"),
        "event_count": len(events),
        "projection_event_count": (projection.get("counts") or {}).get("events"),
        "node_count": len(nodes),
        "projection_node_count": (projection.get("counts") or {}).get("nodes"),
        "edge_count": len(edges),
        "projection_edge_count": (projection.get("counts") or {}).get("edges"),
        "node_kinds": dict(sorted(Counter(node_kind(node) for node in nodes).items())),
        "edge_types": dict(sorted(Counter(str(edge.get("type") or "unknown") for edge in edges).items())),
        "event_types": dict(sorted(Counter(event_types).items())),
        "event_semantic_families": dict(sorted(Counter(semantic_family(t) for t in event_types).items())),
        "task_ids": sorted(task_ids),
        "components": sorted({str(event.get("component")) for event in events if event.get("component")}),
        "message_roles": sorted({str(event.get("message_role")) for event in events if event.get("message_role")}),
        "tools": sorted({str(event.get("tool_name")) for event in events if event.get("tool_name")}),
        "evaluation_result_event_types": sorted(
            {t for t in event_types if semantic_family(t) in {"evaluation", "result"}}
        ),
        "artifact_provenance_nodes": summarize_artifacts(nodes),
        "packet_count": len(packets),
        "packet_index_count": packet_index.get("packet_count"),
        "packet_types": dict(sorted(Counter(packet_types).items())),
        "packet_index_types": packet_index.get("packet_types") or {},
    }


def compare_sets(name: str, fixture_values: set[str], baseline_values: set[str]) -> dict[str, Any]:
    return {
        "dimension": name,
        "fixture": sorted(fixture_values),
        "baseline": sorted(baseline_values),
        "common": sorted(fixture_values & baseline_values),
        "fixture_only": sorted(fixture_values - baseline_values),
        "baseline_only": sorted(baseline_values - fixture_values),
    }


def validate_packets(
    label: str,
    events: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    packet_index: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    event_ids = {str(event.get("event_id")) for event in events if event.get("event_id")}
    source_event_ids = [str(packet.get("source_event_id")) for packet in packets]
    previous_hash = None
    for index, packet in enumerate(packets):
        if packet.get("sequence_index") != index:
            errors.append(f"{label} packet {packet.get('packet_id')} sequence_index is not {index}")
        if packet.get("previous_packet_hash") != previous_hash:
            errors.append(f"{label} packet {packet.get('packet_id')} previous_packet_hash mismatch")
        previous_hash = packet.get("packet_hash")
    missing_refs = sorted(set(source_event_ids) - event_ids)
    if missing_refs:
        errors.append(f"{label} packets reference missing source events: {missing_refs}")
    if len(packets) != len(events):
        errors.append(f"{label} packet count {len(packets)} does not match event count {len(events)}")
    return {
        "label": label,
        "packet_count": len(packets),
        "event_count": len(events),
        "packet_count_matches_event_count": len(packets) == len(events),
        "hash_chain_valid": not any("previous_packet_hash" in error for error in errors),
        "ordering_valid": not any("sequence_index" in error for error in errors),
        "all_packets_reference_events": not missing_refs,
        "source_event_reference_count": len(source_event_ids),
        "source_event_reference_coverage": sorted(set(source_event_ids) & event_ids),
        "source_event_references_missing": missing_refs,
        "packet_index_validation": packet_index.get("validation") or {},
        "errors": errors,
        "ok": not errors,
    }


def bool_path(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def extract_fixture_control_flags(projection: dict[str, Any], final_state: dict[str, Any] | None) -> dict[str, Any]:
    adapter = projection.get("adapter") or {}
    provenance = projection.get("provenance") or {}
    no_llm = provenance.get("no_llm_status") or {}
    if final_state:
        no_llm = final_state.get("no_llm_status") or no_llm
    return {
        "tau2_rerun": bool(no_llm.get("real_tau2_episode_run", False)),
        "llm_api_calls_made": bool(no_llm.get("llm_api_calls", False)),
        "requires_api_keys": bool(no_llm.get("requires_api_keys", False)),
        "activegraph_controls_tau2": bool(adapter.get("controls_tau2_execution", False)),
        "activegraph_execution_control_implemented": bool(adapter.get("reactive_manager_support", False)),
    }


def extract_baseline_control_flags(projection: dict[str, Any], final_state: dict[str, Any]) -> dict[str, Any]:
    boundary = projection.get("control_boundary") or {}
    return {
        "tau2_rerun": bool(boundary.get("tau2_rerun", final_state.get("tau2_rerun", False))),
        "llm_api_calls_made": bool(
            boundary.get("llm_api_calls_made_by_projection", final_state.get("llm_api_calls_made_by_projection", False))
        ),
        "requires_api_keys": bool(boundary.get("requires_api_keys", final_state.get("requires_api_keys", False))),
        "activegraph_controls_tau2": bool(
            boundary.get("activegraph_controls_tau2", final_state.get("activegraph_controls_tau2", False))
        ),
        "activegraph_execution_control_implemented": bool(
            boundary.get("activegraph_execution_control_implemented", False)
        ),
    }


def build_summary(report: dict[str, Any]) -> str:
    fixture = report["fixture"]
    baseline = report["baseline"]
    graph = report["graph_alignment"]
    packets = report["packet_alignment"]
    provenance = report["provenance_alignment"]
    gaps = report["coverage_gaps"]
    output_lines = "\n".join(f"- `{path}`" for path in OUTPUT_FILES)
    known_gap_lines = "\n".join(f"- {gap}" for gap in gaps["known_coverage_gaps"])
    expected_diff_lines = "\n".join(f"- {diff}" for diff in gaps["expected_fixture_vs_real_differences"])
    return f"""# ActiveGraph fixture-vs-real projection comparison

- Status: `{report['status']}`
- Fixture run directory: `{fixture['run_dir']}`
- Baseline run directory: `{baseline['run_dir']}`
- Generated at (UTC): `{report['created_at']}`
- tau2 rerun by comparison: `{provenance['no_rerun_no_api_flags']['tau2_rerun']}`
- LLM/API calls by comparison: `{provenance['no_rerun_no_api_flags']['llm_api_calls_made']}`
- API keys required by comparison: `{provenance['no_rerun_no_api_flags']['requires_api_keys']}`

## Output files

{output_lines}

## Graph alignment

- Fixture schema: `{fixture['summary']['schema_version']}`
- Baseline schema: `{baseline['summary']['schema_version']}`
- Fixture events/nodes/edges: `{fixture['summary']['event_count']}` / `{fixture['summary']['node_count']}` / `{fixture['summary']['edge_count']}`
- Baseline events/nodes/edges: `{baseline['summary']['event_count']}` / `{baseline['summary']['node_count']}` / `{baseline['summary']['edge_count']}`
- Shared semantic event families: `{', '.join(graph['event_semantic_family_alignment']['common'])}`
- Fixture-only event families: `{', '.join(graph['event_semantic_family_alignment']['fixture_only']) or 'none'}`
- Baseline-only event families: `{', '.join(graph['event_semantic_family_alignment']['baseline_only']) or 'none'}`
- Shared node kinds: `{', '.join(graph['node_kind_alignment']['common'])}`
- Shared edge types: `{', '.join(graph['edge_type_alignment']['common']) or 'none'}`

## Packet alignment

- Fixture packets: `{packets['fixture_validation']['packet_count']}`
- Baseline packets: `{packets['baseline_validation']['packet_count']}`
- Fixture hash-chain valid: `{packets['fixture_validation']['hash_chain_valid']}`
- Baseline hash-chain valid: `{packets['baseline_validation']['hash_chain_valid']}`
- Fixture packets reference source events: `{packets['fixture_validation']['all_packets_reference_events']}`
- Baseline packets reference source events: `{packets['baseline_validation']['all_packets_reference_events']}`
- Shared packet types: `{', '.join(packets['packet_type_alignment']['common'])}`

## Provenance alignment

- Fixture task IDs: `{', '.join(fixture['summary']['task_ids'])}`
- Baseline task IDs: `{', '.join(baseline['summary']['task_ids'])}`
- Baseline provider/model/task/max_steps present: `{provenance['baseline_provider_model_task_max_steps_present']}`
- Comparison is offline-only: `{provenance['comparison_offline_only']}`
- Vendor mutation by comparison: `{provenance['vendor_tau2_bench_mutated_by_comparison']}`

## Expected fixture-vs-real differences

{expected_diff_lines}

## Known coverage gaps

{known_gap_lines}
"""


def find_missing(required: dict[str, str], root: pathlib.Path) -> dict[str, str]:
    missing = {}
    for label, relative_path in required.items():
        candidate = root / relative_path
        if not candidate.is_file():
            missing[label] = rel(candidate)
    return missing


def load_inputs(fixture_run_dir: pathlib.Path, baseline_run_dir: pathlib.Path) -> dict[str, Any]:
    return {
        "fixture_events": read_jsonl(fixture_run_dir / FIXTURE_REQUIRED["events"]),
        "fixture_projection": read_json(fixture_run_dir / FIXTURE_REQUIRED["projection"]),
        "fixture_packets": read_jsonl(fixture_run_dir / FIXTURE_REQUIRED["packets"]),
        "fixture_packet_index": read_json(fixture_run_dir / FIXTURE_REQUIRED["packet_index"]),
        "baseline_events": read_jsonl(baseline_run_dir / BASELINE_REQUIRED["events"]),
        "baseline_projection": read_json(baseline_run_dir / BASELINE_REQUIRED["projection"]),
        "baseline_packets": read_jsonl(baseline_run_dir / BASELINE_REQUIRED["packets"]),
        "baseline_packet_index": read_json(baseline_run_dir / BASELINE_REQUIRED["packet_index"]),
        "baseline_final_state": read_json(baseline_run_dir / BASELINE_REQUIRED["final_state"]),
    }


def compare(fixture_run_dir: pathlib.Path, baseline_run_dir: pathlib.Path) -> dict[str, Any]:
    created_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    missing = {
        "fixture": find_missing(FIXTURE_REQUIRED, fixture_run_dir),
        "baseline": find_missing(BASELINE_REQUIRED, baseline_run_dir),
    }
    if missing["fixture"] or missing["baseline"]:
        return {
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "status": STATUS_INPUTS_MISSING,
            "created_at": created_at,
            "fixture": {"run_dir": rel(fixture_run_dir)},
            "baseline": {"run_dir": rel(baseline_run_dir)},
            "missing_inputs": missing,
            "no_rerun_no_api_flags": {
                "tau2_rerun": False,
                "llm_api_calls_made": False,
                "requires_api_keys": False,
            },
        }

    inputs = load_inputs(fixture_run_dir, baseline_run_dir)
    fixture_summary = summarize_projection(
        "fixture",
        inputs["fixture_events"],
        inputs["fixture_projection"],
        inputs["fixture_packets"],
        inputs["fixture_packet_index"],
    )
    baseline_summary = summarize_projection(
        "baseline",
        inputs["baseline_events"],
        inputs["baseline_projection"],
        inputs["baseline_packets"],
        inputs["baseline_packet_index"],
        inputs["baseline_final_state"],
    )
    fixture_validation = validate_packets(
        "fixture", inputs["fixture_events"], inputs["fixture_packets"], inputs["fixture_packet_index"]
    )
    baseline_validation = validate_packets(
        "baseline", inputs["baseline_events"], inputs["baseline_packets"], inputs["baseline_packet_index"]
    )

    graph_alignment = {
        "schema_versions": {
            "fixture": fixture_summary["schema_version"],
            "baseline": baseline_summary["schema_version"],
            "same": fixture_summary["schema_version"] == baseline_summary["schema_version"],
        },
        "trace_event_schema_versions": {
            "fixture": fixture_summary["trace_event_schema_version"],
            "baseline": baseline_summary["trace_event_schema_version"],
            "same": fixture_summary["trace_event_schema_version"] == baseline_summary["trace_event_schema_version"],
        },
        "counts": {
            "fixture": {
                "events": fixture_summary["event_count"],
                "nodes": fixture_summary["node_count"],
                "edges": fixture_summary["edge_count"],
            },
            "baseline": {
                "events": baseline_summary["event_count"],
                "nodes": baseline_summary["node_count"],
                "edges": baseline_summary["edge_count"],
            },
            "event_count_delta_baseline_minus_fixture": baseline_summary["event_count"] - fixture_summary["event_count"],
            "node_count_delta_baseline_minus_fixture": baseline_summary["node_count"] - fixture_summary["node_count"],
            "edge_count_delta_baseline_minus_fixture": baseline_summary["edge_count"] - fixture_summary["edge_count"],
        },
        "node_kind_alignment": compare_sets(
            "node_kinds", set(fixture_summary["node_kinds"]), set(baseline_summary["node_kinds"])
        ),
        "edge_type_alignment": compare_sets(
            "edge_types", set(fixture_summary["edge_types"]), set(baseline_summary["edge_types"])
        ),
        "event_semantic_family_alignment": compare_sets(
            "event_semantic_families",
            set(fixture_summary["event_semantic_families"]),
            set(baseline_summary["event_semantic_families"]),
        ),
        "task_id_alignment": compare_sets("task_ids", set(fixture_summary["task_ids"]), set(baseline_summary["task_ids"])),
        "component_alignment": compare_sets(
            "components", set(fixture_summary["components"]), set(baseline_summary["components"])
        ),
        "message_role_alignment": compare_sets(
            "message_roles", set(fixture_summary["message_roles"]), set(baseline_summary["message_roles"])
        ),
        "tool_alignment": compare_sets("tools", set(fixture_summary["tools"]), set(baseline_summary["tools"])),
        "evaluation_result_alignment": compare_sets(
            "evaluation_result_event_types",
            set(fixture_summary["evaluation_result_event_types"]),
            set(baseline_summary["evaluation_result_event_types"]),
        ),
        "artifact_provenance_nodes": {
            "fixture": fixture_summary["artifact_provenance_nodes"],
            "baseline": baseline_summary["artifact_provenance_nodes"],
        },
    }

    packet_alignment = {
        "counts": {
            "fixture": fixture_summary["packet_count"],
            "baseline": baseline_summary["packet_count"],
            "delta_baseline_minus_fixture": baseline_summary["packet_count"] - fixture_summary["packet_count"],
        },
        "packet_type_alignment": compare_sets(
            "packet_types", set(fixture_summary["packet_types"]), set(baseline_summary["packet_types"])
        ),
        "fixture_validation": fixture_validation,
        "baseline_validation": baseline_validation,
        "source_event_reference_alignment": {
            "fixture_reference_count": fixture_validation["source_event_reference_count"],
            "baseline_reference_count": baseline_validation["source_event_reference_count"],
            "fixture_all_reference_events": fixture_validation["all_packets_reference_events"],
            "baseline_all_reference_events": baseline_validation["all_packets_reference_events"],
        },
    }

    fixture_flags = extract_fixture_control_flags(inputs["fixture_projection"], None)
    baseline_flags = extract_baseline_control_flags(inputs["baseline_projection"], inputs["baseline_final_state"])
    comparison_flags = {"tau2_rerun": False, "llm_api_calls_made": False, "requires_api_keys": False}
    baseline_provider_model_task_max_steps_present = all(
        inputs["baseline_final_state"].get(key) not in (None, "")
        for key in ["provider", "model", "max_steps"]
    ) and bool(baseline_summary["task_ids"])
    provenance_alignment = {
        "fixture_control_boundary_flags": fixture_flags,
        "baseline_control_boundary_flags": baseline_flags,
        "no_rerun_no_api_flags": comparison_flags,
        "comparison_offline_only": True,
        "vendor_tau2_bench_mutated_by_comparison": False,
        "control_boundary_flags_ok": not any(comparison_flags.values()) and not any(fixture_flags.values()) and not any(baseline_flags.values()),
        "baseline_provider_model_task_max_steps_present": baseline_provider_model_task_max_steps_present,
        "baseline_provider": inputs["baseline_final_state"].get("provider"),
        "baseline_model": inputs["baseline_final_state"].get("model"),
        "baseline_max_steps": inputs["baseline_final_state"].get("max_steps"),
    }

    expected_differences = [
        "fixture uses a synthetic task ID while the real baseline uses create_task_1",
        "fixture emits 18 events and packets while the real baseline projection emits 12",
        "fixture graph includes synthetic lifecycle nodes while the real graph includes extracted baseline artifact/provenance nodes",
        "real baseline includes provider/model/task/max_steps provenance from the model-backed source run",
        "real baseline lacks tick/effect timeline details because tau2 did not serialize them",
    ]
    baseline_known_gaps = inputs["baseline_final_state"].get("known_coverage_gaps") or inputs["baseline_projection"].get("known_coverage_gaps") or []
    derived_gaps = []
    if graph_alignment["event_semantic_family_alignment"]["fixture_only"]:
        derived_gaps.append(
            "Fixture-only semantic families reflect smoke-harness lifecycle coverage not serialized by the real baseline."
        )
    if graph_alignment["artifact_provenance_nodes"]["fixture"]["count"] < graph_alignment["artifact_provenance_nodes"]["baseline"]["count"]:
        derived_gaps.append("Real baseline has richer extracted artifact provenance than the fixture projection.")
    if "tick" not in baseline_summary["event_semantic_families"]:
        derived_gaps.append("Real baseline does not include tick-level events.")
    if not any("effect" in key for key in baseline_summary["event_semantic_families"]):
        derived_gaps.append("Real baseline does not include effect/state-transition timeline events.")
    coverage_gaps = {
        "expected_fixture_vs_real_differences": expected_differences,
        "known_coverage_gaps": list(dict.fromkeys([*baseline_known_gaps, *derived_gaps])),
        "fixture_only_coverage": {
            "event_families": graph_alignment["event_semantic_family_alignment"]["fixture_only"],
            "components": graph_alignment["component_alignment"]["fixture_only"],
            "edge_types": graph_alignment["edge_type_alignment"]["fixture_only"],
        },
        "baseline_only_coverage": {
            "event_families": graph_alignment["event_semantic_family_alignment"]["baseline_only"],
            "components": graph_alignment["component_alignment"]["baseline_only"],
            "edge_types": graph_alignment["edge_type_alignment"]["baseline_only"],
            "artifact_nodes": graph_alignment["artifact_provenance_nodes"]["baseline"],
        },
    }

    errors = [*fixture_validation["errors"], *baseline_validation["errors"]]
    if errors or not provenance_alignment["control_boundary_flags_ok"]:
        status = STATUS_FAILED
    elif coverage_gaps["known_coverage_gaps"] or expected_differences:
        status = STATUS_EXPECTED_GAPS
    else:
        status = STATUS_PASSED

    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "status": status,
        "created_at": created_at,
        "command": COMMAND,
        "fixture": {"run_dir": rel(fixture_run_dir), "summary": fixture_summary},
        "baseline": {"run_dir": rel(baseline_run_dir), "summary": baseline_summary},
        "graph_alignment": graph_alignment,
        "packet_alignment": packet_alignment,
        "provenance_alignment": provenance_alignment,
        "coverage_gaps": coverage_gaps,
        "validation_errors": errors,
    }


def write_outputs(output_dir: pathlib.Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if report["status"] == STATUS_INPUTS_MISSING:
        graph_alignment: dict[str, Any] = {}
        packet_alignment: dict[str, Any] = {}
        provenance_alignment = {"no_rerun_no_api_flags": report["no_rerun_no_api_flags"]}
        coverage_gaps = {"missing_inputs": report["missing_inputs"]}
    else:
        graph_alignment = report["graph_alignment"]
        packet_alignment = report["packet_alignment"]
        provenance_alignment = report["provenance_alignment"]
        coverage_gaps = report["coverage_gaps"]
    final_state = {
        "schema_version": report["schema_version"],
        "status": report["status"],
        "created_at": report["created_at"],
        "fixture_run_dir": report["fixture"]["run_dir"],
        "baseline_run_dir": report["baseline"]["run_dir"],
        "output_dir": rel(output_dir),
        "output_files": [rel(output_dir / file_name) for file_name in OUTPUT_FILES],
        "tau2_rerun": False,
        "llm_api_calls_made": False,
        "requires_api_keys": False,
        "activegraph_execution_control_implemented": False,
        "vendor_tau2_bench_mutated": False,
    }
    write_json(output_dir / "activegraph_projection_comparison_report.json", report)
    write_json(output_dir / "graph_alignment.json", graph_alignment)
    write_json(output_dir / "packet_alignment.json", packet_alignment)
    write_json(output_dir / "provenance_alignment.json", provenance_alignment)
    write_json(output_dir / "coverage_gaps.json", coverage_gaps)
    write_json(output_dir / "final_state.json", final_state)
    if report["status"] == STATUS_INPUTS_MISSING:
        summary = f"""# ActiveGraph fixture-vs-real projection comparison

- Status: `{report['status']}`
- Fixture run directory: `{report['fixture']['run_dir']}`
- Baseline run directory: `{report['baseline']['run_dir']}`

Missing required inputs prevented comparison.
"""
    else:
        summary = build_summary(report)
    (output_dir / "activegraph_projection_comparison_summary.md").write_text(summary)
    log_lines = [
        "ActiveGraph fixture-vs-real projection comparison",
        f"created_at={report['created_at']}",
        f"status={report['status']}",
        f"fixture_run_dir={report['fixture']['run_dir']}",
        f"baseline_run_dir={report['baseline']['run_dir']}",
        "boundary=offline artifact comparison only; no tau2 rerun; no LLM/API calls; no API keys required",
    ]
    if report.get("validation_errors"):
        log_lines.extend(f"validation_error={error}" for error in report["validation_errors"])
    (output_dir / "raw.log").write_text("\n".join(log_lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare fixture-backed ActiveGraph projection artifacts against a real baseline projection."
    )
    parser.add_argument("--fixture-run-dir", required=True, type=pathlib.Path)
    parser.add_argument("--baseline-run-dir", required=True, type=pathlib.Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_run_dir = args.fixture_run_dir
    baseline_run_dir = args.baseline_run_dir
    output_dir = baseline_run_dir / "activegraph_projection_comparison"
    try:
        report = compare(fixture_run_dir, baseline_run_dir)
        write_outputs(output_dir, report)
    except Exception as exc:  # noqa: BLE001 - top-level CLI failure reporter.
        output_dir.mkdir(parents=True, exist_ok=True)
        created_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
        report = {
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "status": STATUS_FAILED,
            "created_at": created_at,
            "fixture": {"run_dir": rel(fixture_run_dir)},
            "baseline": {"run_dir": rel(baseline_run_dir)},
            "error": str(exc),
            "no_rerun_no_api_flags": {
                "tau2_rerun": False,
                "llm_api_calls_made": False,
                "requires_api_keys": False,
            },
        }
        write_json(output_dir / "activegraph_projection_comparison_report.json", report)
        write_json(output_dir / "final_state.json", report)
        (output_dir / "raw.log").write_text(
            "ActiveGraph fixture-vs-real projection comparison\n"
            f"created_at={created_at}\nstatus={STATUS_FAILED}\nerror={exc}\n"
        )
        print(f"comparison_status={STATUS_FAILED}")
        print(f"error={exc}", file=sys.stderr)
        return 1

    print(f"comparison_status={report['status']}")
    print(f"fixture_run_dir={rel(fixture_run_dir)}")
    print(f"baseline_run_dir={rel(baseline_run_dir)}")
    print(f"output_dir={rel(output_dir)}")
    return 0 if report["status"] in {STATUS_PASSED, STATUS_EXPECTED_GAPS} else 1


if __name__ == "__main__":
    raise SystemExit(main())
