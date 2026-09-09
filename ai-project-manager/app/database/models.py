from sqlalchemy import Integer, String
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
