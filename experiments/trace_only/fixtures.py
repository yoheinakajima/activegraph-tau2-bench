"""No-LLM fixture data for exercising the Phase 2 trace pipeline.

The fixture mirrors tau2 lifecycle boundaries without importing tau2 or running a
model-backed episode. It is deliberately tiny so the emitted events are easy to
inspect and compare against future real trace hooks.
"""
from __future__ import annotations

from typing import Any

FIXTURE_TASK_ID = "trace-fixture-mock-task-001"
FIXTURE_COMMAND = "python scripts/run_trace_smoke.py"
FIXTURE_DOMAIN = "mock"
FIXTURE_SOURCE_PATHS = {
    "cli": "vendor/tau2-bench/src/tau2/cli.py",
    "runner_batch": "vendor/tau2-bench/src/tau2/runner/batch.py",
    "runner_simulation": "vendor/tau2-bench/src/tau2/runner/simulation.py",
    "orchestrator": "vendor/tau2-bench/src/tau2/orchestrator/orchestrator.py",
    "environment": "vendor/tau2-bench/src/tau2/environment/environment.py",
    "evaluator": "vendor/tau2-bench/src/tau2/evaluator/evaluator.py",
    "results": "vendor/tau2-bench/src/tau2/data_model/simulation.py",
}

FIXTURE_TRANSCRIPT: list[dict[str, Any]] = [
    {
        "turn_index": 0,
        "role": "user",
        "content_summary": "User asks for help with a mock account lookup.",
    },
    {
        "turn_index": 1,
        "role": "assistant",
        "content_summary": "Agent requests the safe fixture lookup tool.",
        "tool_call": {
            "name": "mock_lookup_account",
            "arguments": {"account_id": "acct_fixture_001"},
            "result": {"status": "ok", "tier": "standard"},
        },
    },
    {
        "turn_index": 2,
        "role": "assistant",
        "content_summary": "Agent summarizes the fixture result and ends the task.",
    },
]

INITIAL_FIXTURE_STATE: dict[str, Any] = {
    "account_id": "acct_fixture_001",
    "tier": "unknown",
    "tool_calls": 0,
}

FINAL_FIXTURE_STATE: dict[str, Any] = {
    "account_id": "acct_fixture_001",
    "tier": "standard",
    "tool_calls": 1,
}
