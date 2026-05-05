from __future__ import annotations

import warnings
from datetime import date, datetime

import caldav
from icalendar import Calendar, Event

from .config import AppConfig
from .models import PlanState


def solution_to_ical(state: PlanState) -> str:
    cal = Calendar()
    cal.add("prodid", "-//projarvis//schedule//EN")
    cal.add("version", "2.0")

    for task_id, solution in state.task_solutions.items():
        task = state.tasks.get(task_id)
        if task is None:
            continue

        event = Event()
        event.add("uid", f"projarvis-{task_id}")
        event.add("summary", task.l2_metadata.get("title", task_id))
        event.add("dtstart", datetime.fromisoformat(solution.start))
        event.add("dtend", datetime.fromisoformat(solution.end))
        event.add(
            "description",
            f"Task: {task_id}\nDuration: {solution.duration_minutes} min",
        )
        event.add("X-PROJARVIS-TASK-ID", task_id)
        cal.add_component(event)

    return cal.to_ical().decode("utf-8")


def sync_to_caldav(state: PlanState, config: AppConfig) -> None:
    try:
        client = caldav.DAVClient(
            url=config.caldav.url,
            username=config.caldav.username,
            password=config.caldav.password,
        )
        principal = client.principal()
        cal = _get_or_create_calendar(principal, config.caldav.calendar_name)
        today = date.today()

        _remove_future_projarvis_events(cal, today)
        _create_new_events(cal, state, today)

    except Exception as exc:
        warnings.warn(f"CalDAV sync failed: {exc}")


def _get_or_create_calendar(principal, calendar_name: str):
    for c in principal.calendars():
        if c.name == calendar_name:
            return c
    return principal.make_calendar(calendar_name)


def _remove_future_projarvis_events(cal, today: date) -> None:
    try:
        future_events = cal.date_search(start=today)
    except Exception:
        future_events = cal.events()

    for event in future_events:
        try:
            cal_obj = Calendar.from_ical(event.data)
            for component in cal_obj.walk():
                if component.name == "VEVENT":
                    x_id = component.get("X-PROJARVIS-TASK-ID")
                    if x_id is not None:
                        event.delete()
                    break
        except Exception:
            continue


def _create_new_events(cal, state: PlanState, today: date) -> None:
    for task_id, solution in state.task_solutions.items():
        start_dt = datetime.fromisoformat(solution.start)
        if start_dt.date() < today:
            continue

        task = state.tasks.get(task_id)
        title = task.l2_metadata.get("title", task_id) if task else task_id

        event = Event()
        event.add("uid", f"projarvis-{task_id}")
        event.add("summary", title)
        event.add("dtstart", start_dt)
        event.add("dtend", datetime.fromisoformat(solution.end))
        event.add("description", f"Duration: {solution.duration_minutes} min")
        event.add("X-PROJARVIS-TASK-ID", task_id)

        wrapper = Calendar()
        wrapper.add("prodid", "-//projarvis//schedule//EN")
        wrapper.add("version", "2.0")
        wrapper.add_component(event)

        cal.save_event(wrapper.to_ical().decode("utf-8"))
