from datetime import datetime, timedelta

CADENCE_INTERVALS: dict[str, timedelta] = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}
"""Configurable, not hardcoded into the scheduler (Group F7): adding a new
cadence option is one dict entry, no schema change — monitoring_cadence
itself is a plain string column for the same reason."""


def compute_next_scheduled_run_at(cadence: str, from_time: datetime) -> datetime | None:
    interval = CADENCE_INTERVALS.get(cadence)
    return from_time + interval if interval else None  # "manual" (or any unknown value) -> never auto-scheduled
