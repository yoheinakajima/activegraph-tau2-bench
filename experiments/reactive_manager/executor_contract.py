"""Executor protocol and fail-closed Phase 6 implementations."""
from __future__ import annotations

from typing import Protocol

from experiments.reactive_manager.contracts import (
    ReactiveManagerExecutionDecision,
    ReactiveManagerExecutionRequest,
    ReactiveManagerSafetyPolicy,
)
from experiments.reactive_manager.guards import validate_execution_request


class ReactiveManagerExecutor(Protocol):
    """Execution-like contract boundary for future reactive-manager phases."""

    executor_name: str

    def decide(self, request: ReactiveManagerExecutionRequest, *, decision_id: str) -> ReactiveManagerExecutionDecision:
        """Return a structured decision without executing tau2 control flow."""


class DryRunExecutor:
    """Plan-only executor; accepts only fully valid dry-run requests."""

    executor_name = "DryRunExecutor"

    def __init__(self, *, policy: ReactiveManagerSafetyPolicy, repo_root):
        self.policy = policy
        self.repo_root = repo_root

    def decide(self, request: ReactiveManagerExecutionRequest, *, decision_id: str) -> ReactiveManagerExecutionDecision:
        validation = validate_execution_request(request, policy=self.policy, repo_root=self.repo_root)
        accepted = validation.ok and request.dry_run is True
        return ReactiveManagerExecutionDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            scenario=request.scenario,
            run_id=request.run_id,
            accepted=accepted,
            status="accepted_plan_only" if accepted else "rejected_fail_closed",
            dry_run=True,
            executed=False,
            execution_mode=request.execution_mode,
            executor=self.executor_name,
            reason="Request accepted as plan-only; no tau2 control flow executed." if accepted else "Request failed one or more safety gates and was refused closed.",
            refusal_reasons=[] if accepted else validation.errors,
            validation=validation,
            source_links=list(request.artifact_paths.values()),
        )


class DisabledLiveExecutor:
    """Live executor placeholder that always refuses closed in Phase 6."""

    executor_name = "DisabledLiveExecutor"

    def __init__(self, *, policy: ReactiveManagerSafetyPolicy, repo_root):
        self.policy = policy
        self.repo_root = repo_root

    def decide(self, request: ReactiveManagerExecutionRequest, *, decision_id: str) -> ReactiveManagerExecutionDecision:
        validation = validate_execution_request(request, policy=self.policy, repo_root=self.repo_root)
        refusal_reasons = ["Phase 6 live reactive-manager execution is unavailable by design."] + validation.errors
        return ReactiveManagerExecutionDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            scenario=request.scenario,
            run_id=request.run_id,
            accepted=False,
            status="rejected_fail_closed",
            dry_run=True,
            executed=False,
            execution_mode=request.execution_mode,
            executor=self.executor_name,
            reason="Live execution is disabled; request refused closed without executing tau2.",
            refusal_reasons=refusal_reasons,
            validation=validation,
            source_links=list(request.artifact_paths.values()),
        )


FailClosedExecutor = DisabledLiveExecutor
