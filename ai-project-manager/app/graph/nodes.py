from app.graph.state import ProjectPilotState


def planner_node(state: ProjectPilotState) -> dict:
    """Run the planner agent and update planner output."""
    from app.agents.planner import run_planner_agent

    result = run_planner_agent(state["goal"], state["deadline"], state["team_size"])
    return {"planner_output": result}


def stub_status_node(state: ProjectPilotState) -> dict:
    """Generate placeholder statuses and update the shared state."""
    from app.graph.stubs import generate_stub_statuses

    result = generate_stub_statuses(state["planner_output"])
    return {"statuses": result}


def assignment_node(state: ProjectPilotState) -> dict:
    """Run the Assignment Agent against persisted team and assign Jira issues."""
    from app.agents.assignment import run_assignment_agent
    from app.integrations.jira.client import assign_issue, JiraClientError
    from app.database.connection import SessionLocal
    from app.database.repositories import TeamRepository

    session = SessionLocal()
    try:
        team_repo = TeamRepository(session)
        team = team_repo.list_all()
        if not team:
            raise RuntimeError(
                "No team members found in the database — add at least "
                "one team member before running assignment."
            )

        assignment_output = run_assignment_agent(state["planner_output"].tasks, team)

        team_by_name = {member.name: member for member in team}
        jira_issue_keys = state.get("jira_issue_keys") or {}

        for assignment in assignment_output.assignments:
            member = team_by_name.get(assignment.recommended_assignee)
            issue_key = jira_issue_keys.get(assignment.task_title)

            if member is None or not member.jira_account_id:
                continue
            if issue_key is None:
                continue

            try:
                assign_issue(issue_key, member.jira_account_id)
            except JiraClientError as error:
                raise RuntimeError(
                    f"Failed to assign Jira issue {issue_key} to "
                    f"{member.name}: {error}"
                ) from error

        return {"assignment_output": assignment_output}
    finally:
        session.close()


def progress_node(state: ProjectPilotState) -> dict:
    """Run the progress agent and update progress output."""
    from app.agents.progress import run_progress_agent

    result = run_progress_agent(state["planner_output"].tasks, state["statuses"])
    return {"progress_output": result}


def risk_node(state: ProjectPilotState) -> dict:
    """Run the risk agent and update risk output."""
    from app.agents.risk import run_risk_agent

    result = run_risk_agent(state["planner_output"].tasks, state["statuses"])
    return {"risk_output": result}


def reporting_node(state: ProjectPilotState) -> dict:
    """Run the reporting agent and update report output."""
    from app.agents.reporting import run_reporting_agent

    result = run_reporting_agent(
        state["planner_output"],
        state["assignment_output"],
        state["progress_output"],
        state["risk_output"],
    )
    return {"report_output": result}


def jira_creation_node(state: ProjectPilotState) -> dict:
    """Create or reuse one real Jira issue for each Planner task idempotently."""
    from app.integrations.jira.client import JiraClientError, create_issue
    from app.database.connection import SessionLocal
    from app.database.repositories import TaskJiraLinkRepository
    import os

    project_key = os.getenv("JIRA_PROJECT_KEY")
    session = SessionLocal()
    try:
        link_repo = TaskJiraLinkRepository(session)
        issue_keys: dict[str, str] = {}

        for task in state["planner_output"].tasks:
            existing_key = link_repo.get_issue_key(project_key, task.title)
            if existing_key:
                issue_keys[task.title] = existing_key
                continue

            try:
                response = create_issue(
                    summary=task.title,
                    description=task.description,
                    issue_type="Task",
                )
            except JiraClientError as error:
                raise RuntimeError(
                    f"Failed to create Jira issue for task '{task.title}' "
                    f"after creating {len(issue_keys)} of "
                    f"{len(state['planner_output'].tasks)} issues: {error}"
                ) from error

            link_repo.record_link(project_key, task.title, response.key)
            issue_keys[task.title] = response.key

        return {"jira_issue_keys": issue_keys}
    finally:
        session.close()
