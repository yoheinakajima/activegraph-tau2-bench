# Observer batch emission gap analysis

`scripts/analyze_observer_batch_emission_gap.py` is an offline diagnostic for
observer-enabled tau2 runtime-trace batches where the passive write-intent
observer produced fewer artifacts than expected.

It was added for the airline 5-task batch at
`runs/20260601-033543-612139`, where the runtime trace completed successfully
and contained 526 runtime events, but these observer artifacts were empty:

- `observer_events.jsonl`
- `constraint_ledger_snapshots.jsonl`
- `write_intent_diffs.jsonl`

## Boundary

The analyzer is read-only with respect to tau2 execution:

- It does **not** run tau2.
- It does **not** run model-backed episodes.
- It does **not** call LLM/API services.
- It does **not** require API keys.
- It does **not** mutate `vendor/tau2-bench/`.
- It does **not** add ActiveGraph control.
- It only reads existing artifacts and repository-owned source files.

The script may read the airline domain tool source in `vendor/tau2-bench/` to
classify observed runtime tools by their declared `ToolType`, but it does not
modify the vendored tree.

## Usage

```bash
python scripts/analyze_observer_batch_emission_gap.py \
  --runtime-run-dir runs/20260601-033543-612139
```

By default, outputs are written under:

```text
runs/20260601-033543-612139/observer_emission_gap_analysis/
```

Use `--output-dir <path>` to write the analysis elsewhere.

## Inputs inspected

The analyzer reads these run artifacts when present:

- `runtime_events.jsonl`
- `runtime_trace_final_state.json`
- `observer_events.jsonl`
- `constraint_ledger_snapshots.jsonl`
- `write_intent_diffs.jsonl`
- `observer_final_state.json`
- `tau2_output/results.json` or `tau2_artifacts/results.json`
- `raw.log`

It also reads repository-owned observer/runtime-trace implementation files and
the airline tool source to compare runtime tools with observer hook coverage.

## Outputs

The output directory contains:

- `observer_emission_gap_analysis.json` — complete machine-readable analysis.
- `observer_emission_gap_summary.md` — human-readable summary and
  recommendation.
- `runtime_write_candidate_index.json` — runtime dispatch/tool-call index with
  likely write-candidate classification.
- `observer_hook_coverage.json` — observer `WRITE_TOOL_HINTS`, airline source
  tool types, observed tools, and missed likely writes.
- `task_level_observer_coverage.json` — per-task dispatch, likely write, and
  observer row counts.
- `final_state.json` — analyzer status and safety boundary flags.
- `raw.log` — compact analyzer log.

## Classification logic

A runtime tool is classified as a likely write candidate when one or more of the
following are true:

1. The airline source declares the tool with `@is_tool(ToolType.WRITE)`.
2. The tool name is present in the passive observer's `WRITE_TOOL_HINTS`.
3. The tool name contains write-like words such as `book`, `cancel`, `update`,
   `create`, `delete`, `send`, `refund`, or `payment`, while not beginning with
   read-like prefixes such as `get_`, `list_`, or `search_`.

This conservative classification lets the diagnostic distinguish three cases:

- no write candidates occurred, so no observer code change is needed for that
  run;
- write candidates occurred but were not in observer hook coverage, so the hook
  coverage should be patched; or
- recognized write candidates occurred but artifacts were still empty, so batch
  context propagation or artifact writer initialization should be investigated.

## Airline batch finding

For `runs/20260601-033543-612139`, the analyzer reports that runtime write tools
were observed but were outside the observer's current recognized write-tool set:

- `tool_dispatch_start`: 29 events
- `toolkit_dispatch_start`: 36 events
- combined runtime dispatch start events: 65
- likely write candidate events: 8
- unique likely writes after environment/toolkit duplicate collapse: 2
- likely write tools: `cancel_reservation`, `send_certificate`
- tasks with likely write candidates: `1`, `2`
- observer rows: 0

The observer was enabled in `runtime_trace_final_state.json`, and observer files
existed and were writable. Therefore the likely reason for zero observer
artifacts is hook coverage, not a missing batch observer context. The passive
observer only emitted for tools listed in `WRITE_TOOL_HINTS`; the observed
airline writes `cancel_reservation` and `send_certificate` were not included.

## Recommendation rule

The summary includes one of these recommendations:

- **No code change needed** if no runtime write candidates occurred.
- **Patch observer hook coverage** if likely write candidates occurred but were
  not recognized by the observer.
- **Patch batch context propagation/artifact writer initialization** if the
  observer was disabled, output paths were unavailable, or recognized write
  candidates occurred with no emitted rows.
