"""Progress snapshot model definitions."""

from typing import Literal

from pydantic import BaseModel


class TaskStatusEntry(BaseModel):
    """The current status of one task, matched to a task by title."""

    task_title: str
    status: Literal["todo", "in_progress", "done", "blocked"]
    is_overdue: bool = False


class ProgressOutput(BaseModel):
    """Deterministic progress snapshot computed from task statuses."""

    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    todo_tasks: int
    blocked_tasks: int
    completion_percent: float
    overdue_task_titles: list[str]
    blocked_task_titles: list[str]
