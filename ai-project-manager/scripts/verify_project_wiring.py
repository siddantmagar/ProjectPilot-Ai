"""Standalone verification harness for project ID graph wiring.

WARNING: The approve path runs the full pipeline and creates REAL Jira issues
in the configured project. It also writes project, link, and audit records.

Run from the project root with:
    python -m scripts.verify_project_wiring
"""

import uuid

from dotenv import load_dotenv
from langgraph.types import Command

from app.database.connection import SessionLocal
from app.database.repositories import (
    AuditLogRepository,
    ProjectRepository,
    TaskJiraLinkRepository,
)
from app.graph.workflow import build_workflow


load_dotenv()
results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def print_summary() -> None:
    """Print the final project wiring verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<42} {'STATUS':<8} DETAIL")
    print("-" * 115)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<42} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run the approved graph and verify project-scoped persistence wiring."""
    suffix = uuid.uuid4().hex[:10]
    goal = f"Verify project wiring {suffix}"
    config = {"configurable": {"thread_id": f"project-wiring-{suffix}"}}
    state = {
        "goal": goal,
        "deadline": "2 weeks",
        "team_size": 2,
        "team": [],
    }
    try:
        graph = build_workflow()
        paused_state = graph.invoke(state, config=config)
        if "__interrupt__" not in paused_state:
            add_result(
                "APPROVAL INTERRUPT CHECK",
                False,
                "Graph did not pause before Jira creation",
            )
            print_summary()
            return
        add_result("APPROVAL INTERRUPT CHECK", True, "Plan approval interrupt received")

        final_state = graph.invoke(
            Command(resume={"action": "approve"}),
            config=config,
        )
        pipeline_complete = (
            "jira_issue_keys" in final_state and "report_output" in final_state
        )
        add_result(
            "APPROVED PIPELINE CHECK",
            pipeline_complete,
            "Full pipeline completed" if pipeline_complete else "Final outputs missing",
        )
        if not pipeline_complete:
            print_summary()
            return

        project_id = final_state.get("project_id")
        project_passed = isinstance(project_id, int)
        add_result(
            "FINAL PROJECT ID CHECK",
            project_passed,
            f"final_state project_id={project_id}",
        )
        if not project_passed:
            print_summary()
            return

        session = SessionLocal()
        try:
            project = ProjectRepository(session).get_by_id(project_id)
            project_passed = project["goal"] == goal
            add_result(
                "PROJECT ROW CHECK",
                project_passed,
                f"project_id={project_id}, goal={goal!r}",
            )
            if not project_passed:
                print_summary()
                return

            links = TaskJiraLinkRepository(session).list_for_project(project_id)
            expected_titles = set(final_state.get("jira_issue_keys", {}))
            link_titles = {link["task_title"] for link in links}
            links_passed = (
                link_titles == expected_titles
                and len(links) == len(final_state["planner_output"].tasks)
                and all(link["project_id"] == project_id for link in links)
            )
            add_result(
                "TASK LINK PROJECT ID CHECK",
                links_passed,
                f"{len(links)} link(s) carry project_id={project_id}",
            )

            audit_entries = AuditLogRepository(session).list_for_project_id(project_id)
            audit_passed = bool(audit_entries)
            add_result(
                "AUDIT PROJECT ID CHECK",
                audit_passed,
                f"{len(audit_entries)} audit entr(y/ies) carry project_id={project_id}",
            )
        finally:
            session.close()
    except Exception as error:
        add_result("PROJECT WIRING CHECK", False, str(error))

    print_summary()


if __name__ == "__main__":
    main()
