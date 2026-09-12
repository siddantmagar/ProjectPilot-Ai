from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.database.repositories import TaskJiraLinkRepository
from app.graph.nodes import jira_creation_node
from app.integrations.jira.client import JiraClientError
from app.models.task import PlannerOutput, Task


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


def planner_output() -> PlannerOutput:
    """Create two stable Planner tasks for the node tests."""
    return PlannerOutput(
        epics=["Verification"],
        tasks=[
            Task(
                title="Build API",
                description="Create API endpoints.",
                priority="high",
                estimated_days=3,
                epic="Verification",
            ),
            Task(
                title="Write tests",
                description="Add automated tests.",
                priority="medium",
                estimated_days=2,
                epic="Verification",
            ),
        ],
    )


def node_state() -> dict:
    """Build the minimal state consumed by jira_creation_node."""
    return {"planner_output": planner_output()}


def test_creates_new_issues_when_none_exist(database_session: Session) -> None:
    """Protect against missing Jira issues or skipped creation for new tasks."""
    responses = iter(
        [SimpleNamespace(key="AIPM-100"), SimpleNamespace(key="AIPM-101")]
    )
    mock_create_issue = MagicMock(side_effect=lambda **kwargs: next(responses))
    session_factory = MagicMock(return_value=database_session)

    with patch("app.database.connection.SessionLocal", session_factory), patch(
        "app.integrations.jira.client.create_issue", mock_create_issue
    ), patch.dict("os.environ", {"JIRA_PROJECT_KEY": "AIPM"}):
        result = jira_creation_node(node_state())

    assert result["jira_issue_keys"] == {
        "Build API": "AIPM-100",
        "Write tests": "AIPM-101",
    }
    assert mock_create_issue.call_count == 2


def test_reuses_existing_link_without_calling_create_issue(
    database_session: Session,
) -> None:
    """Protect against duplicate Jira issue creation when a task link already exists."""
    links = TaskJiraLinkRepository(database_session)
    links.record_link("AIPM", "Build API", "AIPM-42")
    mock_create_issue = MagicMock(return_value=SimpleNamespace(key="AIPM-101"))
    session_factory = MagicMock(return_value=database_session)

    with patch("app.database.connection.SessionLocal", session_factory), patch(
        "app.integrations.jira.client.create_issue", mock_create_issue
    ), patch.dict("os.environ", {"JIRA_PROJECT_KEY": "AIPM"}):
        result = jira_creation_node(node_state())

    assert result["jira_issue_keys"]["Build API"] == "AIPM-42"
    assert result["jira_issue_keys"]["Write tests"] == "AIPM-101"
    mock_create_issue.assert_called_once()
    assert mock_create_issue.call_args.kwargs["summary"] == "Write tests"


def test_partial_failure_reports_progress(database_session: Session) -> None:
    """Protect against losing recorded links when a later Jira creation fails."""
    call_count = 0

    def create_issue_side_effect(**kwargs: object) -> SimpleNamespace:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise JiraClientError("Jira server problem", status_code=500)
        return SimpleNamespace(key="AIPM-100")

    mock_create_issue = MagicMock(side_effect=create_issue_side_effect)
    session_factory = MagicMock(return_value=database_session)

    with patch("app.database.connection.SessionLocal", session_factory), patch(
        "app.integrations.jira.client.create_issue", mock_create_issue
    ), patch.dict("os.environ", {"JIRA_PROJECT_KEY": "AIPM"}):
        with pytest.raises(RuntimeError, match=r"1 of 2"):
            jira_creation_node(node_state())

    assert (
        TaskJiraLinkRepository(database_session).get_issue_key("AIPM", "Build API")
        == "AIPM-100"
    )
