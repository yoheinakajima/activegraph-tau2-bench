# Write-intent gap scan

Offline scan over existing failed or partial tau2 runtime artifacts. No tau2 rerun, model-backed episode, LLM/API call, API key, vendored tau2 mutation, or ActiveGraph control is used.

## Scope

- Generated at: `2026-05-31T23:03:10.796818Z`
- Cases scanned: **8**
- Run directories scanned: **6**

## Aggregate results

- Detectable offline today: **7 / 8**
- Require runtime observation: **3 / 8**
- Require future ActiveGraph control for prevention/blocking: **2 / 8**
- General pre-write checker could have flagged: **2 / 8**

## Failure taxonomy counts

| Category | Count | Example cases |
| --- | ---: | --- |
| missing entity | 1 | 20260531-204930-608103:8 |
| wrong quantity | 0 | — |
| wrong price/payment | 2 | 20260531-204930-608103:8, 20260531-222346-104165:8 |
| wrong date/time | 0 | — |
| unsupported selected option | 0 | — |
| missing prerequisite read | 1 | 20260531-222346-104165:8 |
| write before sufficient evidence | 1 | 20260531-222346-104165:8 |
| post-write state mismatch | 4 | 20260531-191847-173904:update_task_with_user_tools, 20260531-204930-608103:8, 20260531-222346-104165:8, 20260531-184109-726391:update_task_with_history_and_env_assertions |
| communication correct but DB state wrong | 3 | 20260531-170523-841701:update_task_1, 20260531-204930-608103:8, 20260531-222346-104165:8 |
| max-steps before write | 0 | — |
| no-write failure | 1 | 20260531-170523-841701:update_task_1 |
| scoring/evaluation ambiguity | 3 | 20260531-191847-173904:update_task_with_user_tools, 20260531-184109-726391:update_task_with_initialization_data, 20260531-184109-726391:update_task_with_user_tools |
| insufficient evidence to classify | 1 | 20260531-170618-525260:create_task_1_with_env_assertions |

## Case index

| Case | Domain | Reward/outcome | Writes | Categories | Flagged by pre-write checker? | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 20260531-170523-841701:update_task_1 | mock | reward=0.0, termination=user_stop, db_match=False | — | communication correct but DB state wrong, no-write failure | False | medium |
| 20260531-170618-525260:create_task_1_with_env_assertions | mock | reward=0.0, termination=max_steps, db_match=None | create_task | insufficient evidence to classify | False | low |
| 20260531-191847-173904:update_task_with_user_tools | mock | reward=0.0, termination=user_stop, db_match=False | update_task_status, dismiss_notification | post-write state mismatch, scoring/evaluation ambiguity | False | medium |
| 20260531-204930-608103:8 | airline | reward=0.0, termination=user_stop, db_match=False | book_reservation | communication correct but DB state wrong, missing entity, post-write state mismatch, wrong price/payment | True | high |
| 20260531-222346-104165:8 | airline | reward=0.0, termination=user_stop, db_match=False | book_reservation | communication correct but DB state wrong, missing prerequisite read, post-write state mismatch, write before sufficient evidence, wrong price/payment | True | high |
| 20260531-184109-726391:update_task_with_initialization_data | mock | reward=0.0, termination=user_stop, db_match=True | update_task_status | scoring/evaluation ambiguity | False | medium |
| 20260531-184109-726391:update_task_with_history_and_env_assertions | mock | reward=1.0, termination=user_stop, db_match=False | create_task, update_task_status | post-write state mismatch | False | medium |
| 20260531-184109-726391:update_task_with_user_tools | mock | reward=0.0, termination=max_steps, db_match=None | update_task_status | scoring/evaluation ambiguity | False | medium |

## Generalization assessment

The mechanism generalizes beyond airline task 8 as a *failure detector class* when intended write arguments and prerequisite evidence can be reconstructed before an irreversible write. The strongest evidence remains the two airline task 8 cases, but the mock and DB-mismatch traces show adjacent task-agnostic failure modes: no-write/max-step failures, post-write DB mismatch, and scoring ambiguity. Those adjacent cases are useful for a passive observer, but they do not all require a pre-write argument ledger or future ActiveGraph control.

Recommendation: proceed to a passive runtime observer next. Do not add ActiveGraph control yet; first collect runtime evidence that the checker can reconstruct ledgers and emit warnings reliably across domains without blocking writes.

## Boundaries

- tau2 rerun: **no**
- model-backed episode: **no**
- LLM/API calls: **no**
- API keys required: **no**
- vendor/tau2-bench mutation: **no**
- ActiveGraph control: **no**
