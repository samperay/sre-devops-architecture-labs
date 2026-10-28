# Async Task Processor — Implementation Plan v0.1

## 1. Objective

Build a small asynchronous task processor using only the Python standard library. A producer accepts tasks into an in-memory queue, one background worker processes them, and the application logs task lifecycle events and shuts down gracefully.

**Source specification:** `v0.1.md` (R1–R7, AC1–AC7).

## 2. Scope and Execution Model

- **Interface:** Minimal command-line application that submits sample tasks; no HTTP API.
- **Runtime:** One Python process, one background worker thread, and one thread-safe in-memory queue.
- **Dependencies:** Python standard library only; no database, broker, or external service.

```text
                 One Python process
   +------------------------------------------+
   | Producer / CLI                           |
   |   |                                      |
   |   | task ID + SUBMITTED log              |
   |   v                                      |
   | queue.Queue  ---> Worker thread          |
   |                      |                   |
   |                      +--> STARTED log    |
   |                      +--> simulated work |
   |                      +--> COMPLETED log  |
   |                                          |
   | Shutdown controller                      |
   |   +--> stop acceptance                   |
   |   +--> drain accepted tasks              |
   |   +--> signal and join worker            |
   +------------------------------------------+
```

## 3. Technical Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Task handoff | `queue.Queue` | Thread-safe in-memory producer/consumer handoff. |
| Worker | `threading.Thread` | One concurrent background worker without additional infrastructure. |
| Task identification | `uuid.uuid4()` | Distinct ID for each accepted task. |
| Task representation | Small standard-library data structure | Keep task ID and payload together without dependencies. |
| Lifecycle events | `logging` | Emit `SUBMITTED`, `STARTED`, `COMPLETED` with the same task ID. |
| Simulated processing | `time.sleep(configured_delay)` | Make asynchronous execution observable. |
| Submission/shutdown coordination | `threading.Lock` plus acceptance state | Make queue acceptance and transition to `STOPPING` mutually exclusive. |
| Queue draining | `queue.join()` and matching `task_done()` calls | Wait for all accepted tasks to be accounted for; not proof of successful processing on its own. |
| Worker termination | Unique sentinel queue item, followed by `thread.join()` | End the worker cleanly after draining accepted work. |
| Automated tests | `unittest` | Standard-library testing, including deterministic concurrency tests where possible. |

## 4. Component Responsibilities

**Producer:** Generate a task ID; while holding the shared coordination lock, check whether submissions are allowed, enqueue the task, and acknowledge successful *in-memory* acceptance. Reject submissions after the shutdown-state transition. Acknowledgment is not a completion or durability guarantee.

**Queue:** Hold accepted tasks until the worker retrieves them. Use `queue.Queue` unfinished-task accounting correctly.

**Worker:** Retrieve items, recognize the termination sentinel, emit lifecycle logs, simulate processing, and call `task_done()` exactly once for each retrieved item (including the sentinel). Ensure accounting happens even when processing raises an exception; v0.1 does not provide automatic retries or successful-completion guarantees for failed tasks.

**Shutdown controller:** Coordinate the transition to `STOPPING` with the same lock used by submissions, wait for already accepted tasks to be accounted for, enqueue the sentinel, and join the worker thread. Avoid holding the submission lock while waiting for the queue to drain.

## 5. Graceful Shutdown Sequence

1. Acquire the shared submission/shutdown lock.
2. Transition the application from `ACCEPTING` to `STOPPING`. Any later submission must be rejected.
3. Release the lock. A submission that acquired the lock and enqueued its task *before* this transition remains accepted.
4. Call `queue.join()` to wait for all accepted work to be marked done.
5. Enqueue a unique termination sentinel after draining accepted tasks.
6. Join the worker thread and confirm it has exited.

**Concurrency invariant:** No task can be accepted after the `STOPPING` transition. All tasks accepted before it are given the opportunity to finish before normal shutdown completes.

**Failure boundary:** This procedure covers graceful shutdown, not process crashes, forced termination, or failed task execution.

## 6. Implementation Tasks

| ID | Task | Main verification |
|---|---|---|
| T1 | Create a minimal CLI entry point and task representation. | Program starts using Python 3. |
| T2 | Add producer, queue, and unique task IDs. | AC1, AC3: three tasks accepted and uniquely identified. |
| T3 | Add one worker and configurable processing delay. | AC2, AC4: worker starts tasks and delays completion. |
| T4 | Add lifecycle logging. | AC5: ordered `SUBMITTED` → `STARTED` → `COMPLETED` for each successful task. |
| T5 | Add coordinated shutdown, queue drain, sentinel, and thread join. | AC6: reject post-shutdown submissions; finish prior accepted tasks; worker exits. |
| T6 | Add standard-library automated tests and dependency check. | AC1–AC7 and all tests pass. |

Implement and review **one task at a time**. Do not add application code until implementation is explicitly approved.

## 7. Testing Strategy

Use `python -m unittest` for automated verification. Include the following cases:

- **AC1:** With no worker consuming, submitting three tasks leaves three queued items.
- **AC2:** A worker retrieves a queued task and emits its `STARTED` event.
- **AC3:** Three submissions produce three distinct task IDs.
- **AC4:** Configured processing delay is observed; `COMPLETED` is logged only after processing.
- **AC5:** Successful task lifecycle events appear in order with a consistent task ID.
- **AC6:** With one task active and two queued, shutdown rejects later submissions, drains the three accepted tasks, and terminates the worker.
- **AC7:** Source imports only standard-library modules; no broker, database, or third-party service is required.

Also test the two lock-acquisition orders: submission first (accepted before shutdown transition) and shutdown first (submission rejected). Prefer synchronization primitives over arbitrary sleeps when coordinating these tests.

## 8. Known Limitations and Trade-offs

- **Durability:** Accepted, unfinished tasks can be lost on crash or restart.
- **Throughput:** One worker processes one task at a time; backlog grows if arrival rate exceeds service rate.
- **Memory:** An unbounded queue can consume excessive memory under sustained overload.
- **Failures:** No retries, persistence, or recovery; a `task_done()` call means queue accounting is complete, not necessarily successful business processing.
- **Observability:** Lifecycle logs only; production metrics, alerting, and tracing are deferred.

These are accepted v0.1 limitations. Evaluate multiple workers, persistence, external messaging, and backpressure in later milestones when requirements justify them.

## 9. Definition of Done

1. R1–R7 are implemented without violating the v0.1 constraints.
2. AC1–AC7 are verified by tests and/or documented repeatable checks.
3. Graceful shutdown is tested, including the concurrent submission boundary.
4. The worker exits cleanly; queue unfinished-task accounting is correct.
5. `python -m unittest` passes and the source is reviewed.
6. Changes are committed on the feature branch and a pull request is opened for review.

**Workflow:** Specification → Plan → Tasks → Implementation → Testing → CI → Pull Request.
