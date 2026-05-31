# Fixture vs real baseline trace comparison

This offline comparison checks whether the repository-owned fixture trace smoke output remains useful as a schema and coverage proxy for the real post-run tau2 model baseline trace.

It compares a no-LLM fixture run such as `python scripts/run_trace_smoke.py` against the extracted artifacts from the completed baseline run `runs/20260531-042306-420109`.

## Command

Generate or select a fixture trace run, then compare it to the extracted baseline trace:

```bash
python scripts/run_trace_smoke.py
python scripts/compare_fixture_vs_baseline_trace.py \
  --fixture-run-dir <runs/...> \
  --baseline-run-dir runs/20260531-042306-420109
```

By default, comparison artifacts are written under:

```text
runs/20260531-042306-420109/trace_comparison/
```

Use `--output-dir <path>` to write the same artifact set somewhere else.

## Input artifacts

The fixture side reads:

- `<fixture-run-dir>/events.jsonl` (required)
- `<fixture-run-dir>/summary.md` (optional)
- `<fixture-run-dir>/final_state.json` (optional)
- `<fixture-run-dir>/raw.log` (optional provenance)

The real baseline side reads only already-extracted post-run artifacts:

- `<baseline-run-dir>/extracted_trace/baseline_trace.jsonl`
- `<baseline-run-dir>/extracted_trace/baseline_trace_final_state.json`
- `<baseline-run-dir>/extracted_trace/baseline_artifact_index.json`
- `<baseline-run-dir>/extracted_trace/baseline_trace_summary.md` (indexed when present)

The comparator does not read API keys, does not invoke `tau2 run`, and does not import the vendored tau2 package.

## Output artifacts

The comparator writes:

- `trace_comparison_report.json` — full machine-readable comparison report.
- `trace_comparison_summary.md` — human-readable status, counts, alignment, and gaps.
- `event_type_alignment.json` — exact event-type differences plus semantic event-family alignment.
- `schema_field_alignment.json` — envelope field compatibility for `trace_event.v1`.
- `coverage_gaps.json` — expected differences, baseline limitations, and future instrumentation gaps.
- `final_state.json` — compact run status and output index.
- `raw.log` — command-level no-rerun/no-API provenance.

## Comparison dimensions

The report covers:

- schema fields and schema version alignment;
- exact event-type sets and semantic event-family alignment;
- event counts;
- task-id coverage;
- turn-index coverage;
- message-role coverage;
- tool-name coverage;
- reward/evaluation metadata availability;
- artifact provenance from fixture files and the baseline artifact index;
- fixture-backed versus real-baseline flags;
- available versus unavailable details;
- no-rerun and no-API guarantees.

## Expected gaps

A comparison status of `trace_comparison_completed_with_expected_gaps` is expected for the current artifacts. The comparator does not treat mismatches as failures by default because the two inputs are intentionally different:

- the fixture trace is synthetic, deterministic, no-LLM smoke output;
- the baseline trace is extracted after a real model-backed tau2 run;
- fixture event names are concise smoke names, while baseline event names are prefixed with `baseline.*`;
- fixture runs include synthetic turn/state/orchestrator lifecycle observations that may not exist in `results.json`;
- tau2 `results.json` does not expose full tick-level state transitions, effect timelines, or audio/speech artifacts for this baseline;
- some reward subfields such as database checks, action checks, and natural-language assertions may be null or absent in the serialized result.

Schema-envelope compatibility and shared semantic event families are the primary success signals. Exact event-count or event-type equality is not required for this milestone.

## How this informs later ActiveGraph trace/state-packet comparison

This comparison establishes the bridge between fixture-only trace smoke artifacts and the first real post-run baseline trace. Later ActiveGraph work can use the same dimensions to compare projected ActiveGraph traces or state packets against real baseline observations:

1. keep `trace_event.v1` envelope compatibility stable;
2. map real baseline events into semantic families before judging coverage;
3. explicitly separate source limitations from implementation failures;
4. preserve artifact provenance so every projected ActiveGraph packet can cite its source event or source artifact;
5. treat missing tick-level data as a future instrumentation target rather than an execution-control requirement.

This step does **not** implement ActiveGraph execution control and does **not** feed state packets back into tau2.

## No tau2/API boundary

`compare_fixture_vs_baseline_trace.py` is an offline artifact reader. It only loads files already present under `runs/`. It does not:

- run tau2;
- start another model-backed episode;
- call LLM/API services;
- require API keys;
- mutate `vendor/tau2-bench`;
- implement ActiveGraph execution control.
