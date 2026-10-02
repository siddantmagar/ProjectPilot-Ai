import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from dotenv import load_dotenv

from app.graph.workflow import build_workflow


load_dotenv()

st.set_page_config(page_title="Project Pilot AI", layout="wide")
st.title("Project Pilot AI")
st.caption("Plan a project, create Jira issues, assign work, and track progress with AI agents.")


@st.cache_resource
def get_graph():
	return build_workflow()


graph = get_graph()

if "thread_id" not in st.session_state:
	st.session_state.thread_id = None
if "pending_interrupt" not in st.session_state:
	st.session_state.pending_interrupt = None
if "final_result" not in st.session_state:
	st.session_state.final_result = None
if "rejection_message" not in st.session_state:
	st.session_state.rejection_message = None


def display_results(result: dict) -> None:
	"""Render the completed pipeline results."""
	st.header("Tasks Created in Jira")
	jira_base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
	for task_title, issue_key in (result.get("jira_issue_keys") or {}).items():
		issue_link = f"[{issue_key}]({jira_base_url}/browse/{issue_key})"
		st.markdown(f"**{task_title}**: {issue_link}")

	st.header("Assignments")
	assignment_rows = [
		{
			"Task": assignment.task_title,
			"Assignee": assignment.recommended_assignee,
			"Reason": assignment.reason,
		}
		for assignment in result["assignment_output"].assignments
	]
	st.table(assignment_rows)

	st.header("Progress")
	progress_output = result["progress_output"]
	st.progress(progress_output.completion_percent / 100)
	progress_columns = st.columns(4)
	progress_columns[0].metric("Completed", progress_output.completed_tasks)
	progress_columns[1].metric("Total", progress_output.total_tasks)
	progress_columns[2].metric("Blocked", progress_output.blocked_tasks)
	progress_columns[3].metric("Overdue", len(progress_output.overdue_task_titles))

	st.header("Risks")
	risk_output = result["risk_output"]
	if not risk_output.risks:
		st.success("No risks identified — project is healthy.")
	else:
		for risk in risk_output.risks:
			if risk.risk_level == "high":
				st.error(f"{risk.task_title} [{risk.risk_level}]: {risk.reason}")
			elif risk.risk_level == "medium":
				st.warning(f"{risk.task_title} [{risk.risk_level}]: {risk.reason}")
			else:
				st.info(f"{risk.task_title} [{risk.risk_level}]: {risk.reason}")
			st.write(f"Recommendation: {risk.recommendation}")

	st.header("Status Report")
	report_output = result["report_output"]
	st.write(report_output.summary)
	for recommendation in report_output.recommendations:
		st.markdown(f"- {recommendation}")


with st.form("project_pilot_form"):
	goal = st.text_area(
		"Project Goal",
		placeholder="e.g. Build a login page for an e-commerce app",
	)
	deadline = st.text_input("Deadline", placeholder="e.g. 2 weeks")
	team_size = st.number_input("Team Size", min_value=1, max_value=10, value=2)
	submitted = st.form_submit_button("Run Project Pilot AI")

if submitted:
	if not goal.strip():
		st.error("Project Goal is required.")
		st.stop()

	import uuid

	st.session_state.thread_id = str(uuid.uuid4())
	st.session_state.final_result = None
	config = {"configurable": {"thread_id": st.session_state.thread_id}}
	with st.spinner("Running Planner Agent..."):
		try:
			result = graph.invoke(
				{
					"goal": goal,
					"deadline": deadline,
					"team_size": team_size,
					"team": [],
				},
				config=config,
			)
		except Exception as error:
			st.error(f"Pipeline failed: {error}")
			st.stop()

	if "__interrupt__" in result:
		st.session_state.pending_interrupt = result["__interrupt__"][0].value
	else:
		st.session_state.final_result = result


if st.session_state.pending_interrupt:
	payload = st.session_state.pending_interrupt
	st.subheader("Review Proposed Plan")
	st.write(f"Epics: {', '.join(payload['proposed_plan']['epics'])}")
	for task in payload["proposed_plan"]["tasks"]:
		st.write(
			f"- **{task['title']}** ({task['priority']}, "
			f"{task['estimated_days']}d): {task['description']}"
		)

	col1, col2 = st.columns(2)
	with col1:
		if st.button("Approve Plan"):
			from langgraph.types import Command

			config = {"configurable": {"thread_id": st.session_state.thread_id}}
			with st.spinner("Creating Jira issues and continuing pipeline..."):
				try:
					result = graph.invoke(
						Command(resume={"action": "approve"}), config=config
					)
				except Exception as error:
					st.error(f"Pipeline failed after approval: {error}")
					st.stop()
			st.session_state.pending_interrupt = None
			st.session_state.final_result = result
			st.rerun()
	with col2:
		if st.button("Reject Plan"):
			from langgraph.types import Command

			config = {"configurable": {"thread_id": st.session_state.thread_id}}
			with st.spinner("Recording rejection..."):
				result = graph.invoke(
					Command(resume={"action": "reject"}), config=config
				)
			st.session_state.rejection_message = (
				"Plan was rejected — no Jira issues were created."
			)
			st.session_state.pending_interrupt = None
			st.rerun()


if st.session_state.rejection_message:
	st.warning(f"Plan was rejected: {st.session_state.rejection_message}")
	st.session_state.rejection_message = None


if st.session_state.final_result:
	display_results(st.session_state.final_result)