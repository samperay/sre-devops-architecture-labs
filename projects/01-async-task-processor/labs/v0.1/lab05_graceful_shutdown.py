#!/usr/bin/env python3
"""Lab 05 — reject new work once shutdown begins, then finish accepted tasks."""

import logging
import sys
import threading
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

from processor import ApplicationState, Processor
from producer import LOGGER_NAME, SubmissionRejected

DELAY = 0.15
TIMEOUT = 5.0


def check(condition: bool, description: str) -> bool:
    print(f"{'PASS' if condition else 'FAIL'}: {description}")
    return condition


def configure_logging() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def main() -> int:
    print("Lab 05 — Graceful shutdown")
    configure_logging()
    processor = Processor(delay=DELAY)
    processor.start()

    shutdown_result: dict[str, bool | Exception] = {}

    def _shutdown() -> None:
        try:
            shutdown_result["ok"] = processor.shutdown(timeout=TIMEOUT)
        except Exception as exc:
            shutdown_result["error"] = exc

    try:
        accepted_ids = [
            processor.submit(payload) for payload in ("alpha", "beta", "gamma")
        ]
        shutdown_thread = threading.Thread(
            target=_shutdown,
            name="shutdown",
            daemon=True,
        )
        shutdown_thread.start()

        state_at_shutdown = ApplicationState.ACCEPTING
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            state_at_shutdown = processor.state
            if state_at_shutdown is not ApplicationState.ACCEPTING:
                break
            time.sleep(0.005)
        in_flight = len(processor.completed_task_ids()) < len(accepted_ids)

        rejected = False
        try:
            processor.submit("delta")
        except SubmissionRejected:
            rejected = True
            state_when_rejected = processor.state
        else:
            state_when_rejected = processor.state

        shutdown_thread.join(TIMEOUT + 1.0)
    finally:
        if processor.worker_is_running():
            processor.shutdown(timeout=TIMEOUT)

    completed = processor.completed_task_ids()
    print("accepted:", " ".join(accepted_ids))
    print(f"state_at_shutdown: {state_at_shutdown.name}")
    print(f"in_flight_when_shutdown_began: {in_flight}")
    print(f"fourth_task_rejected: {rejected}")
    print(f"state_when_rejected: {state_when_rejected.name}")
    print("completed:", " ".join(completed))
    print(f"state: {processor.state.name}")
    print(f"worker_running: {processor.worker_is_running()}")
    if processor.error is not None:
        print(f"worker_error: {processor.error}")

    shutdown_ok = shutdown_result.get("ok") is True
    results = [
        check("error" not in shutdown_result, "shutdown did not raise"),
        check(not shutdown_thread.is_alive(), "shutdown returned before the timeout"),
        check(shutdown_ok, "shutdown completed"),
        check(
            state_at_shutdown is ApplicationState.STOPPING,
            "shutdown began while the processor was still running",
        ),
        check(in_flight, "at least one accepted task was still unfinished"),
        check(rejected, "fourth task was rejected"),
        check(
            state_when_rejected is ApplicationState.STOPPING,
            "fourth task was rejected after STOPPING and before STOPPED",
        ),
        check(completed == tuple(accepted_ids), "first three tasks completed in order"),
        check(processor.worker_is_running() is False, "worker thread exited"),
        check(processor.state is ApplicationState.STOPPED, "application state is STOPPED"),
        check(processor.queue.qsize() == 0, "queue is empty"),
        check(processor.error is None, "worker reported no error"),
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
