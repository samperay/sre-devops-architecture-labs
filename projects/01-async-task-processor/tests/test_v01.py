"""Automated checks for Async Task Processor v0.1."""

from __future__ import annotations

import ast
import logging
import sys
import threading
import time
import unittest
from pathlib import Path
from queue import Empty, Queue

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

import worker as worker_module
from processor import ApplicationState, Processor
from producer import (
    COMPLETED,
    LOGGER_NAME,
    STARTED,
    SUBMITTED,
    Producer,
    SubmissionRejected,
)
from worker import Worker

LOCAL_MODULES = {"task", "producer", "worker", "processor", "main"}
WAIT = 2.0


def wait_until(predicate, timeout: float = WAIT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.001)
    return False


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self._records_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        with self._records_lock:
            self.records.append(record)

    def snapshot(self) -> list[logging.LogRecord]:
        with self._records_lock:
            return list(self.records)


def lifecycle_events(
    records: list[logging.LogRecord],
) -> list[tuple[str, str, float]]:
    events = []
    for record in records:
        message = record.getMessage()
        prefix = "Task "
        if not message.startswith(prefix) or ": " not in message:
            continue
        task_id, event = message[len(prefix) :].rsplit(": ", 1)
        events.append((task_id, event, record.created))
    return events


class ProcessorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.handler = ListHandler()
        self.logger.addHandler(self.handler)
        self.addCleanup(self.logger.removeHandler, self.handler)

    def patch_sleep(self, replacement) -> None:
        original = worker_module.time.sleep
        worker_module.time.sleep = replacement
        self.addCleanup(setattr, worker_module.time, "sleep", original)

    def start(self, delay: float = 0.0) -> Processor:
        processor = Processor(delay)
        self.addCleanup(self.stop, processor)
        processor.start()
        return processor

    def stop(self, processor: Processor) -> None:
        if (
            processor.state is ApplicationState.STOPPED
            and not processor.worker_is_running()
        ):
            return
        timeout = 0.2 if processor.error is not None else WAIT
        processor.shutdown(timeout=timeout)

    def assert_stopped(self, processor: Processor) -> None:
        self.assertIs(processor.state, ApplicationState.STOPPED)
        self.assertFalse(processor.worker_is_running())
        self.assertTrue(
            wait_until(
                lambda: not any(
                    thread.name == "task-worker" and thread.is_alive()
                    for thread in threading.enumerate()
                )
            )
        )


class RequirementTests(ProcessorTestCase):
    def test_r1_three_submissions_stay_queued_without_a_worker(self) -> None:
        task_queue: Queue = Queue()
        producer = Producer(task_queue)
        payloads = ("alpha", "beta", "gamma")
        submitted = [producer.submit(payload) for payload in payloads]

        self.assertEqual(task_queue.qsize(), 3)
        queued = []
        while True:
            try:
                queued.append(task_queue.get_nowait())
            except Empty:
                break
            task_queue.task_done()

        self.assertEqual([task.task_id for task in queued], submitted)
        self.assertEqual([task.payload for task in queued], list(payloads))
        self.assertTrue(task_queue.empty())

    def test_r2_one_worker_thread_processes_tasks_one_at_a_time(self) -> None:
        active = {"current": 0, "max": 0}
        active_lock = threading.Lock()

        def spy(_seconds: float) -> None:
            with active_lock:
                active["current"] += 1
                active["max"] = max(active["max"], active["current"])
            with active_lock:
                active["current"] -= 1

        self.patch_sleep(spy)
        before = {thread.ident for thread in threading.enumerate()}
        processor = self.start(0.2)
        submitted = [processor.submit(str(index)) for index in range(3)]
        workers = [
            thread
            for thread in threading.enumerate()
            if thread.name == "task-worker" and thread.ident not in before
        ]
        self.assertEqual(len(workers), 1)
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(processor.completed_task_ids(), tuple(submitted))
        self.assertEqual(active["max"], 1)
        self.assert_stopped(processor)

    def test_r2_starting_twice_does_not_create_a_second_worker(self) -> None:
        processor = self.start()
        with self.assertRaises(RuntimeError):
            processor.start()
        alive = [
            thread
            for thread in threading.enumerate()
            if thread.name == "task-worker" and thread.is_alive()
        ]
        self.assertEqual(len(alive), 1)

    def test_r3_three_submissions_receive_distinct_ids(self) -> None:
        task_queue: Queue = Queue()
        producer = Producer(task_queue)
        submitted = [producer.submit(str(index)) for index in range(3)]
        self.assertEqual(len(set(submitted)), 3)
        queued_ids = []
        while True:
            try:
                queued_ids.append(task_queue.get_nowait().task_id)
            except Empty:
                break
            task_queue.task_done()
        self.assertEqual(queued_ids, submitted)

    def test_r4_worker_sleeps_for_the_configured_delay(self) -> None:
        seen: list[float] = []

        def spy(seconds: float) -> None:
            seen.append(seconds)

        self.patch_sleep(spy)
        for delay in (0.0, 0.2):
            with self.subTest(delay=delay):
                seen.clear()
                processor = self.start(delay)
                processor.submit("payload")
                self.assertTrue(processor.shutdown(timeout=WAIT))
                self.assertEqual(seen, [delay])

    def test_r4_completed_is_logged_only_after_the_delay(self) -> None:
        delay = 0.05
        processor = self.start(delay)
        task_id = processor.submit("payload")
        self.assertTrue(processor.shutdown(timeout=WAIT))
        events = [
            (event, created)
            for seen_id, event, created in lifecycle_events(self.handler.snapshot())
            if seen_id == task_id
        ]
        self.assertEqual(
            [event for event, _created in events],
            [SUBMITTED, STARTED, COMPLETED],
        )
        started_at = events[1][1]
        completed_at = events[2][1]
        self.assertGreaterEqual(completed_at - started_at, delay * 0.5)

    def test_r5_lifecycle_events_follow_submitted_started_completed(self) -> None:
        processor = self.start()
        submitted = [processor.submit(payload) for payload in ("alpha", "beta", "gamma")]
        self.assertTrue(processor.shutdown(timeout=WAIT))
        by_task: dict[str, list[str]] = {task_id: [] for task_id in submitted}
        for task_id, event, _created in lifecycle_events(self.handler.snapshot()):
            self.assertIn(task_id, by_task)
            by_task[task_id].append(event)
        for task_id in submitted:
            self.assertEqual(by_task[task_id], [SUBMITTED, STARTED, COMPLETED])

    def test_ac2_started_is_logged_when_the_task_leaves_the_queue(self) -> None:
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def gate(_seconds: float) -> None:
            started.set()
            self.assertTrue(release.wait(WAIT))

        self.patch_sleep(gate)
        processor = self.start(0.2)
        task_id = processor.submit("alpha")
        self.assertTrue(started.wait(WAIT))
        events = [
            event
            for seen_id, event, _created in lifecycle_events(self.handler.snapshot())
            if seen_id == task_id
        ]
        self.assertIn(STARTED, events)
        self.assertNotIn(COMPLETED, events)
        self.assertTrue(processor.queue.empty())
        release.set()
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(processor.completed_task_ids(), (task_id,))

    def test_r6_shutdown_drains_three_accepted_tasks_and_rejects_the_fourth(self) -> None:
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        calls = {"count": 0}

        def gate(_seconds: float) -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                started.set()
                self.assertTrue(release.wait(WAIT))

        self.patch_sleep(gate)
        processor = self.start(0.2)
        accepted = [processor.submit(payload) for payload in ("alpha", "beta", "gamma")]
        self.assertTrue(started.wait(WAIT))
        self.assertEqual(processor.queue.qsize(), 2)

        outcome: dict[str, bool | Exception] = {}

        def _shutdown() -> None:
            try:
                outcome["ok"] = processor.shutdown(timeout=WAIT)
            except Exception as exc:
                outcome["error"] = exc

        shutdown_thread = threading.Thread(target=_shutdown, daemon=True)
        shutdown_thread.start()
        self.assertTrue(
            wait_until(lambda: processor.state is ApplicationState.STOPPING)
        )
        with self.assertRaises(SubmissionRejected):
            processor.submit("delta")
        self.assertLess(len(processor.completed_task_ids()), 3)
        release.set()
        shutdown_thread.join(WAIT)
        self.assertFalse(shutdown_thread.is_alive())
        self.assertNotIn("error", outcome)
        self.assertIs(outcome.get("ok"), True)
        self.assertEqual(processor.completed_task_ids(), tuple(accepted))
        self.assert_stopped(processor)
        self.assertTrue(processor.queue.empty())

    def test_r7_application_imports_only_the_standard_library(self) -> None:
        third_party = []
        for path in sorted(SRC.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module.split(".")[0]]
                for module_name in modules:
                    if module_name in LOCAL_MODULES:
                        continue
                    if module_name not in sys.stdlib_module_names:
                        third_party.append(f"{path.name}:{module_name}")
        self.assertEqual(third_party, [])
        self.assertFalse((PROJECT / "requirements.txt").exists())


class ConcurrencyTests(ProcessorTestCase):
    def _replace_acceptance(self, processor: Processor, callback) -> None:
        processor._producer._is_accepting = callback

    def test_submission_inside_the_lock_before_stopping_is_accepted(self) -> None:
        processor = self.start()
        barrier = threading.Barrier(2)
        decision = {"accept": True}

        def is_accepting() -> bool:
            barrier.wait(WAIT)
            return decision["accept"]

        self._replace_acceptance(processor, is_accepting)
        result: dict[str, str | bool] = {}

        def submit() -> None:
            try:
                result["id"] = processor.submit("before-stopping")
            except SubmissionRejected:
                result["rejected"] = True

        thread = threading.Thread(target=submit)
        thread.start()
        decision["accept"] = True
        barrier.wait(WAIT)
        thread.join(WAIT)
        self.assertNotIn("rejected", result)
        task_id = result["id"]
        self.assertIsInstance(task_id, str)
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(processor.completed_task_ids(), (task_id,))
        self.assert_stopped(processor)

    def test_submission_inside_the_lock_after_stopping_is_rejected(self) -> None:
        processor = self.start()
        barrier = threading.Barrier(2)

        def is_accepting() -> bool:
            barrier.wait(WAIT)
            return False

        self._replace_acceptance(processor, is_accepting)
        result: dict[str, str | bool] = {}

        def submit() -> None:
            try:
                result["id"] = processor.submit("after-stopping")
            except SubmissionRejected:
                result["rejected"] = True

        thread = threading.Thread(target=submit)
        thread.start()
        barrier.wait(WAIT)
        thread.join(WAIT)
        self.assertIs(result.get("rejected"), True)
        self.assertNotIn("id", result)
        self.assertTrue(processor.queue.empty())
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(processor.completed_task_ids(), ())
        self.assert_stopped(processor)

    def test_concurrent_producers_receive_distinct_ids(self) -> None:
        processor = self.start()
        barrier = threading.Barrier(6)
        found: list[str] = []
        found_lock = threading.Lock()

        def produce() -> None:
            barrier.wait(WAIT)
            task_id = processor.submit("concurrent")
            with found_lock:
                found.append(task_id)

        threads = [threading.Thread(target=produce) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(found), 6)
        self.assertEqual(len(set(found)), 6)
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(set(processor.completed_task_ids()), set(found))
        self.assert_stopped(processor)

    def test_shutdown_races_concurrent_submissions(self) -> None:
        processor = self.start()
        parties = 8
        barrier = threading.Barrier(parties + 1)
        accepted: list[str] = []
        rejected = {"count": 0}
        result_lock = threading.Lock()

        def produce() -> None:
            barrier.wait(WAIT)
            try:
                task_id = processor.submit("race")
            except SubmissionRejected:
                with result_lock:
                    rejected["count"] += 1
            else:
                with result_lock:
                    accepted.append(task_id)

        threads = [threading.Thread(target=produce) for _ in range(parties)]
        for thread in threads:
            thread.start()
        barrier.wait(WAIT)
        shutdown_ok = processor.shutdown(timeout=WAIT)
        for thread in threads:
            thread.join(WAIT)
            self.assertFalse(thread.is_alive())
        self.assertTrue(shutdown_ok)
        self.assertEqual(len(accepted) + rejected["count"], parties)
        self.assertEqual(set(processor.completed_task_ids()), set(accepted))
        self.assert_stopped(processor)

    def _count_shutdown_work(self, processor: Processor) -> dict[str, int]:
        counts = {"coordinators": 0, "sentinels": 0}
        count_lock = threading.Lock()
        original_drive = processor._drive_shutdown
        original_signal = processor._worker.signal_stop

        def drive(deadline: float) -> bool:
            with count_lock:
                counts["coordinators"] += 1
            return original_drive(deadline)

        def signal_stop() -> None:
            with count_lock:
                counts["sentinels"] += 1
            original_signal()

        processor._drive_shutdown = drive
        processor._worker.signal_stop = signal_stop
        return counts

    def test_repeated_shutdown_requests_stop_the_worker_once(self) -> None:
        processor = self.start()
        task_id = processor.submit("only")
        counts = self._count_shutdown_work(processor)
        barrier = threading.Barrier(2)
        results: list[bool] = []
        result_lock = threading.Lock()

        def request_shutdown() -> None:
            barrier.wait(WAIT)
            ok = processor.shutdown(timeout=WAIT)
            with result_lock:
                results.append(ok)

        threads = [
            threading.Thread(target=request_shutdown, daemon=True) for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(results), [True, True])
        self.assertEqual(counts["coordinators"], 1)
        self.assertEqual(counts["sentinels"], 1)
        self.assertEqual(processor.completed_task_ids(), (task_id,))
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(counts["coordinators"], 1)
        self.assertEqual(counts["sentinels"], 1)
        self.assert_stopped(processor)
        self.assertTrue(processor.queue.empty())

    def test_shutdown_waiter_times_out_while_coordinator_continues(self) -> None:
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def gate(_seconds: float) -> None:
            started.set()
            self.assertTrue(release.wait(WAIT))

        self.patch_sleep(gate)
        processor = self.start(0.2)
        task_id = processor.submit("accepted")
        self.assertTrue(started.wait(WAIT))
        counts = self._count_shutdown_work(processor)
        coordinator_done = threading.Event()
        outcome: dict[str, bool | Exception] = {}

        def coordinate() -> None:
            try:
                outcome["ok"] = processor.shutdown(timeout=WAIT)
            except Exception as exc:
                outcome["error"] = exc
            finally:
                coordinator_done.set()

        coordinator = threading.Thread(target=coordinate, daemon=True)
        coordinator.start()
        self.assertTrue(
            wait_until(lambda: processor.state is ApplicationState.STOPPING)
        )
        with self.assertRaises(SubmissionRejected):
            processor.submit("after-stopping")
        timed_out_at = time.monotonic()
        waiter_ok = processor.shutdown(timeout=0.05)
        waiter_elapsed = time.monotonic() - timed_out_at
        self.assertFalse(waiter_ok)
        self.assertLess(waiter_elapsed, 0.5)
        self.assertFalse(coordinator_done.is_set())
        self.assertIs(processor.state, ApplicationState.STOPPING)
        self.assertEqual(processor.completed_task_ids(), ())
        release.set()
        self.assertTrue(coordinator_done.wait(WAIT))
        self.assertNotIn("error", outcome)
        self.assertIs(outcome.get("ok"), True)
        self.assertEqual(processor.completed_task_ids(), (task_id,))
        self.assertEqual(counts["coordinators"], 1)
        self.assertEqual(counts["sentinels"], 1)
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(counts["coordinators"], 1)
        self.assertEqual(counts["sentinels"], 1)
        self.assert_stopped(processor)
        self.assertTrue(processor.queue.empty())

    def test_later_shutdown_resumes_after_an_incomplete_attempt(self) -> None:
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def gate(_seconds: float) -> None:
            started.set()
            self.assertTrue(release.wait(WAIT))

        self.patch_sleep(gate)
        processor = self.start(0.2)
        task_id = processor.submit("accepted")
        self.assertTrue(started.wait(WAIT))
        counts = self._count_shutdown_work(processor)
        active = {"current": 0, "max": 0}
        active_lock = threading.Lock()
        original_drive = processor._drive_shutdown

        def drive(deadline: float) -> bool:
            with active_lock:
                active["current"] += 1
                active["max"] = max(active["max"], active["current"])
            try:
                return original_drive(deadline)
            finally:
                with active_lock:
                    active["current"] -= 1

        processor._drive_shutdown = drive
        self.assertFalse(processor.shutdown(timeout=0.05))
        self.assertIs(processor.state, ApplicationState.STOPPING)
        self.assertTrue(processor.worker_is_running())
        release.set()
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(processor.completed_task_ids(), (task_id,))
        self.assertEqual(active["max"], 1)
        self.assertEqual(counts["coordinators"], 2)
        self.assertEqual(counts["sentinels"], 1)
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(counts["coordinators"], 2)
        self.assertEqual(counts["sentinels"], 1)
        self.assert_stopped(processor)


class FailureTests(ProcessorTestCase):
    def test_negative_worker_delay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Worker(Queue(), delay=-1)
        with self.assertRaises(ValueError):
            Processor(delay=-0.01)

    def test_negative_shutdown_timeout_is_rejected(self) -> None:
        processor = Processor(0)
        with self.assertRaises(ValueError):
            processor.shutdown(timeout=-1)
        self.assertIs(processor.state, ApplicationState.ACCEPTING)
        self.assertFalse(processor.worker_is_running())

    def test_submission_after_stopped_is_rejected(self) -> None:
        processor = self.start()
        self.assertTrue(processor.shutdown(timeout=WAIT))
        with self.assertRaises(SubmissionRejected):
            processor.submit("too-late")
        self.assertEqual(processor.completed_task_ids(), ())
        self.assert_stopped(processor)

    def test_empty_queue_shutdown_stops_the_worker(self) -> None:
        task_queue: Queue = Queue()
        producer = Producer(task_queue)
        with self.assertRaises(Empty):
            task_queue.get_nowait()
        self.assertTrue(task_queue.empty())
        self.assertEqual(producer.queued_tasks(), ())

        processor = self.start()
        self.assertTrue(processor.queue.empty())
        self.assertTrue(processor.worker_is_running())
        self.assertTrue(processor.shutdown(timeout=WAIT))
        self.assertEqual(processor.completed_task_ids(), ())
        self.assertTrue(processor.queue.empty())
        self.assert_stopped(processor)

    def test_worker_failure_is_not_treated_as_success(self) -> None:
        def fail(_seconds: float) -> None:
            raise RuntimeError("processing failed")

        self.patch_sleep(fail)
        stderr_lines: list[str] = []
        original_hook = threading.excepthook

        def capture_hook(args) -> None:
            stderr_lines.append(str(args.exc_value))
            original_hook(args)

        threading.excepthook = capture_hook
        self.addCleanup(setattr, threading, "excepthook", original_hook)

        processor = self.start(0.2)
        first, second = processor.submit("bad"), processor.submit("later")
        started = time.monotonic()
        shutdown_ok = processor.shutdown(timeout=0.4)
        elapsed = time.monotonic() - started

        self.assertFalse(shutdown_ok)
        self.assertLess(elapsed, 1.5)
        self.assertIs(processor.state, ApplicationState.STOPPING)
        self.assertIsInstance(processor.error, RuntimeError)
        self.assertNotIn(first, processor.completed_task_ids())
        self.assertNotIn(second, processor.completed_task_ids())
        events = [
            event
            for task_id, event, _created in lifecycle_events(self.handler.snapshot())
            if task_id == first
        ]
        self.assertIn(STARTED, events)
        self.assertNotIn(COMPLETED, events)
        self.assertTrue(wait_until(lambda: not processor.worker_is_running()))
        self.assertTrue(any("processing failed" in line for line in stderr_lines))
        self.assertGreaterEqual(processor.queue.unfinished_tasks, 1)


if __name__ == "__main__":
    unittest.main()
