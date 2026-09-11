"""Team member model definitions."""

from typing import Literal

from pydantic import BaseModel, Field


class TeamMember(BaseModel):
	"""A team member and their current workload."""

	name: str
	skills: dict[str, Literal["low", "medium", "high"]]
	# Legacy field kept for backward compatibility; superseded by the Phase 2
	# weekly_capacity_hours-based workload calculation.
	workload_percent: int = Field(ge=0, le=100, default=0)
	jira_account_id: str | None = None
	email: str | None = None
	weekly_capacity_hours: int | None = None


SAMPLE_TEAM = [
	TeamMember(
		name="Rahul",
		skills={"python": "high", "fastapi": "high", "react": "low"},
		workload_percent=60,
	),
	TeamMember(
		name="Amit",
		skills={"python": "medium", "fastapi": "low", "react": "high"},
		workload_percent=30,
	),
	TeamMember(
		name="Priya",
		skills={"python": "high", "fastapi": "medium", "react": "medium"},
		workload_percent=45,
	),
]