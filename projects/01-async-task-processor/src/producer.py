from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from queue import Queue

from task import Task

LOGGER_NAME = "async_task_processor"
SUBMITTED = "SUBMITTED"
STARTED = "STARTED"
COMPLETED = "COMPLETED"

logger = logging.getLogger(LOGGER_NAME)


class SubmissionRejected(Exception):
    """Raised when a task is submitted after shutdown has begun."""


def log_lifecycle(task_id: str, event: str) -> None:
    logger.info("Task %s: %s", task_id, event)


class Producer:
    def __init__(
        self,
        task_queue: Queue | None = None,
        lock: threading.Lock | None = None,
        is_accepting: Callable[[], bool] | None = None,
    ) -> None:
        self._queue = Queue() if task_queue is None else task_queue
        self._lock = lock if lock is not None else threading.Lock()
        self._is_accepting = is_accepting

    @property
    def queue(self) -> Queue:
        return self._queue

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def submit(self, payload: str) -> str:
        with self._lock:
            if self._is_accepting is not None and not self._is_accepting():
                raise SubmissionRejected("task submission rejected")
            task = Task(task_id=str(uuid.uuid4()), payload=payload)
            self._queue.put(task)
            log_lifecycle(task.task_id, SUBMITTED)
        return task.task_id

    def queued_tasks(self) -> tuple[Task, ...]:
        with self._queue.mutex:
            return tuple(self._queue.queue)
