from unittest.mock import MagicMock

import pytest

from app.integrations.jira import client


def set_fake_jira_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic Jira configuration for each mocked test."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")


def fake_response(status_code: int, text: str = "") -> MagicMock:
    """Create an httpx-shaped response for a mocked assignment request."""
    response = MagicMock()
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    response.text = text
    return response


def test_assign_issue_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against treating Jira's successful 204 response as a parseable body."""
    set_fake_jira_environment(monkeypatch)
    mock_put = MagicMock(return_value=fake_response(204))
    monkeypatch.setattr(client.httpx, "put", mock_put)

    result = client.assign_issue("AIPM-1", "account-1")

    assert result is None
    assert mock_put.call_args.kwargs["json"] == {"accountId": "account-1"}


def test_assign_issue_raises_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against losing whether an invalid issue or account caused assignment failure."""
    set_fake_jira_environment(monkeypatch)
    monkeypatch.setattr(
        client.httpx,
        "put",
        MagicMock(return_value=fake_response(404, "not found")),
    )

    with pytest.raises(client.JiraClientError, match="issue.*account ID") as error:
        client.assign_issue("AIPM-1", "account-1")

    assert error.value.status_code == 404


def test_assign_issue_raises_on_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against hiding Jira's invalid-project-assignee rejection."""
    set_fake_jira_environment(monkeypatch)
    monkeypatch.setattr(
        client.httpx,
        "put",
        MagicMock(return_value=fake_response(400, "invalid assignee")),
    )

    with pytest.raises(client.JiraClientError, match="assignee") as error:
        client.assign_issue("AIPM-1", "account-1")

    assert error.value.status_code == 400


def test_assign_issue_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against assignment bypassing the shared Jira authentication error handling."""
    set_fake_jira_environment(monkeypatch)
    monkeypatch.setattr(
        client.httpx,
        "put",
        MagicMock(return_value=fake_response(401, "unauthorized")),
    )

    with pytest.raises(client.JiraClientError, match="authentication") as error:
        client.assign_issue("AIPM-1", "account-1")

    assert error.value.status_code == 401
