"""Standalone verification harness for the planner agent.

Run from the project root with:
    python -m scripts.verify_planner
"""

import io
import json
import logging
import re
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator, Literal

from pydantic import BaseModel, ValidationError, field_validator

from app.agents import planner
from app.agents.planner import PlannerValidationError, run_planner_agent
from app.models.task import PlannerOutput


# Store every check result so the final report can be generated consistently.
results: list[dict[str, str]] = []


class StrictTask(BaseModel):
    """Local task schema used only to exercise a tighter estimate constraint."""

    title: str
    description: str
    priority: Literal["low", "medium", "high"]
    estimated_days: int
    epic: str

    @field_validator("estimated_days")
    @classmethod
    def validate_estimated_days(cls, value: int) -> int:
        """Reject estimates outside the temporary one-to-five-day range."""
        if value < 1 or value > 5:
            raise ValueError("estimated_days must be between 1 and 5")
        return value


class StrictPlannerOutput(BaseModel):
    """Local planner schema used only by the retry-path checks."""

    epics: list[str]
    tasks: list[StrictTask]

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, value: list[StrictTask]) -> list[StrictTask]:
        """Keep the normal non-empty task-list rule in the strict schema."""
        if not value:
            raise ValueError("tasks must not be empty")
        return value


@contextmanager
def capture_planner_logs() -> Iterator[io.StringIO]:
    """Capture planner INFO logs for one check, then restore logging state."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    planner.logger.addHandler(handler)
    previous_level = planner.logger.level
    planner.logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        planner.logger.removeHandler(handler)
        planner.logger.setLevel(previous_level)


def attempt_count(log_text: str) -> int:
    """Count unique planner attempt numbers present in captured logs."""
    return len(set(re.findall(r"Planner attempt (\d+) of 3", log_text)))


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def run_familiar_goal_check() -> None:
    """Check that a familiar goal returns valid planner output."""
    start = time.perf_counter()
    with capture_planner_logs() as log_stream:
        try:
            output = run_planner_agent("Build a login page", "2 weeks", 2)
            elapsed = time.perf_counter() - start
            logs = log_stream.getvalue()
            attempts = attempt_count(logs)
            passed = isinstance(output, PlannerOutput) and 3 <= len(output.tasks) <= 5
            add_result(
                "FAMILIAR GOAL CHECK",
                passed,
                f"{len(output.tasks)} tasks, {attempts} attempt(s), {elapsed:.2f}s",
            )
        except Exception as error:
            elapsed = time.perf_counter() - start
            add_result("FAMILIAR GOAL CHECK", False, f"{error} ({elapsed:.2f}s)")


def run_novel_goal_check(goal: str) -> None:
    """Check task shape for one novel goal and print titles for human review."""
    with capture_planner_logs() as log_stream:
        try:
            output = run_planner_agent(goal, "4 weeks", 4)
            logs = log_stream.getvalue()
            priorities_valid = all(
                task.priority in {"low", "medium", "high"} for task in output.tasks
            )
            estimates_valid = all(1 <= task.estimated_days <= 60 for task in output.tasks)
            passed = 3 <= len(output.tasks) <= 5 and priorities_valid and estimates_valid
            titles = "; ".join(task.title for task in output.tasks)
            details = f"titles: {titles}; {attempt_count(logs)} attempt(s)"
            add_result(f"NOVEL GOAL CHECK: {goal}", passed, details)
        except Exception as error:
            add_result(f"NOVEL GOAL CHECK: {goal}", False, str(error))


def strict_response(days: int) -> SimpleNamespace:
    """Build a valid normal-shaped response with a deliberately strict-invalid estimate."""
    payload = {
        "epics": ["Login"],
        "tasks": [
            {
                "title": "Implement login",
                "description": "Build login flow",
                "priority": "high",
                "estimated_days": days,
                "epic": "Login",
            }
        ],
    }
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def run_retry_path_check() -> None:
    """Check that a strict temporary schema causes retry behavior."""
    original_schema = planner.PlannerOutput
    original_chat = planner.chat
    responses = [strict_response(10), strict_response(10), strict_response(3)]
    planner.PlannerOutput = StrictPlannerOutput
    planner.chat = lambda **kwargs: responses.pop(0)
    try:
        with capture_planner_logs() as log_stream:
            try:
                output = run_planner_agent("Build a login page", "2 weeks", 2)
                logs = log_stream.getvalue()
                passed = attempt_count(logs) > 1
                details = f"{attempt_count(logs)} attempts; final result has {len(output.tasks)} task(s)"
            except PlannerValidationError as error:
                logs = log_stream.getvalue()
                passed = attempt_count(logs) > 1
                details = f"{attempt_count(logs)} attempts before PlannerValidationError: {error}"
        print("Retry-path log lines:")
        print(logs.strip())
        add_result("RETRY-PATH CHECK", passed, details)
    finally:
        planner.PlannerOutput = original_schema
        planner.chat = original_chat


def run_failure_exception_check() -> None:
    """Check that exhausted retries raise a useful diagnostic exception."""
    original_schema = planner.PlannerOutput
    original_chat = planner.chat
    planner.PlannerOutput = StrictPlannerOutput
    planner.chat = lambda **kwargs: strict_response(10)
    try:
        with capture_planner_logs() as log_stream:
            try:
                run_planner_agent("Force a strict validation failure", "today", 1)
            except PlannerValidationError as error:
                message = str(error)
                logs = log_stream.getvalue()
                passed = (
                    "\"estimated_days\": 10" in message
                    and "estimated_days must be between 1 and 5" in message
                )
                details = "Full exception message:\n" + message
            else:
                passed = False
                logs = log_stream.getvalue()
                details = "PlannerValidationError was not raised"
        print("Failure-check log lines:")
        print(logs.strip())
        add_result("FAILURE-EXCEPTION CHECK", passed, details)
    finally:
        planner.PlannerOutput = original_schema
        planner.chat = original_chat


def print_summary() -> None:
    """Print the requested table and the human-only readability reminder."""
    print("\nSUMMARY")
    print(f"{'CHECK':<45} {'STATUS':<8} DETAIL")
    print("-" * 100)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<45} {result['status']:<8} {detail}")

    auto_gradable = results[:]
    passed_count = sum(result["status"] == "PASS" for result in auto_gradable)
    print(f"\nAuto-gradable checks (1-4): {passed_count} passed out of {len(auto_gradable)} total")
    print(
        "Manually confirm: do the logs above clearly show attempt numbers and pass/fail "
        "per attempt without needing to re-read planner.py?"
    )


def main() -> None:
    """Run all planner checks and print their combined report."""
    run_familiar_goal_check()
    for goal in (
        "Build a REST API for a todo app",
        "Set up a CI/CD pipeline for a web app",
        "Create a user authentication system with JWT",
    ):
        run_novel_goal_check(goal)
    run_retry_path_check()
    run_failure_exception_check()
    print_summary()


if __name__ == "__main__":
    main()
