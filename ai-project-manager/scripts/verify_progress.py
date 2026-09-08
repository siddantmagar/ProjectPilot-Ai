"""Standalone verification harness for the deterministic progress agent.

Run from the project root with:
    python -m scripts.verify_progress
"""

from app.agents.progress import run_progress_agent
from app.models.progress import TaskStatusEntry
from app.models.task import Task


# Store every check result so the final report can be generated consistently.
results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def sample_tasks() -> list[Task]:
    """Create the three tasks shared by the normal status checks."""
    return [
        Task(title="Build API", description="Create API endpoints", priority="high", estimated_days=5, epic="Backend"),
        Task(title="Write tests", description="Add automated tests", priority="medium", estimated_days=3, epic="Quality"),
        Task(title="Deploy app", description="Deploy the application", priority="low", estimated_days=2, epic="Release"),
    ]


def run_normal_mixed_status_check() -> None:
    """Verify counts and title lists for a mixed project snapshot."""
    tasks = sample_tasks()
    statuses = [
        TaskStatusEntry(task_title="Build API", status="done"),
        TaskStatusEntry(task_title="Write tests", status="in_progress"),
        TaskStatusEntry(task_title="Deploy app", status="blocked", is_overdue=True),
    ]
    try:
        output = run_progress_agent(tasks, statuses)
        passed = (
            output.total_tasks == 3
            and output.completed_tasks == 1
            and output.completion_percent == 33.3
            and len(output.blocked_task_titles) == 1
            and len(output.overdue_task_titles) == 1
        )
        add_result(
            "NORMAL MIXED-STATUS CHECK",
            passed,
            f"{output.completed_tasks}/" f"{output.total_tasks} complete, {output.completion_percent}%",
        )
    except Exception as error:
        add_result("NORMAL MIXED-STATUS CHECK", False, str(error))


def run_all_done_check() -> None:
    """Verify that three completed tasks produce exactly 100 percent progress."""
    tasks = sample_tasks()
    statuses = [TaskStatusEntry(task_title=task.title, status="done") for task in tasks]
    try:
        output = run_progress_agent(tasks, statuses)
        add_result("ALL DONE CHECK", output.completion_percent == 100.0, f"{output.completion_percent}% complete")
    except Exception as error:
        add_result("ALL DONE CHECK", False, str(error))


def run_all_todo_check() -> None:
    """Verify that no completed tasks produce zero percent progress."""
    tasks = sample_tasks()
    statuses = [TaskStatusEntry(task_title=task.title, status="todo") for task in tasks]
    try:
        output = run_progress_agent(tasks, statuses)
        passed = output.completion_percent == 0.0 and output.completed_tasks == 0
        add_result("ALL TODO CHECK", passed, f"{output.completed_tasks} complete, {output.completion_percent}% complete")
    except Exception as error:
        add_result("ALL TODO CHECK", False, str(error))


def run_empty_task_list_check() -> None:
    """Verify that an empty project raises ValueError instead of reporting zero percent."""
    try:
        run_progress_agent([], [])
    except ValueError as error:
        add_result("EMPTY TASK LIST CHECK", True, f"ValueError raised: {error}")
    except ZeroDivisionError as error:
        add_result("EMPTY TASK LIST CHECK", False, f"Unexpected ZeroDivisionError: {error}")
    else:
        add_result("EMPTY TASK LIST CHECK", False, "No ValueError was raised")


def run_mismatched_titles_check() -> None:
    """Verify that a missing status title is rejected and reported by name."""
    tasks = [
        Task(title="A", description="Task A", priority="low", estimated_days=1, epic="E"),
        Task(title="B", description="Task B", priority="low", estimated_days=1, epic="E"),
    ]
    statuses = [TaskStatusEntry(task_title="A", status="todo")]
    try:
        run_progress_agent(tasks, statuses)
    except ValueError as error:
        message = str(error)
        add_result("MISMATCHED TITLES CHECK", "B" in message, f"ValueError: {message}")
    else:
        add_result("MISMATCHED TITLES CHECK", False, "No ValueError was raised")


def run_duplicate_status_entry_check() -> None:
    """Verify that duplicate status entries fail the explicit length guard."""
    tasks = [Task(title="A", description="Task A", priority="low", estimated_days=1, epic="E")]
    statuses = [
        TaskStatusEntry(task_title="A", status="done"),
        TaskStatusEntry(task_title="A", status="blocked"),
    ]
    try:
        run_progress_agent(tasks, statuses)
    except ValueError as error:
        message = str(error)
        passed = "Expected exactly one status entry per task" in message
        add_result("DUPLICATE STATUS ENTRY CHECK", passed, f"ValueError: {message}")
    else:
        add_result("DUPLICATE STATUS ENTRY CHECK", False, "No ValueError was raised")


def print_summary() -> None:
    """Print the final progress verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<38} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<38} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all progress checks and print their combined report."""
    run_normal_mixed_status_check()
    run_all_done_check()
    run_all_todo_check()
    run_empty_task_list_check()
    run_mismatched_titles_check()
    run_duplicate_status_entry_check()
    print_summary()


if __name__ == "__main__":
    main()
