"""Standalone verification harness for the project repository.

The checks use a temporary ``test_verify_projects.db`` file and remove it
before and after each run so real project data is never touched.

Run from the project root with:
    python -m scripts.verify_project_repository
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.database.repositories import ProjectNotFoundError, ProjectRepository


TEMP_DB_PATH = Path("test_verify_projects.db")
results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def print_summary() -> None:
    """Print the final project repository verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<30} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<30} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all project repository checks and always remove the temp database."""
    TEMP_DB_PATH.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{TEMP_DB_PATH}")
    session = None
    try:
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        repository = ProjectRepository(session)

        try:
            first_id = repository.create(
                "AIPM",
                "Build the Project Pilot API",
                "2 weeks",
                2,
            )
            created = repository.get_by_id(first_id)
            passed = (
                created["id"] == first_id
                and created["jira_project_key"] == "AIPM"
                and created["goal"] == "Build the Project Pilot API"
                and created["deadline"] == "2 weeks"
                and created["team_size"] == 2
                and bool(created["created_at"])
            )
            add_result("CREATE AND RETRIEVE CHECK", passed, str(created))
        except Exception as error:
            add_result("CREATE AND RETRIEVE CHECK", False, str(error))

        try:
            repository.create("AIPM", "Build the dashboard", "3 weeks", 3)
            repository.create("AIPM", "Launch the sandbox", "4 weeks", 4)
            projects = repository.list_all()
            timestamps = [project["created_at"] for project in projects]
            passed = (
                len(projects) == 3
                and timestamps == sorted(timestamps, reverse=True)
            )
            add_result(
                "LIST ALL CHECK",
                passed,
                f"{len(projects)} projects, newest first: {timestamps}",
            )
        except Exception as error:
            add_result("LIST ALL CHECK", False, str(error))

        try:
            repository.get_by_id(999999)
        except ProjectNotFoundError as error:
            add_result("NOT FOUND CHECK", True, str(error))
        except Exception as error:
            add_result("NOT FOUND CHECK", False, str(error))
        else:
            add_result("NOT FOUND CHECK", False, "ProjectNotFoundError was not raised")

        print_summary()
    finally:
        if session is not None:
            session.close()
        engine.dispose()
        TEMP_DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
