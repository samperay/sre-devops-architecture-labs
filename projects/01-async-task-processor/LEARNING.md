# Learning journal — Async Task Processing System

Update this file after a milestone pull request is reviewed, tested, and merged into `master`. Leave a section as a placeholder until that evidence exists. Do not record a lesson, test result, or failure that has not happened.

## 1. Project overview

| Field | Value |
| --- | --- |
| Project name | Async Task Processing System |
| Learning objective | Move work off the caller path: one producer, an in-memory queue, and one worker (v0.1). Durability is not part of v0.1. |
| Current milestone | v0.1 — Single Producer and Worker. The code is local only. |
| Current implementation status | IN PROGRESS |

The working tree contains `src/`, `labs/v0.1/`, and `tests/`. The shape is Producer → in-memory queue → one worker, with shutdown states `ACCEPTING`, `STOPPING`, and `STOPPED`. See `README.md`. This milestone is not merged.

## 2. What I learned

Concepts go here only after they show up in a merged implementation, written in the learner's own words.

| Milestone | Concept | In my own words |
| --- | --- | --- |
| — | — | Left blank. A lesson belongs here only after the milestone pull request is merged. |

## 3. Practical evidence

Local commands are recorded here. A merged pull request is still required before this milestone is complete.

| Item | Evidence |
| --- | --- |
| Commands executed | `python3 -m unittest discover -s projects/01-async-task-processor/tests -v` and `python3 projects/01-async-task-processor/labs/v0.1/lab06_automated_tests.py` |
| Actual terminal output | Local run on this workspace: `Ran 20 tests in 0.669s`, then `OK`. Lab 06 printed `tests_run: 20`, `failures: 0`, `errors: 0`, and `Result: PASS`. Elapsed time varies. |
| Tests performed | 20 unittest methods in `tests/test_v01.py`. This is a local run, not a merged-milestone record. |
| GitHub PR references | None. No milestone PR is open or merged. |

## 4. Failure investigation

`test_worker_failure_is_not_treated_as_success` is the local automated check. A separate written investigation, with the learner's own notes, is still open. The milestone pull request is not merged.

| Field | Record |
| --- | --- |
| Failure scenario | Worker raises while another task is still queued. |
| Expected behavior | `STARTED` is logged, `COMPLETED` is not, `shutdown` returns failure, and the state stays `STOPPING`. |
| Actual observed behavior | The local unittest run reported `RuntimeError: processing failed` on stderr and the test ended `ok`. |
| Root cause | The worker records the exception, calls `task_done()` for the failed item, and exits. Remaining items stay unfinished. |
| Recovery steps | None in v0.1. The failed task is not retried. |
| Verification results | Covered by the 20-test local run. Not yet reviewed through a merged pull request. |

## 5. Architecture decisions

Record a decision when a milestone forces a choice. The notes below are the planned v0.1 boundary, not a completed design review.

| Field | v0.1 plan |
| --- | --- |
| Problem or requirement | Accept a task and process it off the caller's path with one producer and one worker. |
| Available design options | The local code uses an in-memory `queue.Queue`. Persistent storage and RabbitMQ remain later milestones (v0.4, v0.5). |
| Selected approach | In code, not yet reviewed through a merged PR: one producer, one worker thread, `uuid.uuid4()` ids, lifecycle logs, and a shared lock with states `ACCEPTING`, `STOPPING`, and `STOPPED`. |
| Trade-offs and limitations | An in-memory queue does not survive process exit. v0.1 has no durability guarantee. A worker exception is reported and is not retried. Retries are v0.3. Persistence is v0.4. |

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
| Implementation | IN PROGRESS |
| Troubleshooting | NOT STARTED |
| Reliability and operations | NOT STARTED |
| Technical communication | NOT STARTED |

## 8. Next activity

**Open the v0.1 pull request for review.**

The local tree has one producer, one in-memory queue, and one worker. Queued tasks may be lost when the process exits. Do not add multiple workers, retries, disk, RabbitMQ, or metrics in that pull request. The milestone is not complete until the pull request is reviewed, tested, and merged.

## 9. Labs for the current v0.1 code

Sections 1–8 stay the milestone journal. This section is the run guide for the scripts in `labs/v0.1/`. Those scripts call the code in `src/`. Task IDs below are examples from one run; every run creates new IDs. A failed check prints `FAIL` and the script exits with status 1.

### Lab 01 — Task model

**Objective.** Create one `Task` and show that its id and payload stay fixed after construction.

**Restaurant analogy.** The order ticket is written once. The ticket number and the dish name are not erased and rewritten on that same ticket. A change is a new ticket.

**Architecture diagram.**

```text
Task (frozen)
+----------------------+
| task_id:  "101"      |
| payload:  "pack-order" |
+----------------------+
        |
        +-- reading fields succeeds
        +-- assigning either field raises FrozenInstanceError
```

**Command.**

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab01_task_model.py
```

**Expected output.**

```text
Lab 01 — Task model
task_id: 101
payload: pack-order
PASS: task_id is 101
PASS: payload is pack-order
PASS: reassigning task_id raises FrozenInstanceError
PASS: reassigning payload raises FrozenInstanceError
Result: PASS
```

**What to observe.** The printed id and payload match the values passed to `Task`. Both assignment attempts fail, and the script still exits 0 because that failure is the expected protection.

**Knowledge-check question.** What becomes unreliable if code later changes `task_id` on a task that is already sitting on the queue?

**Limitations or failure scenarios.** `frozen=True` blocks reassignment of the two fields. It does not persist the task, and this lab does not put the task on a queue. If `frozen=True` is removed, the reassignment checks print `FAIL` and the script exits 1.

### Lab 02 — Producer and queue

**Objective.** Accept three payloads, give each a unique id, and show that all three tasks are on the queue while no worker is running.

**Restaurant analogy.** Three customers place orders. The waiter writes a different ticket number on each one and clips all three to the board. No chef has picked up a ticket yet. If the restaurant closes and the board is wiped, those orders are gone.

**Architecture diagram.**

```text
payloads: alpha, beta, gamma
        |
        v
   Producer.submit
        |
        +-- uuid4 task_id
        +-- Task(task_id, payload)
        +-- queue.put
        +-- return task_id
        v
   queue.Queue
   +--------+--------+--------+
   | Task   | Task   | Task   |
   +--------+--------+--------+
   No worker thread is started.
```

**Command.**

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab02_producer_queue.py
```

**Expected output.** The three ids change every run. The two id lines match each other, `queue_size` is 3, and every check is `PASS`.

```text
Lab 02 — Producer and queue
submitted: 836461b0-f861-4a9e-92da-15fa1d2e8179 118cd195-b598-484d-b983-c6a1fa86e008 ac7ace56-34b5-4a0d-b02c-b4119cf15acd
queue_size: 3
queued: 836461b0-f861-4a9e-92da-15fa1d2e8179 118cd195-b598-484d-b983-c6a1fa86e008 ac7ace56-34b5-4a0d-b02c-b4119cf15acd
PASS: queue size is 3
PASS: drained task count is 3
PASS: task ids are unique
PASS: returned ids match queued tasks
PASS: queued payloads match submissions
Result: PASS
```

**What to observe.** `submit` returns before any processing. The queue size is 3, the drained ids are the same three ids in the same order, and no two ids are equal. The lab reads the queue with `qsize` and `get_nowait`, then calls `task_done` for each removed task.

**Knowledge-check question.** The producer has already returned three ids. What is true about those tasks if the process exits before a worker starts?

**Limitations or failure scenarios.** The queue lives in this process. Nothing here stores tasks on disk, and no worker is running, so the tasks stay queued until the lab drains them for inspection. This script does not configure logging, so the `SUBMITTED` records are not printed. A duplicate id, a missing queue item, or a payload mismatch prints `FAIL` and exits 1.

### Lab 03 — Single worker

**Objective.** Run one background worker, process three tasks one after another, and leave no worker thread behind.

**Restaurant analogy.** One chef takes the first ticket, cooks it, then takes the next. The board is empty only after the third dish. The chef then clocks out. A second chef is not on this shift.

**Architecture diagram.**

```text
Producer.submit x3
        |
        v
   queue.Queue  ----get---->  one thread: task-worker
        ^                         |
        |                         +-- sleep(0.1) for each task
        |                         +-- record completed task id
        +-------- task_done ------+
   queue.join waits until all three are accounted for
   worker.stop joins the thread
```

**Command.**

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab03_single_worker.py
```

**Expected output.** Ids change every run. `submitted` and `completed` list the same ids in the same order. `elapsed_seconds` varies and is about 0.30 or higher because three tasks sleep for 0.1 seconds each. `queue_size` is 0 and `worker_running_after_stop` is `False`.

```text
Lab 03 — Single worker
submitted: b94cf7f6-ae4a-46cb-ab5d-5e1593774c66 d135f8be-58a7-4d71-9822-4e54f31c876d 6cf16cac-086b-432d-a8df-2b5c5d468ae0
completed: b94cf7f6-ae4a-46cb-ab5d-5e1593774c66 d135f8be-58a7-4d71-9822-4e54f31c876d 6cf16cac-086b-432d-a8df-2b5c5d468ae0
elapsed_seconds: 0.304
queue_size: 0
worker_running_after_stop: False
PASS: queue finished before the timeout
PASS: completed ids match submission order
PASS: processing was sequential
PASS: queue is empty
PASS: worker thread stopped
PASS: worker reported no error
Result: PASS
```

**What to observe.** The worker finishes the tasks in submission order, and the elapsed time is long enough for three serial delays rather than one parallel delay. After `stop`, the worker thread is gone. The script waits at most 5 seconds; it does not sit in `queue.join` forever.

**Knowledge-check question.** Why does the elapsed time stay near three delays when the producer submitted all three tasks without waiting for the first one to finish?

**Limitations or failure scenarios.** There is still one worker, no retry, and no durable queue. `stop` is how this lab joins its thread. It is not graceful shutdown: it does not reject new submissions, and tasks left queued are not part of a shutdown drain. If processing raises, that task is not added to the completed ids, `worker.error` is set, the traceback is printed on stderr, and the lab fails. `task_done` still runs, so the queue wait returns.

### Lab 04 — Lifecycle logging

**Objective.** Show `SUBMITTED`, `STARTED`, and `COMPLETED` for three successful tasks, with the same task id on each of that task's events.

**Restaurant analogy.** The waiter writes "accepted" on ticket 101 when it hits the board. The chef writes "cooking" when work starts and "ready" only after the dish is done. Every note carries 101. A dish that burns does not get a "ready" note.

**Architecture diagram.**

```text
submit(payload)
    |
    +--> queue.put
    +--> log "Task <id>: SUBMITTED"
                |
                v
         worker get
                |
                +--> log "Task <id>: STARTED"
                +--> sleep(delay)
                +--> log "Task <id>: COMPLETED"   only if sleep returns
```

**Command.**

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab04_lifecycle_logging.py
```

**Expected output.** Ids change every run. Each id appears on exactly three lines, in the order `SUBMITTED`, then `STARTED`, then `COMPLETED`. Another task's `SUBMITTED` line may appear between those events. `COMPLETED` is not printed before that task's delay has elapsed. The script exits 0 and ends with `Result: PASS`.

```text
Lab 04 — Lifecycle logging
Task f7fca663-27c6-4c92-b3a2-a4466afbcb48: SUBMITTED
Task 056f542d-fc82-4f64-940f-22ad77055108: SUBMITTED
Task 92909fe6-e623-4df8-baa0-6248d6a317d9: SUBMITTED
Task f7fca663-27c6-4c92-b3a2-a4466afbcb48: STARTED
Task f7fca663-27c6-4c92-b3a2-a4466afbcb48: COMPLETED
Task 056f542d-fc82-4f64-940f-22ad77055108: STARTED
Task 056f542d-fc82-4f64-940f-22ad77055108: COMPLETED
Task 92909fe6-e623-4df8-baa0-6248d6a317d9: STARTED
Task 92909fe6-e623-4df8-baa0-6248d6a317d9: COMPLETED
PASS: queue finished before the timeout
PASS: worker reported no error
PASS: 3 tasks produced 9 lifecycle events
PASS: f7fca663-27c6-4c92-b3a2-a4466afbcb48 events are SUBMITTED, STARTED, COMPLETED
PASS: f7fca663-27c6-4c92-b3a2-a4466afbcb48 COMPLETED is logged after processing
PASS: 056f542d-fc82-4f64-940f-22ad77055108 events are SUBMITTED, STARTED, COMPLETED
PASS: 056f542d-fc82-4f64-940f-22ad77055108 COMPLETED is logged after processing
PASS: 92909fe6-e623-4df8-baa0-6248d6a317d9 events are SUBMITTED, STARTED, COMPLETED
PASS: 92909fe6-e623-4df8-baa0-6248d6a317d9 COMPLETED is logged after processing
PASS: worker thread stopped
Result: PASS
```

**What to observe.** Nine lines cover three tasks. The id in `SUBMITTED` is the id in that task's `STARTED` and `COMPLETED` lines. `COMPLETED` follows a successful delay. The worker thread is stopped before the script exits.

**Knowledge-check question.** A task logs `STARTED` and then processing raises. Which of the three events are present, and which event must be absent?

**Limitations or failure scenarios.** These logs are standard-library `logging` records on the logger named `async_task_processor`. Without a configured handler they are discarded, which is why labs 02 and 03 do not print them. A processing exception logs `STARTED`, does not log `COMPLETED`, stores the error on the worker, prints a traceback on stderr, and exits that thread. The failed task is not retried. The queue and the log lines are both gone after the process exits. Graceful shutdown, multiple workers, and persistence are not part of this lab.

### Lab 05 — Graceful shutdown

**Objective.** Stop accepting new tasks, finish the tasks already accepted, and exit the worker only after those tasks are accounted for.

**Restaurant analogy.** The manager flips the sign from open to closing. A customer still at the counter gets a ticket. A customer who arrives after the sign is turned away. The chef finishes every ticket already on the board, then clocks out. Closing does not mean the food was good; it means the board was cleared and the chef left.

**Architecture diagram.**

```text
submit holds the same lock as shutdown
        |
        +-- state ACCEPTING --> enqueue + "Task <id>: SUBMITTED"
        +-- state STOPPING or STOPPED --> SubmissionRejected

shutdown
  1. lock: ACCEPTING -> STOPPING
  2. unlock
  3. queue.join() with a timeout     # accepted tasks finish; lock is not held
  4. put one sentinel on the queue
  5. worker sees the sentinel, calls task_done() once, and returns
  6. join the worker thread
  7. lock: STOPPING -> STOPPED
```

**Command.**

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab05_graceful_shutdown.py
```

**Expected output.** Task ids change every run. Each accepted id logs `SUBMITTED`, then `STARTED`, then `COMPLETED`. Those lines can be interleaved across the three tasks. The rejected fourth payload, `delta`, has no lifecycle line. `state_at_shutdown` and `state_when_rejected` are `STOPPING`. The final `state` is `STOPPED`, `worker_running` is `False`, and every check is `PASS`.

```text
Lab 05 — Graceful shutdown
Task 06526d1a-08cd-4bbe-bc6a-a12bead4bdaa: SUBMITTED
Task 8fb03fba-e8eb-4af0-90eb-5a8e5fd96a50: SUBMITTED
Task 5abcc0b8-40c0-4324-a283-8609479fb507: SUBMITTED
Task 06526d1a-08cd-4bbe-bc6a-a12bead4bdaa: STARTED
Task 06526d1a-08cd-4bbe-bc6a-a12bead4bdaa: COMPLETED
Task 8fb03fba-e8eb-4af0-90eb-5a8e5fd96a50: STARTED
Task 8fb03fba-e8eb-4af0-90eb-5a8e5fd96a50: COMPLETED
Task 5abcc0b8-40c0-4324-a283-8609479fb507: STARTED
Task 5abcc0b8-40c0-4324-a283-8609479fb507: COMPLETED
accepted: 06526d1a-08cd-4bbe-bc6a-a12bead4bdaa 8fb03fba-e8eb-4af0-90eb-5a8e5fd96a50 5abcc0b8-40c0-4324-a283-8609479fb507
state_at_shutdown: STOPPING
in_flight_when_shutdown_began: True
fourth_task_rejected: True
state_when_rejected: STOPPING
completed: 06526d1a-08cd-4bbe-bc6a-a12bead4bdaa 8fb03fba-e8eb-4af0-90eb-5a8e5fd96a50 5abcc0b8-40c0-4324-a283-8609479fb507
state: STOPPED
worker_running: False
PASS: shutdown did not raise
PASS: shutdown returned before the timeout
PASS: shutdown completed
PASS: shutdown began while the processor was still running
PASS: at least one accepted task was still unfinished
PASS: fourth task was rejected
PASS: fourth task was rejected after STOPPING and before STOPPED
PASS: first three tasks completed in order
PASS: worker thread exited
PASS: application state is STOPPED
PASS: queue is empty
PASS: worker reported no error
Result: PASS
```

**What to observe.** Shutdown begins while at least one of the three tasks is still unfinished. The fourth `submit` raises `SubmissionRejected` during `STOPPING`. The original three ids then show up as completed, in submission order, and only then is the state `STOPPED` and the worker gone.

**Knowledge-check question.** Why does shutdown release the coordination lock before it waits for the queue to drain?

**Limitations or failure scenarios.** This is one worker and an in-memory queue. A task accepted before `STOPPING` can still be lost if the process crashes. There are no retries. `task_done()` means the queue has accounted for that item, including the sentinel; it does not mean processing succeeded. If the worker raises while other tasks are still queued, that failed item is accounted for, `COMPLETED` is not logged, the traceback is printed on stderr, and the thread exits. The remaining tasks stay unfinished, so `queue.join()` would wait forever. `shutdown` waits only up to its timeout, leaves the state at `STOPPING`, and returns failure. The lab's waits are bounded, and the worker thread is a daemon, so a failed run still exits. Multiple workers, persistence, and RabbitMQ are later milestones.

### Lab 06 — Automated tests

**Objective.** Run the unittest suite that checks submission, one worker, unique ids, the processing delay, lifecycle logs, shutdown, standard-library imports, concurrent submission, and worker failure.

**Restaurant analogy.** Before the dinner service is called finished, the manager walks a checklist. Three tickets on the board have different numbers. One chef is on the line. The closing sign turns away a late order. A burned dish is written up as a failure, not served. The checklist is the test suite. Passing it does not mean the restaurant survived a fire.

**Architecture diagram.**

```text
lab06_automated_tests.py
        |
        v
python -m unittest discover tests/
        |
        +-- RequirementTests     R1–R7, AC1–AC6 behavior
        +-- ConcurrencyTests     lock order, racing submits, repeated shutdown
        +-- FailureTests         bad delay, empty queue, rejected submit, worker error
        |
        v
src/  Producer, Worker, Processor
```

**Command.**

```bash
python3 projects/01-async-task-processor/labs/v0.1/lab06_automated_tests.py
```

**Expected output.** Every test line ends in `ok`. During `test_worker_failure_is_not_treated_as_success`, stderr prints a `RuntimeError: processing failed` traceback from the worker thread, and that test still ends in `ok`. The elapsed time changes. The stable ending is:

```text
Ran 20 tests in 0.669s

OK
tests_run: 20
failures: 0
errors: 0
Result: PASS
```

The exit status is 0. A failing test prints `Result: FAIL` and the script exits 1.

**What to observe.** Twenty tests run from `tests/test_v01.py`. The worker-failure traceback is the reported error, not a hidden success. `Result: PASS` appears only after `OK`.

**Knowledge-check question.** The suite passes, and then the process is killed while a task is still queued. Which of those outcomes does this lab prove, and which one is still lost?

**Limitations or failure scenarios.** These tests use bounded waits. They do not prove the queue survives a crash, and they do not add retries or a second worker. A worker exception leaves the state at `STOPPING` and leaves the remaining tasks unfinished. `task_done()` on the failed item is queue accounting, not successful processing. This lab does not open or merge a pull request. `PROGRESS.md` stays unchanged until a reviewed merge exists.
