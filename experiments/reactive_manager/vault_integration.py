"""Design-only future vault-integration readiness contracts.

The module accepts only inert credential://future-vault/<name> handles. It never
resolves secrets, reads environment variables, reads filesystem secrets, or
stores raw credential material.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

VAULT_INTEGRATION_CONTRACT_SCHEMA_VERSION = "activegraph_vault_integration_contracts.v1"
VAULT_INTEGRATION_DECISION_SCHEMA_VERSION = "activegraph_vault_integration_decision.v1"
VAULT_INTEGRATION_LIVE_READY = False
VAULT_HANDLE_PREFIX = "credential://future-vault/"
VAULT_HANDLE_RE = re.compile(r"^credential://future-vault/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
RAW_CREDENTIAL_RE = re.compile(r"(?i)(^sk-[A-Za-z0-9_-]{8,}|api[_-]?key|secret|token|bearer\s+[A-Za-z0-9._-]{8,})")
ENV_LOOKUP_RE = re.compile(r"(?i)^(env:|\$\{?[A-Z_][A-Z0-9_]*\}?$|os\.environ|environment://)")
FILE_LOOKUP_RE = re.compile(r"(?i)^(file://|/|~?/|\.\.?/).*(secret|token|credential|key)")


@dataclass(frozen=True)
class VaultCredentialHandle:
    handle: str

    def to_json_dict(self) -> dict[str, str]:
        return {"handle": self.handle, "reference_type": "future_vault_handle_only"}


class VaultCredentialResolver(Protocol):
    """Future vault resolver protocol. Phase 9 provides no implementation."""

    vault_runtime_available: bool

    def validate_handle(self, reference: str) -> VaultCredentialHandle:
        """Validate a handle reference without resolving secret material."""
        raise NotImplementedError

    def resolve(self, handle: VaultCredentialHandle) -> str:
        """Future placeholder. Phase 9 must not resolve raw credential material."""
        raise NotImplementedError


class DeterministicMockVaultCredentialResolver:
    """Fail-closed deterministic mock resolver used for contract checks only."""

    vault_runtime_available = False

    def validate_handle(self, reference: str) -> VaultCredentialHandle:
        classification = classify_vault_reference(reference)
        if classification["accepted"] is not True:
            raise ValueError(str(classification["reason"]))
        return VaultCredentialHandle(handle=reference)

    def resolve(self, handle: VaultCredentialHandle) -> str:
        raise RuntimeError(f"vault runtime unavailable for handle {handle.handle!r}")


def classify_vault_reference(reference: str) -> dict[str, object]:
    """Classify a candidate reference without returning unsafe raw values."""
    if VAULT_HANDLE_RE.fullmatch(reference):
        return {"accepted": True, "reason": "valid_future_vault_handle", "sanitized_reference": reference}
    if reference.startswith(VAULT_HANDLE_PREFIX):
        return {"accepted": False, "reason": "invalid_future_vault_handle_shape", "sanitized_reference": "credential://future-vault/<invalid>"}
    if ENV_LOOKUP_RE.search(reference):
        return {"accepted": False, "reason": "environment_variable_lookup_rejected", "sanitized_reference": "<env-lookup-redacted>"}
    if FILE_LOOKUP_RE.search(reference):
        return {"accepted": False, "reason": "filesystem_secret_read_rejected", "sanitized_reference": "<file-lookup-redacted>"}
    if RAW_CREDENTIAL_RE.search(reference):
        return {"accepted": False, "reason": "raw_credential_value_rejected", "sanitized_reference": "<raw-credential-redacted>"}
    return {"accepted": False, "reason": "credential_reference_must_be_future_vault_handle", "sanitized_reference": "<redacted>"}


def build_vault_integration_contracts() -> dict[str, object]:
    """Build deterministic handle-only vault readiness contracts."""
    resolver = DeterministicMockVaultCredentialResolver()
    scenarios = [
        {"scenario": "valid_future_vault_handle", "candidate": "credential://future-vault/operator_approval.001"},
        {"scenario": "raw_secret_value", "candidate": "sk-redacted-contract-shape"},
        {"scenario": "environment_variable_lookup", "candidate": "env:ACTIVEGRAPH_TOKEN"},
        {"scenario": "filesystem_secret_read", "candidate": "file:///run/secrets/activegraph-token"},
        {"scenario": "wrong_scheme", "candidate": "vault://future-vault/operator_approval.001"},
        {"scenario": "path_traversal_handle", "candidate": "credential://future-vault/../operator"},
    ]
    decisions: list[dict[str, object]] = []
    for index, scenario in enumerate(scenarios, start=1):
        classification = classify_vault_reference(scenario["candidate"])
        decisions.append(
            {
                "schema_version": VAULT_INTEGRATION_DECISION_SCHEMA_VERSION,
                "decision_id": f"vault-integration-decision-{index:06d}",
                "scenario": scenario["scenario"],
                "accepted": classification["accepted"],
                "reason": classification["reason"],
                "sanitized_reference": classification["sanitized_reference"],
            }
        )
    accepted = [decision for decision in decisions if decision["accepted"]]
    rejected = [decision for decision in decisions if not decision["accepted"]]
    rejected_reasons = {str(decision["reason"]) for decision in rejected}
    required_rejections = {
        "raw_credential_value_rejected",
        "environment_variable_lookup_rejected",
        "filesystem_secret_read_rejected",
        "credential_reference_must_be_future_vault_handle",
        "invalid_future_vault_handle_shape",
    }
    contracts_ok = (
        resolver.vault_runtime_available is False
        and len(accepted) == 1
        and accepted[0]["scenario"] == "valid_future_vault_handle"
        and required_rejections.issubset(rejected_reasons)
        and all("sk-redacted-contract-shape" not in str(decision) for decision in decisions)
    )
    return {
        "schema_version": VAULT_INTEGRATION_CONTRACT_SCHEMA_VERSION,
        "vault_integration_live_ready": VAULT_INTEGRATION_LIVE_READY,
        "resolver_kind": "deterministic_mock_only",
        "real_vault_implemented": False,
        "vault_runtime_available": resolver.vault_runtime_available,
        "accepted_handle_schema": "credential://future-vault/<name>",
        "raw_credential_values_allowed": False,
        "environment_variable_lookup_allowed": False,
        "filesystem_secret_reads_allowed": False,
        "secret_resolution_enabled": False,
        "raw_material_written_to_artifacts": False,
        "future_requirements": [
            "vault availability",
            "access policy",
            "audit logging",
            "rotation metadata",
            "scoped handles",
            "no raw material in artifacts",
        ],
        "accepted_decision_count": len(accepted),
        "rejected_decision_count": len(rejected),
        "required_rejections": sorted(required_rejections),
        "observed_rejected_reasons": sorted(rejected_reasons),
        "decisions": decisions,
        "contracts_ok": contracts_ok,
    }
