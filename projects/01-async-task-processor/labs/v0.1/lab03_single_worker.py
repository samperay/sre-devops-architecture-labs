#!/usr/bin/env python3
"""Lab 03 — one worker processes three tasks, then the thread exits."""

import sys
import threading
import time
from pathlib import Path
from queue import Queue

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

from producer import Producer
from worker import Worker

DELAY = 0.1
TIMEOUT = 5.0


def check(condition: bool, description: str) -> bool:
    print(f"{'PASS' if condition else 'FAIL'}: {description}")
    return condition


def wait_until_idle(task_queue: Queue, timeout: float) -> bool:
    done = threading.Event()

    def _join() -> None:
        task_queue.join()
        done.set()

    threading.Thread(target=_join, name="queue-join", daemon=True).start()
    return done.wait(timeout)


def main() -> int:
    print("Lab 03 — Single worker")
    task_queue = Queue()
    producer = Producer(task_queue)
    worker = Worker(task_queue, delay=DELAY)
    worker.start()
    try:
        submitted_ids = [
            producer.submit(payload) for payload in ("alpha", "beta", "gamma")
        ]
        started = time.monotonic()
        finished = wait_until_idle(task_queue, TIMEOUT)
        elapsed = time.monotonic() - started
        completed = worker.completed_task_ids()
        error = worker.error
    finally:
        worker.stop()

    print("submitted:", " ".join(submitted_ids))
    print("completed:", " ".join(completed))
    print(f"elapsed_seconds: {elapsed:.3f}")
    print(f"queue_size: {task_queue.qsize()}")
    print(f"worker_running_after_stop: {worker.is_running()}")
    if error is not None:
        print(f"worker_error: {error}")

    results = [
        check(finished, "queue finished before the timeout"),
        check(completed == tuple(submitted_ids), "completed ids match submission order"),
        check(elapsed >= DELAY * 3 * 0.9, "processing was sequential"),
        check(task_queue.qsize() == 0 and task_queue.empty(), "queue is empty"),
        check(worker.is_running() is False, "worker thread stopped"),
        check(error is None, "worker reported no error"),
    ]
    passed = all(results)
    print(f"Result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
