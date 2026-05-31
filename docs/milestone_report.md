# Milestone report: Phase 1.5 through Phase 13

Phase 13 consolidates the local tau2-bench/ActiveGraph readiness work into reviewable documentation and a cheap CI-lite repository health check. It does **not** add live reactive-manager execution, enable ActiveGraph control of tau2, mutate tau2-bench, or call LLM/API services.

## Executive summary

- The repository now has a compact validation path: `python scripts/run_all_smokes.py`.
- All completed smoke phases are no-LLM, local-file, deterministic checks.
- The vendored tau2-bench source is treated as provenance-locked input at `vendor/tau2-bench`, with commit marker `vendor/tau2-bench.UPSTREAM_COMMIT`.
- ActiveGraph remains trace-only/mock-adapter-backed for these smokes.
- Reactive-manager behavior remains advisory, dry-run, and fail-closed.
- `live_ready=false` is intentional: the repo has readiness evidence and guard contracts, not live execution authority.

## Phase-by-phase progression

| Phase | What it added | Command | Expected status | Major artifacts |
| --- | --- | --- | --- | --- |
| 1.5 | Baseline no-LLM source/data inspection for the vendored tau2 tree. | `python scripts/run_smoke_baseline.py` | `no_llm_smoke_passed` | `final_state.json`, `raw.log`, `summary.md` |
| 2 | Trace-only lifecycle event stream around a deterministic local smoke. | `python scripts/run_trace_smoke.py` | `trace_smoke_passed` | `events.jsonl`, `final_state.json`, `raw.log`, `summary.md` |
| 3 | ActiveGraph trace-only adapter/mock projection of the event stream. | `python scripts/run_activegraph_trace_smoke.py` | `activegraph_trace_mock_passed` or `activegraph_trace_runtime_passed` | `activegraph_trace.json`, `events.jsonl`, `final_state.json`, `raw.log`, `summary.md` |
| 4 | Deterministic state-packet artifacts derived from trace/projection output. | `python scripts/run_state_packet_smoke.py` | `state_packet_smoke_passed` | `state_packets.jsonl`, `state_packet_index.json`, trace/projection artifacts |
| 5 | Dry-run replay/fork/diff planning for a reactive-manager concept. | `python scripts/run_reactive_manager_dry_run.py` | `reactive_manager_dry_run_passed` | `replay_plan.json`, `fork_plan.json`, `diff_report.json`, `manager_plan.json`, `manager_decisions.jsonl` |
| 6 | Guarded execution contracts for preserving no-live-execution boundaries. | `python scripts/run_reactive_manager_contracts.py` | `reactive_manager_contracts_passed` | `contract_report.json`, `contract_decisions.jsonl` |
| 7 | Live opt-in contracts and live-readiness proposal artifacts. | `python scripts/run_live_manager_opt_in_contracts.py` | `live_manager_opt_in_contracts_passed` | `live_manager_proposal.json`, `live_opt_in_decisions.jsonl`, `live_readiness_report.json` |
| 8 | Live-readiness audit, audit log integrity, sandbox policy, and credential policy evidence. | `python scripts/run_live_readiness_audit.py` | `live_readiness_audit_passed` | `live_readiness_audit_report.json`, `audit_integrity_report.json`, `audit_log.jsonl`, `sandbox_policy_report.json`, `credential_policy_report.json` |
| 9 | External audit-store and vault-readiness contracts. | `python scripts/run_external_readiness_contracts.py` | `external_readiness_contracts_passed` | `external_readiness_report.json`, `external_audit_store_contracts.json`, `external_audit_store_decisions.jsonl`, `vault_integration_contracts.json`, `vault_integration_decisions.jsonl` |
| 10 | Operator authorization and incident-response readiness. | `python scripts/run_operator_incident_readiness.py` | `operator_incident_readiness_passed` | `operator_incident_readiness_report.json`, `operator_authorization_requests.json`, `operator_authorization_decisions.jsonl`, `incident_response_plans.json`, `incident_response_decisions.jsonl` |
| 11 | Human review package for the accumulated readiness evidence. | `python scripts/run_human_review_package.py` | `human_review_package_passed` | `human_review_package.json`, `human_review_packet.md`, `reviewer_checklist.md`, `blocker_matrix.json`, `source_evidence_index.json` |
| 12 | Auditor handoff package, evidence bundle, artifact hashes, and retention manifest. | `python scripts/run_auditor_handoff_package.py` | `auditor_handoff_package_passed` | `auditor_handoff_package.json`, `auditor_handoff_packet.md`, `auditor_questions.md`, `handoff_summary.md`, `evidence_bundle_index.json`, `artifact_hash_manifest.json`, `retention_manifest.json` |
| 13 | Consolidated milestone docs, phase matrix, operations guide, CI-lite health check, and optional GitHub Actions. | `python scripts/check_repo_health.py` | `repo_health_passed` | `docs/milestone_report.md`, `docs/phase_matrix.md`, `docs/operations.md`, `.github/workflows/ci.yml` |

## Current safety posture

- Live execution is unavailable and fail-closed.
- `live_ready=false` is preserved in aggregate smoke output and readiness artifacts.
- State packets are emitted for review and planning only; they are not fed back into tau2 execution.
- ActiveGraph does not control tau2 lifecycle, task state, benchmark runs, or result scoring.
- There is no real credential handling, secret storage, external vault integration, or external audit-store write path.
- Existing smoke scripts run over local files and deterministic fixtures only.

## Current benchmark posture

- The repo vendors tau2-bench source locally and records the upstream commit marker.
- The smokes do not run model-backed tau2 episodes and do not invoke `tau2 run`.
- The current checks are readiness, provenance, traceability, and packaging checks rather than benchmark-score-producing runs.
- Future real tau2 runtime checks must be separately gated, no-LLM by default, and explicit about whether they import tau2, run CLI commands, or produce benchmark artifacts.

## Current ActiveGraph posture

- ActiveGraph is represented by trace-only projections and local adapter seams.
- The normal smoke path is mock/fixture-backed; it may report a runtime-backed trace-only status only if an importable runtime is present, but it still does not grant lifecycle control.
- Reactive-manager phases generate plans, decisions, contracts, and review evidence without executing live actions.

## Mock/fixture-backed vs real/local-source-backed

### Mock/fixture-backed

- Trace event lifecycles.
- ActiveGraph trace-only projection when no real runtime is importable.
- State packets derived from deterministic local traces.
- Reactive-manager replay/fork/diff plans.
- Live opt-in, live-readiness, audit, vault, operator, incident, review, handoff, and retention artifacts.

### Real/local-source-backed

- Presence and provenance checks for `vendor/tau2-bench`.
- Local source-map/source-path inspection.
- Repository health checks for required docs, scripts, `.gitignore`, staged runs, and vendor cleanliness.
- Python syntax/compile checks over local `scripts/` and `experiments/` files.

## Intentionally not implemented

- Live reactive-manager execution.
- Any mechanism that allows ActiveGraph to control tau2 lifecycle or task state.
- Feeding state packets back into tau2 execution.
- Mutating tau2-bench behavior or vendored tau2 source.
- Model-backed tau2 benchmark episodes.
- Paid LLM/API calls.
- API-key requirements.
- Real credential/vault handling.
- Raw secret storage.

## Why `live_ready=false` remains correct

`live_ready=false` is not a failure. It is the correct state for this milestone because the repo contains readiness evidence and fail-closed contracts, not an authorized live execution system. A future change that flips live readiness would need separately reviewed implementation, explicit operator gates, credentials policy, runtime isolation, tau2 lifecycle boundaries, and non-mock verification.

## Next strategic options

1. Stop and use this repository as the readiness artifact.
2. Start real no-LLM tau2 import/CLI checks, separately gated and still avoiding model-backed episodes.
3. Start a separately gated real ActiveGraph runtime adapter spike that remains trace-only until reviewed.
4. Prepare a human-readable blog/report from this milestone report.
