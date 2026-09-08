"""Reporting agent module."""

import json
import logging

from ollama import chat
from pydantic import BaseModel, ValidationError

from app.models.assignment import AssignmentOutput
from app.models.progress import ProgressOutput
from app.models.report import ReportOutput
from app.models.risk import RiskOutput
from app.models.task import PlannerOutput


logger = logging.getLogger(__name__)


class _ReportNarrative(BaseModel):
	"""LLM-generated narrative fields for the final project report."""

	summary: str
	top_risks: list[str]
	recommendations: list[str]


class ReportValidationError(Exception):
	"""Raised when the reporting agent cannot produce valid output after retries."""


def run_reporting_agent(
	planner_output: PlannerOutput,
	assignment_output: AssignmentOutput,
	progress_output: ProgressOutput,
	risk_output: RiskOutput,
) -> ReportOutput:
	"""Synthesize agent outputs while preserving deterministic progress numbers.

	The completion counts and percentage never touch the LLM: they are copied
	directly from ``progress_output`` after the narrative has been validated.
	"""
	planner_details = {
		"epics": planner_output.epics,
		"task_titles": [task.title for task in planner_output.tasks],
	}
	assignment_details = [
		{
			"task_title": assignment.task_title,
			"recommended_assignee": assignment.recommended_assignee,
		}
		for assignment in assignment_output.assignments
	]
	progress_details = {
		"completed_tasks": progress_output.completed_tasks,
		"total_tasks": progress_output.total_tasks,
		"completion_percent": progress_output.completion_percent,
		"blocked_task_titles": progress_output.blocked_task_titles,
		"overdue_task_titles": progress_output.overdue_task_titles,
	}
	risk_details = [
		{
			"task_title": risk.task_title,
			"risk_level": risk.risk_level,
			"reason": risk.reason,
		}
		for risk in risk_output.risks
	]
	prompt = (
		f"Planner output:\n{json.dumps(planner_details, indent=2)}\n\n"
		f"Assignment mapping:\n{json.dumps(assignment_details, indent=2)}\n\n"
		"Progress output (these exact numbers, do not recalculate or restate them "
		f"differently):\n{json.dumps(progress_details, indent=2)}\n\n"
		f"Risk output:\n{json.dumps(risk_details, indent=2)}\n\n"
		"Write a 2-4 sentence plain-English summary of the overall project status. "
		"For top_risks, create one short string per risk that MUST include the task's "
		"title (from task_title) so the risk is identifiable — for example: "
		"'Deploy app: blocked and overdue.' Do NOT output just the risk_level word "
		"alone (e.g. do not output just 'high' or 'medium') — that identifies "
		"nothing on its own. Each string should be the task title plus a brief reason "
		"phrase, do not invent new risks beyond what is supplied. If the supplied "
		"risk output is empty, top_risks "
		"must be an empty list. Give 1-3 short, actionable recommendations based "
		"only on the supplied risks and progress data. Do not restate or recalculate "
		"completed_count, total_count, or completion_percent anywhere in your own "
		"reasoning; those values come from the code, not the model. Respond only "
		"with JSON matching the requested narrative schema."
	)

	last_raw_output = ""
	last_error = ""

	# Make one initial request and allow up to two corrective retries.
	for attempt in range(1, 4):
		logger.info("Reporting attempt %d of 3", attempt)

		# The schema contains only fields the LLM is responsible for generating.
		response = chat(
			model="qwen3:4b",
			messages=[{"role": "user", "content": prompt}],
			think=False,
			format=_ReportNarrative.model_json_schema(),
		)
		last_raw_output = response.message.content

		try:
			# Parse and validate only the model-generated narrative fields.
			parsed_output = json.loads(last_raw_output)
			narrative = _ReportNarrative.model_validate(parsed_output)

			# Prevent invented top risks while allowing the model to phrase titles naturally.
			risk_titles = [risk.task_title.casefold() for risk in risk_output.risks]
			if not risk_titles and narrative.top_risks:
				raise ValueError(
					"top_risks must be empty when risk_output.risks is empty"
				)
			for top_risk in narrative.top_risks:
				if not any(title in top_risk.casefold() for title in risk_titles):
					raise ValueError(f"unknown top risk: {top_risk}")
		except (ValidationError, json.JSONDecodeError, ValueError) as error:
			last_error = str(error)
			logger.info(
				"Reporting attempt %d failed validation: %s", attempt, last_error
			)

			# Give the model the exact failure so the next attempt can correct it.
			if attempt < 3:
				prompt = (
					f"{prompt}\n\n"
					f"Your previous response had this error: {last_error}. "
					"Please correct it and respond again."
				)
			continue

		logger.info("Reporting attempt %d succeeded validation", attempt)
		return ReportOutput(
			summary=narrative.summary,
			completed_count=progress_output.completed_tasks,
			total_count=progress_output.total_tasks,
			completion_percent=progress_output.completion_percent,
			top_risks=narrative.top_risks,
			recommendations=narrative.recommendations,
		)

	# Preserve both response and error details for debugging failed runs.
	raise ReportValidationError(
		"Report output remained invalid after 3 attempts. "
		f"Last validation error: {last_error}. "
		f"Last raw model output: {last_raw_output}"
	)