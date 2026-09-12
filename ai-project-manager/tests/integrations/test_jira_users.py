from unittest.mock import MagicMock

import pytest

from app.integrations.jira import client
from app.integrations.jira.schemas import JiraUserResponse


def set_fake_jira_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic Jira configuration for each mocked test."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://fake.jira")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "AIPM")


def fake_response(json_data: object) -> MagicMock:
    """Create an httpx-shaped successful response for a mocked Jira request."""
    response = MagicMock()
    response.status_code = 200
    response.is_success = True
    response.json.return_value = json_data
    response.text = str(json_data)
    return response


def test_get_account_id_by_email_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against failing to parse a unique Jira user search result."""
    set_fake_jira_environment(monkeypatch)
    response = fake_response(
        [
            {
                "accountId": "acct-1",
                "displayName": "Rahul",
                "emailAddress": "rahul@example.com",
            }
        ]
    )
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    result = client.get_account_id_by_email("rahul@example.com")

    assert isinstance(result, JiraUserResponse)
    assert result.account_id == "acct-1"


def test_get_account_id_by_email_raises_on_zero_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against treating an empty email search as a successful lookup."""
    set_fake_jira_environment(monkeypatch)
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=fake_response([])))

    with pytest.raises(client.JiraClientError) as error:
        client.get_account_id_by_email("missing@example.com")

    assert error.value.status_code == 404


def test_get_account_id_by_email_raises_on_multiple_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against silently selecting the wrong user when email matches are ambiguous."""
    set_fake_jira_environment(monkeypatch)
    response = fake_response(
        [
            {"accountId": "acct-1", "displayName": "Rahul"},
            {"accountId": "acct-2", "displayName": "Another Rahul"},
        ]
    )
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    with pytest.raises(client.JiraClientError, match="(?i)multiple"):
        client.get_account_id_by_email("shared@example.com")


def test_get_account_id_by_email_handles_null_email_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against Jira privacy redaction causing user parsing to fail."""
    set_fake_jira_environment(monkeypatch)
    response = fake_response(
        [{"accountId": "acct-1", "displayName": "Private User", "emailAddress": None}]
    )
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    result = client.get_account_id_by_email("private@example.com")

    assert result.email is None


def test_get_assignable_users_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Protect against losing or misparsing assignable users returned by Jira."""
    set_fake_jira_environment(monkeypatch)
    response = fake_response(
        [
            {"accountId": "acct-1", "displayName": "Rahul"},
            {"accountId": "acct-2", "displayName": "Amit"},
        ]
    )
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=response))

    result = client.get_assignable_users_for_project()

    assert len(result) == 2
    assert all(isinstance(user, JiraUserResponse) for user in result)


def test_get_assignable_users_handles_empty_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect against treating a project with no assignable users as an error."""
    set_fake_jira_environment(monkeypatch)
    monkeypatch.setattr(client.httpx, "get", MagicMock(return_value=fake_response([])))

    result = client.get_assignable_users_for_project()

    assert result == []
