"""Standalone verification harness for the Jira integration.

WARNING: CREATE ISSUE CHECK creates a REAL issue in the AIPM project on every
run. This is expected and fine for a sandbox project, but worth knowing.

Run from the project root with:
    python -m scripts.verify_jira
"""

import os

from app.integrations.jira.client import (
    JiraClientError,
    create_issue,
    get_issue,
)
from app.integrations.jira.schemas import JiraIssueCreateResponse, JiraIssueResponse


results: list[dict[str, str]] = []
created_issue_key: str | None = None
created_summary = "Test task from Project Pilot AI"


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def run_create_issue_check() -> None:
    """Verify that Jira accepts a real issue creation request."""
    global created_issue_key

    try:
        result = create_issue(
            created_summary,
            "Verifying Jira integration works end to end.",
            issue_type="Task",
        )
        created_issue_key = result.key
        passed = isinstance(result, JiraIssueCreateResponse) and bool(result.key)
        print(f"Created issue key: {result.key}")
        add_result("CREATE ISSUE CHECK", passed, f"key={result.key}")
    except Exception as error:
        add_result("CREATE ISSUE CHECK", False, str(error))


def run_get_issue_check() -> None:
    """Verify that the created Jira issue can be retrieved and parsed."""
    if created_issue_key is None:
        add_result("GET ISSUE CHECK", False, "Skipped because issue creation failed")
        return

    try:
        result = get_issue(created_issue_key)
        passed = (
            isinstance(result, JiraIssueResponse)
            and result.summary == created_summary
            and bool(result.status)
        )
        print(f"Retrieved issue: {result}")
        add_result(
            "GET ISSUE CHECK",
            passed,
            f"summary={result.summary!r}, status={result.status!r}",
        )
    except Exception as error:
        add_result("GET ISSUE CHECK", False, str(error))


def run_invalid_issue_key_check() -> None:
    """Verify that a missing Jira issue produces a structured 404 error."""
    try:
        get_issue("AIPM-999999")
    except JiraClientError as error:
        passed = error.status_code == 404
        add_result(
            "INVALID ISSUE KEY CHECK",
            passed,
            f"status_code={error.status_code}: {error}",
        )
    except Exception as error:
        add_result("INVALID ISSUE KEY CHECK", False, str(error))
    else:
        add_result("INVALID ISSUE KEY CHECK", False, "No JiraClientError was raised")


def run_missing_config_check() -> None:
    """Verify that a missing API token is reported before any HTTP request."""
    original_token = os.environ.get("JIRA_API_TOKEN")
    os.environ.pop("JIRA_API_TOKEN", None)
    try:
        try:
            create_issue("Configuration check", "The request should not be sent.")
        except ValueError as error:
            passed = "JIRA_API_TOKEN" in str(error)
            add_result("MISSING CONFIG CHECK", passed, str(error))
        except Exception as error:
            add_result("MISSING CONFIG CHECK", False, str(error))
        else:
            add_result("MISSING CONFIG CHECK", False, "No ValueError was raised")
    finally:
        if original_token is None:
            os.environ.pop("JIRA_API_TOKEN", None)
        else:
            os.environ["JIRA_API_TOKEN"] = original_token


def print_summary() -> None:
    """Print the final Jira verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<30} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<30} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all Jira checks and print their combined report."""
    run_create_issue_check()
    run_get_issue_check()
    run_invalid_issue_key_check()
    run_missing_config_check()
    print_summary()


if __name__ == "__main__":
    main()
