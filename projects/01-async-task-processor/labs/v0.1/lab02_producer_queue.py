#!/usr/bin/env python3
"""Lab 02 — submit three tasks and inspect the queue without a worker."""

import sys
from pathlib import Path
from queue import Empty, Queue

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

from producer import Producer


def check(condition: bool, description: str) -> bool:
    print(f"{'PASS' if condition else 'FAIL'}: {description}")
    return condition


def drain(task_queue: Queue) -> list:
    tasks = []
    while True:
        try:
            task = task_queue.get_nowait()
        except Empty:
            break
        tasks.append(task)
        task_queue.task_done()
    return tasks


def main() -> int:
    print("Lab 02 — Producer and queue")
    task_queue = Queue()
    producer = Producer(task_queue)
    payloads = ("alpha", "beta", "gamma")
    submitted_ids = [producer.submit(payload) for payload in payloads]

    queued_before_drain = task_queue.qsize()
    print("submitted:", " ".join(submitted_ids))
    print(f"queue_size: {queued_before_drain}")

    queued = drain(task_queue)
    queued_ids = [task.task_id for task in queued]
    print("queued:", " ".join(queued_ids))

    results = [
        check(queued_before_drain == 3, "queue size is 3"),
        check(len(queued) == 3, "drained task count is 3"),
        check(len(set(submitted_ids)) == 3, "task ids are unique"),
        check(queued_ids == submitted_ids, "returned ids match queued tasks"),
        check(
            [task.payload for task in queued] == list(payloads),
            "queued payloads match submissions",
        ),
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
