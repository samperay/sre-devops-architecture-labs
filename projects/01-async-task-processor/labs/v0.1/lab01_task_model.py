#!/usr/bin/env python3
"""Lab 01 — create one immutable Task and show that its fields stay fixed."""

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

from task import Task


def check(condition: bool, description: str) -> bool:
    print(f"{'PASS' if condition else 'FAIL'}: {description}")
    return condition


def reassignment_blocked(task: Task, field: str) -> bool:
    try:
        setattr(task, field, "changed")
    except FrozenInstanceError:
        return True
    return False


def main() -> int:
    print("Lab 01 — Task model")
    task = Task(task_id="101", payload="pack-order")
    print(f"task_id: {task.task_id}")
    print(f"payload: {task.payload}")

    results = [
        check(task.task_id == "101", "task_id is 101"),
        check(task.payload == "pack-order", "payload is pack-order"),
        check(
            reassignment_blocked(task, "task_id"),
            "reassigning task_id raises FrozenInstanceError",
        ),
        check(
            reassignment_blocked(task, "payload"),
            "reassigning payload raises FrozenInstanceError",
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
