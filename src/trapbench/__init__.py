"""trapbench: author, lint, grade and verify 'hard to find, easy to verify' benchmark tasks."""
from .grade import CORRECT, INCORRECT, NOT_ATTEMPTED, Grade, grade, grade_all, summarize
from .lint import RULES, Issue, lint, lint_task
from .schema import Source, Task, TaskFileError, load_responses, load_tasks
from .verify import verify_tasks

__all__ = [
    "CORRECT", "INCORRECT", "NOT_ATTEMPTED", "RULES", "Grade", "Issue", "Source", "Task", "TaskFileError",
    "grade", "grade_all", "lint", "lint_task", "load_responses", "load_tasks", "summarize", "verify_tasks",
]
__version__ = "0.1.0"
