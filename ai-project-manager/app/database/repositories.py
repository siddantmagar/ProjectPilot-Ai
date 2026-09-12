"""Database repositories enforce the translation boundary for team members.

Nothing outside ``app/database/`` should import ``TeamMemberORM`` or SQLAlchemy
session objects directly.
"""

import json

from sqlalchemy.orm import Session

from app.database.models import TaskJiraLinkORM, TeamMemberORM
from app.models.team import TeamMember


class TeamMemberNotFoundError(Exception):
	"""Raised when a lookup finds no matching team member."""


class DuplicateJiraAccountError(Exception):
	"""Raised when adding a team member whose jira_account_id already exists."""


class TeamRepository:
	"""Persist and retrieve team members across the Pydantic/ORM boundary."""

	def __init__(self, session: Session) -> None:
		self._session = session

	def add(
		self,
		name: str,
		jira_account_id: str,
		weekly_capacity_hours: int,
		skills: dict[str, str],
		email: str | None = None,
	) -> TeamMember:
		"""Insert a team member, rejecting duplicate Jira account IDs."""
		existing = self._session.query(TeamMemberORM).filter_by(
			jira_account_id=jira_account_id
		).first()
		if existing is not None:
			raise DuplicateJiraAccountError(
				f"A team member with jira_account_id={jira_account_id} already exists"
			)
		row = TeamMemberORM(
			name=name,
			jira_account_id=jira_account_id,
			email=email,
			weekly_capacity_hours=weekly_capacity_hours,
			skills_json=json.dumps(skills),
		)
		self._session.add(row)
		self._session.commit()
		self._session.refresh(row)
		return self._to_pydantic(row)

	def get_by_jira_account_id(self, jira_account_id: str) -> TeamMember:
		"""Return a team member or raise TeamMemberNotFoundError if absent."""
		row = self._session.query(TeamMemberORM).filter_by(
			jira_account_id=jira_account_id
		).first()
		if row is None:
			raise TeamMemberNotFoundError(
				f"No team member with jira_account_id={jira_account_id}"
			)
		return self._to_pydantic(row)

	def list_all(self) -> list[TeamMember]:
		"""Return all persisted team members as Pydantic models."""
		rows = self._session.query(TeamMemberORM).all()
		return [self._to_pydantic(row) for row in rows]

	def _to_pydantic(self, row: TeamMemberORM) -> TeamMember:
		"""Convert one ORM row into the Pydantic TeamMember used by agents."""
		return TeamMember(
			name=row.name,
			skills=json.loads(row.skills_json),
			jira_account_id=row.jira_account_id,
			email=row.email,
			weekly_capacity_hours=row.weekly_capacity_hours,
		)


class TaskJiraLinkRepository:
	"""Persist task-title-to-Jira-issue-key links across graph runs."""

	def __init__(self, session: Session) -> None:
		self._session = session

	def get_issue_key(self, project_key: str, task_title: str) -> str | None:
		"""Return the existing Jira issue key for this project task, if any."""
		row = self._session.query(TaskJiraLinkORM).filter_by(
			project_key=project_key,
			task_title=task_title,
		).first()
		return row.jira_issue_key if row else None

	def get_issue_id(self, project_key: str, task_title: str) -> str | None:
		"""Return the existing Jira issue ID for this project task, if any."""
		row = self._session.query(TaskJiraLinkORM).filter_by(
			project_key=project_key,
			task_title=task_title,
		).first()
		return row.jira_issue_id if row else None

	def record_link(
		self,
		project_key: str,
		task_title: str,
		jira_issue_key: str,
		jira_issue_id: str,
	) -> None:
		"""Store a task-to-issue link after the caller's duplicate pre-check."""
		row = TaskJiraLinkORM(
			project_key=project_key,
			task_title=task_title,
			jira_issue_key=jira_issue_key,
			jira_issue_id=jira_issue_id,
		)
		self._session.add(row)
		self._session.commit()