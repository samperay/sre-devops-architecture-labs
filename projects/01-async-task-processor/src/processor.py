from __future__ import annotations

import enum
import threading
from queue import Queue

from producer import Producer
from worker import Worker


class ApplicationState(enum.Enum):
    ACCEPTING = "ACCEPTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


def _wait_until_idle(task_queue: Queue, timeout: float) -> bool:
    finished = threading.Event()

    def _join() -> None:
        task_queue.join()
        finished.set()

    threading.Thread(target=_join, name="queue-join", daemon=True).start()
    return finished.wait(timeout)


class Processor:
    def __init__(self, delay: float) -> None:
        self._queue: Queue = Queue()
        self._lock = threading.Lock()
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
        with self._lock:
            if self._state is ApplicationState.STOPPED:
                return True
            if self._state is ApplicationState.ACCEPTING:
                self._state = ApplicationState.STOPPING
        # Release the lock before draining so a new submit can be rejected
        # and the worker can finish tasks it already accepted.
        if not _wait_until_idle(self._queue, timeout):
            return False
        # task_done() only means the queue was updated. A worker error is not
        # a clean shutdown, even when the failed item was already accounted for.
        if self._worker.error is not None:
            return False
        self._worker.signal_stop()
        self._worker.join(timeout=timeout)
        if self._worker.is_running():
            return False
        with self._lock:
            self._state = ApplicationState.STOPPED
        return True

    def completed_task_ids(self) -> tuple[str, ...]:
        return self._worker.completed_task_ids()

    def worker_is_running(self) -> bool:
        return self._worker.is_running()

    @property
    def error(self) -> BaseException | None:
        return self._worker.error

    def _is_accepting(self) -> bool:
        return self._state is ApplicationState.ACCEPTING
