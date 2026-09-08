"""Tests for the deterministic progress agent."""

import pytest

from app.agents.progress import run_progress_agent
from app.models.progress import TaskStatusEntry
from app.models.task import Task


def sample_tasks() -> list[Task]:
    """Create three tasks reused by the normal progress scenarios."""
    return [
        Task(title="Build API", description="Create API endpoints", priority="high", estimated_days=5, epic="Backend"),
        Task(title="Write tests", description="Add automated tests", priority="medium", estimated_days=3, epic="Quality"),
        Task(title="Deploy app", description="Deploy the application", priority="low", estimated_days=2, epic="Release"),
    ]


def test_progress_normal_mixed_status() -> None:
    """Protect against incorrect status counts or overdue and blocked title lists."""
    tasks = sample_tasks()
    statuses = [
        TaskStatusEntry(task_title="Build API", status="done"),
        TaskStatusEntry(task_title="Write tests", status="in_progress"),
        TaskStatusEntry(task_title="Deploy app", status="blocked", is_overdue=True),
    ]

    result = run_progress_agent(tasks, statuses)

    assert result.total_tasks == 3
    assert result.completed_tasks == 1
    assert result.completion_percent == pytest.approx(33.3)
    assert len(result.blocked_task_titles) == 1
    assert len(result.overdue_task_titles) == 1


def test_progress_all_done() -> None:
    """Protect against completion percentages below 100 when every task is done."""
    tasks = sample_tasks()
    statuses = [TaskStatusEntry(task_title=task.title, status="done") for task in tasks]

    result = run_progress_agent(tasks, statuses)

    assert result.completion_percent == 100.0


def test_progress_all_todo() -> None:
    """Protect against reporting completed work when every task is still todo."""
    tasks = sample_tasks()
    statuses = [TaskStatusEntry(task_title=task.title, status="todo") for task in tasks]

    result = run_progress_agent(tasks, statuses)

    assert result.completion_percent == 0.0
    assert result.completed_tasks == 0


def test_progress_empty_task_list_raises() -> None:
    """Protect against silently reporting zero progress for an empty project."""
    with pytest.raises(ValueError):
        run_progress_agent([], [])


def test_progress_mismatched_titles_raises() -> None:
    """Protect against silently ignoring a task with no matching status entry."""
    tasks = [
        Task(title="A", description="Task A", priority="low", estimated_days=1, epic="E"),
        Task(title="B", description="Task B", priority="low", estimated_days=1, epic="E"),
    ]
    statuses = [TaskStatusEntry(task_title="A", status="todo")]

    with pytest.raises(ValueError, match="B"):
        run_progress_agent(tasks, statuses)


def test_progress_duplicate_status_entry_raises() -> None:
    """Protect against accepting duplicate statuses when title sets appear to match."""
    task = Task(title="A", description="Task A", priority="low", estimated_days=1, epic="E")
    statuses = [
        TaskStatusEntry(task_title="A", status="done"),
        TaskStatusEntry(task_title="A", status="blocked"),
    ]

    with pytest.raises(ValueError, match=r"2|duplicate"):
        run_progress_agent([task], statuses)
