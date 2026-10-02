from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class TeamMemberORM(Base):
    """Persisted team member record.

    Distinct from the Pydantic TeamMember in app/models/team.py: this is the
    database row shape, and the repository layer translates between the two.
    """

    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Stable identity key per design; uniqueness prevents duplicate Jira imports.
    jira_account_id: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    weekly_capacity_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=40
    )
    # SQLite has no simple portable native dict/JSON type across engines without
    # extra setup; the repository converts this JSON string with json.dumps/loads.
    skills_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")


class TaskJiraLinkORM(Base):
    """Track Planner task titles that already have real Jira issues."""

    __tablename__ = "task_jira_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_key: Mapped[str] = mapped_column(String(50), nullable=False)
    task_title: Mapped[str] = mapped_column(String(500), nullable=False)
    jira_issue_key: Mapped[str] = mapped_column(String(50), nullable=False)
    jira_issue_id: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_key", "task_title", name="uq_project_task_title"),
    )


class AuditLogORM(Base):
    """Record AI recommendations and resulting human approval decisions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_key: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)
    proposed_payload_json: Mapped[str] = mapped_column(String, nullable=False)
    human_decision: Mapped[str] = mapped_column(String(20), nullable=False)
    final_payload_json: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)


class ProjectORM(Base):
    """One planning run: one submitted goal and workflow invocation.

    There is deliberately no relationship to other Project rows yet. A richer
    "one product, many runs" model is deferred until RAG-based duplicate and
    overlap detection exists in roadmap M17.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jira_project_key: Mapped[str] = mapped_column(String(50), nullable=False)
    goal: Mapped[str] = mapped_column(String(2000), nullable=False)
    deadline: Mapped[str] = mapped_column(String(100), nullable=False)
    team_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
