"""Small HTTP client for the Jira REST API."""

import base64
import json
import os

import httpx
from dotenv import load_dotenv

from app.integrations.jira.schemas import (
	JiraIssueCreateResponse,
	JiraIssueResponse,
	JiraUserResponse,
)


load_dotenv()


class JiraClientError(Exception):
	"""Raised when Jira configuration, networking, or an HTTP response fails."""

	def __init__(
		self,
		message: str,
		status_code: int | None = None,
		response_body: str = "",
	) -> None:
		super().__init__(message)
		self.status_code = status_code
		self.response_body = response_body


def _load_config() -> tuple[str, str, str, str]:
	"""Load Jira settings from the environment and report missing variables."""
	values = {
		"JIRA_BASE_URL": os.getenv("JIRA_BASE_URL"),
		"JIRA_EMAIL": os.getenv("JIRA_EMAIL"),
		"JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN"),
		"JIRA_PROJECT_KEY": os.getenv("JIRA_PROJECT_KEY"),
	}
	for name, value in values.items():
		if not value:
			raise ValueError(f"Missing required environment variable: {name}")

	return (
		values["JIRA_BASE_URL"],
		values["JIRA_EMAIL"],
		values["JIRA_API_TOKEN"],
		values["JIRA_PROJECT_KEY"],
	)


def _auth_header(email: str, token: str) -> dict[str, str]:
	"""Build the JSON Basic Authentication header expected by Jira."""
	credentials = f"{email}:{token}".encode("utf-8")
	encoded = base64.b64encode(credentials).decode("ascii")
	return {
		"Authorization": f"Basic {encoded}",
		"Content-Type": "application/json",
	}


def _text_to_adf(text: str) -> dict:
	"""Wrap plain text in the minimal Atlassian Document Format structure."""
	return {
		"type": "doc",
		"version": 1,
		"content": [
			{
				"type": "paragraph",
				"content": [{"type": "text", "text": text}],
			}
		],
	}


def _http_error_message(status_code: int, operation: str) -> str:
	"""Return the Jira-specific explanation for an unsuccessful HTTP status."""
	if status_code == 400 and operation == "assign_issue":
		return "Jira rejected the assignment — the account ID may not be a valid assignee for this project."
	if status_code == 401:
		return "Jira authentication problem — check JIRA_EMAIL/JIRA_API_TOKEN"
	if status_code == 403:
		return "Jira permission problem"
	if status_code == 404:
		if operation == "create_issue":
			return "Jira project or issue type not found — check JIRA_PROJECT_KEY"
		if operation == "assign_issue":
			return "Jira issue or account ID not found — check the issue key and account ID"
		return "Jira issue not found — check the issue key"
	if status_code == 429:
		return "Jira rate limited the request"
	if 500 <= status_code <= 599:
		return "Jira server problem"
	return f"Jira request failed with HTTP status {status_code}"


def _raise_http_error(response: httpx.Response, operation: str) -> None:
	"""Raise a structured client error for an unsuccessful Jira response."""
	if response.is_success:
		return
	message = _http_error_message(response.status_code, operation)
	raise JiraClientError(
		f"{message}: {response.text}",
		status_code=response.status_code,
		response_body=response.text,
	)


def create_issue(
	summary: str, description: str, issue_type: str = "Task"
) -> JiraIssueCreateResponse:
	"""Create a Jira issue and return Jira's creation response."""
	base_url, email, token, project_key = _load_config()
	payload = {
		"fields": {
			"project": {"key": project_key},
			"summary": summary,
			"description": _text_to_adf(description),
			"issuetype": {"name": issue_type},
		}
	}
	try:
		response = httpx.post(
			f"{base_url.rstrip('/')}/rest/api/3/issue",
			headers=_auth_header(email, token),
			json=payload,
			timeout=10,
		)
	except httpx.TimeoutException as error:
		raise JiraClientError("Jira network/timeout error while creating issue") from error
	except httpx.ConnectError as error:
		raise JiraClientError("Jira network/timeout error while connecting") from error

	_raise_http_error(response, "create_issue")
	if response.status_code != 201:
		raise JiraClientError(
		f"Jira issue creation returned unexpected HTTP status {response.status_code}",
		status_code=response.status_code,
		response_body=response.text,
	)
	try:
		response_data = response.json()
	except json.JSONDecodeError as error:
		raise JiraClientError(
			f"Jira returned an unparseable response body: {response.text}",
			status_code=response.status_code,
			response_body=response.text,
		) from error
	return JiraIssueCreateResponse.model_validate(response_data)


def get_issue(issue_key: str) -> JiraIssueResponse:
	"""Fetch a Jira issue and return its supported response fields."""
	base_url, email, token, _ = _load_config()
	try:
		response = httpx.get(
			f"{base_url.rstrip('/')}/rest/api/3/issue/{issue_key}",
			headers=_auth_header(email, token),
			timeout=10,
		)
	except httpx.TimeoutException as error:
		raise JiraClientError("Jira network/timeout error while fetching issue") from error
	except httpx.ConnectError as error:
		raise JiraClientError("Jira network/timeout error while connecting") from error

	_raise_http_error(response, "get_issue")
	try:
		data = response.json()
	except json.JSONDecodeError as error:
		raise JiraClientError(
			f"Jira returned an unparseable response body: {response.text}",
			status_code=response.status_code,
			response_body=response.text,
		) from error
	fields = data["fields"]
	assignee = fields.get("assignee")
	return JiraIssueResponse(
		key=data["key"],
		summary=fields["summary"],
		status=fields["status"]["name"],
		assignee_email=assignee.get("emailAddress") if assignee else None,
	)


def assign_issue(issue_key: str, account_id: str) -> None:
	"""Assign a Jira issue by account ID; use get_issue() to confirm the result."""
	base_url, email, token, _ = _load_config()
	try:
		response = httpx.put(
			f"{base_url.rstrip('/')}/rest/api/3/issue/{issue_key}/assignee",
			headers=_auth_header(email, token),
			json={"accountId": account_id},
			timeout=10,
		)
	except httpx.TimeoutException as error:
		raise JiraClientError("Jira network/timeout error while assigning issue") from error
	except httpx.ConnectError as error:
		raise JiraClientError("Jira network/timeout error while connecting") from error

	if response.status_code == 204:
		return None
	_raise_http_error(response, "assign_issue")


def get_account_id_by_email(email: str) -> JiraUserResponse:
	"""Find one Jira user by email, rejecting zero or multiple matches explicitly."""
	base_url, auth_email, token, _ = _load_config()
	try:
		response = httpx.get(
			f"{base_url.rstrip('/')}/rest/api/3/user/search?query={email}",
			headers=_auth_header(auth_email, token),
			timeout=10,
		)
	except httpx.TimeoutException as error:
		raise JiraClientError(
			"Jira network/timeout error while searching for a user"
		) from error
	except httpx.ConnectError as error:
		raise JiraClientError("Jira network/timeout error while connecting") from error

	_raise_http_error(response, "get_account_id_by_email")
	try:
		users = response.json()
	except json.JSONDecodeError as error:
		raise JiraClientError(
			f"Jira returned an unparseable response body: {response.text}",
			status_code=response.status_code,
			response_body=response.text,
		) from error

	if not users:
		raise JiraClientError(
			f"No Jira user found matching email: {email}",
			status_code=404,
			response_body=response.text,
		)
	if len(users) > 1:
		raise JiraClientError(
			f"Multiple Jira users found matching email: {email}",
			status_code=409,
			response_body=response.text,
		)
	return JiraUserResponse.model_validate(users[0])


def get_assignable_users_for_project(
	project_key: str | None = None,
) -> list[JiraUserResponse]:
	"""Return all Jira users assignable to the selected project."""
	base_url, auth_email, token, configured_project_key = _load_config()
	selected_project_key = project_key or configured_project_key
	try:
		response = httpx.get(
			f"{base_url.rstrip('/')}/rest/api/3/user/assignable/search?project={selected_project_key}",
			headers=_auth_header(auth_email, token),
			timeout=10,
		)
	except httpx.TimeoutException as error:
		raise JiraClientError(
			"Jira network/timeout error while searching assignable users"
		) from error
	except httpx.ConnectError as error:
		raise JiraClientError("Jira network/timeout error while connecting") from error

	_raise_http_error(response, "get_assignable_users_for_project")
	try:
		users = response.json()
	except json.JSONDecodeError as error:
		raise JiraClientError(
			f"Jira returned an unparseable response body: {response.text}",
			status_code=response.status_code,
			response_body=response.text,
		) from error

	if not users:
		return []
	return [JiraUserResponse.model_validate(user) for user in users]