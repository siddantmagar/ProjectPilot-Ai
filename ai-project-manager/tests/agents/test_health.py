from app.agents.health import compute_health
from app.models.progress import ProgressOutput
from app.models.risk import RiskFlag, RiskOutput


def test_red_when_high_risk() -> None:
    """Protect against high-severity risks being understated as yellow health."""
    progress = ProgressOutput(
        total_tasks=5,
        completed_tasks=2,
        in_progress_tasks=2,
        todo_tasks=1,
        blocked_tasks=0,
        completion_percent=40.0,
        overdue_task_titles=[],
        blocked_task_titles=[],
    )
    risks = RiskOutput(
        risks=[
            RiskFlag(
                task_title="Build API",
                risk_level="high",
                reason="Blocked dependency.",
                recommendation="Escalate immediately.",
            )
        ]
    )

    assert compute_health(progress, risks).status == "red"


def test_red_when_overdue_over_20pct() -> None:
    """Protect against projects with more than one-fifth overdue tasks appearing healthy."""
    progress = ProgressOutput(
        total_tasks=10,
        completed_tasks=5,
        in_progress_tasks=2,
        todo_tasks=3,
        blocked_tasks=0,
        completion_percent=50.0,
        overdue_task_titles=["A", "B", "C"],
        blocked_task_titles=[],
    )
    risks = RiskOutput(risks=[])

    assert compute_health(progress, risks).status == "red"


def test_yellow_when_risk_no_high() -> None:
    """Protect against non-high risks being ignored instead of lowering health to yellow."""
    progress = ProgressOutput(
        total_tasks=3,
        completed_tasks=1,
        in_progress_tasks=2,
        todo_tasks=0,
        blocked_tasks=0,
        completion_percent=33.3,
        overdue_task_titles=[],
        blocked_task_titles=[],
    )
    risks = RiskOutput(
        risks=[
            RiskFlag(
                task_title="Write tests",
                risk_level="medium",
                reason="Testing is behind schedule.",
                recommendation="Add test capacity.",
            )
        ]
    )

    assert compute_health(progress, risks).status == "yellow"


def test_yellow_when_blocked() -> None:
    """Protect against blocked work being reported as green without a risk flag."""
    progress = ProgressOutput(
        total_tasks=3,
        completed_tasks=1,
        in_progress_tasks=1,
        todo_tasks=0,
        blocked_tasks=1,
        completion_percent=33.3,
        overdue_task_titles=[],
        blocked_task_titles=["Deploy app"],
    )
    risks = RiskOutput(risks=[])

    assert compute_health(progress, risks).status == "yellow"


def test_green_otherwise() -> None:
    """Protect against healthy projects being assigned a warning without a trigger."""
    progress = ProgressOutput(
        total_tasks=3,
        completed_tasks=1,
        in_progress_tasks=2,
        todo_tasks=0,
        blocked_tasks=0,
        completion_percent=33.3,
        overdue_task_titles=[],
        blocked_task_titles=[],
    )
    risks = RiskOutput(risks=[])

    assert compute_health(progress, risks).status == "green"
