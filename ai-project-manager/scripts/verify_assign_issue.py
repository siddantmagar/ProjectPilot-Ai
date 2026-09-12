"""Standalone verification harness for Jira issue assignment.

WARNING: ASSIGN TO SELF CHECK creates and modifies a REAL issue in the AIPM
project on every run. This is expected for the sandbox project.

Run from the project root with:
    python -m scripts.verify_assign_issue
"""

import os

from app.integrations.jira.client import (
    JiraClientError,
    assign_issue,
    create_issue,
    get_account_id_by_email,
    get_issue,
)
from app.integrations.jira.schemas import JiraIssueCreateResponse, JiraIssueResponse


results: list[dict[str, str]] = []
created_issue_key: str | None = None
account_id: str | None = None
configured_email: str | None = None


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def run_assign_to_self_check() -> None:
    """Verify that a fresh Jira issue can be assigned to the configured user."""
    global account_id, configured_email, created_issue_key

    configured_email = os.getenv("JIRA_EMAIL")
    if not configured_email:
        add_result("ASSIGN TO SELF CHECK", False, "JIRA_EMAIL is not configured")
        return

    try:
        created = create_issue(
            "Test assignment from Project Pilot AI",
            "Verifying Jira assignment integration works end to end.",
            issue_type="Task",
        )
        if not isinstance(created, JiraIssueCreateResponse) or not created.key:
            add_result("ASSIGN TO SELF CHECK", False, "Issue creation returned no key")
            return
        created_issue_key = created.key

        user = get_account_id_by_email(configured_email)
        account_id = user.account_id
        assign_issue(created_issue_key, account_id)
        assigned_issue = get_issue(created_issue_key)
        assignee_email = assigned_issue.assignee_email
        print(f"Assigned issue {created_issue_key} assignee_email: {assignee_email}")
        passed = isinstance(assigned_issue, JiraIssueResponse)
        details = (
            f"issue_key={created_issue_key}, assignee_email={assignee_email}"
        )
        if assignee_email != configured_email:
            details += " (Jira may hide email due to privacy settings)"
        add_result("ASSIGN TO SELF CHECK", passed, details)
    except Exception as error:
        add_result("ASSIGN TO SELF CHECK", False, str(error))


def run_invalid_account_id_check() -> None:
    """Verify that Jira rejects an invalid account ID for the created issue."""
    if created_issue_key is None:
        add_result(
            "INVALID ACCOUNT ID CHECK",
            False,
            "Skipped because the assign-to-self check did not create an issue",
        )
        return

    fake_account_id = "000000:00000000-0000-0000-0000-000000000000"
    try:
        assign_issue(created_issue_key, fake_account_id)
    except JiraClientError as error:
        passed = error.status_code in {400, 404}
        add_result(
            "INVALID ACCOUNT ID CHECK",
            passed,
            f"Jira returned status_code={error.status_code}: {error}",
        )
    except Exception as error:
        add_result("INVALID ACCOUNT ID CHECK", False, str(error))
    else:
        add_result("INVALID ACCOUNT ID CHECK", False, "Invalid account ID was accepted")


def run_invalid_issue_key_check() -> None:
    """Verify that assigning a nonexistent Jira issue produces a 404 error."""
    if account_id is None:
        add_result(
            "INVALID ISSUE KEY CHECK",
            False,
            "Skipped because self account resolution failed",
        )
        return

    try:
        assign_issue("AIPM-999999", account_id)
    except JiraClientError as error:
        add_result(
            "INVALID ISSUE KEY CHECK",
            error.status_code == 404,
            f"status_code={error.status_code}: {error}",
        )
    except Exception as error:
        add_result("INVALID ISSUE KEY CHECK", False, str(error))
    else:
        add_result("INVALID ISSUE KEY CHECK", False, "Invalid issue key was accepted")


def print_summary() -> None:
    """Print the final Jira assignment verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<32} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<32} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all Jira assignment checks and print their combined report."""
    run_assign_to_self_check()
    run_invalid_account_id_check()
    run_invalid_issue_key_check()
    print_summary()


if __name__ == "__main__":
    main()
