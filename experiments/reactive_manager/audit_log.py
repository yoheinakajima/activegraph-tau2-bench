"""Review-only audit-log integrity helpers for live-readiness artifacts.

The audit log is artifact-only. It reads Phase 7 proposal/readiness artifacts,
creates deterministic JSONL records, and validates a local hash chain. It never
executes replay/fork/diff plans, tau2 control flow, or model/API calls.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

AUDIT_RECORD_SCHEMA_VERSION = "activegraph_live_readiness_audit_record.v1"
AUDIT_INTEGRITY_REPORT_SCHEMA_VERSION = "activegraph_live_readiness_audit_integrity_report.v1"
GENESIS_AUDIT_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    """Return the canonical JSON representation used for deterministic hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(value: Any) -> str:
    """Return a SHA-256 hash over canonical JSON bytes."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    timestamp: str
    run_id: str
    record_type: str
    source_artifact: str
    source_record_id: str | None
    subject: str
    action: str
    result: str
    previous_audit_hash: str
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = AUDIT_RECORD_SCHEMA_VERSION
    audit_hash: str = ""

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "record_type": self.record_type,
            "source_artifact": self.source_artifact,
            "source_record_id": self.source_record_id,
            "subject": self.subject,
            "action": self.action,
            "result": self.result,
            "previous_audit_hash": self.previous_audit_hash,
            "provenance": self.provenance,
        }

    def to_json_dict(self) -> dict[str, Any]:
        value = self.payload_without_hash()
        value["audit_hash"] = self.audit_hash or canonical_hash(value)
        return value


def _load_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _existing_artifact(out_dir: pathlib.Path, artifact_name: str) -> bool:
    return (out_dir / artifact_name).is_file()


def _proposal_ids(proposal_bundle: dict[str, Any]) -> set[str]:
    return {proposal.get("proposal_id", "") for proposal in proposal_bundle.get("proposals", [])}


def _decision_ids(decisions: list[dict[str, Any]]) -> set[str]:
    return {decision.get("decision_id", "") for decision in decisions}


def _append_record(records: list[dict[str, Any]], *, timestamp: str, run_id: str, record_type: str, source_artifact: str, source_record_id: str | None, subject: str, action: str, result: str, provenance: dict[str, Any]) -> None:
    previous = records[-1]["audit_hash"] if records else GENESIS_AUDIT_HASH
    audit_id = f"audit-{len(records) + 1:06d}"
    record = AuditRecord(
        audit_id=audit_id,
        timestamp=timestamp,
        run_id=run_id,
        record_type=record_type,
        source_artifact=source_artifact,
        source_record_id=source_record_id,
        subject=subject,
        action=action,
        result=result,
        previous_audit_hash=previous,
        provenance=provenance,
    ).to_json_dict()
    records.append(record)


def build_audit_records(*, out_dir: pathlib.Path, run_id: str, timestamp: str) -> list[dict[str, Any]]:
    """Build deterministic audit records for Phase 7 proposals and decisions."""
    proposal_bundle = _load_json(out_dir / "live_manager_proposal.json")
    decisions = _load_jsonl(out_dir / "live_opt_in_decisions.jsonl")
    readiness_report = _load_json(out_dir / "live_readiness_report.json")
    contract_report = _load_json(out_dir / "contract_report.json")

    records: list[dict[str, Any]] = []
    for proposal in proposal_bundle.get("proposals", []):
        _append_record(
            records,
            timestamp=timestamp,
            run_id=run_id,
            record_type="live_manager_proposal",
            source_artifact="live_manager_proposal.json",
            source_record_id=proposal.get("proposal_id"),
            subject=proposal.get("scenario", "unknown"),
            action="review_proposal_readiness_inputs",
            result="recorded_for_review_only",
            provenance={
                "phase": proposal_bundle.get("phase"),
                "source_artifact_hash": canonical_hash(proposal),
                "live_execution_requested": proposal.get("requested_capabilities", {}).get("live_execution_requested"),
                "tau2_control_flow_requested": proposal.get("requested_capabilities", {}).get("tau2_control_flow_requested"),
                "llm_api_services_requested": proposal.get("requested_capabilities", {}).get("llm_api_services_requested"),
            },
        )

    for decision in decisions:
        _append_record(
            records,
            timestamp=timestamp,
            run_id=run_id,
            record_type="live_readiness_decision",
            source_artifact="live_opt_in_decisions.jsonl",
            source_record_id=decision.get("decision_id"),
            subject=decision.get("proposal_id", "unknown"),
            action="review_readiness_decision",
            result=decision.get("status", "unknown"),
            provenance={
                "source_artifact_hash": canonical_hash(decision),
                "proposal_id": decision.get("proposal_id"),
                "scenario": decision.get("scenario"),
                "live_ready": decision.get("live_ready"),
                "executed": decision.get("executed"),
                "blocker_count": len(decision.get("blockers", [])),
            },
        )

    _append_record(
        records,
        timestamp=timestamp,
        run_id=run_id,
        record_type="live_readiness_report",
        source_artifact="live_readiness_report.json",
        source_record_id=None,
        subject="phase_7_readiness_report",
        action="review_readiness_report",
        result="live_ready_false" if readiness_report.get("live_ready") is False else "unexpected_live_ready",
        provenance={
            "source_artifact_hash": canonical_hash(readiness_report),
            "proposal_count": readiness_report.get("proposal_count"),
            "decision_count": readiness_report.get("decision_count"),
            "live_execution_available": readiness_report.get("live_execution_available"),
            "disabled_by_construction": readiness_report.get("disabled_by_construction"),
        },
    )
    _append_record(
        records,
        timestamp=timestamp,
        run_id=run_id,
        record_type="phase_6_contract_report",
        source_artifact="contract_report.json",
        source_record_id=None,
        subject="phase_6_contract_report",
        action="review_contract_fail_closed_boundary",
        result=contract_report.get("status", "unknown"),
        provenance={
            "source_artifact_hash": canonical_hash(contract_report),
            "live_execution_available": contract_report.get("live_execution_available"),
            "tau2_control_flow_executed": contract_report.get("tau2_control_flow_executed"),
            "llm_api_calls_made": contract_report.get("llm_api_calls_made"),
        },
    )
    return records


def validate_audit_records(*, out_dir: pathlib.Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    proposal_bundle = _load_json(out_dir / "live_manager_proposal.json")
    decisions = _load_jsonl(out_dir / "live_opt_in_decisions.jsonl")
    proposal_ids = _proposal_ids(proposal_bundle)
    decision_ids = _decision_ids(decisions)
    errors: list[str] = []
    previous = GENESIS_AUDIT_HASH

    for index, record in enumerate(records):
        expected_audit_id = f"audit-{index + 1:06d}"
        if record.get("audit_id") != expected_audit_id:
            errors.append(f"record {index} expected audit_id {expected_audit_id}")
        if record.get("previous_audit_hash") != previous:
            errors.append(f"record {record.get('audit_id')} previous hash mismatch")
        without_hash = {key: value for key, value in record.items() if key != "audit_hash"}
        expected_hash = canonical_hash(without_hash)
        if record.get("audit_hash") != expected_hash:
            errors.append(f"record {record.get('audit_id')} audit hash mismatch")
        source_artifact = record.get("source_artifact")
        if not isinstance(source_artifact, str) or not _existing_artifact(out_dir, source_artifact):
            errors.append(f"record {record.get('audit_id')} links to missing source artifact {source_artifact}")
        if record.get("record_type") == "live_manager_proposal" and record.get("source_record_id") not in proposal_ids:
            errors.append(f"record {record.get('audit_id')} links to missing proposal {record.get('source_record_id')}")
        if record.get("record_type") == "live_readiness_decision" and record.get("source_record_id") not in decision_ids:
            errors.append(f"record {record.get('audit_id')} links to missing decision {record.get('source_record_id')}")
        if record.get("record_type") == "live_readiness_decision" and record.get("provenance", {}).get("proposal_id") not in proposal_ids:
            errors.append(f"record {record.get('audit_id')} decision provenance links to missing proposal")
        previous = record.get("audit_hash", "")

    return {
        "schema_version": AUDIT_INTEGRITY_REPORT_SCHEMA_VERSION,
        "record_count": len(records),
        "hash_chain_valid": not errors,
        "source_links_valid": not errors,
        "genesis_hash": GENESIS_AUDIT_HASH,
        "final_audit_hash": previous if records else GENESIS_AUDIT_HASH,
        "errors": errors,
        "source_artifacts": sorted({record.get("source_artifact") for record in records}),
        "proposal_record_count": sum(1 for record in records if record.get("record_type") == "live_manager_proposal"),
        "decision_record_count": sum(1 for record in records if record.get("record_type") == "live_readiness_decision"),
        "review_only": True,
        "live_execution_enabled": False,
    }
