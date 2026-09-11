from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.database.repositories import (
    DuplicateJiraAccountError,
    TeamMemberNotFoundError,
    TeamRepository,
)


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[TeamRepository]:
    """Provide an isolated TeamRepository backed by a temporary SQLite file."""
    database_path = tmp_path / "test_team_repository.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )()
    try:
        yield TeamRepository(session)
    finally:
        session.close()
        engine.dispose()


def test_add_and_retrieve_by_jira_account_id(repository: TeamRepository) -> None:
    """Protect against losing team member fields during persistence translation."""
    inserted = repository.add(
        name="Rahul",
        jira_account_id="jira-rahul",
        weekly_capacity_hours=40,
        skills={"python": "high", "fastapi": "high"},
        email="rahul@example.com",
    )

    retrieved = repository.get_by_jira_account_id("jira-rahul")

    assert retrieved.name == inserted.name == "Rahul"
    assert retrieved.skills == inserted.skills == {"python": "high", "fastapi": "high"}
    assert retrieved.email == inserted.email == "rahul@example.com"
    assert retrieved.weekly_capacity_hours == inserted.weekly_capacity_hours == 40


def test_add_duplicate_jira_account_id_raises(repository: TeamRepository) -> None:
    """Protect against duplicate Jira imports being silently accepted."""
    repository.add(
        name="Amit",
        jira_account_id="jira-duplicate",
        weekly_capacity_hours=40,
        skills={"react": "high"},
    )

    with pytest.raises(DuplicateJiraAccountError):
        repository.add(
            name="Another Amit",
            jira_account_id="jira-duplicate",
            weekly_capacity_hours=40,
            skills={"react": "low"},
        )


def test_get_nonexistent_raises_not_found(repository: TeamRepository) -> None:
    """Protect against missing Jira members returning an invalid empty model."""
    with pytest.raises(TeamMemberNotFoundError):
        repository.get_by_jira_account_id("jira-does-not-exist")


def test_list_all_returns_every_member(repository: TeamRepository) -> None:
    """Protect against list_all omitting persisted team members."""
    for name, jira_account_id in (
        ("Rahul", "jira-rahul"),
        ("Amit", "jira-amit"),
        ("Priya", "jira-priya"),
    ):
        repository.add(
            name=name,
            jira_account_id=jira_account_id,
            weekly_capacity_hours=40,
            skills={"python": "high"},
        )

    members = repository.list_all()

    assert len(members) == 3
    assert {member.name for member in members} == {"Rahul", "Amit", "Priya"}


def test_add_with_no_email_defaults_to_none(repository: TeamRepository) -> None:
    """Protect against the optional email parameter being treated as required."""
    member = repository.add(
        name="Priya",
        jira_account_id="jira-priya",
        weekly_capacity_hours=40,
        skills={"python": "high"},
    )

    assert member.email is None
