# Failed trace write-intent gap scan

`scripts/scan_failed_traces_for_write_intent_gaps.py` performs an offline scan over already-produced failed or partial tau2 runtime artifacts and prior analysis outputs. It is designed to test whether the airline task 8 write-intent / constraint-ledger failure class appears outside the original task-specific case.

## Boundaries

The scanner is intentionally artifact-only:

- does **not** run tau2;
- does **not** run another model-backed episode;
- does **not** call LLM/API services;
- does **not** require API keys;
- does **not** mutate `vendor/tau2-bench`;
- does **not** add ActiveGraph control.

The script reads committed `results.json`, `runtime_events.jsonl`, and existing analysis outputs where present. It also reads static task metadata under `vendor/tau2-bench/data/tau2/domains/.../tasks.json` for labels and context only.

## Usage

Run the default committed candidate scan:

```bash
python scripts/scan_failed_traces_for_write_intent_gaps.py
```

By default it scans these existing run directories:

- `runs/20260531-170523-841701` (`update_task_1`, failed/no write)
- `runs/20260531-170618-525260` (`create_task_1_with_env_assertions`, partial progress)
- `runs/20260531-191847-173904` (`update_task_with_user_tools`, DB mismatch / scoring ambiguity)
- `runs/20260531-204930-608103` (airline task 8 baseline failure)
- `runs/20260531-222346-104165` (airline task 8 prompt-variant failure and write-intent ledger)
- `runs/20260531-184109-726391` (failed or ambiguous cases from the full mock baseline results)

You can override the input set with one or more explicit run or analysis directories:

```bash
python scripts/scan_failed_traces_for_write_intent_gaps.py \
  --case-dir runs/20260531-204930-608103 \
  --case-dir runs/20260531-222346-104165/write_intent_analysis
```

## Outputs

Each invocation writes a timestamped directory:

```text
runs/write_intent_gap_scan_<timestamp>/
```

The directory contains:

- `write_intent_gap_scan.json` — complete scan result, per-case classifications, scope boundaries, aggregate counts, and recommendation.
- `write_intent_gap_scan_summary.md` — human-readable summary with case table, taxonomy counts, generalization assessment, and no-rerun/no-API boundaries.
- `failure_taxonomy.json` — task-agnostic failure category definitions, counts, and example cases.
- `trace_case_index.json` — scanned sources, artifact hashes, prior analysis files, and case index.
- `candidate_intervention_matrix.json` — per-case matrix for offline detectability, runtime-observation need, pre-write-checker flaggability, and future ActiveGraph-control need.
- `final_state.json` — compact status and output index.
- `raw.log` — run boundary/status log.

## Failure taxonomy

The scanner uses task-agnostic categories:

- missing entity
- wrong quantity
- wrong price/payment
- wrong date/time
- unsupported selected option
- missing prerequisite read
- write before sufficient evidence
- post-write state mismatch
- communication correct but DB state wrong
- max-steps before write
- no-write failure
- scoring/evaluation ambiguity
- insufficient evidence to classify

The scanner deliberately avoids overclaiming. If a trace has no reconstructed write-intent ledger and deterministic heuristics cannot prove a more specific gap, it reports `insufficient evidence to classify` and records limitations.

## Interpretation

The scan separates three questions:

1. **Can offline analysis detect the failure today?** This means existing artifacts are enough for a deterministic after-the-fact classification.
2. **Would runtime observation be needed?** This means a passive observer would need to watch read/write ordering or stalled progress during an episode to detect the condition at the useful time.
3. **Would future ActiveGraph control be needed?** This is reserved for cases where prevention or blocking would require controlling an irreversible write, not merely observing or reporting after the fact.

Current committed scan output (`runs/write_intent_gap_scan_20260531-230310/`) finds strongest general pre-write checker evidence in the two airline task 8 failures. Other mock-domain failures exercise adjacent observer/evaluator classes such as no-write failure, post-write state mismatch, and scoring ambiguity. The recommended next step is therefore a passive runtime observer, not ActiveGraph control.
