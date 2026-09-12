"""Translate Jira workflow statuses into Project Pilot AI statuses."""


STATUS_MAP: dict[str, dict[str, str]] = {
	"AIPM": {
		"Idea": "todo",
		"To Do": "todo",
		"In Progress": "in_progress",
		"Testing": "in_progress",
		"Done": "done",
	}
}


def map_jira_status(
	project_key: str, status_name: str, status_category: str
) -> str:
	"""Translate a Jira status name into Project Pilot AI's internal status."""
	project_map = STATUS_MAP.get(project_key, {})
	if status_name in project_map:
		return project_map[status_name]

	# Category fallback is lower-confidence because Jira categories can be unreliable.
	category_fallback = {
		"To Do": "todo",
		"In Progress": "in_progress",
		"Done": "done",
	}
	return category_fallback.get(status_category, "unknown")