from unittest.mock import MagicMock

from app.graph.nodes import status_sync_node
from app.integrations.jira import client


def jira_issue(
    key: str,
    status_name: str,
    category: str,
    flagged: bool = False,
) -> dict:
    """Create a raw Jira issue payload for status-sync tests."""
    return {
        "key": key,
        "fields": {
            "summary": f"Summary for {key}",
            "status": {
                "name": status_name,
                "statusCategory": {"name": category},
            },
            "flagged": flagged,
        },
    }


def sync_state() -> dict:
    """Create state with two tracked Jira keys and numeric IDs."""
    return {
        "jira_issue_keys": {
            "Build API": "AIPM-1",
            "Write tests": "AIPM-2",
        },
        "jira_issue_ids": {
            "Build API": "1001",
            "Write tests": "1002",
        },
    }


def test_syncs_statuses_for_tracked_issues(monkeypatch) -> None:
    """Protect against tracked Jira issues failing to become internal statuses."""
    state = sync_state()
    mock_search = MagicMock(
        return_value=[
            jira_issue("AIPM-1", "To Do", "In Progress"),
            jira_issue("AIPM-2", "Done", "Done"),
        ]
    )
    monkeypatch.setattr(client, "search_issues_by_project", mock_search)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")

    result = status_sync_node(state)

    statuses = {status.task_title: status for status in result["statuses"]}
    assert len(statuses) == 2
    assert statuses["Build API"].status == "todo"
    assert statuses["Write tests"].status == "done"
    assert statuses["Build API"].jira_status_name == "To Do"


def test_ignores_issues_not_created_by_this_run(monkeypatch) -> None:
    """Protect against unrelated project issues entering this run's task state."""
    state = sync_state()
    mock_search = MagicMock(
        return_value=[
            jira_issue("AIPM-1", "To Do", "To Do"),
            jira_issue("AIPM-2", "In Progress", "In Progress"),
            jira_issue("AIPM-999", "Done", "Done"),
        ]
    )
    monkeypatch.setattr(client, "search_issues_by_project", mock_search)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")

    result = status_sync_node(state)

    assert len(result["statuses"]) == 2
    assert {status.task_title for status in result["statuses"]} == {
        "Build API",
        "Write tests",
    }


def test_passes_reconcile_ids_from_state(monkeypatch) -> None:
    """Protect against status sync reconciling issue keys instead of numeric IDs."""
    state = sync_state()
    mock_search = MagicMock(return_value=[])
    monkeypatch.setattr(client, "search_issues_by_project", mock_search)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")

    status_sync_node(state)

    mock_search.assert_called_once_with(
        "AIPM",
        reconcile_issue_ids=["1001", "1002"],
    )


def test_sets_is_overdue_from_flagged_field(monkeypatch) -> None:
    """Protect against losing Jira flagged state when building task statuses."""
    state = sync_state()
    mock_search = MagicMock(
        return_value=[jira_issue("AIPM-1", "In Progress", "In Progress", flagged=True)]
    )
    monkeypatch.setattr(client, "search_issues_by_project", mock_search)
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")

    result = status_sync_node(state)

    assert result["statuses"][0].is_overdue is True
