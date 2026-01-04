"""
App Home handlers for BrightDayBot.

Displays user's birthday status, quick actions, and upcoming birthdays
when users open the app's Home tab.
"""

from datetime import datetime, timezone

from slack_sdk.errors import SlackApiError

from config import (
    APP_HOME_UPCOMING_BIRTHDAYS_LIMIT,
    APP_HOME_UPCOMING_SPECIAL_DAYS,
    get_logger,
)
from slack.client import get_username
from storage.birthdays import get_user_preferences, load_birthdays
from storage.special_days import get_upcoming_special_days
from utils.date import calculate_days_until_birthday

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

        except SlackApiError as e:
            logger.error(f"APP_HOME_ERROR: Slack API error publishing home view: {e}")
            # Try to show a fallback error view
            _publish_fallback_view(client, user_id)

        except Exception as e:
            logger.error(f"APP_HOME_ERROR: Failed to publish home view: {e}")
            # Try to show a fallback error view
            _publish_fallback_view(client, user_id)

    logger.info("APP_HOME: App Home handlers registered")


def _build_home_view(user_id, app):
    """Build the App Home view blocks."""
    from utils.date import calculate_age, date_to_words, get_star_sign

    # Get user's birthday status
    birthdays = load_birthdays()
    user_birthday = birthdays.get(user_id)

    # Get upcoming birthdays
    upcoming = _get_upcoming_birthdays(birthdays, app, limit=APP_HOME_UPCOMING_BIRTHDAYS_LIMIT)

    blocks = []

    # Header
    blocks.append({"type": "header", "text": {"type": "plain_text", "text": "BrightDayBot"}})

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
        age = calculate_age(user_birthday["year"]) if user_birthday.get("year") else None

        fields = [
            {"type": "mrkdwn", "text": f"*Birthday:*\n{date_words}"},
            {"type": "mrkdwn", "text": f"*Star Sign:*\n{star_sign}"},
        ]

        if age:
            fields.append({"type": "mrkdwn", "text": f"*Age:*\n{age} years"})

        blocks.append({"type": "section", "fields": fields})

        # Get and display preferences
        prefs = get_user_preferences(user_id) or {}
        is_active = prefs.get("active", True)
        image_enabled = prefs.get("image_enabled", True)
        show_age = prefs.get("show_age", True)

        pref_items = []
        if is_active:
            pref_items.append("Celebrations: Active")
        else:
            pref_items.append("Celebrations: Paused")
        pref_items.append(f"AI Images: {'On' if image_enabled else 'Off'}")
        pref_items.append(f"Show Age: {'Yes' if show_age else 'No'}")

        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " | ".join(pref_items)}],
            }
        )

        # Edit and Remove buttons
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Edit Birthday"},
                        "action_id": "open_birthday_modal",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Remove Birthday"},
                        "action_id": "remove_birthday_confirm",
                        "style": "danger",
                        "confirm": {
                            "title": {"type": "plain_text", "text": "Remove Birthday?"},
                            "text": {
                                "type": "mrkdwn",
                                "text": "Are you sure you want to remove your birthday? You won't receive celebrations until you add it again.",
                            },
                            "confirm": {"type": "plain_text", "text": "Remove"},
                            "deny": {"type": "plain_text", "text": "Cancel"},
                        },
                    },
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
            "text": {"type": "mrkdwn", "text": "*Upcoming Birthdays*"},
        }
    )

    if upcoming:
        # Build bulleted list of upcoming birthdays
        birthday_lines = []
        for bday in upcoming:
            if bday["days_until"] == 0:
                days_text = "_Today!_ 🎂"
            elif bday["days_until"] == 1:
                days_text = "_Tomorrow_"
            else:
                days_text = f"_in {bday['days_until']} days_"

            birthday_lines.append(f"• <@{bday['user_id']}> ({bday['date']}) - {days_text}")

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
                    "text": "_No birthdays registered yet._",
                },
            }
        )

    blocks.append({"type": "divider"})

    # Upcoming Special Days
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Upcoming Special Days*"},
        }
    )

    upcoming_special = get_upcoming_special_days(days_ahead=APP_HOME_UPCOMING_SPECIAL_DAYS)

    if upcoming_special:
        special_lines = []
        today = datetime.now(timezone.utc).date()

        for date_str, days_list in upcoming_special.items():
            # Parse date and calculate days until
            day, month = map(int, date_str.split("/"))
            special_date = today.replace(month=month, day=day)
            # Handle year rollover
            if special_date < today:
                special_date = special_date.replace(year=today.year + 1)
            days_until = (special_date - today).days

            if days_until == 0:
                days_text = "_Today!_ 🎉"
            elif days_until == 1:
                days_text = "_Tomorrow_"
            else:
                days_text = f"_in {days_until} days_"

            # Show up to 2 special days per date to avoid clutter
            day_names = [d.name for d in days_list[:2]]
            if len(days_list) > 2:
                day_names.append(f"+{len(days_list) - 2} more")
            special_lines.append(f"• {', '.join(day_names)} ({date_str}) - {days_text}")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(special_lines),
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No special days in the next week._",
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


def _get_upcoming_birthdays(birthdays, app, limit=APP_HOME_UPCOMING_BIRTHDAYS_LIMIT):
    """Get list of upcoming birthdays."""
    reference_date = datetime.now(timezone.utc)
    upcoming = []

    for user_id, data in birthdays.items():
        days = calculate_days_until_birthday(data["date"], reference_date)
        if days is not None:
            upcoming.append(
                {
                    "user_id": user_id,
                    "username": get_username(app, user_id),
                    "date": data["date"],
                    "year": data.get("year"),
                    "days_until": days,
                }
            )

    # Sort by days until and limit
    upcoming.sort(key=lambda x: x["days_until"])
    return upcoming[:limit]


def _publish_fallback_view(client, user_id):
    """Publish a minimal fallback view when the main view fails."""
    fallback_view = {
        "type": "home",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "BrightDayBot"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Something went wrong loading your birthday info. Please try again in a moment.",
                },
            },
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
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "You can also use `/birthday` to manage your birthday.",
                    }
                ],
            },
        ],
    }

    try:
        client.views_publish(user_id=user_id, view=fallback_view)
        logger.info(f"APP_HOME: Published fallback view for {user_id}")
    except Exception as e:
        logger.error(f"APP_HOME_ERROR: Failed to publish fallback view: {e}")
