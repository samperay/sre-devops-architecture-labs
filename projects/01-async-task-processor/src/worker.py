import threading
import time
from queue import Empty, Queue

from producer import COMPLETED, STARTED, _handoff_lock, log_lifecycle
from task import Task

_POLL_SECONDS = 0.05


class Worker:
    def __init__(self, task_queue: Queue, delay: float) -> None:
        if delay < 0:
            raise ValueError("delay must be non-negative")
        self._queue = task_queue
        self._delay = delay
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="task-worker")
        self._completed: list[str] = []
        self._completed_lock = threading.Lock()
        self.error: BaseException | None = None
        _handoff_lock(self._queue)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join()

    def is_running(self) -> bool:
        return self._thread.is_alive()

    def completed_task_ids(self) -> tuple[str, ...]:
        with self._completed_lock:
            return tuple(self._completed)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                task = self._queue.get(timeout=_POLL_SECONDS)
            except Empty:
                continue
            try:
                self._handle(task)
            finally:
                # Count the retrieved task once, including when processing raises.
                self._queue.task_done()

    def _handle(self, task: Task) -> None:
        try:
            with _handoff_lock(self._queue):
                log_lifecycle(task.task_id, STARTED)
            time.sleep(self._delay)
            log_lifecycle(task.task_id, COMPLETED)
            with self._completed_lock:
                self._completed.append(task.task_id)
        except Exception as exc:
            self.error = exc
            raise
