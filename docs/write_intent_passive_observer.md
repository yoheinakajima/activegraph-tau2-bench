# Passive write-intent observer

The passive write-intent observer is a repo-owned experiment for emitting
runtime-adjacent write-intent artifacts without controlling tau2 execution. It
is the next step after the offline write-intent gap scan: it preserves the
scan's constraint-ledger framing, but emits event-shaped artifacts that can be
produced during runtime-traced episodes before or around write dispatch.

## Purpose

During runtime-traced tau2 episodes, the observer approximates:

- the current constraint ledger snapshot,
- the proposed write intent,
- the proposed write arguments,
- the argument-vs-ledger diff,
- a deterministic readiness score,
- warning lists with evidence references, and
- explicit no-control boundary flags.

The observer is intentionally passive. It does **not** implement ActiveGraph
control, does **not** block tool calls, does **not** rewrite tool arguments,
does **not** repair or roll back state, and does **not** feed state packets back
into tau2.

## No-LLM smoke command

Run the deterministic fixture smoke without tau2, paid models, or API calls:

```bash
python scripts/run_write_intent_observer_smoke.py
```

The smoke writes artifacts under an ignored `runs/<timestamp>/` directory:

- `observer_events.jsonl` — event stream for ledger snapshots, candidates,
  diffs, and readiness scores.
- `constraint_ledger_snapshots.jsonl` — one snapshot per fixture case.
- `write_intent_diffs.jsonl` — proposed write arguments compared to the
  ledger.
- `observer_summary.md` — human-readable fixture coverage, warning taxonomy,
  and no-control boundary status.
- `observer_final_state.json` — machine-readable aggregate final state.
- `raw.log` — compact validation log.

## Optional runtime-trace integration

The paid/API-backed runtime traced baseline wrapper accepts an explicit passive
observer flag:

```bash
python scripts/run_tau2_runtime_traced_baseline.py \
  --provider <provider> \
  --model <model> \
  --domain mock \
  --task-id create_task_1 \
  --max-steps 2 \
  --enable-write-intent-observer \
  --yes-i-understand-this-may-call-paid-apis
```

This is only an emission hook layered onto existing runtime trace dispatch
observation. It does not alter tau2 inputs, task state, tool calls, or control
flow. Do not run paid observer-enabled episodes until the no-LLM smoke output is
reviewed.

## Fixture coverage

The smoke covers five representative cases from the completed offline scan and
adjacent analyses:

1. Airline task 8 baseline: missing Kevin and wrong payment.
2. Airline task 8 prompt variant: passengers preserved, wrong payment, missing
   prerequisite search evidence.
3. Successful `create_task_1`: supported write with no medium/high warning.
4. Failed no-write case: expected write absent at runtime.
5. DB mismatch / scoring ambiguity case: valid-looking write followed by
   post-write mismatch and scoring ambiguity.

## Warning taxonomy

Warnings are classified by phase:

- `pre_write_detectable` — detectable from the ledger and proposed write
  arguments before dispatch, such as missing required entities, payment/price
  mismatches, unsupported selected options, or unsupported write arguments.
- `runtime_observable` — requires runtime observation, such as a write issued
  before prerequisite read evidence or an expected write that never appears.
- `post_write_only` — visible only after dispatch/evaluation, such as persisted
  DB mismatch or scorer/evaluator ambiguity.
- `requires_future_control` — marks situations where prevention would require a
  future ActiveGraph control layer. The current observer only records this fact.

## How this differs from the offline scan

The offline scan classified already-produced failed or partial traces and asked
whether write-intent gaps were detectable from existing artifacts. The passive
observer turns that analysis into event-shaped runtime artifacts: it can emit a
candidate, ledger snapshot, diff, score, and warnings at the write-dispatch
boundary when such a boundary is visible. The smoke remains fixture-based so it
can validate the schema and deterministic checks without rerunning tau2.

## How this prepares future controlled intervention

The observer produces stable evidence references, warning codes, readiness
scores, and boundary flags that a future control layer could consume. That makes
it possible to evaluate whether a later ActiveGraph intervention would have had
enough evidence to block or request review. This repository change deliberately
stops before that point: there is no blocking, no argument rewriting, no repair,
no rollback, and no feedback into tau2.

## Why full tau-2 is still premature

The scan showed partial but meaningful generalization beyond airline task 8, but
the strongest pre-write checker evidence is still concentrated in the two
airline task 8 failures. Mock and DB-mismatch traces expose adjacent no-write,
post-write mismatch, and scoring/evaluation classes, some of which cannot be
prevented without future control or post-write observation. A tiny paid
observer-enabled episode should only be considered after the passive smoke
artifacts are reviewed and the no-control boundary remains intact.
