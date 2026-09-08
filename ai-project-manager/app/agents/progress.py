"""Deterministic progress calculation agent module."""

from app.models.progress import ProgressOutput, TaskStatusEntry
from app.models.task import Task


def run_progress_agent(
	tasks: list[Task], statuses: list[TaskStatusEntry]
) -> ProgressOutput:
	"""Compute progress deterministically; arithmetic does not need an LLM."""
	# Compare both title sets so no task or status entry is silently ignored.
	task_titles = {task.title for task in tasks}
	status_titles = {entry.task_title for entry in statuses}
	missing_statuses = sorted(task_titles - status_titles)
	unmatched_statuses = sorted(status_titles - task_titles)
	if missing_statuses or unmatched_statuses:
		raise ValueError(
			f"Task/status title mismatch; missing statuses: {missing_statuses}; "
			f"unmatched statuses: {unmatched_statuses}"
		)
	if len(tasks) != len(statuses):
		raise ValueError(
			f"Expected exactly one status entry per task, but got "
			f"{len(tasks)} tasks and {len(statuses)} status entries — "
			"check for duplicate or missing status entries."
		)

	# Reject an empty project explicitly instead of dividing by zero or reporting 0%.
	total_tasks = len(tasks)
	if total_tasks == 0:
		raise ValueError("Cannot compute progress for an empty task list")

	# Count each status category from the validated status entries.
	completed_tasks = sum(entry.status == "done" for entry in statuses)
	in_progress_tasks = sum(entry.status == "in_progress" for entry in statuses)
	todo_tasks = sum(entry.status == "todo" for entry in statuses)
	blocked_tasks = sum(entry.status == "blocked" for entry in statuses)

	# Calculate completion as a percentage and round it to one decimal place.
	completion_percent = round((completed_tasks / total_tasks) * 100, 1)

	# Collect titles for overdue and blocked task views.
	overdue_task_titles = [
		entry.task_title for entry in statuses if entry.is_overdue
	]
	blocked_task_titles = [
		entry.task_title for entry in statuses if entry.status == "blocked"
	]

	return ProgressOutput(
		total_tasks=total_tasks,
		completed_tasks=completed_tasks,
		in_progress_tasks=in_progress_tasks,
		todo_tasks=todo_tasks,
		blocked_tasks=blocked_tasks,
		completion_percent=completion_percent,
		overdue_task_titles=overdue_task_titles,
		blocked_task_titles=blocked_task_titles,
	)