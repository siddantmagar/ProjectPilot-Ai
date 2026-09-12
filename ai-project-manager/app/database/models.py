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
    project_key: Mapped[str] = mapped_column(String(50), nullable=False)
    task_title: Mapped[str] = mapped_column(String(500), nullable=False)
    jira_issue_key: Mapped[str] = mapped_column(String(50), nullable=False)
    jira_issue_id: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_key", "task_title", name="uq_project_task_title"),
    )
