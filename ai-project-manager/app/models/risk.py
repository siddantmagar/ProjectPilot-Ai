"""Risk model definitions for risk agent output."""

from typing import Literal

from pydantic import BaseModel


class RiskFlag(BaseModel):
	"""A single identified risk tied to a specific task."""

	task_title: str
	risk_level: Literal["low", "medium", "high"]
	reason: str
	recommendation: str


class RiskOutput(BaseModel):
	"""Structured output containing all identified risks for a project."""

	risks: list[RiskFlag]