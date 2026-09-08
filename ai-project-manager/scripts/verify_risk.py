"""Standalone verification harness for the risk agent.

Run from the project root with:
    python -m scripts.verify_risk
"""

import io
import json
import logging
import re
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator

from app.agents import risk
from app.agents.risk import RiskValidationError, run_risk_agent
from app.models.progress import TaskStatusEntry
from app.models.risk import RiskOutput
from app.models.task import Task


# Store every check result so the final report can be generated consistently.
results: list[dict[str, str]] = []
obvious_risk_output: RiskOutput | None = None


@contextmanager
def capture_risk_logs() -> Iterator[io.StringIO]:
    """Capture risk INFO logs for one check, then restore logging state."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    risk.logger.addHandler(handler)
    previous_level = risk.logger.level
    risk.logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        risk.logger.removeHandler(handler)
        risk.logger.setLevel(previous_level)


def attempt_count(log_text: str) -> int:
    """Count unique risk attempt numbers present in captured logs."""
    return len(set(re.findall(r"Risk attempt (\d+) of 3", log_text)))


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def make_task(
    title: str,
    description: str,
    priority: str,
    estimated_days: int,
) -> Task:
    """Build a task with the standard task model fields."""
    return Task(
        title=title,
        description=description,
        priority=priority,
        estimated_days=estimated_days,
        epic="Verification",
    )


def run_healthy_project_check() -> None:
    """Verify that a healthy project returns no fabricated risks."""
    tasks = [
        make_task("Build API", "Create API endpoints", "high", 5),
        make_task("Write tests", "Add automated tests", "medium", 3),
        make_task("Deploy app", "Deploy the application", "low", 2),
    ]
    statuses = [
        TaskStatusEntry(task_title="Build API", status="in_progress"),
        TaskStatusEntry(task_title="Write tests", status="done"),
        TaskStatusEntry(task_title="Deploy app", status="in_progress"),
    ]
    try:
        with capture_risk_logs() as log_stream:
            output = run_risk_agent(tasks, statuses)
        passed = output.risks == []
        if not passed:
            print("\nHealthy-project invented-risk details:")
            for item in output.risks:
                print(f"- {item.task_title} [{item.risk_level}]: {item.reason}")
        add_result(
            "HEALTHY PROJECT CHECK",
            passed,
            f"{len(output.risks)} risks, {attempt_count(log_stream.getvalue())} attempt(s)",
        )
    except Exception as error:
        add_result("HEALTHY PROJECT CHECK", False, str(error))


def obvious_risk_tasks() -> list[Task]:
    """Create the three tasks used by the obvious-risk and grounding checks."""
    return [
        make_task("Resolve payment outage", "Restore payment processing", "high", 5),
        make_task("Write tests", "Add automated tests", "medium", 3),
        make_task("Deploy app", "Deploy the application", "low", 2),
    ]


def obvious_risk_statuses() -> list[TaskStatusEntry]:
    """Create one severe risk and two healthy task statuses."""
    return [
        TaskStatusEntry(
            task_title="Resolve payment outage",
            status="blocked",
            is_overdue=True,
        ),
        TaskStatusEntry(task_title="Write tests", status="in_progress"),
        TaskStatusEntry(task_title="Deploy app", status="done"),
    ]


def run_obvious_risk_check() -> None:
    """Verify that an obvious blocked, overdue, high-priority task is high risk."""
    global obvious_risk_output

    try:
        tasks = obvious_risk_tasks()
        with capture_risk_logs() as log_stream:
            output = run_risk_agent(tasks, obvious_risk_statuses())
        obvious_risk_output = output
        risky_title = "Resolve payment outage"
        matching_risks = [risk for risk in output.risks if risk.task_title == risky_title]
        passed = bool(output.risks) and bool(matching_risks) and matching_risks[0].risk_level == "high"
        add_result(
            "OBVIOUS RISK CHECK",
            passed,
            f"{len(output.risks)} risks, {attempt_count(log_stream.getvalue())} attempt(s); "
            f"{risky_title}: {matching_risks[0].risk_level if matching_risks else 'missing'}",
        )
    except Exception as error:
        add_result("OBVIOUS RISK CHECK", False, str(error))


def run_severity_ordering_check() -> None:
    """Verify that a severe blocked risk ranks at least as high as a low overdue risk."""
    tasks = [
        make_task("Resolve outage", "Restore the service", "high", 5),
        make_task("Update documentation", "Refresh user documentation", "low", 2),
        make_task("Write tests", "Add automated tests", "medium", 3),
        make_task("Deploy app", "Deploy the application", "medium", 2),
    ]
    statuses = [
        TaskStatusEntry(task_title="Resolve outage", status="blocked", is_overdue=True),
        TaskStatusEntry(task_title="Update documentation", status="in_progress", is_overdue=True),
        TaskStatusEntry(task_title="Write tests", status="in_progress"),
        TaskStatusEntry(task_title="Deploy app", status="done"),
    ]
    severity = {"low": 1, "medium": 2, "high": 3}
    try:
        with capture_risk_logs() as log_stream:
            output = run_risk_agent(tasks, statuses)
        by_title = {item.task_title: item for item in output.risks}
        severe = by_title.get("Resolve outage")
        overdue_low = by_title.get("Update documentation")
        passed = (
            severe is not None
            and overdue_low is not None
            and severity[severe.risk_level] >= severity[overdue_low.risk_level]
        )
        severe_level = severe.risk_level if severe else "missing"
        overdue_level = overdue_low.risk_level if overdue_low else "missing"
        details = (
            f"Resolve outage={severe_level}, Update documentation={overdue_level}; "
            f"{attempt_count(log_stream.getvalue())} attempt(s)"
        )
        print(f"Severity manual review: Resolve outage={severe_level}; Update documentation={overdue_level}")
        add_result("SEVERITY ORDERING CHECK", passed, details)
    except Exception as error:
        add_result("SEVERITY ORDERING CHECK", False, str(error))


def run_grounding_sanity_check() -> None:
    """Print obvious-risk reasons for manual grounding review."""
    if obvious_risk_output is None:
        add_result("GROUNDING SANITY CHECK", False, "No check 2 output available")
        return

    print("\nGrounding sanity details:")
    for item in obvious_risk_output.risks:
        print(f"- {item.task_title}: {item.reason}")
    add_result(
        "GROUNDING SANITY CHECK",
        True,
        "Printed each check 2 reason for manual review",
    )


def mocked_response(content: str) -> SimpleNamespace:
    """Wrap JSON text in the response shape returned by Ollama."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


def run_forced_hallucinated_task_check() -> None:
    """Verify that an unknown task title triggers the grounding retry guard."""
    tasks = obvious_risk_tasks()
    hallucinated_payload = json.dumps(
        {
            "risks": [
                {
                    "task_title": "Invented task",
                    "risk_level": "high",
                    "reason": "The task is blocked.",
                    "recommendation": "Escalate it.",
                }
            ]
        }
    )
    original_chat = risk.chat
    risk.chat = lambda **kwargs: mocked_response(hallucinated_payload)
    try:
        with capture_risk_logs() as log_stream:
            try:
                run_risk_agent(tasks, obvious_risk_statuses())
            except RiskValidationError as error:
                logs = log_stream.getvalue()
                attempts = attempt_count(logs)
                passed = attempts > 1
                details = f"{attempts} attempts before RiskValidationError: {error}"
            else:
                logs = log_stream.getvalue()
                attempts = attempt_count(logs)
                passed = attempts > 1
                details = f"retry count: {attempts}"
        print("\nForced hallucinated-task log lines:")
        print(logs.strip())
        add_result("FORCED HALLUCINATED TASK CHECK", passed, details)
    finally:
        risk.chat = original_chat


def print_summary() -> None:
    """Print the final risk verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<40} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<40} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all risk checks and print their combined report."""
    run_healthy_project_check()
    run_obvious_risk_check()
    run_severity_ordering_check()
    run_grounding_sanity_check()
    run_forced_hallucinated_task_check()
    print_summary()


if __name__ == "__main__":
    main()
