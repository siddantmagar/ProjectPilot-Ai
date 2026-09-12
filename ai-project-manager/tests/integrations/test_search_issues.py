from unittest.mock import MagicMock

import pytest

from app.integrations.jira import client


def set_fake_jira_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic Jira configuration for each mocked test."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")


def fake_response(status_code: int, json_data: object = None) -> MagicMock:
    """Create an httpx-shaped response for a mocked search request."""
    response = MagicMock()
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    response.text = str(json_data)
    if json_data is not None:
        response.json.return_value = json_data
    return response


def test_search_issues_returns_parsed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against losing raw issue data needed by status synchronization."""
    set_fake_jira_environment(monkeypatch)
    response = fake_response(
        200,
        {
            "issues": [
                {
                    "key": "AIPM-1",
                    "fields": {
                        "summary": "Test",
                        "status": {
                            "name": "Idea",
                            "statusCategory": {"name": "To Do"},
                        },
                        "flagged": False,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    result = client.search_issues_by_project()

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["key"] == "AIPM-1"


def test_search_issues_uses_correct_jql(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against searches ignoring the configured default project key."""
    set_fake_jira_environment(monkeypatch)
    mock_get = MagicMock(return_value=fake_response(200, {"issues": []}))
    monkeypatch.setattr(client.httpx, "get", mock_get)

    client.search_issues_by_project()

    assert mock_get.call_args.kwargs["params"]["jql"] == "project = AIPM"


def test_search_issues_uses_explicit_project_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against an explicit project override being replaced by configuration."""
    set_fake_jira_environment(monkeypatch)
    mock_get = MagicMock(return_value=fake_response(200, {"issues": []}))
    monkeypatch.setattr(client.httpx, "get", mock_get)

    client.search_issues_by_project("OTHERPROJECT")

    assert mock_get.call_args.kwargs["params"]["jql"] == "project = OTHERPROJECT"


def test_search_issues_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against project search hiding Jira authentication failures."""
    set_fake_jira_environment(monkeypatch)
    response = fake_response(401, "unauthorized")
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    with pytest.raises(client.JiraClientError) as error:
        client.search_issues_by_project()

    assert error.value.status_code == 401
