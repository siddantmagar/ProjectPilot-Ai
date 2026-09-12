from collections.abc import Iterator
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.database.repositories import TeamRepository
from app.graph.nodes import assignment_node
from app.integrations.jira.client import JiraClientError
from app.models.assignment import AssignmentOutput, TaskAssignment
from app.models.task import PlannerOutput, Task
from app.models.team import TeamMember


@pytest.fixture
def database_session() -> Iterator[Session]:
    """Provide an isolated in-memory SQLite session for each node test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def planner_state() -> dict:
    """Create the minimal state consumed by assignment_node."""
    planner_output = PlannerOutput(
        epics=["Verification"],
        tasks=[
            Task(
                title="Build API",
                description="Create API endpoints.",
                priority="high",
                estimated_days=3,
                epic="Verification",
            )
        ],
    )
    return {
        "planner_output": planner_output,
        "jira_issue_keys": {"Build API": "AIPM-100"},
    }


def assignment_output(member_name: str) -> AssignmentOutput:
    """Create a fixed assignment response for one Planner task."""
    return AssignmentOutput(
        assignments=[
            TaskAssignment(
                task_title="Build API",
                recommended_assignee=member_name,
                reason="Matches the task skills.",
            )
        ]
    )


def patch_assignment_dependencies(
    database_session: Session,
    mocked_assignment: AssignmentOutput,
    mocked_assign_issue: MagicMock,
    team: list[TeamMember] | None = None,
):
    """Patch the node's local dependencies while keeping repository behavior real."""
    session_factory = MagicMock(return_value=database_session)
    patches = [
        patch("app.database.connection.SessionLocal", session_factory),
        patch(
            "app.agents.assignment.run_assignment_agent",
            return_value=mocked_assignment,
        ),
        patch("app.integrations.jira.client.assign_issue", mocked_assign_issue),
        patch.dict("os.environ", {"JIRA_PROJECT_KEY": "AIPM"}),
    ]
    if team is not None:
        repository = MagicMock()
        repository.list_all.return_value = team
        patches.append(
            patch("app.database.repositories.TeamRepository", return_value=repository)
        )
    return patches


def test_assigns_using_real_team_and_calls_assign_issue(
    database_session: Session,
) -> None:
    """Protect against assignment_node using transient state instead of persisted team data."""
    repository = TeamRepository(database_session)
    repository.add(
        name="Rahul",
        jira_account_id="jira-rahul",
        weekly_capacity_hours=40,
        skills={"python": "high"},
    )
    mocked_assign_issue = MagicMock()
    dependencies = patch_assignment_dependencies(
        database_session,
        assignment_output("Rahul"),
        mocked_assign_issue,
    )
    with ExitStack() as stack:
        for dependency in dependencies:
            stack.enter_context(dependency)
        result = assignment_node(planner_state())

    assert result["assignment_output"].assignments[0].task_title == "Build API"
    mocked_assign_issue.assert_called_once_with("AIPM-100", "jira-rahul")


def test_skips_assignment_when_team_member_has_no_jira_account_id(
    database_session: Session,
) -> None:
    """Protect against attempting Jira assignment without a real account ID."""
    team = [
        TeamMember(
            name="Rahul",
            skills={"python": "high"},
            jira_account_id=None,
            weekly_capacity_hours=40,
        )
    ]
    mocked_assign_issue = MagicMock()
    dependencies = patch_assignment_dependencies(
        database_session,
        assignment_output("Rahul"),
        mocked_assign_issue,
        team=team,
    )
    with ExitStack() as stack:
        for dependency in dependencies:
            stack.enter_context(dependency)
        result = assignment_node(planner_state())

    assert result["assignment_output"].assignments[0].recommended_assignee == "Rahul"
    mocked_assign_issue.assert_not_called()


def test_skips_assignment_when_no_jira_issue_key_exists(
    database_session: Session,
) -> None:
    """Protect against assigning Jira issues when task links are not available yet."""
    repository = TeamRepository(database_session)
    repository.add(
        name="Rahul",
        jira_account_id="jira-rahul",
        weekly_capacity_hours=40,
        skills={"python": "high"},
    )
    mocked_assign_issue = MagicMock()
    dependencies = patch_assignment_dependencies(
        database_session,
        assignment_output("Rahul"),
        mocked_assign_issue,
    )
    state = planner_state()
    state["jira_issue_keys"] = {}
    with ExitStack() as stack:
        for dependency in dependencies:
            stack.enter_context(dependency)
        result = assignment_node(state)

    assert result["assignment_output"].assignments[0].task_title == "Build API"
    mocked_assign_issue.assert_not_called()


def test_raises_when_no_team_members_exist(database_session: Session) -> None:
    """Protect against silently running assignments without persisted team members."""
    mocked_assign_issue = MagicMock()
    dependencies = patch_assignment_dependencies(
        database_session,
        assignment_output("Rahul"),
        mocked_assign_issue,
        team=[],
    )
    with ExitStack() as stack:
        for dependency in dependencies:
            stack.enter_context(dependency)
        with pytest.raises(RuntimeError, match="team members"):
            assignment_node(planner_state())


def test_raises_on_real_jira_assignment_failure(database_session: Session) -> None:
    """Protect against swallowing Jira assignment errors without task context."""
    repository = TeamRepository(database_session)
    repository.add(
        name="Rahul",
        jira_account_id="jira-rahul",
        weekly_capacity_hours=40,
        skills={"python": "high"},
    )
    mocked_assign_issue = MagicMock(
        side_effect=JiraClientError("Jira rejected assignment", status_code=400)
    )
    dependencies = patch_assignment_dependencies(
        database_session,
        assignment_output("Rahul"),
        mocked_assign_issue,
    )
    with ExitStack() as stack:
        for dependency in dependencies:
            stack.enter_context(dependency)
        with pytest.raises(RuntimeError, match=r"AIPM-100.*Rahul"):
            assignment_node(planner_state())
