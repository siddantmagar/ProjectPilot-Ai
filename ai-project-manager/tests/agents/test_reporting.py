"""Tests for reporting synthesis, grounding, and numeric passthrough behavior."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.reporting import ReportValidationError, run_reporting_agent
from app.models.assignment import AssignmentOutput, TaskAssignment
from app.models.progress import ProgressOutput
from app.models.report import ReportOutput
from app.models.risk import RiskFlag, RiskOutput
from app.models.task import PlannerOutput, Task


def sample_inputs(
    with_risk: bool = True,
) -> tuple[PlannerOutput, AssignmentOutput, ProgressOutput, RiskOutput]:
    """Create the shared three-task reporting inputs."""
    tasks = [
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
    planner_output = PlannerOutput(
        epics=["Backend", "Quality", "Release"],
        tasks=tasks,
    )
    assignment_output = AssignmentOutput(
        assignments=[
            TaskAssignment(
                task_title=task.title,
                recommended_assignee="Alex",
                reason="Matches the task area.",
            )
            for task in tasks
        ]
    )
    progress_output = ProgressOutput(
        total_tasks=3,
        completed_tasks=1,
        in_progress_tasks=1,
        todo_tasks=0,
        blocked_tasks=1,
        completion_percent=33.3,
        overdue_task_titles=[],
        blocked_task_titles=["Deploy app"],
    )
    risks = [
        RiskFlag(
            task_title="Deploy app",
            risk_level="high",
            reason="The deployment task is blocked.",
            recommendation="Escalate the deployment blocker.",
        )
    ] if with_risk else []
    return planner_output, assignment_output, progress_output, RiskOutput(risks=risks)


def mocked_response(summary: str, top_risks: list[str]) -> SimpleNamespace:
    """Create an Ollama-shaped response containing reporting narrative fields."""
    payload = {
        "summary": summary,
        "top_risks": top_risks,
        "recommendations": ["Address the highest-priority work next."],
    }
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


@pytest.mark.integration
def test_reporting_preserves_exact_progress_numbers() -> None:
    """Protect against the report changing deterministic progress numbers during synthesis."""
    planner, assignments, progress, risks = sample_inputs()

    result = run_reporting_agent(planner, assignments, progress, risks)

    assert isinstance(result, ReportOutput)
    assert result.completed_count == 1
    assert result.total_count == 3
    assert result.completion_percent == 33.3


@pytest.mark.integration
def test_reporting_empty_risks_stays_empty() -> None:
    """Protect against the reporting model inventing top risks for a healthy project."""
    planner, assignments, progress, risks = sample_inputs(with_risk=False)

    result = run_reporting_agent(planner, assignments, progress, risks)

    assert result.top_risks == []


def test_reporting_numbers_immune_to_contradictory_narrative() -> None:
    """Protect the core guarantee that numeric fields are structural passthrough, never LLM-generated."""
    planner, assignments, progress, risks = sample_inputs()
    response = mocked_response(
        "The project is 90% complete, with 8 of 8 tasks done.",
        ["Deploy app: blocked."],
    )

    with patch("app.agents.reporting.chat", return_value=response):
        result = run_reporting_agent(planner, assignments, progress, risks)

    assert "90%" in result.summary
    assert result.completed_count == 1
    assert result.total_count == 3
    assert result.completion_percent == 33.3


def test_reporting_raises_on_fabricated_risk() -> None:
    """Protect against accepting a top risk whose task is absent from the supplied risks."""
    planner, assignments, progress, risks = sample_inputs()
    response = mocked_response("The project status is current.", ["Invented task: blocked."])

    with patch("app.agents.reporting.chat", return_value=response):
        with pytest.raises(ReportValidationError, match="Invented task"):
            run_reporting_agent(planner, assignments, progress, risks)


def test_reporting_raises_on_nonempty_risks_when_none_supplied() -> None:
    """Protect against fabricating top risks when the supplied risk output is empty."""
    planner, assignments, progress, risks = sample_inputs(with_risk=False)
    response = mocked_response("The project status is current.", ["Invented risk: blocked."])

    with patch("app.agents.reporting.chat", return_value=response):
        with pytest.raises(ReportValidationError, match="top_risks must be empty"):
            run_reporting_agent(planner, assignments, progress, risks)