"""Design-only external audit-store readiness contracts.

This module defines the interface and deterministic mock-contract checks for a
future external immutable audit store. It does not connect to any service,
perform network I/O, enable live reactive-manager execution, or write secrets.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

from experiments.reactive_manager.audit_log import GENESIS_AUDIT_HASH, canonical_hash

EXTERNAL_AUDIT_STORE_CONTRACT_SCHEMA_VERSION = "activegraph_external_audit_store_contracts.v1"
EXTERNAL_AUDIT_STORE_DECISION_SCHEMA_VERSION = "activegraph_external_audit_store_decision.v1"
EXTERNAL_AUDIT_STORE_LIVE_READY = False


class ExternalAuditStore(Protocol):
    """Future external append-only audit-store interface.

    Phase 9 only specifies this protocol. No production implementation exists.
    """

    store_available: bool
    externally_immutable: bool

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append one audit record and return an acknowledgement."""
        raise NotImplementedError

    def read_back(self, audit_id: str) -> dict[str, Any] | None:
        """Read back one stored audit record by deterministic audit ID."""
        raise NotImplementedError


@dataclass
class DeterministicMockExternalAuditStore:
    """In-memory mock used only for deterministic contract validation."""

    store_available: bool = True
    externally_immutable: bool = True
    reject_writes: bool = False
    records: list[dict[str, Any]] = field(default_factory=list)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        if not self.store_available:
            return {"accepted": False, "reason": "store_unavailable"}
        if self.reject_writes:
            return {"accepted": False, "reason": "write_rejected"}
        audit_id = record.get("audit_id")
        if any(existing.get("audit_id") == audit_id for existing in self.records):
            return {"accepted": False, "reason": "duplicate_audit_id"}
        if not record.get("source_artifact"):
            return {"accepted": False, "reason": "missing_source_artifact_link"}
        expected_previous = self.records[-1]["audit_hash"] if self.records else GENESIS_AUDIT_HASH
        if record.get("previous_audit_hash") != expected_previous:
            return {"accepted": False, "reason": "hash_chain_mismatch"}
        payload = {key: value for key, value in record.items() if key != "audit_hash"}
        if record.get("audit_hash") != canonical_hash(payload):
            return {"accepted": False, "reason": "hash_chain_mismatch"}
        self.records.append(copy.deepcopy(record))
        return {"accepted": True, "reason": "append_only_write_accepted", "audit_id": audit_id, "audit_hash": record["audit_hash"]}

    def read_back(self, audit_id: str) -> dict[str, Any] | None:
        for record in self.records:
            if record.get("audit_id") == audit_id:
                return copy.deepcopy(record)
        return None


def _decision(decision_id: str, scenario: str, accepted: bool, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": EXTERNAL_AUDIT_STORE_DECISION_SCHEMA_VERSION,
        "decision_id": decision_id,
        "scenario": scenario,
        "accepted": accepted,
        "reason": reason,
        "details": details or {},
    }


def _verify_read_back(store: ExternalAuditStore, record: dict[str, Any]) -> tuple[bool, str]:
    read_back = store.read_back(record["audit_id"])
    if read_back != record:
        return False, "read_back_mismatch"
    return True, "read_back_verified"


def build_external_audit_store_contracts(*, audit_records: list[dict[str, Any]], required_source_artifacts: list[str]) -> dict[str, Any]:
    """Validate deterministic mock contracts for a future external audit store."""
    decisions: list[dict[str, Any]] = []
    valid_store = DeterministicMockExternalAuditStore()
    valid_records = audit_records[:2]
    for index, record in enumerate(valid_records, start=1):
        ack = valid_store.append(record)
        read_ok, read_reason = _verify_read_back(valid_store, record) if ack["accepted"] else (False, ack["reason"])
        decisions.append(
            _decision(
                f"external-audit-decision-{index:06d}",
                f"valid_append_and_readback_{index}",
                ack["accepted"] and read_ok,
                read_reason if read_ok else ack["reason"],
                {"audit_id": record.get("audit_id"), "source_artifact": record.get("source_artifact")},
            )
        )

    unavailable = DeterministicMockExternalAuditStore(store_available=False)
    unavailable_ack = unavailable.append(audit_records[0])
    decisions.append(_decision("external-audit-decision-000003", "store_unavailable", False, unavailable_ack["reason"]))

    rejecting = DeterministicMockExternalAuditStore(reject_writes=True)
    rejected_ack = rejecting.append(audit_records[0])
    decisions.append(_decision("external-audit-decision-000004", "write_rejected", False, rejected_ack["reason"]))

    duplicate_ack = valid_store.append(valid_records[0])
    decisions.append(_decision("external-audit-decision-000005", "duplicate_audit_id", False, duplicate_ack["reason"]))

    bad_read_store = DeterministicMockExternalAuditStore()
    bad_read_store.append(audit_records[0])
    tampered = bad_read_store.read_back(audit_records[0]["audit_id"])
    if tampered is not None:
        tampered["result"] = "tampered_after_read"
    read_back_mismatch = tampered != audit_records[0]
    decisions.append(_decision("external-audit-decision-000006", "read_back_mismatch", False, "read_back_mismatch" if read_back_mismatch else "read_back_unexpectedly_matched"))

    bad_hash_record = copy.deepcopy(audit_records[1])
    bad_hash_record["previous_audit_hash"] = "f" * 64
    hash_ack = DeterministicMockExternalAuditStore().append(bad_hash_record)
    decisions.append(_decision("external-audit-decision-000007", "hash_chain_mismatch", False, hash_ack["reason"]))

    missing_source_record = copy.deepcopy(audit_records[0])
    missing_source_record["source_artifact"] = ""
    missing_source_ack = DeterministicMockExternalAuditStore().append(missing_source_record)
    decisions.append(_decision("external-audit-decision-000008", "missing_source_artifact_link", False, missing_source_ack["reason"]))

    accepted = [decision for decision in decisions if decision["accepted"]]
    rejected = [decision for decision in decisions if not decision["accepted"]]
    rejected_reasons = {decision["reason"] for decision in rejected}
    required_failure_modes = {
        "store_unavailable",
        "write_rejected",
        "read_back_mismatch",
        "hash_chain_mismatch",
        "duplicate_audit_id",
        "missing_source_artifact_link",
    }
    all_source_links_required = all(record.get("source_artifact") in required_source_artifacts for record in audit_records)
    contracts_ok = (
        len(accepted) == len(valid_records)
        and required_failure_modes.issubset(rejected_reasons)
        and all_source_links_required
        and valid_store.externally_immutable is True
    )
    return {
        "schema_version": EXTERNAL_AUDIT_STORE_CONTRACT_SCHEMA_VERSION,
        "external_audit_store_live_ready": EXTERNAL_AUDIT_STORE_LIVE_READY,
        "store_kind": "deterministic_mock_only",
        "real_external_service_implemented": False,
        "network_io_enabled": False,
        "append_only_required": True,
        "read_back_verification_required": True,
        "external_immutability_required": True,
        "hash_chain_anchoring_required": True,
        "source_artifact_anchoring_required": True,
        "required_source_artifacts": required_source_artifacts,
        "all_source_links_required": all_source_links_required,
        "accepted_decision_count": len(accepted),
        "rejected_decision_count": len(rejected),
        "required_failure_modes": sorted(required_failure_modes),
        "observed_rejected_reasons": sorted(rejected_reasons),
        "decisions": decisions,
        "contracts_ok": contracts_ok,
    }
