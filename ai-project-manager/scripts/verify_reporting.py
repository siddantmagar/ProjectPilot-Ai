"""Standalone verification harness for the reporting agent.

Run from the project root with:
    python -m scripts.verify_reporting
"""

import json
from types import SimpleNamespace

from app.agents import reporting
from app.agents.reporting import ReportValidationError, run_reporting_agent
from app.models.assignment import AssignmentOutput, TaskAssignment
from app.models.progress import ProgressOutput
from app.models.risk import RiskFlag, RiskOutput
from app.models.task import PlannerOutput, Task
from app.models.report import ReportOutput


results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def sample_inputs(with_risk: bool) -> tuple[
    PlannerOutput, AssignmentOutput, ProgressOutput, RiskOutput
]:
    """Build the fixed three-task reporting inputs used by every check."""
    tasks = [
        Task(
            title="Build API",
            description="Create API endpoints",
            priority="high",
            estimated_days=5,
            epic="Backend",
        ),
        Task(
            title="Write tests",
            description="Add automated tests",
            priority="medium",
            estimated_days=3,
            epic="Quality",
        ),
        Task(
            title="Deploy app",
            description="Deploy the application",
            priority="low",
            estimated_days=2,
            epic="Release",
        ),
    ]
    planner_output = PlannerOutput(epics=["Backend", "Quality", "Release"], tasks=tasks)
    assignment_output = AssignmentOutput(
        assignments=[
            TaskAssignment(
                task_title=task.title,
                recommended_assignee="Alex",
                reason="Matches the task area.",
            )
            for task in tasks
        ]
    )
    progress_output = ProgressOutput(
        total_tasks=3,
        completed_tasks=1,
        in_progress_tasks=1,
        todo_tasks=0,
        blocked_tasks=1,
        completion_percent=33.3,
        overdue_task_titles=[],
        blocked_task_titles=["Deploy app"],
    )
    risks = []
    if with_risk:
        risks.append(
            RiskFlag(
                task_title="Deploy app",
                risk_level="high",
                reason="The deployment task is blocked.",
                recommendation="Escalate the deployment blocker.",
            )
        )
    return planner_output, assignment_output, progress_output, RiskOutput(risks=risks)


def narrative_response(summary: str, top_risks: list[str] | None = None) -> SimpleNamespace:
    """Create an Ollama-shaped response for a mocked reporting call."""
    payload = {
        "summary": summary,
        "top_risks": top_risks or [],
        "recommendations": ["Address the highest-priority work next."],
    }
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def run_normal_synthesis_check() -> None:
    """Verify a report with one real risk and exact copied progress numbers."""
    planner, assignments, progress, risks = sample_inputs(with_risk=True)
    try:
        output = run_reporting_agent(planner, assignments, progress, risks)
        passed = (
            isinstance(output, ReportOutput)
            and bool(output.summary.strip())
            and output.completed_count == progress.completed_tasks == 1
            and output.total_count == progress.total_tasks == 3
            and output.completion_percent == progress.completion_percent == 33.3
        )
        add_result(
            "NORMAL SYNTHESIS CHECK",
            passed,
            f"{output.completed_count}/{output.total_count}, {output.completion_percent}%",
        )
    except Exception as error:
        add_result("NORMAL SYNTHESIS CHECK", False, str(error))


def run_healthy_project_check() -> None:
    """Verify that an empty risk input produces no top risks."""
    planner, assignments, progress, risks = sample_inputs(with_risk=False)
    try:
        output = run_reporting_agent(planner, assignments, progress, risks)
        add_result(
            "HEALTHY PROJECT REPORT CHECK",
            isinstance(output, ReportOutput) and output.top_risks == [],
            f"top_risks={output.top_risks}",
        )
    except Exception as error:
        add_result("HEALTHY PROJECT REPORT CHECK", False, str(error))


def run_number_integrity_check() -> None:
    """Verify that contradictory narrative numbers cannot alter structural fields."""
    planner, assignments, progress, risks = sample_inputs(with_risk=True)
    original_chat = reporting.chat
    contradictory_summary = "The project is 90% complete with 8 of 8 tasks done."
    reporting.chat = lambda **kwargs: narrative_response(
        contradictory_summary, ["Deploy app is blocked"]
    )
    try:
        output = run_reporting_agent(planner, assignments, progress, risks)
        print(
            "\nContradictory summary: "
            f"{output.summary}\n"
            "Correct numeric fields: "
            f"completed_count={output.completed_count}, "
            f"total_count={output.total_count}, "
            f"completion_percent={output.completion_percent}"
        )
        passed = (
            output.completed_count == 1
            and output.total_count == 3
            and output.completion_percent == 33.3
        )
        add_result("NUMBER-INTEGRITY UNDER PRESSURE CHECK", passed, "Structural numbers preserved")
    except Exception as error:
        add_result("NUMBER-INTEGRITY UNDER PRESSURE CHECK", False, str(error))
    finally:
        reporting.chat = original_chat


def run_forced_invalid_risk_check(check: str, with_risk: bool, top_risks: list[str]) -> None:
    """Verify that unsupported top risks cause retries and eventual rejection."""
    planner, assignments, progress, risks = sample_inputs(with_risk=with_risk)
    original_chat = reporting.chat
    calls = 0

    def mocked_chat(**kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return narrative_response("The supplied project status is current.", top_risks)

    reporting.chat = mocked_chat
    try:
        try:
            run_reporting_agent(planner, assignments, progress, risks)
        except ReportValidationError as error:
            add_result(check, calls > 1, f"{calls} attempts before ReportValidationError: {error}")
        else:
            add_result(check, calls > 1, f"Unexpectedly accepted after {calls} attempt(s)")
    except Exception as error:
        add_result(check, False, str(error))
    finally:
        reporting.chat = original_chat


def print_summary() -> None:
    """Print the final reporting verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<52} {'STATUS':<8} DETAIL")
    print("-" * 120)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<52} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Run all reporting checks and print their combined report."""
    run_normal_synthesis_check()
    run_healthy_project_check()
    run_number_integrity_check()
    run_forced_invalid_risk_check(
        "FORCED FABRICATED RISK CHECK", with_risk=True, top_risks=["Invented task risk"]
    )
    run_forced_invalid_risk_check(
        "FORCED NONEMPTY-RISK-ON-HEALTHY-PROJECT CHECK",
        with_risk=False,
        top_risks=["Invented healthy-project risk"],
    )
    print_summary()


if __name__ == "__main__":
    main()