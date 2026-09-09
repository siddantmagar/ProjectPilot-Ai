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