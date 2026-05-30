"""Handle-only credential-vault stubs for live-readiness review.

This module intentionally does not implement credential storage or environment
secret lookup. It validates inert future-vault handles only and refuses raw
secret-shaped values before any future live manager can become ready.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

CREDENTIAL_POLICY_REPORT_SCHEMA_VERSION = "activegraph_credential_policy_report.v1"
HANDLE_PREFIX = "credential://future-vault/"
HANDLE_RE = re.compile(r"^credential://future-vault/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
RAW_SECRET_RE = re.compile(
    r"(?i)(^sk-[A-Za-z0-9_-]{8,}|api[_-]?key|secret|token|bearer\s+[A-Za-z0-9._-]{8,}|[A-Za-z0-9+/]{32,}={0,2}$)"
)


@dataclass(frozen=True)
class CredentialReference:
    handle: str

    def to_json_dict(self) -> dict[str, str]:
        return {"handle": self.handle, "reference_type": "handle_only_future_vault"}


class CredentialVault(Protocol):
    """Future vault protocol stub; no runtime implementation exists in Phase 8."""

    vault_runtime_available: bool

    def resolve(self, reference: CredentialReference) -> str:
        """Future interface placeholder. Phase 8 never resolves handles."""
        raise NotImplementedError


class UnavailableCredentialVault:
    """Fail-closed credential-vault stub with no secret storage or resolution."""

    vault_runtime_available = False

    def resolve(self, reference: CredentialReference) -> str:
        raise RuntimeError(f"credential vault runtime unavailable for handle {reference.handle!r}")


def classify_credential_reference(value: str) -> dict[str, object]:
    """Classify a candidate without returning raw secret values in reports."""
    if HANDLE_RE.fullmatch(value):
        return {"accepted": True, "reason": "valid_future_vault_handle", "sanitized_reference": value}
    if value.startswith(HANDLE_PREFIX):
        return {"accepted": False, "reason": "invalid_future_vault_handle_shape", "sanitized_reference": "credential://future-vault/<invalid>"}
    if RAW_SECRET_RE.search(value):
        return {"accepted": False, "reason": "raw_secret_like_value_rejected", "sanitized_reference": "<redacted>"}
    return {"accepted": False, "reason": "credential_reference_must_be_future_vault_handle", "sanitized_reference": "<redacted>"}


def build_credential_policy_report() -> dict[str, object]:
    """Build a deterministic report proving only inert handles are accepted."""
    vault = UnavailableCredentialVault()
    scenarios = [
        {"scenario": "valid_future_handle", "classification": classify_credential_reference("credential://future-vault/review-only-demo")},
        {"scenario": "invalid_raw_api_key_shape", "classification": classify_credential_reference("sk-redactedrawshape1234567890")},
        {"scenario": "invalid_secret_label", "classification": classify_credential_reference("API_KEY=redacted-value")},
        {"scenario": "invalid_wrong_scheme", "classification": classify_credential_reference("vault://future-vault/review-only-demo")},
        {"scenario": "invalid_handle_name", "classification": classify_credential_reference("credential://future-vault/../secret")},
    ]
    accepted = [item for item in scenarios if item["classification"]["accepted"] is True]
    rejected = [item for item in scenarios if item["classification"]["accepted"] is False]
    return {
        "schema_version": CREDENTIAL_POLICY_REPORT_SCHEMA_VERSION,
        "vault_runtime_available": vault.vault_runtime_available,
        "credential_live_ready": False,
        "credential_reference_policy": "handle_only",
        "accepted_handle_prefix": HANDLE_PREFIX,
        "raw_secret_storage_enabled": False,
        "environment_secret_lookup_enabled": False,
        "real_credential_resolution_enabled": False,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "scenarios": scenarios,
        "valid_handle_accepted": len(accepted) == 1 and accepted[0]["scenario"] == "valid_future_handle",
        "raw_secret_like_values_rejected": all(
            item["classification"]["accepted"] is False
            for item in scenarios
            if item["scenario"].startswith("invalid_raw") or item["scenario"] == "invalid_secret_label"
        ),
        "no_raw_secrets_written": all(item["classification"]["sanitized_reference"] != "sk-redactedrawshape1234567890" for item in scenarios),
        "live_ready_blocker": "credential vault runtime is not implemented in Phase 8",
    }
