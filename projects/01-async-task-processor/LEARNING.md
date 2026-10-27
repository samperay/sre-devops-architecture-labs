# Learning journal — Async Task Processing System

Update this file after a milestone pull request is reviewed, tested, and merged into `master`. Leave a section as a placeholder until that evidence exists. Do not record a lesson, test result, or failure that has not happened.

## 1. Project overview

| Field | Value |
| --- | --- |
| Project name | Async Task Processing System |
| Learning objective | Move work off the caller path: one producer, an in-memory queue, and one worker (v0.1). Durability is not part of v0.1. |
| Current milestone | None. Next planned milestone is v0.1 — Single Producer and Worker. |
| Current implementation status | NOT STARTED |

The planned shape is Producer → In-memory Queue → Worker. See `README.md` in this directory. No application code has been written.

## 2. What I learned

Concepts go here only after they show up in a merged implementation, written in the learner's own words.

| Milestone | Concept | In my own words |
| --- | --- | --- |
| — | — | No implementation yet. Nothing learned from running code. |

## 3. Practical evidence

Placeholders until a milestone is exercised.

| Item | Evidence |
| --- | --- |
| Commands executed | None. |
| Actual terminal output | None. |
| Tests performed | None. |
| GitHub PR references | None. No milestone PR is open or merged. |

## 4. Failure investigation

No failure experiment has been run.

| Field | Record |
| --- | --- |
| Failure scenario | — |
| Expected behavior | — |
| Actual observed behavior | — |
| Root cause | — |
| Recovery steps | — |
| Verification results | — |

## 5. Architecture decisions

Record a decision when a milestone forces a choice. The notes below are the planned v0.1 boundary, not a completed design review.

| Field | v0.1 plan |
| --- | --- |
| Problem or requirement | Accept a task and process it off the caller's path with one producer and one worker. |
| Available design options | Not compared in an implementation yet. The planned first option is an in-memory queue. Persistent storage and RabbitMQ are later milestones (v0.4, v0.5). |
| Selected approach | Not selected in code. Target for v0.1: Producer → In-memory Queue → Worker. |
| Trade-offs and limitations | An in-memory queue does not survive process exit. v0.1 has no durability guarantee. Retries are v0.3. Persistence is v0.4. |

## 6. Interview preparation

Answer these after the related milestone is merged. Do not fill in answers early.

| Question | Learner’s answer | Tutor feedback | Needs revision |
| --- | --- | --- | --- |
| Why queue the work instead of doing it inline? | — | — | — |
| What does v0.1 lose when the process exits? | — | — | — |
| What happens if the worker stops while a task is in progress? | — | — | — |
| When do retries and duplicate processing become your problem? | — | — | — |

## 7. Confidence assessment

States match `PROGRESS.md`: `NOT STARTED`, `IN PROGRESS`, `LAB COMPLETED`, `UNDERSTOOD`, `APPLIED`, `ARCHITECT READY`.

| Competency | State |
| --- | --- |
| Architecture understanding | NOT STARTED |
| Design decisions and trade-offs | NOT STARTED |
| Implementation | NOT STARTED |
| Troubleshooting | NOT STARTED |
| Reliability and operations | NOT STARTED |
| Technical communication | NOT STARTED |

## 8. Next activity

**v0.1 — Single Producer and Worker.**

Build one producer, one in-memory queue, and one worker. Queued tasks may be lost when the process exits. Do not add multiple workers, retries, disk, RabbitMQ, or metrics in that pull request.
