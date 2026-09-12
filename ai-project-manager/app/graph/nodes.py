from app.graph.state import ProjectPilotState


def planner_node(state: ProjectPilotState) -> dict:
    """Run the planner agent and update planner output."""
    from app.agents.planner import run_planner_agent

    result = run_planner_agent(state["goal"], state["deadline"], state["team_size"])
    return {"planner_output": result}


def status_sync_node(state: ProjectPilotState) -> dict:
    """Replace stubbed statuses with real Jira status data and mapped states."""
    from app.integrations.jira.client import search_issues_by_project
    from app.integrations.jira.status_map import map_jira_status
    from app.models.progress import TaskStatusEntry
    import os

    project_key = os.getenv("JIRA_PROJECT_KEY")
    jira_issue_keys = state.get("jira_issue_keys") or {}
    jira_issue_ids = state.get("jira_issue_ids") or {}
    issue_key_to_title = {value: key for key, value in jira_issue_keys.items()}

    raw_issues = search_issues_by_project(
        project_key,
        reconcile_issue_ids=list(jira_issue_ids.values()),
    )

    statuses = []
    for issue in raw_issues:
        task_title = issue_key_to_title.get(issue["key"])
        if task_title is None:
            continue

        status_name = issue["fields"]["status"]["name"]
        status_category = issue["fields"]["status"]["statusCategory"]["name"]
        internal_status = map_jira_status(
            project_key, status_name, status_category
        )
        statuses.append(
            TaskStatusEntry(
                task_title=task_title,
                status=internal_status,
                jira_status_name=status_name,
                is_overdue=bool(issue["fields"].get("flagged", False)),
            )
        )

    return {"statuses": statuses}


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
        issue_ids: dict[str, str] = {}

        for task in state["planner_output"].tasks:
            existing_key = link_repo.get_issue_key(project_key, task.title)
            if existing_key:
                existing_id = link_repo.get_issue_id(project_key, task.title)
                issue_keys[task.title] = existing_key
                if existing_id is not None:
                    issue_ids[task.title] = existing_id
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

            link_repo.record_link(
                project_key,
                task.title,
                response.key,
                response.id,
            )
            issue_keys[task.title] = response.key
            issue_ids[task.title] = response.id

        return {"jira_issue_keys": issue_keys, "jira_issue_ids": issue_ids}
    finally:
        session.close()
