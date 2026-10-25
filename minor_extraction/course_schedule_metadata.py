"""Shared, persistent course-schedule freshness date for generated pages."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATE_FILE = Path(__file__).with_name("course_schedule_updated_on.txt")


def course_schedule_update_date():
    updated = date.fromisoformat(DATE_FILE.read_text(encoding="utf-8").strip())
    return f"{updated.year}/{updated.month}/{updated.day}"


def update_course_schedule_date():
    today = datetime.now(timezone(timedelta(hours=8))).date()
    DATE_FILE.write_text(today.isoformat() + "\n", encoding="utf-8")
    return course_schedule_update_date()
