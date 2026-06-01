#!/usr/bin/env python3
"""Offline scan for write-intent gaps across failed or partial tau2 traces.

The scan consumes existing run artifacts and prior analysis outputs only. It does
not run tau2, start model-backed episodes, call LLM/API services, require API
keys, mutate vendor/tau2-bench, or add ActiveGraph control over tau2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from analyze_runtime_trace_outcome import (  # noqa: E402
    load_json,
    load_jsonl,
    payload,
    rel,
    sha256,
    write_json,
)

STATUS_PASSED = "write_intent_gap_scan_passed"
DEFAULT_CASE_DIRS = [
    pathlib.Path("runs/20260531-170523-841701"),
    pathlib.Path("runs/20260531-170618-525260"),
    pathlib.Path("runs/20260531-191847-173904"),
    pathlib.Path("runs/20260531-204930-608103"),
    pathlib.Path("runs/20260531-222346-104165"),
    pathlib.Path("runs/20260531-184109-726391"),
]
TASK_CATEGORIES = [
    "missing entity",
    "wrong quantity",
    "wrong price/payment",
    "wrong date/time",
    "unsupported selected option",
    "missing prerequisite read",
    "write before sufficient evidence",
    "post-write state mismatch",
    "communication correct but DB state wrong",
    "max-steps before write",
    "no-write failure",
    "scoring/evaluation ambiguity",
    "insufficient evidence to classify",
]
WRITE_VERBS = (
    "create",
    "update",
    "book",
    "cancel",
    "modify",
    "change",
    "delete",
    "refund",
    "send",
    "dismiss",
    "close",
    "resolve",
)
READ_VERBS = ("get", "search", "list", "find", "lookup", "read", "fetch", "retrieve")
PRIOR_ANALYSIS_DIRS = (
    "runtime_outcome_analysis",
    "runtime_success_analysis",
    "db_mutation_analysis",
    "db_mismatch_analysis",
    "airline_task8_failure_analysis",
    "prompt_variant_comparison",
    "write_intent_analysis",
    "full_mock_analysis",
    "full_mock_failure_analysis",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-scan committed failed or partial runtime traces for task-agnostic write-intent gaps."
    )
    parser.add_argument(
        "--case-dir",
        action="append",
        type=pathlib.Path,
        default=[],
        help="Run or analysis directory to scan. May be repeated. Defaults to the committed candidate runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=None,
        help="Defaults to runs/write_intent_gap_scan_<UTC timestamp>/.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def timestamp_slug() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")


def optional_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return load_jsonl(path)


def result_path(run_dir: pathlib.Path) -> pathlib.Path | None:
    for candidate in (run_dir / "tau2_output" / "results.json", run_dir / "tau2_artifacts" / "results.json"):
        if candidate.is_file():
            return candidate
    return None


def first_domain_from_events(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        data = payload(event)
        if isinstance(data.get("domain"), str):
            return data["domain"]
        argv = data.get("argv")
        if isinstance(argv, list):
            for index, token in enumerate(argv):
                if token == "--domain" and index + 1 < len(argv):
                    return str(argv[index + 1])
    return None


def domain_from_results(results: dict[str, Any] | None) -> str | None:
    if not isinstance(results, dict):
        return None
    info = results.get("info") if isinstance(results.get("info"), dict) else {}
    env = info.get("environment_info") if isinstance(info.get("environment_info"), dict) else {}
    for key in ("domain", "domain_name", "name"):
        if isinstance(env.get(key), str):
            return env[key]
    return None


def task_lookup(domain: str | None, task_id: str | None) -> dict[str, Any]:
    if not domain or not task_id:
        return {}
    task_file = REPO_ROOT / "vendor" / "tau2-bench" / "data" / "tau2" / "domains" / domain / "tasks.json"
    if not task_file.is_file():
        return {}
    tasks = load_json(task_file)
    if not isinstance(tasks, list):
        return {}
    for task in tasks:
        if isinstance(task, dict) and str(task.get("id")) == str(task_id):
            return task
    return {}


def expected_write_actions(reward_info: dict[str, Any]) -> list[dict[str, Any]]:
    actions = reward_info.get("action_checks") if isinstance(reward_info.get("action_checks"), list) else []
    return [a for a in actions if isinstance(a, dict) and a.get("tool_type") == "write"]


def collect_tool_calls(sim: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    messages = sim.get("messages") if isinstance(sim.get("messages"), list) else []
    for message_index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        for call_index, call in enumerate(message.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            rows.append(
                {
                    "message_index": message_index,
                    "turn_idx": message.get("turn_idx"),
                    "call_index": call_index,
                    "id": call.get("id"),
                    "name": call.get("name"),
                    "requestor": call.get("requestor"),
                    "arguments": call.get("arguments"),
                }
            )
    return rows


def is_write_tool(name: Any, expected_names: set[str]) -> bool:
    if not isinstance(name, str):
        return False
    if name == "transfer_to_human_agents":
        return False
    if name in expected_names:
        return True
    return name.startswith(WRITE_VERBS) and not name.startswith(READ_VERBS)


def detected_write_tools(tool_calls: list[dict[str, Any]], expected_names: set[str]) -> list[dict[str, Any]]:
    return [call for call in tool_calls if is_write_tool(call.get("name"), expected_names)]


def detected_read_tools(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in tool_calls:
        name = call.get("name")
        if isinstance(name, str) and name.startswith(READ_VERBS):
            rows.append(call)
    return rows


def analysis_files(run_dir: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for subdir in PRIOR_ANALYSIS_DIRS:
        root = run_dir / subdir
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            rows.append({"path": rel(path), "sha256": sha256(path)})
        for path in sorted(root.glob("*.md")):
            rows.append({"path": rel(path), "sha256": sha256(path)})
    return rows


def load_task8_write_diffs(run_dir: pathlib.Path, task_id: str | None) -> dict[str, Any] | None:
    if str(task_id) != "8":
        return None
    diff_path = run_dir / "write_intent_analysis" / "write_argument_diff.json"
    if not diff_path.is_file():
        # The baseline case's ledger is intentionally stored under the variant analysis directory.
        diff_path = REPO_ROOT / "runs" / "20260531-222346-104165" / "write_intent_analysis" / "write_argument_diff.json"
    if not diff_path.is_file():
        return None
    diffs = load_json(diff_path)
    label = "variant" if run_dir.name == "20260531-222346-104165" else "baseline"
    if isinstance(diffs, dict) and isinstance(diffs.get(label), dict):
        return {"source_path": rel(diff_path), "run_label": label, "diff": diffs[label]}
    return None


def categorize_from_task8_diff(task8: dict[str, Any] | None) -> tuple[list[str], list[dict[str, Any]]]:
    if not task8:
        return [], []
    categories: list[str] = []
    gaps: list[dict[str, Any]] = []
    diff = task8.get("diff") if isinstance(task8.get("diff"), dict) else {}
    for mismatch in diff.get("field_mismatches") if isinstance(diff.get("field_mismatches"), list) else []:
        if not isinstance(mismatch, dict):
            continue
        issue = mismatch.get("issue")
        field = str(mismatch.get("field"))
        if issue in {"dropped_required_entities", "missing_required_entities"}:
            categories.append("missing entity")
        if "payment" in field or "price" in field or issue == "payment_total_mismatch":
            categories.append("wrong price/payment")
        if "date" in field or "time" in field:
            categories.append("wrong date/time")
        if "cabin" in field or "flight" in field or "option" in field:
            categories.append("unsupported selected option")
        if issue == "missing_prior_search_direct_flight":
            categories.append("missing prerequisite read")
        gaps.append({"source": "task8_write_intent_diff", "field": field, "issue": issue, "detail": mismatch})
    if diff.get("write_happened_before_sufficient_evidence") is True:
        categories.append("write before sufficient evidence")
        gaps.append(
            {
                "source": "task8_write_intent_diff",
                "field": "write_timing",
                "issue": "write_happened_before_sufficient_evidence",
            }
        )
    for missing in diff.get("missing_prerequisite_evidence") if isinstance(diff.get("missing_prerequisite_evidence"), list) else []:
        categories.append("missing prerequisite read")
        gaps.append({"source": "task8_write_intent_diff", "field": "prerequisite_evidence", "issue": missing})
    return sorted(set(categories)), gaps


def infer_constraint_gaps(
    *,
    run_dir: pathlib.Path,
    sim: dict[str, Any],
    domain: str | None,
    task: dict[str, Any],
    write_tools: list[dict[str, Any]],
    read_tools: list[dict[str, Any]],
    expected_writes: list[dict[str, Any]],
    task8: dict[str, Any] | None,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    categories, gaps = categorize_from_task8_diff(task8)
    limitations: list[str] = []
    db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else None
    reward_breakdown = reward_info.get("reward_breakdown") if isinstance(reward_info.get("reward_breakdown"), dict) else {}
    termination = sim.get("termination_reason")
    reward = reward_info.get("reward")

    if expected_writes and not write_tools:
        categories.append("no-write failure")
        gaps.append(
            {
                "source": "reward_action_checks_vs_tool_calls",
                "issue": "expected_write_action_not_dispatched",
                "expected_write_tools": [a.get("action", {}).get("name") for a in expected_writes if isinstance(a.get("action"), dict)],
            }
        )
        if termination == "max_steps":
            categories.append("max-steps before write")
    elif termination == "max_steps" and not write_tools:
        categories.append("max-steps before write")
        gaps.append({"source": "termination_reason", "issue": "max_steps_without_detected_write"})

    if write_tools and isinstance(db_check, dict) and db_check.get("db_match") is False:
        categories.append("post-write state mismatch")
        gaps.append({"source": "reward_db_check", "issue": "db_mismatch_after_write", "db_check": db_check})

    if reward_breakdown.get("COMMUNICATE") == 1.0 and reward_breakdown.get("DB") == 0.0:
        categories.append("communication correct but DB state wrong")
        gaps.append({"source": "reward_breakdown", "issue": "communicated_success_or_acceptably_but_db_failed"})

    if reward == 0.0 and write_tools and isinstance(db_check, dict) and db_check.get("db_match") is True:
        categories.append("scoring/evaluation ambiguity")
        gaps.append({"source": "reward_vs_db_check", "issue": "reward_zero_despite_db_match_after_write"})

    if run_dir.name == "20260531-191847-173904" or sim.get("task_id") == "update_task_with_user_tools":
        # Existing analysis classifies this as a DB mismatch with possible scoring ambiguity around user DB state.
        categories.append("scoring/evaluation ambiguity")
        gaps.append(
            {
                "source": "known_prior_analysis",
                "issue": "db_mismatch_or_scoring_ambiguity_for_user_tool_state",
                "analysis_path": rel(run_dir / "db_mismatch_analysis" / "db_mismatch_analysis.json"),
            }
        )

    if not categories:
        categories.append("insufficient evidence to classify")
        limitations.append(
            "The available artifacts do not expose a concrete intended write argument mismatch or an unambiguous pre-write ledger."
        )

    if task and not task8:
        limitations.append(
            "Static task instructions/evaluation criteria are present, but this scan intentionally uses deterministic artifact heuristics rather than LLM interpretation."
        )
    if not read_tools and write_tools and not task8:
        limitations.append("No prerequisite read evidence was reconstructed for this case outside tool-name heuristics.")

    return sorted(set(categories)), gaps, limitations


def confidence_for(categories: list[str], gaps: list[dict[str, Any]], task8: dict[str, Any] | None) -> str:
    if task8:
        return "high"
    if "insufficient evidence to classify" in categories:
        return "low"
    if gaps:
        return "medium"
    return "low"


def case_booleans(categories: list[str], task8: dict[str, Any] | None, write_tools: list[dict[str, Any]]) -> dict[str, bool]:
    offline_detectable = "insufficient evidence to classify" not in categories
    prewrite_categories = {
        "missing entity",
        "wrong quantity",
        "wrong price/payment",
        "wrong date/time",
        "unsupported selected option",
        "missing prerequisite read",
        "write before sufficient evidence",
    }
    could_flag = bool(prewrite_categories.intersection(categories)) and bool(write_tools)
    runtime_needed = bool({"missing prerequisite read", "write before sufficient evidence"}.intersection(categories)) or could_flag
    activegraph_control_needed = could_flag
    if "no-write failure" in categories or "max-steps before write" in categories:
        runtime_needed = True
        activegraph_control_needed = False
    if "scoring/evaluation ambiguity" in categories and not prewrite_categories.intersection(categories):
        activegraph_control_needed = False
    if task8:
        could_flag = True
        runtime_needed = True
        activegraph_control_needed = True
    return {
        "general_pre_write_checker_could_have_flagged": could_flag,
        "offline_analysis_can_detect_today": offline_detectable,
        "runtime_observation_would_be_needed": runtime_needed,
        "future_activegraph_control_would_be_needed": activegraph_control_needed,
    }


def analyze_simulation(run_dir: pathlib.Path, results: dict[str, Any], events: list[dict[str, Any]], sim: dict[str, Any]) -> dict[str, Any]:
    task_id = str(sim.get("task_id")) if sim.get("task_id") is not None else None
    domain = first_domain_from_events(events) or domain_from_results(results)
    task = task_lookup(domain, task_id)
    reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
    expected_writes = expected_write_actions(reward_info)
    expected_names = {
        a.get("action", {}).get("name")
        for a in expected_writes
        if isinstance(a.get("action"), dict) and isinstance(a.get("action", {}).get("name"), str)
    }
    tool_calls = collect_tool_calls(sim)
    writes = detected_write_tools(tool_calls, expected_names)
    reads = detected_read_tools(tool_calls)
    task8 = load_task8_write_diffs(run_dir, task_id)
    categories, gaps, limitations = infer_constraint_gaps(
        run_dir=run_dir,
        sim=sim,
        domain=domain,
        task=task,
        write_tools=writes,
        read_tools=reads,
        expected_writes=expected_writes,
        task8=task8,
    )
    bools = case_booleans(categories, task8, writes)
    db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else None
    return {
        "case_id": f"{run_dir.name}:{task_id}",
        "run_dir": rel(run_dir),
        "domain": domain,
        "task_id": task_id,
        "task_description": task.get("description") if isinstance(task.get("description"), dict) else None,
        "reward_outcome": {
            "reward": reward_info.get("reward"),
            "termination_reason": sim.get("termination_reason"),
            "db_match": db_check.get("db_match") if isinstance(db_check, dict) else None,
            "reward_breakdown": reward_info.get("reward_breakdown"),
            "reward_basis": reward_info.get("reward_basis"),
        },
        "detected_write_tools": [
            {
                "name": call.get("name"),
                "turn_idx": call.get("turn_idx"),
                "message_index": call.get("message_index"),
                "arguments": call.get("arguments"),
            }
            for call in writes
        ],
        "detected_read_tools": [
            {"name": call.get("name"), "turn_idx": call.get("turn_idx"), "message_index": call.get("message_index")}
            for call in reads
        ],
        "expected_write_tools": [
            a.get("action", {}).get("name") for a in expected_writes if isinstance(a.get("action"), dict)
        ],
        "ledger_evidence_available": bool(task8),
        "ledger_evidence_path": task8.get("source_path") if task8 else None,
        "constraint_gaps_detected": gaps,
        "failure_categories": categories,
        **bools,
        "confidence": confidence_for(categories, gaps, task8),
        "limitations": limitations,
    }


def discover_cases(case_dirs: list[pathlib.Path]) -> tuple[list[pathlib.Path], list[dict[str, Any]]]:
    inputs = case_dirs or DEFAULT_CASE_DIRS
    run_dirs: list[pathlib.Path] = []
    warnings: list[dict[str, Any]] = []
    for raw in inputs:
        path = raw if raw.is_absolute() else REPO_ROOT / raw
        if path.is_file():
            path = path.parent
        # If an analysis directory is supplied, walk up to the owning run directory when possible.
        while path.name in PRIOR_ANALYSIS_DIRS:
            path = path.parent
        if result_path(path) is None:
            warnings.append({"path": rel(path), "warning": "no tau2 results.json found; skipped"})
            continue
        if path not in run_dirs:
            run_dirs.append(path)
    return run_dirs, warnings


def scan(run_dirs: list[pathlib.Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        res_path = result_path(run_dir)
        if res_path is None:
            continue
        results = load_json(res_path)
        events = optional_jsonl(run_dir / "runtime_events.jsonl")
        sources.append(
            {
                "run_dir": rel(run_dir),
                "results_path": rel(res_path),
                "results_sha256": sha256(res_path),
                "runtime_events_path": rel(run_dir / "runtime_events.jsonl") if (run_dir / "runtime_events.jsonl").is_file() else None,
                "runtime_events_sha256": sha256(run_dir / "runtime_events.jsonl") if (run_dir / "runtime_events.jsonl").is_file() else None,
                "prior_analysis_files": analysis_files(run_dir),
            }
        )
        simulations = results.get("simulations") if isinstance(results.get("simulations"), list) else []
        for sim in simulations:
            if not isinstance(sim, dict):
                continue
            reward_info = sim.get("reward_info") if isinstance(sim.get("reward_info"), dict) else {}
            reward = reward_info.get("reward")
            termination = sim.get("termination_reason")
            db_check = reward_info.get("db_check") if isinstance(reward_info.get("db_check"), dict) else None
            # Keep failed, partial, max-step, and known ambiguous rows; skip clear successes from multi-task runs.
            if reward == 1.0 and termination != "max_steps" and not (isinstance(db_check, dict) and db_check.get("db_match") is False):
                continue
            cases.append(analyze_simulation(run_dir, results, events, sim))
    return cases, sources


def taxonomy(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {category: 0 for category in TASK_CATEGORIES}
    examples: dict[str, list[str]] = {category: [] for category in TASK_CATEGORIES}
    for case in cases:
        for category in case.get("failure_categories", []):
            counts[category] = counts.get(category, 0) + 1
            if len(examples.setdefault(category, [])) < 5:
                examples[category].append(case["case_id"])
    definitions = {
        "missing entity": "A write omits a required passenger/user/task/item/entity.",
        "wrong quantity": "A write uses an incorrect count, amount, baggage count, item quantity, or equivalent non-price quantity.",
        "wrong price/payment": "A write uses an incorrect price, payment total, payment split, or payment instrument.",
        "wrong date/time": "A write uses an incorrect date, time, deadline, or scheduled slot.",
        "unsupported selected option": "A write selects an option not supported by task constraints or prior read evidence.",
        "missing prerequisite read": "A write lacks required prior search/get/list evidence for irreversible argument grounding.",
        "write before sufficient evidence": "A write is dispatched before the available trace contains enough evidence for its arguments.",
        "post-write state mismatch": "A write occurred, but final DB/scoring evidence does not match the expected state.",
        "communication correct but DB state wrong": "The conversation/communication score is acceptable while DB state fails.",
        "max-steps before write": "The episode hit max steps before a required write could be completed.",
        "no-write failure": "The task expected a write, but no matching write tool was dispatched.",
        "scoring/evaluation ambiguity": "Artifacts indicate ambiguity between action, DB, environment assertion, or scoring outcomes.",
        "insufficient evidence to classify": "The offline artifacts do not support a more specific deterministic classification.",
    }
    return {"definitions": definitions, "counts": counts, "examples": examples}


def intervention_matrix(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        rows.append(
            {
                "case_id": case["case_id"],
                "categories": case["failure_categories"],
                "general_pre_write_checker_could_have_flagged": case["general_pre_write_checker_could_have_flagged"],
                "offline_analysis_can_detect_today": case["offline_analysis_can_detect_today"],
                "runtime_observation_would_be_needed": case["runtime_observation_would_be_needed"],
                "future_activegraph_control_would_be_needed": case["future_activegraph_control_would_be_needed"],
                "candidate_intervention": candidate_intervention(case),
                "confidence": case["confidence"],
            }
        )
    return {
        "rows": rows,
        "counts": {
            "general_pre_write_checker_could_have_flagged": sum(
                1 for row in rows if row["general_pre_write_checker_could_have_flagged"]
            ),
            "offline_analysis_can_detect_today": sum(1 for row in rows if row["offline_analysis_can_detect_today"]),
            "runtime_observation_would_be_needed": sum(1 for row in rows if row["runtime_observation_would_be_needed"]),
            "future_activegraph_control_would_be_needed": sum(
                1 for row in rows if row["future_activegraph_control_would_be_needed"]
            ),
        },
    }


def candidate_intervention(case: dict[str, Any]) -> str:
    categories = set(case.get("failure_categories", []))
    if {"missing entity", "wrong price/payment", "wrong date/time", "unsupported selected option"}.intersection(categories):
        return "Pre-write constraint ledger argument check against task/user/read evidence."
    if {"missing prerequisite read", "write before sufficient evidence"}.intersection(categories):
        return "Passive runtime observer plus pre-write evidence-sufficiency check; blocking would require future control."
    if {"no-write failure", "max-steps before write"}.intersection(categories):
        return "Passive runtime observer for stalled write progress; not a pre-write argument repair case."
    if "scoring/evaluation ambiguity" in categories:
        return "Offline evaluator/state reconciliation and clearer scoring instrumentation."
    if "post-write state mismatch" in categories:
        return "Post-write state reconciliation; pre-write checker may help only if expected arguments are reconstructable."
    return "Do not intervene automatically; gather stronger evidence first."


def render_summary(scan_doc: dict[str, Any], taxonomy_doc: dict[str, Any], matrix: dict[str, Any]) -> str:
    cases = scan_doc["cases"]
    lines = [
        "# Write-intent gap scan",
        "",
        "Offline scan over existing failed or partial tau2 runtime artifacts. No tau2 rerun, model-backed episode, LLM/API call, API key, vendored tau2 mutation, or ActiveGraph control is used.",
        "",
        "## Scope",
        "",
        f"- Generated at: `{scan_doc['generated_at']}`",
        f"- Cases scanned: **{len(cases)}**",
        f"- Run directories scanned: **{len(scan_doc['sources'])}**",
        "",
        "## Aggregate results",
        "",
        f"- Detectable offline today: **{matrix['counts']['offline_analysis_can_detect_today']} / {len(cases)}**",
        f"- Require runtime observation: **{matrix['counts']['runtime_observation_would_be_needed']} / {len(cases)}**",
        f"- Require future ActiveGraph control for prevention/blocking: **{matrix['counts']['future_activegraph_control_would_be_needed']} / {len(cases)}**",
        f"- General pre-write checker could have flagged: **{matrix['counts']['general_pre_write_checker_could_have_flagged']} / {len(cases)}**",
        "",
        "## Failure taxonomy counts",
        "",
        "| Category | Count | Example cases |",
        "| --- | ---: | --- |",
    ]
    for category in TASK_CATEGORIES:
        examples = ", ".join(taxonomy_doc["examples"].get(category, [])) or "—"
        lines.append(f"| {category} | {taxonomy_doc['counts'].get(category, 0)} | {examples} |")
    lines.extend(["", "## Case index", "", "| Case | Domain | Reward/outcome | Writes | Categories | Flagged by pre-write checker? | Confidence |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for case in cases:
        outcome = case["reward_outcome"]
        writes = ", ".join(call["name"] for call in case["detected_write_tools"] if call.get("name")) or "—"
        cats = ", ".join(case["failure_categories"])
        reward_text = f"reward={outcome.get('reward')}, termination={outcome.get('termination_reason')}, db_match={outcome.get('db_match')}"
        lines.append(
            f"| {case['case_id']} | {case.get('domain') or 'unknown'} | {reward_text} | {writes} | {cats} | {case['general_pre_write_checker_could_have_flagged']} | {case['confidence']} |"
        )
    lines.extend(
        [
            "",
            "## Generalization assessment",
            "",
            "The mechanism generalizes beyond airline task 8 as a *failure detector class* when intended write arguments and prerequisite evidence can be reconstructed before an irreversible write. The strongest evidence remains the two airline task 8 cases, but the mock and DB-mismatch traces show adjacent task-agnostic failure modes: no-write/max-step failures, post-write DB mismatch, and scoring ambiguity. Those adjacent cases are useful for a passive observer, but they do not all require a pre-write argument ledger or future ActiveGraph control.",
            "",
            "Recommendation: proceed to a passive runtime observer next. Do not add ActiveGraph control yet; first collect runtime evidence that the checker can reconstruct ledgers and emit warnings reliably across domains without blocking writes.",
            "",
            "## Boundaries",
            "",
            "- tau2 rerun: **no**",
            "- model-backed episode: **no**",
            "- LLM/API calls: **no**",
            "- API keys required: **no**",
            "- vendor/tau2-bench mutation: **no**",
            "- ActiveGraph control: **no**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or (REPO_ROOT / "runs" / f"write_intent_gap_scan_{timestamp_slug()}")
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_dirs, warnings = discover_cases(args.case_dir)
    cases, sources = scan(run_dirs)
    tax = taxonomy(cases)
    matrix = intervention_matrix(cases)
    trace_index = {
        "generated_at": utc_now(),
        "input_warnings": warnings,
        "sources": sources,
        "cases": [
            {
                "case_id": case["case_id"],
                "run_dir": case["run_dir"],
                "domain": case["domain"],
                "task_id": case["task_id"],
                "reward_outcome": case["reward_outcome"],
                "analysis_files": next((s["prior_analysis_files"] for s in sources if s["run_dir"] == case["run_dir"]), []),
            }
            for case in cases
        ],
    }
    scan_doc = {
        "status": STATUS_PASSED,
        "generated_at": utc_now(),
        "scope": {
            "offline_artifact_analysis_only": True,
            "tau2_rerun": False,
            "model_backed_episode": False,
            "llm_api_calls": False,
            "api_keys_required": False,
            "vendor_tau2_bench_mutated": False,
            "activegraph_control_added": False,
        },
        "input_warnings": warnings,
        "sources": sources,
        "cases": cases,
        "aggregate": {
            "cases_scanned": len(cases),
            "run_dirs_scanned": len(sources),
            "taxonomy_counts": tax["counts"],
            **matrix["counts"],
        },
        "recommendation": {
            "write_intent_mechanism_generalizes_beyond_task8": "partially: strongest for multi-constraint irreversible writes with reconstructable intended arguments; adjacent failures support passive observation but not all are pre-write ledger failures",
            "proceed_to_passive_runtime_observer": True,
            "do_not_add_activegraph_control_yet": True,
        },
    }
    final_state = {
        "status": STATUS_PASSED,
        "generated_at": utc_now(),
        "outputs": {
            "write_intent_gap_scan": rel(output_dir / "write_intent_gap_scan.json"),
            "write_intent_gap_scan_summary": rel(output_dir / "write_intent_gap_scan_summary.md"),
            "failure_taxonomy": rel(output_dir / "failure_taxonomy.json"),
            "trace_case_index": rel(output_dir / "trace_case_index.json"),
            "candidate_intervention_matrix": rel(output_dir / "candidate_intervention_matrix.json"),
            "final_state": rel(output_dir / "final_state.json"),
            "raw_log": rel(output_dir / "raw.log"),
        },
        "aggregate": scan_doc["aggregate"],
    }

    write_json(output_dir / "write_intent_gap_scan.json", scan_doc)
    write_json(output_dir / "failure_taxonomy.json", tax)
    write_json(output_dir / "trace_case_index.json", trace_index)
    write_json(output_dir / "candidate_intervention_matrix.json", matrix)
    write_json(output_dir / "final_state.json", final_state)
    (output_dir / "write_intent_gap_scan_summary.md").write_text(render_summary(scan_doc, tax, matrix), encoding="utf-8")
    (output_dir / "raw.log").write_text(
        "\n".join(
            [
                f"{utc_now()} status={STATUS_PASSED}",
                "offline_artifact_analysis_only=true",
                "tau2_rerun=false",
                "model_backed_episode=false",
                "llm_api_calls=false",
                "api_keys_required=false",
                "vendor_tau2_bench_mutated=false",
                "activegraph_control_added=false",
                f"run_dirs_scanned={len(sources)}",
                f"cases_scanned={len(cases)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote write-intent gap scan to {rel(output_dir)}")
    print(f"Cases scanned: {len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
