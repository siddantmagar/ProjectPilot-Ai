from typing import Optional, TypedDict

from app.models.task import PlannerOutput
from app.models.assignment import AssignmentOutput
from app.models.progress import ProgressOutput, TaskStatusEntry
from app.models.risk import RiskOutput
from app.models.report import ReportOutput
from app.models.team import TeamMember


class ProjectPilotState(TypedDict):
	"""Shared state passed between nodes in the Project Pilot AI workflow.

	Fields start as None/empty and are populated as each node runs.
	Node functions read what they need and return a partial dict of
	updates — LangGraph merges these into state automatically.
	"""
	# Inputs, provided at graph invocation
	goal: str
	deadline: str
	team_size: int
	team: list[TeamMember]

	# Populated by each node in sequence
	planner_output: Optional[PlannerOutput]
	statuses: Optional[list[TaskStatusEntry]]
	assignment_output: Optional[AssignmentOutput]
	progress_output: Optional[ProgressOutput]
	risk_output: Optional[RiskOutput]
	report_output: Optional[ReportOutput]
	jira_issue_keys: Optional[dict[str, str]]