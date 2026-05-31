"""Design-only operator authorization contracts for future live-manager phases.

Phase 10 models authorization request and decision shapes only. These records are
inert review artifacts: they cannot enable live execution, cannot authorize
model/API calls, cannot carry raw secrets, and cannot execute or control tau2.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import re
from typing import Any

OPERATOR_AUTHORIZATION_REQUEST_SCHEMA_VERSION = "activegraph_operator_authorization_request.v1"
OPERATOR_AUTHORIZATION_DECISION_SCHEMA_VERSION = "activegraph_operator_authorization_decision.v1"
OPERATOR_AUTHORIZATION_LIVE_READY = False
DESIGN_ONLY_MODE = "design_only_review"
PLAN_ONLY_MODE = "plan_only"

_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer)")
_SECRET_VALUE_RE = re.compile(r"(?i)(sk-[a-z0-9_-]{8,}|bearer\s+[a-z0-9._-]+|xox[baprs]-[a-z0-9-]+|gh[pousr]_[a-z0-9_]+)")


@dataclasses.dataclass(frozen=True)
class OperatorAuthorizationRequest:
    """A non-executable future-operator authorization request."""

    operator_id: str | None
    request_id: str | None
    experiment_id: str
    run_scope: str
    requested_mode: str
    acknowledgement_text: str | None
    rollback_acknowledged: bool
    audit_acknowledged: bool
    credential_policy_acknowledged: bool
    sandbox_policy_acknowledged: bool
    expires_at: str
    source_artifact_links: list[str]
    scenario: str
    request_payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    revoked: bool = False
    requested_live_execution: bool = False
    requested_model_api_call: bool = False
    schema_version: str = OPERATOR_AUTHORIZATION_REQUEST_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class OperatorAuthorizationDecision:
    """Validation result for one design-only authorization request."""

    decision_id: str
    request_id: str | None
    scenario: str
    structurally_complete: bool
    accepted: bool
    disabled: bool
    revoked: bool
    expired: bool
    status: str
    reason: str
    blockers: list[str]
    source_links: list[str]
    live_ready: bool = False
    live_execution_available: bool = False
    operator_authorization_live_ready: bool = OPERATOR_AUTHORIZATION_LIVE_READY
    schema_version: str = OPERATOR_AUTHORIZATION_DECISION_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _parse_utc(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _contains_secret_like_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                return True
            if _contains_secret_like_payload(nested):
                return True
        return False
    if isinstance(value, list | tuple | set):
        return any(_contains_secret_like_payload(item) for item in value)
    if isinstance(value, str):
        return bool(_SECRET_VALUE_RE.search(value) or _SECRET_KEY_RE.fullmatch(value.strip()))
    return False


def validate_operator_authorization_request(request: OperatorAuthorizationRequest, *, now: dt.datetime) -> OperatorAuthorizationDecision:
    """Validate shape and fail-closed semantics for one authorization request."""
    blockers: list[str] = []
    parsed_expiry = _parse_utc(request.expires_at)
    required_acknowledgements = {
        "rollback_acknowledged": request.rollback_acknowledged,
        "audit_acknowledged": request.audit_acknowledged,
        "credential_policy_acknowledged": request.credential_policy_acknowledged,
        "sandbox_policy_acknowledged": request.sandbox_policy_acknowledged,
    }

    if not request.operator_id:
        blockers.append("missing_operator_id")
    if not request.request_id:
        blockers.append("missing_request_id")
    if not request.acknowledgement_text:
        blockers.append("missing_acknowledgement_text")
    for name, acknowledged in required_acknowledgements.items():
        if acknowledged is not True:
            blockers.append(f"missing_{name}")
    if parsed_expiry is None:
        blockers.append("invalid_expires_at")
        expired = True
    else:
        expired = parsed_expiry <= now.astimezone(dt.UTC)
        if expired:
            blockers.append("expired_authorization")
    if request.revoked:
        blockers.append("revoked_authorization")
    if request.requested_mode not in {DESIGN_ONLY_MODE, PLAN_ONLY_MODE}:
        blockers.append("requested_live_execution")
    if request.requested_live_execution:
        blockers.append("requested_live_execution")
    if request.requested_model_api_call:
        blockers.append("requested_model_api_call")
    if not request.source_artifact_links:
        blockers.append("missing_source_artifact_links")
    if _contains_secret_like_payload(request.request_payload):
        blockers.append("secret_like_payload_rejected")

    unique_blockers = sorted(set(blockers))
    structurally_complete = not unique_blockers
    disabled = True
    accepted = False
    status = "disabled_design_only" if structurally_complete else "rejected"
    reason = (
        "authorization_structurally_complete_but_live_execution_disabled"
        if structurally_complete
        else "authorization_rejected_fail_closed"
    )
    return OperatorAuthorizationDecision(
        decision_id=f"operator-authorization-decision-for-{request.scenario}",
        request_id=request.request_id,
        scenario=request.scenario,
        structurally_complete=structurally_complete,
        accepted=accepted,
        disabled=disabled,
        revoked=request.revoked,
        expired=expired,
        status=status,
        reason=reason,
        blockers=unique_blockers or ["operator_authorization_live_ready_false", "live_execution_unavailable_fail_closed"],
        source_links=list(request.source_artifact_links),
    )


def build_operator_authorization_contracts(*, run_id: str, source_artifact_links: list[str], now: dt.datetime | None = None) -> dict[str, Any]:
    """Build deterministic Phase 10 authorization scenarios and decisions."""
    now = now or dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    future = (now + dt.timedelta(days=7)).isoformat().replace("+00:00", "Z")
    past = (now - dt.timedelta(days=1)).isoformat().replace("+00:00", "Z")

    base = {
        "operator_id": "operator-fixture-phase10",
        "request_id": "operator-auth-request-000001",
        "experiment_id": "phase10-operator-incident-readiness",
        "run_scope": "mock_contract_validation_only",
        "requested_mode": DESIGN_ONLY_MODE,
        "acknowledgement_text": "I acknowledge this is design-only and cannot enable live execution.",
        "rollback_acknowledged": True,
        "audit_acknowledged": True,
        "credential_policy_acknowledged": True,
        "sandbox_policy_acknowledged": True,
        "expires_at": future,
        "source_artifact_links": source_artifact_links,
        "request_payload": {"credential_reference": "credential://future-vault/operator_approval.001"},
        "revoked": False,
        "requested_live_execution": False,
        "requested_model_api_call": False,
    }

    def request(index: int, scenario: str, **updates: Any) -> OperatorAuthorizationRequest:
        data = copy.deepcopy(base)
        data["request_id"] = f"operator-auth-request-{index:06d}"
        data.update(updates)
        return OperatorAuthorizationRequest(scenario=scenario, **data)

    requests = [
        request(1, "complete_but_disabled_authorization"),
        request(2, "missing_operator_id", operator_id=""),
        request(3, "missing_request_id", request_id=""),
        request(4, "missing_acknowledgements", rollback_acknowledged=False, audit_acknowledged=False, credential_policy_acknowledged=False, sandbox_policy_acknowledged=False),
        request(5, "expired_authorization", expires_at=past),
        request(6, "revoked_authorization", revoked=True),
        request(7, "requested_live_execution", requested_mode="live_execution", requested_live_execution=True),
        request(8, "requested_model_api_call", requested_model_api_call=True),
        request(9, "missing_source_artifact_links", source_artifact_links=[]),
        request(10, "secret_like_payload", request_payload={"api_key": "<redacted-secret-like-contract-value>"}),
    ]
    decisions = [validate_operator_authorization_request(item, now=now).to_json_dict() for item in requests]
    disabled_count = sum(1 for decision in decisions if decision["status"] == "disabled_design_only")
    rejected_count = sum(1 for decision in decisions if decision["status"] == "rejected")
    required_blockers = {
        "missing_operator_id",
        "missing_request_id",
        "missing_rollback_acknowledged",
        "missing_audit_acknowledged",
        "missing_credential_policy_acknowledged",
        "missing_sandbox_policy_acknowledged",
        "expired_authorization",
        "revoked_authorization",
        "requested_live_execution",
        "requested_model_api_call",
        "missing_source_artifact_links",
        "secret_like_payload_rejected",
    }
    observed_blockers = {blocker for decision in decisions for blocker in decision["blockers"]}
    contracts_ok = (
        OPERATOR_AUTHORIZATION_LIVE_READY is False
        and disabled_count == 1
        and rejected_count == len(decisions) - 1
        and required_blockers.issubset(observed_blockers)
        and all(decision["accepted"] is False for decision in decisions)
    )
    return {
        "schema_version": "activegraph_operator_authorization_contracts.v1",
        "run_id": run_id,
        "operator_authorization_live_ready": OPERATOR_AUTHORIZATION_LIVE_READY,
        "live_ready": False,
        "live_execution_available": False,
        "live_execution_unavailable_fail_closed": True,
        "authorization_requests": [item.to_json_dict() for item in requests],
        "decisions": decisions,
        "structurally_complete_disabled_count": disabled_count,
        "accepted_decision_count": 0,
        "rejected_decision_count": rejected_count,
        "required_blockers": sorted(required_blockers),
        "observed_blockers": sorted(observed_blockers),
        "contracts_ok": contracts_ok,
    }
