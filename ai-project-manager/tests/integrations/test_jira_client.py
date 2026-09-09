import json
from unittest.mock import MagicMock

import pytest

from app.integrations.jira import client
from app.integrations.jira.schemas import JiraIssueCreateResponse


def fake_response(
    status_code: int,
    json_data: object = None,
    text: str = "",
) -> MagicMock:
    """Create an httpx-shaped response for a mocked Jira request."""
    response = MagicMock()
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    response.text = text
    if json_data is not None:
        response.json.return_value = json_data
    return response


def test_create_issue_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against successful Jira issue responses failing schema parsing."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(
        201,
        {
            "id": "123",
            "key": "AIPM-1",
            "self": "https://fake/issue/123",
        },
    )
    monkeypatch.setattr(client.httpx, "post", MagicMock(return_value=response))

    result = client.create_issue("Test task", "Test description")

    assert isinstance(result, JiraIssueCreateResponse)
    assert result.key == "AIPM-1"


def test_create_issue_sends_adf_description(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against sending raw descriptions that Jira v3 rejects instead of ADF."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(
        201,
        {"id": "123", "key": "AIPM-1", "self": "https://fake/issue/123"},
    )
    mock_post = MagicMock(return_value=response)
    monkeypatch.setattr(client.httpx, "post", mock_post)

    client.create_issue("Test task", "Plain text description")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["fields"]["description"]["type"] == "doc"


def test_create_issue_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against hiding Jira authentication failures behind generic errors."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(401, text="unauthorized")
    monkeypatch.setattr(client.httpx, "post", MagicMock(return_value=response))

    with pytest.raises(client.JiraClientError, match="authentication") as error:
        client.create_issue("Test task", "Test description")

    assert error.value.status_code == 401


def test_create_issue_raises_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against losing the project-specific context for create failures."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(404, text="not found")
    monkeypatch.setattr(client.httpx, "post", MagicMock(return_value=response))

    with pytest.raises(client.JiraClientError, match="project") as error:
        client.create_issue("Test task", "Test description")

    assert error.value.status_code == 404


def test_get_issue_raises_on_404_with_different_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against get failures reusing create-specific project wording."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(404, text="not found")
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    with pytest.raises(client.JiraClientError, match="issue") as error:
        client.get_issue("AIPM-999999")

    assert error.value.status_code == 404
    assert "project" not in str(error.value).lower()


def test_get_issue_handles_missing_assignee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against unassigned Jira issues crashing during response parsing."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(
        200,
        {
            "key": "AIPM-1",
            "fields": {
                "summary": "Test task",
                "status": {"name": "To Do"},
                "assignee": None,
            },
        },
    )
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    result = client.get_issue("AIPM-1")

    assert result.assignee_email is None


def test_missing_config_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against issuing Jira requests when the API token is not configured."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    monkeypatch.delenv("JIRA_API_TOKEN")
    mock_post = MagicMock()
    monkeypatch.setattr(client.httpx, "post", mock_post)

    with pytest.raises(ValueError, match="JIRA_API_TOKEN"):
        client.create_issue("Test task", "Test description")

    mock_post.assert_not_called()


def test_create_issue_raises_on_unparseable_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against leaking raw JSONDecodeError from malformed Jira success responses."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")
    response = fake_response(201, text="not valid JSON")
    response.json.side_effect = json.JSONDecodeError("invalid", "not valid JSON", 0)
    monkeypatch.setattr(client.httpx, "post", MagicMock(return_value=response))

    with pytest.raises(client.JiraClientError, match="unparseable response body"):
        client.create_issue("Test task", "Test description")
