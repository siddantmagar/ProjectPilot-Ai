from unittest.mock import MagicMock, patch

import pytest

from app.graph.workflow import build_workflow
from app.models.assignment import AssignmentOutput, TaskAssignment
from app.models.progress import ProgressOutput, TaskStatusEntry
from app.models.report import ReportOutput
from app.models.risk import RiskOutput
from app.models.task import PlannerOutput, Task
from app.models.team import SAMPLE_TEAM


def workflow_inputs() -> dict:
    """Create the shared graph invocation inputs."""
    return {
        "goal": "Build a project tracking API",
        "deadline": "2026-10-01",
        "team_size": len(SAMPLE_TEAM),
        "team": SAMPLE_TEAM,
    }


def fixture_outputs() -> tuple[
    PlannerOutput,
    AssignmentOutput,
    ProgressOutput,
    RiskOutput,
    ReportOutput,
]:
    """Create fixed valid outputs for the mocked agent nodes."""
    planner_output = PlannerOutput(
        epics=["Backend"],
        tasks=[
            Task(
                title="Build API",
                description="Create API endpoints",
                priority="high",
                estimated_days=5,
                epic="Backend",
            )
        ],
    )
    assignment_output = AssignmentOutput(
        assignments=[
            TaskAssignment(
                task_title="Build API",
                recommended_assignee="Rahul",
                reason="Strong Python skill match.",
            )
        ]
    )
    progress_output = ProgressOutput(
        total_tasks=1,
        completed_tasks=0,
        in_progress_tasks=0,
        todo_tasks=1,
        blocked_tasks=0,
        completion_percent=0.0,
        overdue_task_titles=[],
        blocked_task_titles=[],
    )
    risk_output = RiskOutput(risks=[])
    report_output = ReportOutput(
        summary="The project is ready to begin.",
        completed_count=0,
        total_count=1,
        completion_percent=0.0,
        top_risks=[],
        recommendations=["Start the API work."],
    )
    return (
        planner_output,
        assignment_output,
        progress_output,
        risk_output,
        report_output,
    )


@patch("app.agents.reporting.run_reporting_agent")
@patch("app.agents.risk.run_risk_agent")
@patch("app.agents.progress.run_progress_agent")
@patch("app.agents.assignment.run_assignment_agent")
@patch("app.agents.planner.run_planner_agent")
def test_workflow_structure_with_mocked_agents(
    mock_planner,
    mock_assignment,
    mock_progress,
    mock_risk,
    mock_reporting,
) -> None:
    """Protect against state-flow or node-wiring regressions without making LLM calls."""
    (
        planner_output,
        assignment_output,
        progress_output,
        risk_output,
        report_output,
    ) = fixture_outputs()
    mock_planner.return_value = planner_output
    mock_assignment.return_value = assignment_output
    mock_progress.return_value = progress_output
    mock_risk.return_value = risk_output
    mock_reporting.return_value = report_output

    mock_session = MagicMock()
    mock_team_repository = MagicMock()
    mock_team_repository.list_all.return_value = SAMPLE_TEAM
    with patch(
        "app.graph.workflow.jira_creation_node",
        return_value={
            "jira_issue_keys": {"Build API": "AIPM-1"},
            "jira_issue_ids": {"Build API": "1"},
        },
    ), patch(
        "app.graph.workflow.status_sync_node",
        return_value={
            "statuses": [
                TaskStatusEntry(
                    task_title="Build API",
                    status="todo",
                    jira_status_name="To Do",
                    is_overdue=False,
                )
            ]
        },
    ), patch(
        "app.database.connection.SessionLocal",
        return_value=mock_session,
    ), patch(
        "app.database.repositories.TeamRepository",
        return_value=mock_team_repository,
    ):
        final_state = build_workflow().invoke(workflow_inputs())

    assert final_state["planner_output"] is planner_output
    assert final_state["jira_issue_keys"] == {"Build API": "AIPM-1"}
    assert final_state["jira_issue_ids"] == {"Build API": "1"}
    assert final_state["statuses"] == [
        TaskStatusEntry(
            task_title="Build API",
            status="todo",
            jira_status_name="To Do",
            is_overdue=False,
        )
    ]
    assert final_state["assignment_output"] is assignment_output
    assert final_state["progress_output"] is progress_output
    assert final_state["risk_output"] is risk_output
    assert final_state["report_output"] is report_output


@pytest.mark.integration
def test_workflow_end_to_end_real_agents() -> None:
    """Protect against the full linear chain producing an incoherent final report."""
    final_state = build_workflow().invoke(workflow_inputs())

    report_output = final_state["report_output"]
    planner_output = final_state["planner_output"]
    assert isinstance(report_output, ReportOutput)
    assert report_output.total_count == len(planner_output.tasks)
