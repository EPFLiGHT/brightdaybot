"""
App Home handlers for BrightDayBot.

Displays user's birthday status, quick actions, and upcoming birthdays
when users open the app's Home tab.
"""

from datetime import datetime, timezone

from config import get_logger
from utils.storage import load_birthdays
from utils.date_utils import calculate_days_until_birthday
from utils.slack_utils import get_username

logger = get_logger("events")


def register_app_home_handlers(app):
    """Register App Home event handlers."""

    @app.event("app_home_opened")
    def handle_app_home_opened(event, client):
        """
        Render App Home when user opens it.

        Shows:
        - User's birthday status
        - Quick action buttons
        - Upcoming birthdays preview
        """
        user_id = event["user"]

        logger.info(f"APP_HOME: User {user_id} opened App Home")

        try:
            # Build the home view
            view = _build_home_view(user_id, app)

            # Publish the view
            client.views_publish(user_id=user_id, view=view)

            logger.info(f"APP_HOME: Published home view for {user_id}")

        except Exception as e:
            logger.error(f"APP_HOME_ERROR: Failed to publish home view: {e}")

    logger.info("APP_HOME: App Home handlers registered")


def _build_home_view(user_id, app):
    """Build the App Home view blocks."""
    from utils.date_utils import date_to_words, calculate_age, get_star_sign

    # Get user's birthday status
    birthdays = load_birthdays()
    user_birthday = birthdays.get(user_id)

    # Get upcoming birthdays (top 5)
    upcoming = _get_upcoming_birthdays(birthdays, app, limit=5)

    blocks = []

    # Header
    blocks.append(
        {"type": "header", "text": {"type": "plain_text", "text": "BrightDayBot"}}
    )

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Your friendly birthday celebration bot with AI-generated messages and images.",
            },
        }
    )

    blocks.append({"type": "divider"})

    # User's Birthday Status
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Your Birthday Status*"},
        }
    )

    if user_birthday:
        date_words = date_to_words(user_birthday["date"], user_birthday.get("year"))
        star_sign = get_star_sign(user_birthday["date"])
        age = (
            calculate_age(user_birthday["year"]) if user_birthday.get("year") else None
        )

        fields = [
            {"type": "mrkdwn", "text": f"*Birthday:*\n{date_words}"},
            {"type": "mrkdwn", "text": f"*Star Sign:*\n{star_sign}"},
        ]

        if age:
            fields.append({"type": "mrkdwn", "text": f"*Age:*\n{age} years"})

        blocks.append({"type": "section", "fields": fields})

        # Edit button
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit Birthday"},
                        "action_id": "open_birthday_modal",
                        "style": "primary",
                    }
                ],
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "You haven't added your birthday yet!",
                },
            }
        )

        # Add button
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Add My Birthday"},
                        "action_id": "open_birthday_modal",
                        "style": "primary",
                    }
                ],
            }
        )

    blocks.append({"type": "divider"})

    # Upcoming Birthdays
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Upcoming Birthdays (Next 30 Days)*"},
        }
    )

    if upcoming:
        # Build bulleted list of upcoming birthdays
        birthday_lines = []
        for bday in upcoming:
            if bday["days_until"] == 0:
                days_text = "Today! 🎂"
            elif bday["days_until"] == 1:
                days_text = "Tomorrow"
            else:
                days_text = f"in {bday['days_until']} days"

            birthday_lines.append(f"• <@{bday['user_id']}> - {days_text}")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(birthday_lines),
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No upcoming birthdays in the next 30 days._",
                },
            }
        )

    blocks.append({"type": "divider"})

    # Quick Commands
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Quick Commands*"},
        }
    )

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Use these slash commands anywhere:\n"
                + "- `/birthday` - Add or edit your birthday\n"
                + "- `/birthday check` - Check your birthday\n"
                + "- `/birthday list` - See upcoming birthdays\n"
                + "- `/special-day` - View today's special days",
            },
        }
    )

    # Context footer
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Tip: Send me a DM with your date (e.g., 25/12) to quickly add your birthday!",
                }
            ],
        }
    )

    return {"type": "home", "blocks": blocks}


def _get_upcoming_birthdays(birthdays, app, limit=5):
    """Get list of upcoming birthdays within 30 days."""
    reference_date = datetime.now(timezone.utc)
    upcoming = []

    for uid, data in birthdays.items():
        days = calculate_days_until_birthday(data["date"], reference_date)
        if days is not None and days <= 30:
            upcoming.append(
                {
                    "user_id": uid,
                    "username": get_username(app, uid),
                    "date": data["date"],
                    "year": data.get("year"),
                    "days_until": days,
                }
            )

    # Sort by days until and limit
    upcoming.sort(key=lambda x: x["days_until"])
    return upcoming[:limit]
