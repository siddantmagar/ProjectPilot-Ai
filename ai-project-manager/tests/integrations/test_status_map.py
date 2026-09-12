from app.integrations.jira.status_map import map_jira_status


def test_maps_idea_to_todo() -> None:
    """Protect against the AIPM Idea status being treated as active work."""
    assert map_jira_status("AIPM", "Idea", "To Do") == "todo"


def test_maps_todo_to_todo() -> None:
    """Protect the explicit AIPM mapping from Jira's unreliable category label."""
    assert map_jira_status("AIPM", "To Do", "In Progress") == "todo"


def test_maps_in_progress_and_testing_to_in_progress() -> None:
    """Protect against active AIPM workflow statuses being marked complete or todo."""
    assert map_jira_status("AIPM", "In Progress", "In Progress") == "in_progress"
    assert map_jira_status("AIPM", "Testing", "In Progress") == "in_progress"


def test_maps_done_to_done() -> None:
    """Protect against completed AIPM issues being reported as unfinished."""
    assert map_jira_status("AIPM", "Done", "Done") == "done"


def test_unmapped_status_falls_back_to_category() -> None:
    """Protect against new Jira status names failing when their category is known."""
    assert map_jira_status("AIPM", "SomeNewColumn", "Done") == "done"


def test_unmapped_status_unknown_category_returns_unknown() -> None:
    """Protect against guessing an internal status for an entirely unknown Jira state."""
    assert (
        map_jira_status("AIPM", "SomeNewColumn", "SomeWeirdCategory")
        == "unknown"
    )


def test_unknown_project_returns_unknown_or_uses_category() -> None:
    """Protect against an unmapped project's workflow crashing status synchronization."""
    assert map_jira_status("SOME_OTHER_PROJECT", "Idea", "To Do") == "todo"
