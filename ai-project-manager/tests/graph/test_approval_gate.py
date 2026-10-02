from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.database.repositories import AuditLogRepository
from app.graph.nodes import audit_log_node, plan_approval_node
from app.graph.workflow import route_after_audit
from app.models.task import PlannerOutput, Task


@pytest.fixture
def database_session() -> Iterator[Session]:
    """Provide an isolated in-memory SQLite session for each audit test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def planner_state() -> dict:
    """Build a small planner state for approval decisions."""
    return {
        "planner_output": PlannerOutput(
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
    }


def test_plan_approval_node_returns_interrupt_payload() -> None:
    """Protect against approved plans losing their original planner output or decision."""
    state = planner_state()
    original_output = state["planner_output"]

    with patch("langgraph.types.interrupt", return_value={"action": "approve"}):
        result = plan_approval_node(state)

    assert result.get("planner_output", original_output) is original_output
    assert result["_approval_decision"]["action"] == "approve"
    assert result["_approval_payload"]["epics"] == ["Verification"]


def test_plan_approval_node_handles_modify() -> None:
    """Protect against edited approval tasks being ignored before Jira creation."""
    state = planner_state()
    edited_task = {
        "title": "Build GraphQL API",
        "description": "Create GraphQL endpoints.",
        "priority": "medium",
        "estimated_days": 5,
        "epic": "Verification",
    }

    with patch(
        "langgraph.types.interrupt",
        return_value={"action": "modify", "edited_tasks": [edited_task]},
    ):
        result = plan_approval_node(state)

    assert result["planner_output"].tasks[0].title == "Build GraphQL API"
    assert result["planner_output"].tasks[0].description == "Create GraphQL endpoints."
    assert result["_approval_decision"]["action"] == "modify"


def test_plan_approval_node_handles_reject() -> None:
    """Protect the fix for the original exception-based rejection bug."""
    with patch("langgraph.types.interrupt", return_value={"action": "reject"}):
        result = plan_approval_node(planner_state())

    assert result["_approval_decision"]["action"] == "reject"


def audit_state(action: str, final_payload: dict | None = None) -> dict:
    """Build state containing an approval decision and proposed plan payload."""
    return {
        "_approval_decision": {"action": action},
        "_approval_payload": {
            "proposed_plan": {
                "epics": ["Verification"],
                "tasks": [{"title": "Build API"}],
            }
        },
        "_test_final_payload": final_payload,
    }


def test_audit_log_node_records_decision(database_session: Session, monkeypatch) -> None:
    """Protect against approved human decisions failing to enter audit history."""
    session_factory = MagicMock(return_value=database_session)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")

    with patch("app.database.connection.SessionLocal", session_factory):
        result = audit_log_node(audit_state("approve"))

    assert result == {}
    records = AuditLogRepository(database_session).list_for_project("AIPM")
    assert len(records) == 1
    assert records[0]["human_decision"] == "approve"
    assert records[0]["final_payload"] == {
        "epics": ["Verification"],
        "tasks": [{"title": "Build API"}],
    }


def test_audit_log_node_records_rejection_with_null_final_payload(
    database_session: Session,
    monkeypatch,
) -> None:
    """Protect against rejected decisions being logged with a misleading final plan."""
    session_factory = MagicMock(return_value=database_session)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")

    with patch("app.database.connection.SessionLocal", session_factory):
        audit_log_node(audit_state("reject"))

    records = AuditLogRepository(database_session).list_for_project("AIPM")
    assert len(records) == 1
    assert records[0]["human_decision"] == "reject"
    assert records[0]["final_payload"] is None


def test_route_after_audit_sends_reject_to_end() -> None:
    """Protect against rejected plans continuing into Jira creation."""
    assert route_after_audit({"_approval_decision": {"action": "reject"}}) == "rejected_end"


def test_route_after_audit_sends_approve_to_continue() -> None:
    """Protect against approved plans being stopped before Jira creation."""
    assert route_after_audit({"_approval_decision": {"action": "approve"}}) == "continue"
