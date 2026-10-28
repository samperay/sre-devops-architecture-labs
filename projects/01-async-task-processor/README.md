# 01 — Async Task Processing System

**Status:** IN PROGRESS. The v0.1 application, labs, and unittest suite are in this directory. No milestone pull request has been reviewed or merged into `master`.

## Problem

Some work should not run inside the caller's request. The caller submits a task and continues. A worker performs the task later. This version keeps that hand-off inside one process so the queue, the worker, and shutdown behavior are visible before a broker is introduced.

## v0.1 architecture

```text
Producer → queue.Queue → one worker thread
                |
                +-- shutdown: ACCEPTING → STOPPING → STOPPED
```

- **Producer** accepts a payload, assigns a `uuid.uuid4()` id, and places a frozen `Task` on the queue.
- **In-memory queue** holds accepted tasks until the worker retrieves them. It lives in the process and is empty after a restart.
- **Worker** is one background thread. It sleeps for a configured delay and logs `SUBMITTED`, `STARTED`, and `COMPLETED`.
- **Shutdown** shares one lock with submission. After the state changes to `STOPPING`, new submissions are rejected. Tasks already accepted are finished, then a sentinel stops the worker and the state becomes `STOPPED`.

Retries, disk, RabbitMQ, and metrics are later milestones.

## Planned milestones

| Version | Planned capability | This working tree |
| --- | --- | --- |
| v0.1 | Single producer and one worker using an in-memory queue. | Implemented locally. Not merged. |
| v0.2 | More than one worker consuming the same queue. | Not implemented. |
| v0.3 | Failure handling and retries, including a visible dead or exhausted task. | Not implemented. |
| v0.4 | Persistent task storage so queued work survives a process restart. | Not implemented. |
| v0.5 | RabbitMQ integration in place of the in-memory queue. | Not implemented. |
| v0.6 | Observability: enough signals to see queue depth, successes, failures, and delay. | Not implemented. |

Each version is a separate pull request into `master`. A version is implementation-complete only after that PR is reviewed, tested, and merged. See the rules in `PROGRESS.md`.

## Restaurant analogy

A small restaurant is the same hand-off:

| Restaurant | This application |
| --- | --- |
| Customer submits an order | Caller submits a task to the producer |
| Waiter records it | Producer accepts the task and places it on the queue |
| Order board holds pending orders | In-memory queue holds tasks not yet taken |
| Chef processes orders | One worker runs the task |
| Manager turns the sign to closing | Shutdown rejects new orders and lets accepted ones finish |
| Manager observes failures and delays | Operator uses the signals planned for v0.6 |

The order board is not a kitchen diary. If the board is wiped, pending orders are gone. That is the in-memory queue. Durability (v0.4) and a real board in another room (v0.5, RabbitMQ) are later choices.

## Check the local v0.1 code

From the repository root:

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab06_automated_tests.py
python3 -m unittest discover -s projects/01-async-task-processor/tests -v
```

Labs 01 through 05 exercise the task model, queue, worker, logs, and shutdown one step at a time. See `LEARNING.md`.

## Out of scope for v0.1

No second worker, retries, disk, RabbitMQ, metrics, Docker, or extra dependencies. The application uses the Python standard library only.
