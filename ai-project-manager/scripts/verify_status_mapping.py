"""Standalone verification harness for Jira status mapping.

Run from the project root with:
    python -m scripts.verify_status_mapping
"""

from app.integrations.jira.client import search_issues_by_project
from app.integrations.jira.status_map import map_jira_status


VALID_INTERNAL_STATUSES = {"todo", "in_progress", "done", "blocked", "unknown"}
results: list[dict[str, str]] = []
fetched_issues: list[dict] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def run_fetch_real_issues_check() -> None:
    """Verify that the configured AIPM project returns raw issues."""
    global fetched_issues

    try:
        fetched_issues = search_issues_by_project()
        passed = bool(fetched_issues)
        for issue in fetched_issues:
            fields = issue["fields"]
            print(f"{issue['key']}: {fields['status']['name']}")
        add_result(
            "FETCH REAL ISSUES CHECK",
            passed,
            f"Fetched {len(fetched_issues)} issue(s)",
        )
    except Exception as error:
        add_result("FETCH REAL ISSUES CHECK", False, str(error))


def run_mapping_check() -> None:
    """Verify that every fetched Jira status maps to a valid internal value."""
    if not fetched_issues:
        add_result("MAPPING CHECK", False, "Skipped because no issues were fetched")
        return

    try:
        mapped_values: list[str] = []
        for issue in fetched_issues:
            fields = issue["fields"]
            jira_status = fields["status"]["name"]
            category = fields["status"]["statusCategory"]["name"]
            internal_status = map_jira_status("AIPM", jira_status, category)
            mapped_values.append(internal_status)
            print(
                f"{issue['key']}: Jira={jira_status!r}, "
                f"category={category!r}, internal={internal_status!r}"
            )
        passed = all(status in VALID_INTERNAL_STATUSES for status in mapped_values)
        add_result(
            "MAPPING CHECK",
            passed,
            f"Mapped {len(mapped_values)} issue status(es)",
        )
    except Exception as error:
        add_result("MAPPING CHECK", False, str(error))


def run_unmapped_status_fallback_check() -> None:
    """Verify that an unknown status name falls back to its Jira category."""
    try:
        result = map_jira_status(
            "AIPM",
            "SomeRandomStatusThatDoesNotExist",
            "In Progress",
        )
        add_result(
            "UNMAPPED STATUS FALLBACK CHECK",
            result == "in_progress",
            f"Mapped unknown status to {result!r}",
        )
    except Exception as error:
        add_result("UNMAPPED STATUS FALLBACK CHECK", False, str(error))


def print_summary() -> None:
    """Print the final status mapping verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<38} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<38} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all Jira status mapping checks and print their combined report."""
    run_fetch_real_issues_check()
    run_mapping_check()
    run_unmapped_status_fallback_check()
    print_summary()


if __name__ == "__main__":
    main()
