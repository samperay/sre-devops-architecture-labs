from __future__ import annotations

import threading
import time
from queue import Queue

from producer import COMPLETED, STARTED, log_lifecycle
from task import Task


class Worker:
    def __init__(
        self,
        task_queue: Queue,
        delay: float,
        lock: threading.Lock | None = None,
    ) -> None:
        if delay < 0:
            raise ValueError("delay must be non-negative")
        self._queue = task_queue
        self._delay = delay
        self._lock = lock if lock is not None else threading.Lock()
        self._sentinel = object()
        self._sentinel_lock = threading.Lock()
        self._signaled = False
        self._thread = threading.Thread(
            target=self._run,
            name="task-worker",
            daemon=True,
        )
        self._completed: list[str] = []
        self._completed_lock = threading.Lock()
        self.error: BaseException | None = None

    def start(self) -> None:
        self._thread.start()

    def signal_stop(self) -> None:
        with self._sentinel_lock:
            if self._signaled or not self._thread.is_alive():
                return
            self._signaled = True
            self._queue.put(self._sentinel)

    def join(self, timeout: float | None = None) -> None:
        if self._thread.ident is not None:
            self._thread.join(timeout)

    def stop(self) -> None:
        self.signal_stop()
        self.join()

    def is_running(self) -> bool:
        return self._thread.is_alive()

    def completed_task_ids(self) -> tuple[str, ...]:
        with self._completed_lock:
            return tuple(self._completed)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._sentinel:
                    return
                self._handle(item)
            finally:
                # One accounting call for every retrieved item, including the sentinel.
                self._queue.task_done()

    def _handle(self, task: Task) -> None:
        try:
            with self._lock:
                log_lifecycle(task.task_id, STARTED)
            time.sleep(self._delay)
            log_lifecycle(task.task_id, COMPLETED)
            with self._completed_lock:
                self._completed.append(task.task_id)
        except Exception as exc:
            self.error = exc
            raise
