"""Standalone verification harness for the idempotent Jira creation node.

WARNING: This script creates two REAL Jira issues in the configured project on
its first run. The links are intentionally persisted so the second run reuses
them; task titles include a unique run ID to avoid colliding with old checks.

Run from the project root with:
    python -m scripts.verify_jira_creation_node
"""

import re
import uuid

from app.graph.nodes import jira_creation_node
from app.models.task import PlannerOutput, Task


results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def sample_state() -> dict:
    """Build two uniquely titled Planner tasks for this verification run."""
    run_id = uuid.uuid4().hex[:10]
    tasks = [
        Task(
            title=f"Verify Jira creation A {run_id}",
            description="Temporary task for Jira creation idempotency verification.",
            priority="medium",
            estimated_days=1,
            epic="Verification",
        ),
        Task(
            title=f"Verify Jira creation B {run_id}",
            description="Temporary task for Jira creation idempotency verification.",
            priority="medium",
            estimated_days=1,
            epic="Verification",
        ),
    ]
    return {"planner_output": PlannerOutput(epics=["Verification"], tasks=tasks)}


def issue_keys_look_real(issue_keys: dict[str, str]) -> bool:
    """Check that returned values resemble Jira project-number issue keys."""
    return len(issue_keys) == 2 and all(
        re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", key) for key in issue_keys.values()
    )


def print_summary() -> None:
    """Print the final Jira creation verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<38} {'STATUS':<8} DETAIL")
    print("-" * 110)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<38} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run the two-run Jira creation idempotency verification."""
    state = sample_state()
    try:
        first_result = jira_creation_node(state)
        first_keys = first_result["jira_issue_keys"]
        print(f"First run Jira issue keys: {first_keys}")
        first_passed = issue_keys_look_real(first_keys)
        add_result(
            "FIRST RUN CREATES ISSUES",
            first_passed,
            f"Created/retrieved 2 Jira issue keys: {first_keys}",
        )
    except Exception as error:
        first_keys = {}
        add_result("FIRST RUN CREATES ISSUES", False, str(error))

    if not first_keys:
        add_result(
            "SECOND RUN REUSES ISSUES",
            False,
            "Skipped because the first run did not return issue keys",
        )
        print_summary()
        return

    try:
        second_result = jira_creation_node(state)
        second_keys = second_result["jira_issue_keys"]
        print(f"Second run Jira issue keys: {second_keys}")
        passed = second_keys == first_keys
        add_result(
            "SECOND RUN REUSES ISSUES",
            passed,
            f"First run: {first_keys}; second run: {second_keys}",
        )
    except Exception as error:
        add_result("SECOND RUN REUSES ISSUES", False, str(error))

    print_summary()


if __name__ == "__main__":
    main()
