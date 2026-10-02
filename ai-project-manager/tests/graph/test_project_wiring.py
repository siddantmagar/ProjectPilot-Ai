from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.database.models import TaskJiraLinkORM
from app.database.repositories import (
    AuditLogRepository,
    ProjectRepository,
    TaskJiraLinkRepository,
)
from app.graph.nodes import (
    audit_log_node,
    create_project_node,
    jira_creation_node,
)
from app.models.task import PlannerOutput, Task


@pytest.fixture
def database_session() -> Iterator[Session]:
    """Provide an isolated in-memory SQLite session for each wiring test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def patch_session(database_session: Session):
    """Patch the node-local SessionLocal import to use the test session."""
    return patch(
        "app.database.connection.SessionLocal",
        MagicMock(return_value=database_session),
    )


def planner_output() -> PlannerOutput:
    """Create one small planner output for Jira link tests."""
    return PlannerOutput(
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


def test_create_project_node_persists_and_returns_id(
    database_session: Session,
) -> None:
    """Protect against planning runs proceeding without a persisted project row."""
    state = {
        "goal": "Build a project tracking API",
        "deadline": "2 weeks",
        "team_size": 3,
    }

    with patch_session(database_session), patch.dict(
        "os.environ", {"JIRA_PROJECT_KEY": "AIPM"}
    ):
        result = create_project_node(state)

    project_id = result["project_id"]
    project = ProjectRepository(database_session).get_by_id(project_id)
    assert project["goal"] == state["goal"]
    assert project["deadline"] == state["deadline"]
    assert project["team_size"] == state["team_size"]


def test_jira_creation_node_passes_project_id_to_links(
    database_session: Session,
) -> None:
    """Protect against Jira links losing the project run that created them."""
    state = {
        "project_id": 42,
        "planner_output": planner_output(),
    }
    mock_create_issue = MagicMock(return_value=SimpleNamespace(key="AIPM-100", id="100"))

    with patch_session(database_session), patch(
        "app.integrations.jira.client.create_issue",
        mock_create_issue,
    ), patch.dict("os.environ", {"JIRA_PROJECT_KEY": "AIPM"}):
        jira_creation_node(state)

    links = TaskJiraLinkRepository(database_session).list_for_project(42)
    assert len(links) == 1
    assert links[0]["project_id"] == 42
    assert links[0]["jira_issue_key"] == "AIPM-100"


def test_audit_log_node_passes_project_id(database_session: Session) -> None:
    """Protect against human approval audit entries becoming detached from runs."""
    state = {
        "project_id": 42,
        "_approval_decision": {"action": "approve"},
        "_approval_payload": {
            "epics": ["Verification"],
            "tasks": [{"title": "Build API"}],
        },
    }

    with patch_session(database_session), patch.dict(
        "os.environ", {"JIRA_PROJECT_KEY": "AIPM"}
    ):
        audit_log_node(state)

    entries = AuditLogRepository(database_session).list_for_project_id(42)
    assert len(entries) == 1
    assert entries[0]["human_decision"] == "approve"


def test_jira_creation_node_handles_missing_project_id_gracefully(
    database_session: Session,
) -> None:
    """Protect the nullable project_id design from becoming a hard requirement."""
    state = {"planner_output": planner_output()}
    mock_create_issue = MagicMock(return_value=SimpleNamespace(key="AIPM-101", id="101"))

    with patch_session(database_session), patch(
        "app.integrations.jira.client.create_issue",
        mock_create_issue,
    ), patch.dict("os.environ", {"JIRA_PROJECT_KEY": "AIPM"}):
        result = jira_creation_node(state)

    assert result["jira_issue_keys"]["Build API"] == "AIPM-101"
    links = TaskJiraLinkRepository(database_session).list_for_project(999)
    assert links == []
    all_links = database_session.query(TaskJiraLinkORM).all()
    assert len(all_links) == 1
    assert all_links[0].project_id is None
