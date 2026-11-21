"""Validation on write. Rules apply only to new rows and changed fields, never to rows that are read,
so old rows from Access that break a rule never stop the program."""
from datetime import datetime

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"   # the format of all date and time columns (design doc §4)


class ValidationError(ValueError):
    """A write was refused. `problems` lists each reason as a sentence for the user."""

    def __init__(self, problems: list[str]):
        super().__init__(" ".join(problems))
        self.problems = problems


def now_text() -> str:
    """The current local time in the format of the database."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def is_timestamp(value) -> bool:
    """True if `value` is a text in the format YYYY-MM-DD HH:MM:SS with a real date and time."""
    try:
        datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return False
    return True
