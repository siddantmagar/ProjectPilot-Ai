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
