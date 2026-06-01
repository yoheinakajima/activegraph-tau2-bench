# tau2 Regimes port milestone report

## 1. Purpose and scope

This report is an implementation handoff for porting the completed `activegraph-tau2-bench` tau2 tracing, failure-analysis, write-intent, and passive-observer work into the separate `regimes` repository as a tau2 target. It is deliberately scoped as **target-port and mechanism-validation evidence**, not as an empirical-improvement claim.

Non-goals and boundaries:

- No ActiveGraph control over tau2 has been implemented or validated.
- No tau2 reward, database-check, communication, or action-score improvement has been shown.
- No blocking, rewriting, repair, rollback, or intervention policy is production-ready.
- The evidence is based on already-produced artifacts; this report does not require rerunning tau2, model-backed episodes, LLM/API calls, API keys, or vendored tau2 mutation.
- The primary deliverable is a concrete implementation plan for `regimes`, including outcome parsing, deterministic taxonomy, tool ownership typing, observer artifact ingestion, and stop conditions before any broader paid tau2 execution.

## 2. Relation to Regimes

### Concept mapping

| Regimes concept | tau2 port mapping | Implementation implication |
| --- | --- | --- |
| `Target` | `Tau2Target` wrapper around existing tau2 artifact directories first, with optional paid-run bridge later | Start in artifact-only mode so `regimes` can evaluate historical runs deterministically before owning execution. |
| `EvalBackend` | tau2 evaluator output plus post-run/runtime artifacts: reward, DB checks, communication score, action/env/NL scores, stop reason, tool timeline | Backend adapter should normalize heterogeneous result JSON/log layouts into a stable `Tau2Outcome`. |
| `Outcome` | Per task/trial object containing scalar scores, action-match counts, termination, tool calls, write candidates, observer counts, warning classes, and source paths | `Outcome` must preserve enough provenance for deterministic taxonomy and report regeneration. |
| `RegimeTaxonomy` | Deterministic labels such as `success`, `failed_no_write`, `write_argument_mismatch`, `observer_emission_gap_by_tool_coverage` | Classification should be artifact-derived and side-effect free; ambiguous cases should become `insufficient_evidence`, not guessed successes/failures. |
| `ActionSpace` | tau2 tool calls partitioned into reads, assistant/business writes, user/environment writes, evaluator replay writes, and observer-supported/unsupported writes | Tool ownership registry is required before intervention-style reasoning is meaningful. |
| Held-out/gated discipline | Full tau2 runs remain gated until artifact parsing, taxonomy histograms, registry coverage, small reports, and guardrails exist | `regimes` should prevent paid execution from being the first integration test for the target. |

### LongMemEval comparison

The LongMemEval `assemble-internal` failures are reconciliation failures over retrieved memory fragments: the system must decide which internal evidence to assemble into a final answer. The tau2 failures observed here are structurally related but operationally different: the assistant must ground a state-changing tool call in multi-turn evidence, policy constraints, and tool arguments before the evaluator checks a persistent state transition.

The common Regimes seam is **evidence-to-commit reconciliation**. LongMemEval stresses answer assembly from partially conflicting or incomplete memory; tau2 stresses write-intent construction from reads, user instructions, policy constraints, and tool schemas. The tau2 target is therefore not a clone of LongMemEval. It is a structurally different target: **multi-turn, policy-constrained, tool-using, and stateful**, with failures that can occur before a write, during write argument construction, after a write, or inside observer/evaluator coverage.

## 3. Artifact inventory

### Primary milestone artifacts

| Artifact | Domain / scope | Outcome | Runtime events | Observer artifacts | Analysis directories / notes |
| --- | --- | --- | ---: | --- | --- |
| `runs/20260531-184109-726391` | `mock`, 10 tasks | Pass rate `0.800`; average reward `0.8000` | 446 | Not the main observer case | Mock full traced baseline for baseline outcome parsing and event-count handling. |
| `runs/20260531-193831-340466` | `airline`, task `0` | Reward `1.0`; DB check `1.0` | 70 | Not the main observer case | Read-only success fixture for non-write success parsing. |
| `runs/20260531-204930-608103` | `airline`, task `8` baseline | Reward `0.0`; DB check `0.0`; read actions `3/3`; write actions `0/1` | Not specified in prompt | Offline analysis artifacts | `airline_task8_failure_analysis/`; expected Sophia + Kevin on HAT271 for `$348`, observed Sophia only for `$174`. |
| `runs/20260531-222346-104165` | `airline`, task `8` prompt variant | Reward `0.0`; DB check `0.0`; read actions `2/3`; write actions `0/1` | Not specified in prompt | Offline analysis artifacts | `prompt_variant_comparison/`; `write_intent_analysis/`; preserved Sophia + Kevin but used wrong payment and lacked/failed required search evidence. |
| `runs/write_intent_gap_scan_20260531-230310/` | Multi-case offline scan | 8 cases scanned; `7/8` detectable offline; `3/8` require runtime observation; `2/8` require future ActiveGraph control | N/A | N/A | Evidence that generalization beyond airline task 8 is partial but meaningful. |
| Passive observer smoke from `run_write_intent_observer_smoke.py` | Fixture set | Observer smoke passed | Fixture-backed | Fixture observer outputs | Includes airline task 8 baseline, prompt variant, successful `create_task_1`, no-write failure, and DB/scoring ambiguity. |
| `runs/20260601-033142-413096` | Paid observer-enabled airline task `8` | Task remains failed; live observer emits incomplete ledgers and not-evaluable diffs | Not specified in prompt | `observer_events=39`; `constraint_ledger_snapshots=13`; `write_intent_diffs=13` | Expected task ledger is missing at runtime; live ledger status is `runtime_incomplete_ledger`. |
| `runs/20260601-033543-612139` | `airline`, 5-task observer-enabled batch | Average reward `0.200`; pass `0.200`; read actions `5/7`; DB match `2/4`; normal stop `4`; max steps `1` | 526 | Observer files all had `0` lines | Observer emission gap analysis found likely write candidates `cancel_reservation` and `send_certificate`; likely root cause is missing hook coverage for those write tools, not absence of writes. |

### Cross-domain mini-tests

| Artifact | Domain / task | Outcome | Tool / action evidence | Observer result | Regimes use |
| --- | --- | --- | --- | --- | --- |
| `runs/20260601-041116-120115` | `airline`, task `1` | Reward `0.0`; DB match `0.0`; read actions `2/2`; normal stop | Tools included `get_user_details`, `get_reservation_details`, `cancel_reservation` | Observer files had `0` rows | Cancellation/write coverage gap fixture; demonstrates observer gap beyond task 8. |
| `runs/20260601-041151-558787` | `retail`, task `0` | Reward `1.0`; DB match `1.0`; read actions `4/4`; write actions `1/1` | Write tool `exchange_delivered_order_items` | Observer files had `0` rows | Successful non-airline assistant/business write fixture that is currently unobserved. |
| `runs/20260601-041221-091109` | `telecom`, one task | Reward `1.0`; DB match `1.0`; write actions `2/2` | User-side write tools `toggle_airplane_mode`, `toggle_roaming` | Observer files had `0` rows | Successful user/environment write fixture that is currently unobserved. |

Cross-domain interpretation for `regimes`:

- Observer coverage gaps generalize beyond airline task 8.
- Retail exposes successful assistant/business write flows that should not be warned on merely because they write.
- Telecom exposes user/environment writes that should be typed separately from assistant/business state commits.
- tau2 write ownership should be explicitly typed as `assistant_business_write`, `user_environment_write`, `evaluator_replay_write`, `observer_supported_write`, and `observer_unsupported_write` rather than inferred from reward alone.

## 4. Proposed `Tau2Outcome` schema

`Tau2Outcome` should be a stable, serializable object with lossy-normalized scalar fields and lossless source-path provenance.

```python
@dataclass(frozen=True)
class Tau2Outcome:
    # Identity
    run_id: str
    domain: str
    task_id: str | int | None
    trial_id: str | int | None
    artifact_root: str

    # Scores
    reward: float | None
    db_check: float | None
    communicate_score: float | None
    action_score: float | None
    env_score: float | None
    nl_score: float | None

    # Termination
    termination_reason: str | None  # normal_stop, max_steps, error, unknown
    max_steps_reached: bool | None

    # Action checks
    expected_read_actions: int | None
    matched_read_actions: int | None
    expected_write_actions: int | None
    matched_write_actions: int | None

    # Tool evidence
    tool_timeline: list[Tau2ToolCall]
    read_tools: list[str]
    write_tools: list[str]
    write_candidates: list[Tau2WriteCandidate]
    write_ownership_types: list[str]

    # Observer evidence
    observer_event_count: int
    constraint_ledger_snapshot_count: int
    write_intent_diff_count: int
    observer_warning_count: int
    observer_warnings: list[str]
    observer_artifact_counts: dict[str, int]
    observer_coverage_notes: list[str]

    # Classification/provenance
    regime_labels: list[str]
    insufficient_evidence_reasons: list[str]
    source_artifact_paths: dict[str, str]
```

Recommended nested fields:

- `Tau2ToolCall`: `turn_index`, `actor`, `tool_name`, `arguments_redacted`, `result_status`, `state_hash_before`, `state_hash_after`, `is_read`, `is_write`, `ownership_type`, `source_event_path`.
- `Tau2WriteCandidate`: `tool_name`, `candidate_source` (`runtime_tool_call`, `postrun_action_check`, `observer_gap_analysis`, `manual_analysis`), `expected_args_summary`, `observed_args_summary`, `argument_match_status`, `prerequisite_reads_present`, `post_write_state_match`, `coverage_status`.
- `source_artifact_paths`: paths to raw results, runtime events, observer JSONL, analysis JSON, summary markdown, and generated `regimes` report inputs.

## 5. Proposed tau2 failure-regime taxonomy

Taxonomy should be deterministic, multi-label where useful, and conservative when artifacts are incomplete.

| Label | Trigger / rule sketch | Example source |
| --- | --- | --- |
| `success` | Reward and DB check indicate pass, or task-specific evaluator reports full success. | Airline task 0; retail task 0; telecom mini-test. |
| `failed_no_write` | Expected writes exist, matched writes are zero, and no state-changing tool call candidate is observed. | No-write fixture cases from observer smoke. |
| `failed_partial_progress` | Some reads or intermediate actions match but final reward/DB fails. | Airline task 8 failures. |
| `failed_max_steps` | Termination reason or batch aggregate indicates max-step stop. | Airline 5-task batch has one max-step case. |
| `write_argument_mismatch` | A write tool was called or proposed but arguments miss required entities, payment, item, flight, user, or policy constraints. | Airline task 8 baseline/prompt-variant payment/passenger mismatch. |
| `missing_prerequisite_read` | Required read evidence is absent or failed before write construction. | Airline task 8 prompt variant with missing/failed search evidence. |
| `post_write_state_mismatch` | Write occurred but final DB/state does not match expected state. | Successful/failed write cases should be checked once parser supports state deltas. |
| `communication_correct_db_wrong` | NL/communication score appears correct while DB check fails. | DB/scoring ambiguity fixture. |
| `scoring_evaluation_ambiguity` | Artifacts disagree or lack enough fields to distinguish assistant failure from evaluator/replay mismatch. | DB/scoring ambiguity fixture. |
| `observer_emission_gap` | Runtime contains likely write candidates but observer artifacts are empty or incomplete. | Airline 5-task batch and cross-domain mini-tests. |
| `observer_emission_gap_by_tool_coverage` | Emission gap aligns with tools absent from the observer hook registry. | `cancel_reservation`, `send_certificate`, `exchange_delivered_order_items`, `toggle_airplane_mode`, `toggle_roaming`. |
| `observer_unsupported_write_tool` | Tool is classified as write-capable but unsupported by the current observer. | Retail and telecom mini-test write tools. |
| `insufficient_evidence` | Required artifacts or fields are missing; classification cannot be made without guessing. | Any run missing result JSON, action counts, and tool timeline. |

## 6. Proposed write ownership / tool taxonomy

Ownership and observer support are separate axes. A tool can be an assistant/business write while currently unsupported by the observer, or a user/environment write that should not be treated as an assistant business-state mutation.

| Type | Meaning | Current examples |
| --- | --- | --- |
| `assistant_business_write` | Assistant-issued tool mutates task/business domain state that evaluator checks. | `book_reservation`, `cancel_reservation`, `exchange_delivered_order_items`; possibly `send_certificate`. |
| `user_environment_write` | User-side or environment-side state mutation that may be required for task completion but is not the assistant's business write. | `toggle_airplane_mode`, `toggle_roaming`. |
| `evaluator_replay_write` | Evaluator or replay machinery mutates/checks state outside the assistant action stream. | Reserved for parser-visible evaluator replay effects. |
| `observer_supported_write` | Write tool currently covered by passive observer hooks for at least some paths. | `book_reservation` in the paid observer-enabled task 8 path. |
| `observer_unsupported_write` | Write tool known or suspected to mutate state but not emitted by current observer hooks. | `cancel_reservation`, `send_certificate`, `exchange_delivered_order_items`, `toggle_airplane_mode`, `toggle_roaming`. |
| `read_only_tool` | Tool should not mutate persistent task state. | `get_user_details`, `get_reservation_details`, `get_product_details`. |
| `ambiguous_tool` | Tool effect cannot be classified from current artifacts or naming alone. | Any newly parsed tool missing registry entry and state-delta evidence. |

Concrete registry seeds for `regimes`:

- `book_reservation`: `assistant_business_write`; currently observer-supported in some paths.
- `cancel_reservation`: `assistant_business_write`; currently observer-missed.
- `send_certificate`: `assistant_business_write` or system/customer-facing write; currently observer-missed and should remain explicitly typed as ambiguous business/system-facing until confirmed.
- `exchange_delivered_order_items`: `assistant_business_write`; currently observer-missed.
- `toggle_airplane_mode`: `user_environment_write`; currently observer-missed.
- `toggle_roaming`: `user_environment_write`; currently observer-missed.
- `get_user_details`: `read_only_tool`.
- `get_reservation_details`: `read_only_tool`.
- `get_product_details`: `read_only_tool`.

## 7. Proposed action seams

Ordered from lowest to highest risk:

1. **Artifact-only analysis**: parse existing run directories into `Tau2Outcome`, classify regimes, and write reports. No tau2 execution, no API calls, no intervention.
2. **Passive observer**: ingest observer artifacts and warning streams when present. Observer warnings remain advisory and do not affect tau2 execution.
3. **Write-tool registry / ownership registry**: centralize tool typing and observer support flags so failures can distinguish unsupported coverage from absent write intent.
4. **Task-aware ledger source**: load expected task constraints into a ledger abstraction owned by `regimes`, not into `activegraph-tau2-bench` first. This enables offline comparison of expected vs observed write arguments.
5. **Pre-write warning seam**: advisory warnings before state-changing calls once false-positive behavior is quantified on successes. Warnings must remain non-blocking initially.
6. **Future gated control seam**: only after metrics, guardrails, false-positive rates, and coverage are declared should `regimes` consider controlled interventions.

Not ready: blocking, rewriting, repair, rollback, automatic argument patching, and any policy that changes tau2 execution. The current evidence supports observation, classification, reporting, and registry construction only.

## 8. Current known implementation gaps

- Observer hook coverage misses airline writes beyond `book_reservation`, including `cancel_reservation` and `send_certificate`.
- Observer hook coverage misses retail `exchange_delivered_order_items`.
- Observer hook coverage misses telecom user/environment writes `toggle_airplane_mode` and `toggle_roaming`.
- Live ledgers are `runtime_incomplete_ledger` artifacts without task-aware expected constraints.
- Batch observer emission needs a broader write-tool registry before empty observer files can be interpreted safely.
- False-positive behavior is not yet measured across enough successful write tasks.
- Tool ownership typing is missing; write/no-write alone is too coarse for `regimes` control decisions.
- Current cross-domain evidence is enough to design seams and fixtures, not enough to claim robust empirical generalization.

## 9. Proposed `regimes` implementation plan

Suggested package layout:

```text
src/regimes/targets/tau2/
  __init__.py
  outcome.py
  artifacts.py
  taxonomy.py
  tool_registry.py
  ledger.py
  observer.py
  reports.py
  target.py

tests/targets/tau2/
```

Suggested module responsibilities:

- `outcome.py`: dataclasses for `Tau2Outcome`, `Tau2ToolCall`, `Tau2WriteCandidate`, score summaries, and termination summaries.
- `artifacts.py`: artifact discovery and parsers for run directories, analysis directories, observer JSONL, runtime events, and summary JSON/Markdown sidecars.
- `taxonomy.py`: pure functions mapping `Tau2Outcome` to deterministic regime labels and histogram rows.
- `tool_registry.py`: seed registry for known tau2 tools, ownership types, write/read classification, observer support state, and unknown-tool fallback.
- `ledger.py`: task-aware expected-constraint abstraction; initially supports offline task 8 and fixture-derived ledgers without live control.
- `observer.py`: ingestion of observer event counts, ledger snapshots, diff counts, warning types, and coverage gaps.
- `reports.py`: markdown/JSON report generation for batches, cross-domain fixtures, failure examples, and guardrail summaries.
- `target.py`: `Tau2Target` artifact mode entrypoint; optional execution bridge remains disabled/gated until stop conditions are satisfied.

Suggested PR ladder:

1. **Artifact-only target skeleton**: create `Tau2Target` in artifact mode, parse run IDs and minimal scalar scores.
2. **Deterministic taxonomy**: implement taxonomy labels and histogram generation on the provided fixtures.
3. **Tool ownership registry**: add read/write/ownership/observer-support registry seeded from this report.
4. **Report writer**: generate batch markdown and JSON with citations back to source artifacts.
5. **Observer artifact ingestion**: parse observer event counts, ledger snapshots, diff counts, empty-file gaps, and warning summaries.
6. **Task-aware ledger support**: load expected constraints into a `regimes` ledger abstraction and compare to observed writes offline.
7. **Optional paid-run bridge later**: only after artifact mode, registry, reports, false-positive checks, and guardrails pass.

## 10. Stop conditions before full tau2

Full tau2 should not run from `regimes` until all of the following are true:

- `Tau2Target` artifact mode exists in `regimes`.
- The current artifacts listed in this report parse into `Tau2Outcome` objects.
- Deterministic regime histogram generation works.
- Tool ownership registry exists and has unknown-tool fallback behavior.
- Observer coverage is broadened or unsupported tools are explicitly marked.
- A small batch report exists for the artifact set.
- False-positive behavior is measured on successful writes, including retail and telecom fixtures.
- Metrics and guardrails are declared in code and report output.

Declared metrics:

Primary metrics:

- Reward.
- DB check.

Secondary metrics:

- Write action correctness.
- Read action correctness.
- Communicate score.
- Normal stop / max steps.

Guardrails:

- No unnecessary write blocking.
- No increased max steps.
- No communication regression.
- No read-action regression.
- Observer warning false-positive rate on successful tasks.

## 11. Recommended next implementation step

Recommended next PR in `regimes`: **add an artifact-only tau2 target skeleton**.

Requirements for that PR:

- Parse existing artifact directories without running tau2.
- Construct minimal `Tau2Outcome` records with identity, scalar scores, termination, action counts, observer counts, and source paths.
- Seed taxonomy with `success`, `failed_partial_progress`, `observer_emission_gap`, `observer_emission_gap_by_tool_coverage`, `observer_unsupported_write_tool`, and `insufficient_evidence`.
- Seed `tool_registry.py` with the concrete tools listed in this report.
- Produce a small markdown/JSON report over the listed artifacts.

Do not run more paid tau2 until the target/report abstraction exists, unless collecting one very specific missing fixture with a predeclared purpose. Do not add task-aware ledger loading inside `activegraph-tau2-bench` first; move that abstraction into `regimes` so future targets share the same evidence-to-commit mechanism.
