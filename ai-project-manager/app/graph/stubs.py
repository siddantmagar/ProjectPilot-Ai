from app.models.progress import TaskStatusEntry
from app.models.task import PlannerOutput


def generate_stub_statuses(planner_output: PlannerOutput) -> list[TaskStatusEntry]:
    """Placeholder task statuses until real Jira sync exists.

    Every task starts as 'todo', not overdue. This exists purely so
    Progress and Risk agents have status data to consume before Jira
    integration is built. Replace this node's logic with a real Jira
    query in a later milestone.
    """
    return [
        TaskStatusEntry(
            task_title=task.title,
            status="todo",
            is_overdue=False,
        )
        for task in planner_output.tasks
    ]
