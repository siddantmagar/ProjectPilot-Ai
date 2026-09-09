from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
	assignment_node,
	planner_node,
	progress_node,
	reporting_node,
	risk_node,
	stub_status_node,
)
from app.graph.state import ProjectPilotState


def build_workflow():
	"""Build and compile the linear Project Pilot AI graph (milestone 1:
	no branching, no human-approval gate, no real Jira — those are
	later milestones layered onto this working linear path).
	"""
	graph = StateGraph(ProjectPilotState)

	graph.add_node("planner", planner_node)
	graph.add_node("stub_status", stub_status_node)
	graph.add_node("assignment", assignment_node)
	graph.add_node("progress", progress_node)
	graph.add_node("risk", risk_node)
	graph.add_node("reporting", reporting_node)

	graph.add_edge(START, "planner")
	graph.add_edge("planner", "stub_status")
	graph.add_edge("stub_status", "assignment")
	graph.add_edge("assignment", "progress")
	graph.add_edge("progress", "risk")
	graph.add_edge("risk", "reporting")
	graph.add_edge("reporting", END)

	return graph.compile()