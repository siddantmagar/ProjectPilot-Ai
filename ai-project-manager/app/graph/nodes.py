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
    """Run the assignment agent and update assignment output."""
    from app.agents.assignment import run_assignment_agent

    result = run_assignment_agent(state["planner_output"].tasks, state["team"])
    return {"assignment_output": result}


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
