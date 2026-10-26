from app.models.health import HealthStatus


def compute_health(progress_output, risk_output) -> HealthStatus:
    """Red if any high risk or >20% overdue; yellow if any risk or blocked>0; else green."""
    total_tasks = progress_output.total_tasks
    overdue_count = len(progress_output.overdue_task_titles)
    overdue_percent = overdue_count / total_tasks * 100 if total_tasks else 0
    has_high_risk = any(risk.risk_level == "high" for risk in risk_output.risks)

    if has_high_risk or overdue_percent > 20:
        reasons = []
        if has_high_risk:
            reasons.append("at least one high risk")
        if overdue_percent > 20:
            reasons.append(f"{overdue_percent:.1f}% of tasks overdue")
        return HealthStatus(status="red", explanation="Red: " + " and ".join(reasons) + ".")

    if risk_output.risks or progress_output.blocked_tasks > 0:
        reasons = []
        if risk_output.risks:
            reasons.append("risks identified")
        if progress_output.blocked_tasks > 0:
            reasons.append(f"{progress_output.blocked_tasks} blocked task(s)")
        return HealthStatus(status="yellow", explanation="Yellow: " + " and ".join(reasons) + ".")

    return HealthStatus(status="green", explanation="Green: no risks or blocked tasks identified.")
