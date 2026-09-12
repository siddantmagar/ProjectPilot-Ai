"""Standalone end-to-end verification harness for real Jira assignment.

WARNING: This script creates real Jira issues and assigns them to Siddant Magar
in the configured AIPM project on every run. It also persists the team member
record and task-to-issue links for idempotent reruns.

Run from the project root with:
    python -m scripts.verify_real_assignment
"""

import os
import uuid

from app.database.connection import SessionLocal
from app.database.repositories import (
    DuplicateJiraAccountError,
    TeamMemberNotFoundError,
    TeamRepository,
)
from app.graph.nodes import assignment_node, jira_creation_node
from app.integrations.jira.client import JiraClientError, get_issue
from app.models.task import PlannerOutput, Task


REAL_NAME = "Siddant Magar"
REAL_ACCOUNT_ID = "712020:f77bac30-a156-48af-8bb8-548c690fa15a"
REAL_EMAIL = "siddantmagar01@gmail.com"
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "AIPM")
results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def ensure_real_team_member() -> None:
    """Ensure the real assignment target exists in the local team database."""
    session = SessionLocal()
    try:
        team_repo = TeamRepository(session)
        try:
            team_repo.add(
                name=REAL_NAME,
                jira_account_id=REAL_ACCOUNT_ID,
                email=REAL_EMAIL,
                weekly_capacity_hours=40,
                skills={"python": "high"},
            )
        except DuplicateJiraAccountError:
            existing = team_repo.get_by_jira_account_id(REAL_ACCOUNT_ID)
            if existing.jira_account_id != REAL_ACCOUNT_ID:
                raise RuntimeError("Existing team member has an unexpected Jira account ID")
            print(f"Using existing team member: {existing.name}")
    finally:
        session.close()


def build_state() -> dict:
    """Build a two-task ProjectPilotState for this live verification run."""
    suffix = uuid.uuid4().hex[:10]
    planner_output = PlannerOutput(
        epics=["Verification"],
        tasks=[
            Task(
                title=f"Verify assignment task A {suffix}",
                description="Verify real Jira assignment for Project Pilot AI.",
                priority="medium",
                estimated_days=1,
                epic="Verification",
            ),
            Task(
                title=f"Verify assignment task B {suffix}",
                description="Verify real Jira assignment for Project Pilot AI.",
                priority="medium",
                estimated_days=1,
                epic="Verification",
            ),
        ],
    )
    return {
        "goal": "Verify real Jira assignment",
        "deadline": "sandbox verification",
        "team_size": 1,
        "team": [],
        "planner_output": planner_output,
        "jira_issue_keys": {},
    }


def run_real_assignment_check() -> None:
    """Create issues, run assignment, and visibly verify assigned emails."""
    try:
        ensure_real_team_member()
        state = build_state()
        state.update(jira_creation_node(state))
        assignment_result = assignment_node(state)
        assignment_output = assignment_result["assignment_output"]
        tasks = state["planner_output"].tasks
        assignments = assignment_output.assignments
        expected_titles = {task.title for task in tasks}
        assigned_titles = {assignment.task_title for assignment in assignments}
        if len(assignments) != len(tasks) or assigned_titles != expected_titles:
            add_result(
                "REAL ASSIGNMENT CHECK",
                False,
                f"Expected {len(tasks)} task assignments, got {len(assignments)}",
            )
            return

        email_matches = True
        for assignment in assignments:
            issue_key = state["jira_issue_keys"].get(assignment.task_title)
            if issue_key is None:
                email_matches = False
                print(f"{assignment.task_title}: missing Jira issue key")
                continue
            issue = get_issue(issue_key)
            actual_email = issue.assignee_email
            print(
                f"{assignment.task_title} ({issue_key}) assignee_email: "
                f"expected={REAL_EMAIL}, actual={actual_email}"
            )
            if actual_email != REAL_EMAIL:
                email_matches = False

        add_result(
            "REAL ASSIGNMENT CHECK",
            email_matches,
            f"{len(assignments)} assignments completed and verified",
        )
    except (JiraClientError, TeamMemberNotFoundError, RuntimeError, ValueError) as error:
        add_result("REAL ASSIGNMENT CHECK", False, str(error))
    except Exception as error:
        add_result("REAL ASSIGNMENT CHECK", False, str(error))


def print_summary() -> None:
    """Print the final real assignment verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<32} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<32} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run the live assignment check and print its summary."""
    run_real_assignment_check()
    print_summary()


if __name__ == "__main__":
    main()
