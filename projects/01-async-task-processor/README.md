# 01 — Async Task Processing System

**Status:** not started. This file describes the planned system. There is no application code in this directory yet.

## Problem

Some work should not run inside the caller's request. The caller submits a task and continues. A worker performs the task later. The first version keeps that hand-off small enough to run in one process so the queue, the worker, and failure behavior are visible before a broker is introduced.

## Initial architecture (planned)

```text
Producer → In-memory Queue → Worker
```

- **Producer** accepts a task and places it on the queue.
- **In-memory queue** holds tasks that are waiting. It lives in the process. It is empty after a restart.
- **Worker** takes a task and runs it.

That shape is the v0.1 target. Retries, disk, RabbitMQ, and metrics are later milestones.

## Planned milestones

These capabilities are not implemented.

| Version | Planned capability |
| --- | --- |
| v0.1 | Single producer and one worker using an in-memory queue. |
| v0.2 | More than one worker consuming the same queue. |
| v0.3 | Failure handling and retries, including a visible dead or exhausted task. |
| v0.4 | Persistent task storage so queued work survives a process restart. |
| v0.5 | RabbitMQ integration in place of the in-memory queue. |
| v0.6 | Observability: enough signals to see queue depth, successes, failures, and delay. |

Each version is a separate pull request into `master`. A version is implementation-complete only after that PR is reviewed, tested, and merged. See the rules in `PROGRESS.md`.

## Restaurant analogy

A small restaurant is the same hand-off:

| Restaurant | This application |
| --- | --- |
| Customer submits an order | Caller submits a task to the producer |
| Waiter records it | Producer accepts the task and places it on the queue |
| Order board holds pending orders | In-memory queue holds tasks not yet taken |
| Chef processes orders | Worker runs the task |
| Manager observes failures and delays | Operator uses the signals planned for v0.6 |

The order board is not a kitchen diary. If the board is wiped, pending orders are gone. That is the in-memory queue. Durability (v0.4) and a real board in another room (v0.5, RabbitMQ) are later choices, made after the basic service works.

## Out of scope for now

No producer, worker, queue, tests, dependencies, Docker, or broker configuration until a milestone PR is opened for that work.
