from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    task_id: str
    payload: str
