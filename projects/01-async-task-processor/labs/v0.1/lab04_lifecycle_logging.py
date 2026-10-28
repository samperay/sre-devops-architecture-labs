#!/usr/bin/env python3
"""Lab 04 — each accepted task logs SUBMITTED, STARTED, and COMPLETED."""

import logging
import sys
import threading
from pathlib import Path
from queue import Queue

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

from producer import COMPLETED, LOGGER_NAME, STARTED, SUBMITTED, Producer
from worker import Worker

DELAY = 0.1
TIMEOUT = 5.0
EVENTS = (SUBMITTED, STARTED, COMPLETED)


def check(condition: bool, description: str) -> bool:
    print(f"{'PASS' if condition else 'FAIL'}: {description}")
    return condition


def configure_logging(records: list[logging.LogRecord]) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    formatter = logging.Formatter("%(message)s")
    capture = Capture()
    capture.setFormatter(formatter)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(capture)
    logger.addHandler(stream)


def wait_until_idle(task_queue: Queue, timeout: float) -> bool:
    done = threading.Event()

    def _join() -> None:
        task_queue.join()
        done.set()

    threading.Thread(target=_join, name="queue-join", daemon=True).start()
    return done.wait(timeout)


def parse_event(message: str) -> tuple[str, str] | None:
    prefix = "Task "
    if not message.startswith(prefix) or ": " not in message:
        return None
    task_id, event = message[len(prefix) :].rsplit(": ", 1)
    if event not in EVENTS:
        return None
    return task_id, event


def main() -> int:
    print("Lab 04 — Lifecycle logging")
    records: list[logging.LogRecord] = []
    configure_logging(records)

    task_queue = Queue()
    producer = Producer(task_queue)
    worker = Worker(task_queue, delay=DELAY, lock=producer.lock)
    worker.start()
    try:
        submitted_ids = [
            producer.submit(payload) for payload in ("alpha", "beta", "gamma")
        ]
        finished = wait_until_idle(task_queue, TIMEOUT)
        error = worker.error
    finally:
        worker.stop()

    parsed: list[tuple[str, str, float]] = []
    for record in records:
        event = parse_event(record.getMessage())
        if event is not None:
            parsed.append((event[0], event[1], record.created))

    by_task: dict[str, list[tuple[str, float]]] = {task_id: [] for task_id in submitted_ids}
    unexpected = False
    for task_id, event, created in parsed:
        if task_id not in by_task:
            unexpected = True
            continue
        by_task[task_id].append((event, created))

    results = [
        check(finished, "queue finished before the timeout"),
        check(error is None, "worker reported no error"),
        check(len(parsed) == 9 and not unexpected, "3 tasks produced 9 lifecycle events"),
    ]
    for task_id in submitted_ids:
        events = by_task[task_id]
        names = [event for event, _created in events]
        results.append(
            check(
                names == [SUBMITTED, STARTED, COMPLETED],
                f"{task_id} events are SUBMITTED, STARTED, COMPLETED",
            )
        )
        if names == [SUBMITTED, STARTED, COMPLETED]:
            started_at = events[1][1]
            completed_at = events[2][1]
            results.append(
                check(
                    completed_at - started_at >= DELAY * 0.5,
                    f"{task_id} COMPLETED is logged after processing",
                )
            )
        else:
            results.append(check(False, f"{task_id} COMPLETED is logged after processing"))

    results.append(check(worker.is_running() is False, "worker thread stopped"))
    passed = all(results)
    print(f"Result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
