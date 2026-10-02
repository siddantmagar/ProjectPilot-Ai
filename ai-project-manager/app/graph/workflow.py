from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
	assignment_node,
	audit_log_node,
	create_project_node,
	plan_approval_node,
	planner_node,
	progress_node,
	reporting_node,
	risk_node,
	jira_creation_node,
	status_sync_node,
)
from app.graph.state import ProjectPilotState
from app.models.assignment import AssignmentOutput, TaskAssignment
from app.models.progress import ProgressOutput, TaskStatusEntry
from app.models.report import ReportOutput
from app.models.risk import RiskFlag, RiskOutput
from app.models.task import PlannerOutput, Task
from app.models.team import TeamMember


def route_after_audit(state: ProjectPilotState) -> str:
	"""Send approved or modified plans onward; stop rejected plans."""
	decision = state.get("_approval_decision")
	if decision and decision.get("action") == "reject":
		return "rejected_end"
	return "continue"


def build_workflow():
	"""Build and compile the Project Pilot AI graph with human-in-the-loop pauses."""
	graph = StateGraph(ProjectPilotState)

	graph.add_node("planner", planner_node)
	graph.add_node("create_project", create_project_node)
	graph.add_node("plan_approval", plan_approval_node)
	graph.add_node("audit_log", audit_log_node)
	graph.add_node("jira_creation", jira_creation_node)
	graph.add_node("status_sync", status_sync_node)
	graph.add_node("assignment", assignment_node)
	graph.add_node("progress", progress_node)
	graph.add_node("risk", risk_node)
	graph.add_node("reporting", reporting_node)

	graph.add_edge(START, "create_project")
	graph.add_edge("create_project", "planner")
	graph.add_edge("planner", "plan_approval")
	graph.add_edge("plan_approval", "audit_log")
	graph.add_conditional_edges(
		"audit_log",
		route_after_audit,
		{"continue": "jira_creation", "rejected_end": END},
	)
	graph.add_edge("jira_creation", "status_sync")
	graph.add_edge("status_sync", "assignment")
	graph.add_edge("assignment", "progress")
	graph.add_edge("progress", "risk")
	graph.add_edge("risk", "reporting")
	graph.add_edge("reporting", END)

	serde = JsonPlusSerializer(
		allowed_msgpack_modules=[
			AssignmentOutput,
			TaskAssignment,
			ProgressOutput,
			TaskStatusEntry,
			ReportOutput,
			RiskFlag,
			RiskOutput,
			PlannerOutput,
			Task,
			TeamMember,
		]
	)
	checkpointer = InMemorySaver(serde=serde)
	return graph.compile(checkpointer=checkpointer)