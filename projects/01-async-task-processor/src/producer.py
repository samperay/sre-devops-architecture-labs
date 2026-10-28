import logging
import threading
import uuid
from queue import Queue

from task import Task

LOGGER_NAME = "async_task_processor"
SUBMITTED = "SUBMITTED"
STARTED = "STARTED"
COMPLETED = "COMPLETED"

logger = logging.getLogger(LOGGER_NAME)


def log_lifecycle(task_id: str, event: str) -> None:
    logger.info("Task %s: %s", task_id, event)


def _handoff_lock(task_queue: Queue) -> threading.Lock:
    with task_queue.mutex:
        lock = getattr(task_queue, "handoff_lock", None)
        if lock is None:
            lock = threading.Lock()
            task_queue.handoff_lock = lock
        return lock


class Producer:
    def __init__(self, task_queue: Queue | None = None) -> None:
        self._queue = Queue() if task_queue is None else task_queue
        _handoff_lock(self._queue)

    @property
    def queue(self) -> Queue:
        return self._queue

    def submit(self, payload: str) -> str:
        task = Task(task_id=str(uuid.uuid4()), payload=payload)
        # Keep SUBMITTED before STARTED: the worker logs STARTED under this same lock.
        with _handoff_lock(self._queue):
            self._queue.put(task)
            log_lifecycle(task.task_id, SUBMITTED)
        return task.task_id

    def queued_tasks(self) -> tuple[Task, ...]:
        with self._queue.mutex:
            return tuple(self._queue.queue)
