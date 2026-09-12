"""Standalone verification harness for live Jira status synchronization.

WARNING: This script creates two REAL Jira issues in the configured project.
After the first status check, manually transition exactly one printed issue to
In Progress in Jira, then press Enter so the second sync can verify the change.

Run from the project root with:
    python -m scripts.verify_status_sync
"""

import uuid

from app.graph.nodes import jira_creation_node, status_sync_node
from app.models.task import PlannerOutput, Task


results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def build_state() -> dict:
    """Build a two-task state whose issues are created during this run."""
    suffix = uuid.uuid4().hex[:10]
    planner_output = PlannerOutput(
        epics=["Verification"],
        tasks=[
            Task(
                title=f"Verify status sync A {suffix}",
                description="Temporary task for live Jira status sync verification.",
                priority="medium",
                estimated_days=1,
                epic="Verification",
            ),
            Task(
                title=f"Verify status sync B {suffix}",
                description="Temporary task for live Jira status sync verification.",
                priority="medium",
                estimated_days=1,
                epic="Verification",
            ),
        ],
    )
    return {
        "goal": "Verify Jira status synchronization",
        "deadline": "sandbox verification",
        "team_size": 0,
        "team": [],
        "planner_output": planner_output,
        "jira_issue_keys": {},
    }


def status_by_title(statuses: list) -> dict[str, str]:
    """Index internal status values by task title."""
    return {status.task_title: status.status for status in statuses}


def print_summary() -> None:
    """Print the final status synchronization summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<42} {'STATUS':<8} DETAIL")
    print("-" * 115)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<42} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run initial and post-transition Jira status synchronization checks."""
    state = build_state()
    task_titles = [task.title for task in state["planner_output"].tasks]

    try:
        state.update(jira_creation_node(state))
        print(f"Created/reused Jira issue keys: {state['jira_issue_keys']}")

        first_sync = status_sync_node(state)
        first_statuses = first_sync["statuses"]
        first_by_title = status_by_title(first_statuses)
        first_passed = (
            len(first_statuses) == len(task_titles)
            and all(first_by_title.get(title) == "todo" for title in task_titles)
        )
        add_result(
            "INITIAL STATUS SYNC CHECK",
            first_passed,
            f"Initial statuses: {first_by_title}",
        )
        if not first_passed:
            print_summary()
            return

        print("\nTransition exactly one of these Jira issues to 'In Progress' in the Jira UI:")
        for title, issue_key in state["jira_issue_keys"].items():
            print(f"- {issue_key}: {title}")
        transitioned_key = input(
            "Enter the issue key you transitioned, then press Enter: "
        ).strip()
        if transitioned_key not in state["jira_issue_keys"].values():
            add_result(
                "LIVE STATUS TRANSITION CHECK",
                False,
                f"Unknown issue key entered: {transitioned_key}",
            )
            print_summary()
            return

        second_statuses = status_sync_node(state)["statuses"]
        second_by_title = status_by_title(second_statuses)
        transitioned_title = next(
            title
            for title, issue_key in state["jira_issue_keys"].items()
            if issue_key == transitioned_key
        )
        other_titles = [title for title in task_titles if title != transitioned_title]
        second_passed = (
            len(second_statuses) == len(task_titles)
            and second_by_title.get(transitioned_title) == "in_progress"
            and all(second_by_title.get(title) == "todo" for title in other_titles)
        )
        add_result(
            "LIVE STATUS TRANSITION CHECK",
            second_passed,
            f"After transition: {second_by_title}; transitioned={transitioned_key}",
        )
    except Exception as error:
        add_result("STATUS SYNC WORKFLOW CHECK", False, str(error))

    print_summary()


if __name__ == "__main__":
    main()
