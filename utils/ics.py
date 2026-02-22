"""
ICS calendar generation for BrightDayBot.

Generates RFC 5545 compliant ICS files for birthday and special day
calendar exports using the icalendar library.
"""

import hashlib
from datetime import date, datetime

from icalendar import Calendar, Event, vRecur


def generate_birthday_ics(birthdays):
    """
    Generate ICS calendar content for birthdays.

    Creates a VCALENDAR with VEVENT entries for each birthday,
    configured as yearly recurring all-day events.

    Args:
        birthdays: List of birthday dicts with user_id, username, date, year

    Returns:
        str: ICS format calendar content
    """
    cal = Calendar()
    cal.add("prodid", "-//BrightDayBot//Birthday Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Team Birthdays")

    current_year = datetime.now().year

    for bday in birthdays:
        username = bday["username"]
        date_str = bday["date"]  # DD/MM format
        user_id = bday["user_id"]
        year = bday.get("year")

        try:
            day, month = map(int, date_str.split("/"))
        except (ValueError, AttributeError):
            continue

        summary = f"🎂 {username}'s Birthday"
        if year:
            turning_age = current_year - year
            summary = f"🎂 {username}'s Birthday (turning {turning_age})"

        event = Event()
        event.add("uid", f"birthday-{user_id}@brightdaybot")
        event.add("dtstamp", datetime.utcnow())
        event.add("dtstart", date(current_year, month, day))
        event.add("summary", summary)
        event.add("rrule", vRecur({"FREQ": "YEARLY"}))
        event.add("transp", "TRANSPARENT")

        cal.add_component(event)

    return cal.to_ical().decode("utf-8")


def generate_special_days_ics(days, source_label=None):
    """
    Generate ICS calendar content for special days.

    Args:
        days: List of SpecialDay objects
        source_label: Optional label for calendar name (e.g. "UN")

    Returns:
        str: ICS format calendar content
    """
    cal_name = f"Special Days ({source_label})" if source_label else "Special Days"

    cal = Calendar()
    cal.add("prodid", "-//BrightDayBot//Special Days Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", cal_name)

    current_year = datetime.now().year
    now = datetime.utcnow()

    for day in days:
        try:
            day_num, month_num = map(int, day.date.split("/"))
        except (ValueError, AttributeError):
            continue

        # Stable UID based on name
        name_hash = hashlib.md5(day.name.lower().encode()).hexdigest()[:12]

        # Summary with emoji if available
        summary = f"{day.emoji} {day.name}" if day.emoji else day.name

        event = Event()
        event.add("uid", f"special-{name_hash}@brightdaybot")
        event.add("dtstamp", now)
        event.add("dtstart", date(current_year, month_num, day_num))
        event.add("summary", summary)
        event.add("transp", "TRANSPARENT")

        # Description with source attribution
        desc_parts = []
        if day.description:
            desc_parts.append(day.description)
        if day.source:
            desc_parts.append(f"Source: {day.source}")
        if desc_parts:
            event.add("description", "\n".join(desc_parts))

        # Yearly recurrence for fixed-date sources only (not Calendarific — variable dates)
        source = getattr(day, "source", "") or ""
        if source.lower() != "calendarific":
            event.add("rrule", vRecur({"FREQ": "YEARLY"}))

        cal.add_component(event)

    return cal.to_ical().decode("utf-8")
