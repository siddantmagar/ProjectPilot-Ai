"""Task model definitions for planner output."""

from typing import Literal

from pydantic import BaseModel, field_validator


class Task(BaseModel):
	"""A task produced by the planner agent."""

	title: str
	description: str
	priority: Literal["low", "medium", "high"]
	estimated_days: int
	epic: str

	@field_validator("estimated_days")
	@classmethod
	def validate_estimated_days(cls, value: int) -> int:
		"""Ensure a task estimate is between one and sixty days."""
		if value < 1 or value > 60:
			raise ValueError("estimated_days must be between 1 and 60")
		return value


class PlannerOutput(BaseModel):
	"""Structured output returned by the planner agent."""

	epics: list[str]
	tasks: list[Task]

	@field_validator("tasks")
	@classmethod
	def validate_tasks(cls, value: list[Task]) -> list[Task]:
		"""Require the planner to return at least one task."""
		if not value:
			raise ValueError("tasks must not be empty")
		return value