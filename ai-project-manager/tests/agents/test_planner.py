"""Tests for the planner agent's structured output and failure handling."""

from unittest.mock import patch

import pytest

from app.agents.planner import PlannerValidationError, run_planner_agent
from app.models.task import PlannerOutput


@pytest.mark.integration
def test_planner_returns_valid_output_for_known_goal() -> None:
    """Protect against the planner returning the wrong schema or task count."""
    result = run_planner_agent("Build a login page", "2 weeks", 2)

    assert isinstance(result, PlannerOutput)
    assert 3 <= len(result.tasks) <= 5
    assert len(result.epics) >= 1


@pytest.mark.integration
def test_planner_tasks_have_valid_priority() -> None:
    """Protect against the model emitting priorities outside the supported vocabulary."""
    result = run_planner_agent("Build a login page", "2 weeks", 2)

    assert all(task.priority in {"low", "medium", "high"} for task in result.tasks)


@pytest.mark.integration
def test_planner_tasks_have_valid_estimated_days() -> None:
    """Protect against task estimates falling outside the model's one-to-sixty-day range."""
    result = run_planner_agent("Build a login page", "2 weeks", 2)

    assert all(1 <= task.estimated_days <= 60 for task in result.tasks)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("goal", "keywords"),
    [
        (
            "Build a REST API for a todo app",
            ("api", "endpoint"),
        ),
        (
            "Set up a CI/CD pipeline for a web app",
            (
                "ci",
                "cd",
                "pipeline",
                "deploy",
                "deployment",
                "docker",
                "workflow",
                "automation",
                "build",
                "actions",
                "container",
            ),
        ),
        (
            "Create a user authentication system with JWT",
            ("jwt", "auth", "token"),
        ),
    ],
)
def test_planner_generalizes_across_goals(
    goal: str, keywords: tuple[str, ...]
) -> None:
    """Protect against regressions where every goal receives generic unrelated tasks."""
    result = run_planner_agent(goal, "4 weeks", 4)

    assert isinstance(result, PlannerOutput)
    assert 3 <= len(result.tasks) <= 5
    assert len(result.epics) >= 1

    task_text = " ".join(
        f"{task.title} {task.description}" for task in result.tasks
    ).lower()
    assert any(keyword in task_text for keyword in keywords)


def test_planner_raises_on_unrecoverable_invalid_output() -> None:
    """Protect against swallowed validation failures when the model stays invalid after retries."""
    invalid_response = {
        "message": type("Message", (), {"content": '{"epics": ["Login"], "tasks": [{"title": "Build login", "description": "Create login flow", "priority": "high", "estimated_days": 999, "epic": "Login"}]}'})()
    }

    with patch("app.agents.planner.chat", return_value=type("Response", (), invalid_response)()):
        with pytest.raises(PlannerValidationError, match="estimated_days"):
            run_planner_agent("Build a login page", "2 weeks", 2)
