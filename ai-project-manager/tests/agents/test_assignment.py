"""Tests for the assignment agent's grounding and coverage behavior."""

import json
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.assignment import AssignmentValidationError, run_assignment_agent
from app.models.assignment import AssignmentOutput
from app.models.task import Task
from app.models.team import SAMPLE_TEAM, TeamMember


def sample_tasks() -> list[Task]:
    """Create tasks covering strong Python, FastAPI, and no-match scenarios."""
    return [
        Task(
            title="Build data processing service",
            description="Implement Python data processing and validation logic.",
            priority="high",
            estimated_days=8,
            epic="Backend",
        ),
        Task(
            title="Create FastAPI endpoints",
            description="Expose the application through FastAPI REST endpoints.",
            priority="high",
            estimated_days=5,
            epic="Backend",
        ),
        Task(
            title="Prepare launch announcement",
            description="Write a product announcement for the launch.",
            priority="medium",
            estimated_days=2,
            epic="Launch",
        ),
    ]


def mocked_response(tasks: list[Task], assignee: str = "Rahul") -> SimpleNamespace:
    """Create an Ollama-shaped response assigning every supplied task."""
    payload = {
        "assignments": [
            {
                "task_title": task.title,
                "recommended_assignee": assignee,
                "reason": "Selected based on the available skill match and workload.",
            }
            for task in tasks
        ]
    }
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


@pytest.mark.integration
def test_assignment_covers_all_tasks() -> None:
    """Protect against valid-looking output that omits or duplicates input tasks."""
    tasks = sample_tasks()
    result = run_assignment_agent(tasks, SAMPLE_TEAM)

    assert isinstance(result, AssignmentOutput)
    assert Counter(item.task_title for item in result.assignments) == Counter(
        task.title for task in tasks
    )


@pytest.mark.integration
def test_assignment_only_uses_real_team_members() -> None:
    """Protect against the model inventing an assignee outside the provided roster."""
    tasks = sample_tasks()
    result = run_assignment_agent(tasks, SAMPLE_TEAM)
    team_names = {member.name for member in SAMPLE_TEAM}

    assert all(item.recommended_assignee in team_names for item in result.assignments)


def test_assignment_raises_on_hallucinated_assignee() -> None:
    """Protect against silently accepting a person who is absent from the team roster."""
    tasks = sample_tasks()

    with patch(
        "app.agents.assignment.chat",
        return_value=mocked_response(tasks, assignee="David"),
    ):
        with pytest.raises(AssignmentValidationError, match="David"):
            run_assignment_agent(tasks, SAMPLE_TEAM)


def test_assignment_raises_on_incomplete_coverage() -> None:
    """Protect against accepting output that leaves one or more input tasks unassigned."""
    tasks = sample_tasks()
    incomplete_response = mocked_response(tasks[:2])

    with patch("app.agents.assignment.chat", return_value=incomplete_response):
        with pytest.raises(
            AssignmentValidationError, match="Prepare launch announcement"
        ):
            run_assignment_agent(tasks, SAMPLE_TEAM)


@pytest.mark.integration
def test_assignment_handles_single_person_team() -> None:
    """Protect against assignment failures when there is no choice among team members."""
    tasks = sample_tasks()
    single_person_team = [
        TeamMember(
            name="Rahul",
            skills={"python": "high", "fastapi": "high", "react": "low"},
            workload_percent=60,
        )
    ]

    result = run_assignment_agent(tasks, single_person_team)

    assert len(result.assignments) == len(tasks)
    assert {item.recommended_assignee for item in result.assignments} == {"Rahul"}
    assert Counter(item.task_title for item in result.assignments) == Counter(
        task.title for task in tasks
    )
