from __future__ import annotations

import enum
import threading
import time
from queue import Queue

from producer import Producer
from worker import Worker


class ApplicationState(enum.Enum):
    ACCEPTING = "ACCEPTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _wait_until_idle(task_queue: Queue, timeout: float) -> bool:
    if timeout < 0:
        timeout = 0.0
    with task_queue.all_tasks_done:
        if task_queue.unfinished_tasks == 0:
            return True
        if timeout == 0:
            return False
        deadline = time.monotonic() + timeout
        while task_queue.unfinished_tasks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            task_queue.all_tasks_done.wait(remaining)
        return True


class Processor:
    def __init__(self, delay: float) -> None:
        self._queue: Queue = Queue()
        self._lock = threading.Lock()
        self._shutdown_waiting = threading.Condition(self._lock)
        self._shutdown_active = False
        self._state = ApplicationState.ACCEPTING
        self._producer = Producer(
            self._queue,
            lock=self._lock,
            is_accepting=self._is_accepting,
        )
        self._worker = Worker(self._queue, delay, lock=self._lock)

    @property
    def queue(self) -> Queue:
        return self._queue

    @property
    def state(self) -> ApplicationState:
        with self._lock:
            return self._state

    def start(self) -> None:
        self._worker.start()

    def submit(self, payload: str) -> str:
        return self._producer.submit(payload)

    def shutdown(self, timeout: float = 5.0) -> bool:
        if timeout < 0:
            raise ValueError("timeout must be non-negative")
        deadline = time.monotonic() + timeout
        with self._lock:
            if self._state is ApplicationState.STOPPED:
                return True
            if self._shutdown_active:
                return self._wait_for_shutdown(deadline)
            self._shutdown_active = True
            if self._state is ApplicationState.ACCEPTING:
                self._state = ApplicationState.STOPPING
        return self._coordinate_shutdown(deadline)

    def _wait_for_shutdown(self, deadline: float) -> bool:
        while self._shutdown_active:
            remaining = _remaining(deadline)
            if remaining <= 0:
                return False
            self._shutdown_waiting.wait(remaining)
        return self._state is ApplicationState.STOPPED

    def _coordinate_shutdown(self, deadline: float) -> bool:
        completed = False
        try:
            completed = self._drive_shutdown(deadline)
        finally:
            with self._lock:
                if completed:
                    self._state = ApplicationState.STOPPED
                self._shutdown_active = False
                self._shutdown_waiting.notify_all()
        return completed

    def _drive_shutdown(self, deadline: float) -> bool:
        # The submission lock is not held here. Accepted tasks can finish,
        # and a new submit can observe STOPPING and be rejected.
        if not _wait_until_idle(self._queue, max(0.0, _remaining(deadline))):
            return False
        # task_done() only means the queue was updated. A worker error is not
        # a clean shutdown, even when the failed item was already accounted for.
        if self._worker.error is not None:
            return False
        if _remaining(deadline) <= 0:
            return False
        self._worker.signal_stop()
        self._worker.join(timeout=max(0.0, _remaining(deadline)))
        return not self._worker.is_running()

    def completed_task_ids(self) -> tuple[str, ...]:
        return self._worker.completed_task_ids()

    def worker_is_running(self) -> bool:
        return self._worker.is_running()

    @property
    def error(self) -> BaseException | None:
        return self._worker.error

    def _is_accepting(self) -> bool:
        return self._state is ApplicationState.ACCEPTING
