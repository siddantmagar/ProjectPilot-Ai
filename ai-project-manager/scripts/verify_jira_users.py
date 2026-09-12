"""Standalone verification harness for Jira user lookups.

Run from the project root with:
    python -m scripts.verify_jira_users
"""

import os

from app.integrations.jira.client import (
    JiraClientError,
    get_account_id_by_email,
    get_assignable_users_for_project,
)
from app.integrations.jira.schemas import JiraUserResponse


results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def run_resolve_own_email_check() -> None:
    """Verify that the configured Jira login email resolves to one account."""
    email = os.getenv("JIRA_EMAIL")
    if not email:
        add_result(
            "RESOLVE OWN EMAIL CHECK",
            False,
            "JIRA_EMAIL is not configured",
        )
        return

    try:
        result = get_account_id_by_email(email)
        passed = isinstance(result, JiraUserResponse) and bool(result.account_id)
        print(f"Resolved Jira account: {result.account_id} ({result.display_name})")
        add_result(
            "RESOLVE OWN EMAIL CHECK",
            passed,
            f"account_id={result.account_id}, display_name={result.display_name}",
        )
    except Exception as error:
        add_result("RESOLVE OWN EMAIL CHECK", False, str(error))


def run_unknown_email_check() -> None:
    """Verify that an unknown email is translated into a 404 client error."""
    try:
        get_account_id_by_email("definitely-not-a-real-user-xyz@example.com")
    except JiraClientError as error:
        add_result(
            "UNKNOWN EMAIL CHECK",
            error.status_code == 404,
            f"status_code={error.status_code}: {error}",
        )
    except Exception as error:
        add_result("UNKNOWN EMAIL CHECK", False, str(error))
    else:
        add_result("UNKNOWN EMAIL CHECK", False, "No JiraClientError was raised")


def run_assignable_users_check() -> None:
    """Verify that the configured project returns at least one assignable user."""
    try:
        users = get_assignable_users_for_project()
        passed = bool(users) and all(isinstance(user, JiraUserResponse) for user in users)
        print("Assignable Jira users:")
        for user in users:
            print(f"- {user.display_name}")
        add_result(
            "ASSIGNABLE USERS CHECK",
            passed,
            f"{len(users)} assignable user(s)",
        )
    except Exception as error:
        add_result("ASSIGNABLE USERS CHECK", False, str(error))


def print_summary() -> None:
    """Print the final Jira user verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<32} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<32} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all Jira user checks and print their combined report."""
    run_resolve_own_email_check()
    run_unknown_email_check()
    run_assignable_users_check()
    print_summary()


if __name__ == "__main__":
    main()
