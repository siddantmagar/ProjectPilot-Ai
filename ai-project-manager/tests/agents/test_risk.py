"""Tests for deterministic risk qualification and grounded risk output."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.risk import RiskValidationError, run_risk_agent
from app.models.progress import TaskStatusEntry
from app.models.risk import RiskOutput
from app.models.task import Task


def healthy_tasks() -> list[Task]:
    """Create tasks with no overdue, blocked, or high-priority todo status."""
    return [
        Task(
            title="Build API",
            description="Create API endpoints",
            priority="high",
            estimated_days=5,
            epic="Backend",
        ),
        Task(
            title="Write tests",
            description="Add automated tests",
            priority="medium",
            estimated_days=3,
            epic="Quality",
        ),
        Task(
            title="Deploy app",
            description="Deploy the application",
            priority="low",
            estimated_days=2,
            epic="Release",
        ),
    ]


def healthy_statuses() -> list[TaskStatusEntry]:
    """Create in-progress and done statuses with no overdue flags."""
    return [
        TaskStatusEntry(task_title="Build API", status="in_progress"),
        TaskStatusEntry(task_title="Write tests", status="done"),
        TaskStatusEntry(task_title="Deploy app", status="in_progress"),
    ]


def risk_tasks_and_statuses() -> tuple[list[Task], list[TaskStatusEntry]]:
    """Create one qualifying risk and two non-qualifying tasks."""
    tasks = [
        Task(
            title="Resolve payment outage",
            description="Restore payment processing",
            priority="high",
            estimated_days=5,
            epic="Backend",
        ),
        Task(
            title="Write tests",
            description="Add automated tests",
            priority="medium",
            estimated_days=3,
            epic="Quality",
        ),
        Task(
            title="Deploy app",
            description="Deploy the application",
            priority="low",
            estimated_days=2,
            epic="Release",
        ),
    ]
    statuses = [
        TaskStatusEntry(
            task_title="Resolve payment outage",
            status="blocked",
            is_overdue=True,
        ),
        TaskStatusEntry(task_title="Write tests", status="in_progress"),
        TaskStatusEntry(task_title="Deploy app", status="done"),
    ]
    return tasks, statuses


def mocked_response(task_title: str) -> SimpleNamespace:
    """Create an Ollama-shaped response containing one high-severity risk."""
    payload = {
        "risks": [
            {
                "task_title": task_title,
                "risk_level": "high",
                "reason": "The task is blocked and overdue.",
                "recommendation": "Escalate the blocker immediately.",
            }
        ]
    }
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def test_risk_healthy_project_returns_empty() -> None:
    """Protect against fabricating risks for a project with no qualifying statuses."""
    result = run_risk_agent(healthy_tasks(), healthy_statuses())

    assert isinstance(result, RiskOutput)
    assert result.risks == []


@pytest.mark.integration
def test_risk_identifies_qualifying_task() -> None:
    """Protect against missing a blocked, overdue, high-priority task."""
    tasks, statuses = risk_tasks_and_statuses()

    result = run_risk_agent(tasks, statuses)
    matching_risks = [
        risk for risk in result.risks if risk.task_title == "Resolve payment outage"
    ]

    assert matching_risks
    assert matching_risks[0].risk_level == "high"


@pytest.mark.integration
def test_risk_ignores_non_qualifying_tasks() -> None:
    """Protect against reporting normal tasks merely because another task is risky."""
    tasks, statuses = risk_tasks_and_statuses()

    result = run_risk_agent(tasks, statuses)
    risk_titles = {risk.task_title for risk in result.risks}

    assert "Write tests" not in risk_titles
    assert "Deploy app" not in risk_titles


def test_risk_raises_on_hallucinated_task() -> None:
    """Protect against accepting a risk title absent from the qualifying task set."""
    tasks, statuses = risk_tasks_and_statuses()

    with patch(
        "app.agents.risk.chat",
        return_value=mocked_response("Invented task"),
    ):
        with pytest.raises(RiskValidationError, match="Invented task"):
            run_risk_agent(tasks, statuses)


def test_risk_no_llm_call_when_no_qualifying_tasks() -> None:
    """Verify the deterministic pre-filter skips the LLM, not just that it returns no risks."""
    with patch("app.agents.risk.chat") as mocked_chat:
        result = run_risk_agent(healthy_tasks(), healthy_statuses())

    assert result.risks == []
    mocked_chat.assert_not_called()
