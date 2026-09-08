"""Task assignment agent module."""

import json
import logging
from collections import Counter

from ollama import chat
from pydantic import ValidationError

from app.models.assignment import AssignmentOutput
from app.models.task import Task
from app.models.team import TeamMember


logger = logging.getLogger(__name__)


class AssignmentValidationError(Exception):
	"""Raised when the assignment agent cannot produce valid output after retries."""


def run_assignment_agent(
	tasks: list[Task], team: list[TeamMember]
) -> AssignmentOutput:
	"""Assign tasks in one batch, retrying up to two times after validation failures."""
	# Serialize the complete input context so the model can assign the batch coherently.
	task_details = [
		{
			"title": task.title,
			"description": task.description,
			"priority": task.priority,
			"estimated_days": task.estimated_days,
		}
		for task in tasks
	]
	team_details = [
		{
			"name": member.name,
			"skills": member.skills,
			"workload_percent": member.workload_percent,
		}
		for member in team
	]
	prompt = (
		f"Tasks:\n{json.dumps(task_details, indent=2)}\n\n"
		f"Team roster:\n{json.dumps(team_details, indent=2)}\n\n"
		"Assign each task to exactly one team member based on relevant skills "
		"and current workload. Give each choice a short, one-sentence text reason. "
		"Do not invent a confidence score or numeric certainty; provide only the text reason. "
		"If NO team member has a genuinely relevant skill for a task, you MUST respond "
		"with exactly this reason: 'no strong skill match; assigned to least-loaded "
		"member based on availability.' Do NOT invent a tenuous or unrelated skill "
		"connection to justify the assignment - for example, do not claim an unrelated "
		"skill like React is relevant to a task like writing a launch announcement. "
		"Honesty about missing skill matches is required, not optional. "
		"Respond only with JSON matching the requested schema."
	)

	last_raw_output = ""
	last_error = ""

	# Make one initial request and allow up to two corrective retries.
	for attempt in range(1, 4):
		logger.info("Assignment attempt %d of 3", attempt)

		# Ask Ollama for one structured response containing the whole assignment batch.
		response = chat(
			model="qwen3:4b",
			messages=[{"role": "user", "content": prompt}],
			think=False,
			format=AssignmentOutput.model_json_schema(),
		)
		last_raw_output = response.message.content

		try:
			# Parse the response, then validate its shape and field values with Pydantic.
			parsed_output = json.loads(last_raw_output)
			assignment_output = AssignmentOutput.model_validate(parsed_output)

			# Cross-check model references against the actual input, preventing hallucinated names.
			input_task_titles = {task.title for task in tasks}
			input_team_names = {member.name for member in team}
			for assignment in assignment_output.assignments:
				if assignment.task_title not in input_task_titles:
					raise ValueError(
						f"unknown task_title in assignment: {assignment.task_title}"
					)
				if assignment.recommended_assignee not in input_team_names:
					raise ValueError(
						"unknown recommended_assignee in assignment: "
						f"{assignment.recommended_assignee}"
					)

			# Ensure every input task is assigned exactly once, with no omissions or duplicates.
			assigned_titles = {
				assignment.task_title for assignment in assignment_output.assignments
			}
			if assigned_titles != input_task_titles:
				duplicate_titles = sorted(
					title
					for title, count in Counter(
						assignment.task_title
						for assignment in assignment_output.assignments
					).items()
					if count > 1
				)
				missing_titles = sorted(input_task_titles - assigned_titles)
				raise ValueError(
					f"task assignment completeness check failed; "
					f"missing: {missing_titles}; duplicated: {duplicate_titles}"
				)
		except (ValidationError, json.JSONDecodeError, ValueError) as error:
			last_error = str(error)
			logger.info(
				"Assignment attempt %d failed validation: %s", attempt, last_error
			)

			# Give the model the exact failure so the next attempt can correct it.
			if attempt < 3:
				prompt = (
					f"{prompt}\n\n"
					f"Your previous response had this error: {last_error}. "
					"Please correct it and respond again."
				)
			continue

		logger.info("Assignment attempt %d succeeded validation", attempt)
		return assignment_output

	# Preserve both response and error details for debugging failed runs.
	raise AssignmentValidationError(
		"Assignment output remained invalid after 3 attempts. "
		f"Last validation error: {last_error}. "
		f"Last raw model output: {last_raw_output}"
	)
