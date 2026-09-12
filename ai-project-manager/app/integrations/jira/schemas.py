from pydantic import BaseModel, Field


class JiraIssueCreateResponse(BaseModel):
	"""Response returned by Jira after successfully creating an issue."""
	id: str
	key: str
	self_url: str = Field(alias="self")

	model_config = {"populate_by_name": True}


class JiraIssueResponse(BaseModel):
	"""Parsed subset of a Jira issue, from GET /issue/{key}."""
	key: str
	summary: str
	status: str
	assignee_email: str | None = None


class JiraUserResponse(BaseModel):
	"""A Jira user's identity fields, as returned by user-search endpoints."""
	account_id: str = Field(alias="accountId")
	display_name: str = Field(alias="displayName")
	email: str | None = Field(alias="emailAddress", default=None)

	model_config = {"populate_by_name": True}