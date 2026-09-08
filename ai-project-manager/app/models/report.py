"""Report model definitions for synthesized project status output."""

from pydantic import BaseModel


class ReportOutput(BaseModel):
    """A synthesized project status report grounded in agent outputs."""

    summary: str
    completed_count: int
    total_count: int
    completion_percent: float
    top_risks: list[str]
    recommendations: list[str]
