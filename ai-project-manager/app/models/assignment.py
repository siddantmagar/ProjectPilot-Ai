"""Task assignment model definitions."""

from pydantic import BaseModel, field_validator


class TaskAssignment(BaseModel):
    """A recommended team member assignment for a task."""

    task_title: str
    recommended_assignee: str
    reason: str


class AssignmentOutput(BaseModel):
    """Structured output containing recommended task assignments."""

    assignments: list[TaskAssignment]

    @field_validator("assignments")
    @classmethod
    def validate_not_empty(cls, value: list[TaskAssignment]) -> list[TaskAssignment]:
        """Require at least one task assignment."""
        if not value:
            raise ValueError("assignments must not be empty")
        return value