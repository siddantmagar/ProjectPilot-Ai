"""Risk agent module."""

import json
import logging

from ollama import chat
from pydantic import ValidationError

from app.models.progress import TaskStatusEntry
from app.models.risk import RiskFlag, RiskOutput
from app.models.task import Task


logger = logging.getLogger(__name__)


class RiskValidationError(Exception):
	"""Raised when the risk agent cannot produce valid output after retries."""


def run_risk_agent(
	tasks: list[Task], statuses: list[TaskStatusEntry]
) -> RiskOutput:
	"""Identify and assess task risks in one batch, retrying invalid responses."""
	status_by_title = {status.task_title: status for status in statuses}

	# Python decides WHICH tasks are risks deterministically; the LLM only explains
	# and ranks severity for confirmed risks, where its judgment adds real value.
	qualifying_tasks = []
	for task in tasks:
		status_entry = status_by_title.get(task.title)
		if status_entry is None:
			continue
		is_risk = (
			status_entry.is_overdue
			or status_entry.status == "blocked"
			or (task.priority == "high" and status_entry.status == "todo")
		)
		if is_risk:
			qualifying_tasks.append((task, status_entry))

	# Healthy projects do not need an LLM call and must return no fabricated risks.
	if not qualifying_tasks:
		return RiskOutput(risks=[])

	task_details = [
		{
			"title": task.title,
			"description": task.description,
			"priority": task.priority,
			"estimated_days": task.estimated_days,
			"status": status_entry.status,
			"is_overdue": status_entry.is_overdue,
		}
		for task, status_entry in qualifying_tasks
	]
	prompt = (
		"The following tasks have already been identified as at-risk based on their "
		"status. For each one, assign a risk_level (low/medium/high) based on relative "
		"severity, write a one-sentence reason grounded in the status data given, and "
		"a short recommendation.\n\n"
		f"Tasks and current statuses:\n{json.dumps(task_details, indent=2)}\n\n"
		"Assign risk_level based on relative severity; "
		"a blocked high-priority task is worse than an overdue low-priority one. "
		"Base each reason only on the status information given; do not invent additional "
		"context like team member availability or external dependencies not mentioned. "
		"Respond only with JSON matching the requested schema."
	)

	last_raw_output = ""
	last_error = ""

	# Make one initial request and allow up to two corrective retries.
	for attempt in range(1, 4):
		logger.info("Risk attempt %d of 3", attempt)

		# Ask Ollama for one structured response containing the whole risk batch.
		response = chat(
			model="qwen3:4b",
			messages=[{"role": "user", "content": prompt}],
			think=False,
			format=RiskOutput.model_json_schema(),
		)
		last_raw_output = response.message.content

		try:
			# Parse the response, then validate its shape and field values with Pydantic.
			parsed_output = json.loads(last_raw_output)
			risk_output = RiskOutput.model_validate(parsed_output)

			# An empty list is valid: a healthy project may have no genuine risks.
			input_task_titles = {task.title for task in tasks}
			for risk in risk_output.risks:
				if risk.task_title not in input_task_titles:
					raise ValueError(
						f"unknown task_title in risk: {risk.task_title}"
					)
		except (ValidationError, json.JSONDecodeError, ValueError) as error:
			last_error = str(error)
			logger.info("Risk attempt %d failed validation: %s", attempt, last_error)

			# Give the model the exact failure so the next attempt can correct it.
			if attempt < 3:
				prompt = (
					f"{prompt}\n\n"
					f"Your previous response had this error: {last_error}. "
					"Please correct it and respond again."
				)
			continue

		logger.info("Risk attempt %d succeeded validation", attempt)
		return risk_output

	# Preserve both response and error details for debugging failed runs.
	raise RiskValidationError(
		"Risk output remained invalid after 3 attempts. "
		f"Last validation error: {last_error}. "
		f"Last raw model output: {last_raw_output}"
	)
