"""Planning agent module."""

import json
import logging

from ollama import chat
from pydantic import ValidationError

from app.models.task import PlannerOutput


logger = logging.getLogger(__name__)


class PlannerValidationError(Exception):
	"""Raised when the planner cannot produce valid output after retries."""


def run_planner_agent(goal: str, deadline: str, team_size: int) -> PlannerOutput:
	"""Generate planner output, retrying up to two times after validation failures."""
	# Build the initial prompt with all project context and output constraints.
	prompt = (
		f"Goal: {goal}\n"
		f"Deadline: {deadline}\n"
		f"Team size: {team_size}\n\n"
		"Produce exactly 3 to 5 tasks total, not more and not fewer. "
		"Keep each task description under 20 words. "
		'Assign each task a priority of "low", "medium", or "high". '
		"Assign estimated_days as a realistic integer between 1 and 60. "
		"Group all tasks under one or more epics relevant to the goal. "
		"Respond only with JSON matching the requested schema."
	)

	last_raw_output = ""
	last_error = ""

	# Make one initial request and allow up to two corrective retries.
	for attempt in range(1, 4):
		logger.info("Planner attempt %d of 3", attempt)

		# Ask Ollama for JSON matching the Pydantic schema.
		response = chat(
			model="qwen3:4b",
			messages=[{"role": "user", "content": prompt}],
			think=False,
			format=PlannerOutput.model_json_schema(),
		)
		last_raw_output = response.message.content

		try:
			# Parse the model response, then validate its fields with Pydantic.
			parsed_output = json.loads(last_raw_output)
			planner_output = PlannerOutput.model_validate(parsed_output)
		except (ValidationError, json.JSONDecodeError) as error:
			last_error = str(error)
			logger.info("Planner attempt %d failed validation: %s", attempt, last_error)

			# Give the model the exact failure so the next attempt can correct it.
			if attempt < 3:
				prompt = (
					f"{prompt}\n\n"
					f"Your previous response had this error: {last_error}. "
					"Please correct it and respond again."
				)
			continue

		logger.info("Planner attempt %d succeeded validation", attempt)
		return planner_output

	# Preserve both response and error details for debugging failed runs.
	raise PlannerValidationError(
		"Planner output remained invalid after 3 attempts. "
		f"Last validation error: {last_error}. "
		f"Last raw model output: {last_raw_output}"
	)