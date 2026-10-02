"""Database repositories enforce the translation boundary for team members.

Nothing outside ``app/database/`` should import ``TeamMemberORM`` or SQLAlchemy
session objects directly.
"""

import json

from sqlalchemy.orm import Session

from app.database.models import (
	AuditLogORM,
	ProjectORM,
	TaskJiraLinkORM,
	TeamMemberORM,
)
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
		project_id: int | None = None,
	) -> None:
		"""Store a task-to-issue link after the caller's duplicate pre-check."""
		row = TaskJiraLinkORM(
			project_key=project_key,
			task_title=task_title,
			jira_issue_key=jira_issue_key,
			jira_issue_id=jira_issue_id,
			project_id=project_id,
		)
		self._session.add(row)
		self._session.commit()

	def list_for_project(self, project_id: int) -> list[dict]:
		"""Return all task-Jira links recorded for a project ID."""
		rows = self._session.query(TaskJiraLinkORM).filter_by(
			project_id=project_id
		).all()
		return [
			{
				"task_title": row.task_title,
				"jira_issue_key": row.jira_issue_key,
				"project_id": row.project_id,
			}
			for row in rows
		]


class AuditLogRepository:
	"""Persist human decisions on AI-proposed actions."""

	def __init__(self, session: Session) -> None:
		self._session = session

	def record_decision(
		self,
		project_key: str,
		decision_type: str,
		proposed_payload: dict,
		human_decision: str,
		final_payload: dict | None,
		project_id: int | None = None,
	) -> None:
		"""Record one AI recommendation and its human decision."""
		from datetime import datetime, timezone

		row = AuditLogORM(
			project_key=project_key,
			decision_type=decision_type,
			proposed_payload_json=json.dumps(proposed_payload),
			human_decision=human_decision,
			final_payload_json=json.dumps(final_payload) if final_payload else None,
			project_id=project_id,
			created_at=datetime.now(timezone.utc).isoformat(),
		)
		self._session.add(row)
		self._session.commit()

	def list_for_project(self, project_key: str) -> list[dict]:
		"""Return chronological audit decisions for one project."""
		rows = self._session.query(AuditLogORM).filter_by(
			project_key=project_key
		).order_by(AuditLogORM.created_at).all()
		return [
			{
				"decision_type": row.decision_type,
				"human_decision": row.human_decision,
				"created_at": row.created_at,
				"proposed_payload": json.loads(row.proposed_payload_json),
				"final_payload": (
					json.loads(row.final_payload_json)
					if row.final_payload_json
					else None
				),
			}
			for row in rows
		]

	def list_for_project_id(self, project_id: int) -> list[dict]:
		"""Return chronological audit decisions for a project ID."""
		rows = self._session.query(AuditLogORM).filter_by(
			project_id=project_id
		).order_by(AuditLogORM.created_at).all()
		return [
			{
				"decision_type": row.decision_type,
				"human_decision": row.human_decision,
				"created_at": row.created_at,
				"proposed_payload": json.loads(row.proposed_payload_json),
				"final_payload": (
					json.loads(row.final_payload_json)
					if row.final_payload_json
					else None
				),
			}
			for row in rows
		]


class ProjectNotFoundError(Exception):
	"""Raised when a lookup finds no matching project."""


class ProjectRepository:
	"""Persist and retrieve Project rows, one row per planning run."""

	def __init__(self, session: Session) -> None:
		self._session = session

	def create(
		self,
		jira_project_key: str,
		goal: str,
		deadline: str,
		team_size: int,
	) -> int:
		"""Insert a new project row and return its ID."""
		from datetime import datetime, timezone

		row = ProjectORM(
			jira_project_key=jira_project_key,
			goal=goal,
			deadline=deadline,
			team_size=team_size,
			created_at=datetime.now(timezone.utc).isoformat(),
		)
		self._session.add(row)
		self._session.commit()
		self._session.refresh(row)
		return row.id

	def get_by_id(self, project_id: int) -> dict:
		"""Return a project's fields or raise ProjectNotFoundError."""
		row = self._session.query(ProjectORM).filter_by(id=project_id).first()
		if row is None:
			raise ProjectNotFoundError(f"No project with id={project_id}")
		return {
			"id": row.id,
			"jira_project_key": row.jira_project_key,
			"goal": row.goal,
			"deadline": row.deadline,
			"team_size": row.team_size,
			"created_at": row.created_at,
		}

	def list_all(self) -> list[dict]:
		"""Return all projects, newest first."""
		rows = self._session.query(ProjectORM).order_by(ProjectORM.created_at.desc()).all()
		return [
			{
				"id": row.id,
				"jira_project_key": row.jira_project_key,
				"goal": row.goal,
				"deadline": row.deadline,
				"team_size": row.team_size,
				"created_at": row.created_at,
			}
			for row in rows
		]
	