"""Standalone verification harness for the assignment agent.

Run from the project root with:
    python -m scripts.verify_assignment
"""

import io
import json
import logging
import re
from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator

from app.agents import assignment
from app.agents.assignment import AssignmentValidationError, run_assignment_agent
from app.models.task import Task
from app.models.team import SAMPLE_TEAM, TeamMember


# Store every check result so the final report can be generated consistently.
results: list[dict[str, str]] = []


@contextmanager
def capture_assignment_logs() -> Iterator[io.StringIO]:
    """Capture assignment INFO logs for one check, then restore logging state."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    assignment.logger.addHandler(handler)
    previous_level = assignment.logger.level
    assignment.logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        assignment.logger.removeHandler(handler)
        assignment.logger.setLevel(previous_level)


def attempt_count(log_text: str) -> int:
    """Count unique assignment attempt numbers present in captured logs."""
    return len(set(re.findall(r"Assignment attempt (\d+) of 3", log_text)))


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def sample_tasks() -> list[Task]:
    """Create three tasks covering strong and weak skill-match scenarios."""
    return [
        Task(
            title="Build data processing service",
            description="Implement Python data processing and validation logic.",
            priority="high",
            estimated_days=8,
            epic="Backend",
        ),
        Task(
            title="Create FastAPI endpoints",
            description="Expose the application through FastAPI REST endpoints.",
            priority="high",
            estimated_days=5,
            epic="Backend",
        ),
        Task(
            title="Prepare launch announcement",
            description="Write a product announcement for the launch.",
            priority="medium",
            estimated_days=2,
            epic="Launch",
        ),
    ]


def assignment_payload(tasks: list[Task], assignee: str = "Rahul") -> str:
    """Create valid JSON assignments for the supplied task list."""
    return json.dumps(
        {
            "assignments": [
                {
                    "task_title": task.title,
                    "recommended_assignee": assignee,
                    "reason": "Selected based on the available skill match and workload.",
                }
                for task in tasks
            ]
        }
    )


def mocked_response(content: str) -> SimpleNamespace:
    """Wrap JSON text in the response shape returned by Ollama."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


def run_basic_and_sanity_checks() -> None:
    """Run one real assignment call for basic validation and human-readable review."""
    tasks = sample_tasks()
    with capture_assignment_logs() as log_stream:
        try:
            # Use one batch call for both the automated grounding check and visual review.
            output = run_assignment_agent(tasks, SAMPLE_TEAM)
            task_titles = [task.title for task in tasks]
            assigned_titles = [item.task_title for item in output.assignments]
            assigned_names = {item.recommended_assignee for item in output.assignments}
            expected_names = {member.name for member in SAMPLE_TEAM}
            passed = (
                Counter(assigned_titles) == Counter(task_titles)
                and assigned_names <= expected_names
                and len(output.assignments) == len(tasks)
            )
            details = f"{len(output.assignments)} assignments, {attempt_count(log_stream.getvalue())} attempt(s)"
            add_result("BASIC ASSIGNMENT CHECK", passed, details)

            # Print every assignment so skill choices can be judged by a person.
            print("\nSkill-match sanity details:")
            for item in output.assignments:
                print(f"- {item.task_title} -> {item.recommended_assignee}: {item.reason}")
            add_result(
                "SKILL-MATCH SANITY CHECK",
                True,
                "Printed task, assignee, and reason for manual review",
            )
        except Exception as error:
            add_result("BASIC ASSIGNMENT CHECK", False, str(error))
            add_result("SKILL-MATCH SANITY CHECK", False, "No assignment output available")


def run_forced_hallucination_check() -> None:
    """Verify that an assignee outside the roster triggers the grounding guard."""
    tasks = sample_tasks()
    original_chat = assignment.chat
    assignment.chat = lambda **kwargs: mocked_response(assignment_payload(tasks, "David"))
    try:
        with capture_assignment_logs() as log_stream:
            try:
                run_assignment_agent(tasks, SAMPLE_TEAM)
            except AssignmentValidationError as error:
                logs = log_stream.getvalue()
                passed = attempt_count(logs) > 1
                details = f"{attempt_count(logs)} attempts before AssignmentValidationError: {error}"
            else:
                logs = log_stream.getvalue()
                passed = attempt_count(logs) > 1
                details = f"retry count: {attempt_count(logs)}"
        print("\nForced hallucination log lines:")
        print(logs.strip())
        add_result("FORCED HALLUCINATION CHECK", passed, details)
    finally:
        # Restore Ollama so later checks use the real agent implementation.
        assignment.chat = original_chat


def run_forced_incompleteness_check() -> None:
    """Verify that omitting an input task triggers the completeness guard."""
    tasks = sample_tasks()
    incomplete_payload = json.dumps(
        {
            "assignments": [
                {
                    "task_title": task.title,
                    "recommended_assignee": "Rahul",
                    "reason": "Selected for this check.",
                }
                for task in tasks[:2]
            ]
        }
    )
    original_chat = assignment.chat
    assignment.chat = lambda **kwargs: mocked_response(incomplete_payload)
    try:
        with capture_assignment_logs() as log_stream:
            try:
                run_assignment_agent(tasks, SAMPLE_TEAM)
            except AssignmentValidationError as error:
                logs = log_stream.getvalue()
                passed = attempt_count(logs) > 1
                details = f"{attempt_count(logs)} attempts before AssignmentValidationError: {error}"
            else:
                logs = log_stream.getvalue()
                passed = attempt_count(logs) > 1
                details = f"retry count: {attempt_count(logs)}"
        print("\nForced incompleteness log lines:")
        print(logs.strip())
        add_result("FORCED INCOMPLETENESS CHECK", passed, details)
    finally:
        assignment.chat = original_chat


def run_single_person_edge_case() -> None:
    """Verify that all tasks can be assigned when only one person is available."""
    tasks = sample_tasks()
    single_team = [
        TeamMember(
            name="Rahul",
            skills={"python": "high", "fastapi": "high", "react": "low"},
            workload_percent=60,
        )
    ]
    try:
        output = run_assignment_agent(tasks, single_team)
        passed = (
            len(output.assignments) == len(tasks)
            and {item.recommended_assignee for item in output.assignments} == {"Rahul"}
            and Counter(item.task_title for item in output.assignments)
            == Counter(task.title for task in tasks)
        )
        add_result(
            "SINGLE-PERSON TEAM EDGE CASE",
            passed,
            f"{len(output.assignments)} tasks assigned to Rahul",
        )
    except Exception as error:
        add_result("SINGLE-PERSON TEAM EDGE CASE", False, str(error))


def print_summary() -> None:
    """Print the final assignment verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<40} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<40} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all assignment checks and print their combined report."""
    run_basic_and_sanity_checks()
    run_forced_hallucination_check()
    run_forced_incompleteness_check()
    run_single_person_edge_case()
    print_summary()


if __name__ == "__main__":
    main()
