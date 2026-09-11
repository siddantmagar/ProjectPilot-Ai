"""Standalone verification harness for the team repository.

The checks use a temporary ``test_verify.db`` file and remove it before and
after each run so real project data is never touched.

Run from the project root with:
    python -m scripts.verify_team_repository
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.database.models import TeamMemberORM
from app.database.repositories import (
    DuplicateJiraAccountError,
    TeamMemberNotFoundError,
    TeamRepository,
)


TEMP_DB_PATH = Path("test_verify.db")
results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def run_add_and_retrieve_check(repository: TeamRepository) -> None:
    """Verify that inserted team members can be retrieved by Jira account ID."""
    try:
        inserted = repository.add(
            name="Rahul",
            jira_account_id="jira-rahul",
            weekly_capacity_hours=40,
            skills={"python": "high", "fastapi": "high"},
            email="rahul@example.com",
        )
        retrieved = repository.get_by_jira_account_id("jira-rahul")
        passed = (
            retrieved.name == inserted.name == "Rahul"
            and retrieved.skills == inserted.skills == {"python": "high", "fastapi": "high"}
        )
        add_result("ADD AND RETRIEVE CHECK", passed, f"{retrieved.name}: {retrieved.skills}")
    except Exception as error:
        add_result("ADD AND RETRIEVE CHECK", False, str(error))


def run_duplicate_rejection_check(repository: TeamRepository) -> None:
    """Verify that duplicate Jira account IDs raise the repository exception."""
    try:
        repository.add(
            name="Amit",
            jira_account_id="jira-duplicate",
            weekly_capacity_hours=40,
            skills={"react": "high"},
        )
        try:
            repository.add(
                name="Another Amit",
                jira_account_id="jira-duplicate",
                weekly_capacity_hours=40,
                skills={"react": "low"},
            )
        except DuplicateJiraAccountError as error:
            add_result("DUPLICATE REJECTION CHECK", True, str(error))
        else:
            add_result(
                "DUPLICATE REJECTION CHECK",
                False,
                "DuplicateJiraAccountError was not raised",
            )
    except Exception as error:
        add_result("DUPLICATE REJECTION CHECK", False, str(error))


def run_not_found_check(repository: TeamRepository) -> None:
    """Verify that an unknown Jira account ID raises the repository exception."""
    try:
        repository.get_by_jira_account_id("jira-does-not-exist")
    except TeamMemberNotFoundError as error:
        add_result("NOT FOUND CHECK", True, str(error))
    except Exception as error:
        add_result("NOT FOUND CHECK", False, str(error))
    else:
        add_result("NOT FOUND CHECK", False, "TeamMemberNotFoundError was not raised")


def run_list_all_check(repository: TeamRepository) -> None:
    """Verify that list_all returns every persisted team member."""
    try:
        repository.add(
            name="Priya",
            jira_account_id="jira-priya",
            weekly_capacity_hours=40,
            skills={"python": "high"},
        )
        repository.add(
            name="David",
            jira_account_id="jira-david",
            weekly_capacity_hours=40,
            skills={"react": "medium"},
        )
        members = repository.list_all()
        names = {member.name for member in members}
        passed = len(members) == 4 and {"Rahul", "Amit", "Priya", "David"} == names
        add_result("LIST ALL CHECK", passed, f"{len(members)} members: {sorted(names)}")
    except Exception as error:
        add_result("LIST ALL CHECK", False, str(error))


def print_summary() -> None:
    """Print the final repository verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<32} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<32} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all repository checks and always remove the temporary database."""
    TEMP_DB_PATH.unlink(missing_ok=True)
    engine = create_engine(
        f"sqlite:///{TEMP_DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    session = None
    try:
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        repository = TeamRepository(session)
        run_add_and_retrieve_check(repository)
        run_duplicate_rejection_check(repository)
        run_not_found_check(repository)
        run_list_all_check(repository)
        print_summary()
    finally:
        if session is not None:
            session.close()
        engine.dispose()
        TEMP_DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
