"""Standalone verification harness for the plan approval interrupt.

WARNING: The approve path resumes the full pipeline and creates REAL Jira
issues in the configured project. The initial invocation pauses before Jira
creation; approving it performs the live sandbox write.

Run from the project root with:
    python -m scripts.verify_interrupt
"""

from langgraph.types import Command

from app.graph.workflow import build_workflow


results: list[dict[str, str]] = []


def add_result(check: str, passed: bool, details: str) -> None:
    """Append one normalized result and print useful details immediately."""
    status = "PASS" if passed else "FAIL"
    results.append({"check": check, "status": status, "details": details})
    print(f"[{status}] {check}: {details}")


def print_summary() -> None:
    """Print the final interrupt verification summary table."""
    print("\nSUMMARY")
    print(f"{'CHECK':<34} {'STATUS':<8} DETAIL")
    print("-" * 110)
    for result in results:
        detail = result["details"].replace("\n", " ")
        print(f"{result['check']:<34} {result['status']:<8} {detail}")

    passed_count = sum(result["status"] == "PASS" for result in results)
    print(f"\nChecks passed: {passed_count} out of {len(results)}")


def main() -> None:
    """Verify pause-before-Jira and approval-resume behavior."""
    graph = build_workflow()
    config = {"configurable": {"thread_id": "test-interrupt-1"}}
    state = {
        "goal": "Build a small project tracking API",
        "deadline": "2 weeks",
        "team_size": 2,
        "team": [],
    }

    try:
        paused_result = graph.invoke(state, config=config)
        interrupts = paused_result.get("__interrupt__", [])
        if interrupts:
            interrupt_value = interrupts[0].value
            print(f"Approval interrupt payload: {interrupt_value}")
            add_result(
                "INTERRUPT PAUSE CHECK",
                True,
                "Graph paused before Jira creation with a proposed plan",
            )
        else:
            add_result(
                "INTERRUPT PAUSE CHECK",
                False,
                "No __interrupt__ value was returned",
            )
            print_summary()
            return

        final_result = graph.invoke(Command(resume={"action": "approve"}), config=config)
        resumed = "jira_issue_keys" in final_result and "report_output" in final_result
        add_result(
            "APPROVAL RESUME CHECK",
            resumed,
            "Full pipeline completed after approval"
            if resumed
            else "Pipeline did not return jira_issue_keys and report_output",
        )
    except Exception as error:
        add_result("INTERRUPT WORKFLOW CHECK", False, str(error))

    print_summary()


if __name__ == "__main__":
    main()
