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

    # Get channel members for filtering (used by multiple sections)
    from config import BIRTHDAY_CHANNEL
    from slack.client import get_channel_members

    channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
    channel_member_set = set(channel_members) if channel_members else set()

    # Get upcoming birthdays
    upcoming = _get_upcoming_birthdays(birthdays, app, limit=APP_HOME_UPCOMING_BIRTHDAYS_LIMIT)

    # Get birthday statistics
    stats = _get_birthday_statistics(birthdays, channel_member_set)

    blocks = []

    # Header
    blocks.append({"type": "header", "text": {"type": "plain_text", "text": "🎉 BrightDayBot"}})

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
            "text": {"type": "mrkdwn", "text": "*🎂 Your Birthday Status*"},
        }
    )

    if user_birthday:
        date_words = date_to_words(user_birthday["date"], user_birthday.get("year"))
        star_sign = get_star_sign(user_birthday["date"])
        age = calculate_age(user_birthday["year"]) if user_birthday.get("year") else None

        fields = [
            {"type": "mrkdwn", "text": f"📅 *Birthday*\n{date_words}"},
            {"type": "mrkdwn", "text": f"⭐ *Star Sign*\n{star_sign}"},
        ]

        if age:
            fields.append({"type": "mrkdwn", "text": f"🎈 *Age*\n{age} years"})

        blocks.append({"type": "section", "fields": fields})

        # Get and display preferences (use centralized defaults)
        from storage.birthdays import DEFAULT_PREFERENCES

        prefs = get_user_preferences(user_id) or {}
        is_active = prefs.get("active", DEFAULT_PREFERENCES["active"])
        image_enabled = prefs.get("image_enabled", DEFAULT_PREFERENCES["image_enabled"])
        show_age = prefs.get("show_age", DEFAULT_PREFERENCES["show_age"])
        celebration_style = prefs.get("celebration_style", DEFAULT_PREFERENCES["celebration_style"])

        pref_items = []
        if is_active:
            pref_items.append("✅ Active")
        else:
            pref_items.append("⏸️ Paused")
        pref_items.append(
            f"{'🖼️' if image_enabled else '📝'} {'Images On' if image_enabled else 'Text Only'}"
        )
        pref_items.append(
            f"{'🎂' if show_age else '🤫'} {'Age Shown' if show_age else 'Age Hidden'}"
        )
        style_emoji = {"quiet": "🤫", "standard": "🎊", "epic": "🚀"}.get(celebration_style, "🎊")
        pref_items.append(f"{style_emoji} {celebration_style.title()}")

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
                        "text": {"type": "plain_text", "text": "✏️ Edit Birthday", "emoji": True},
                        "action_id": "open_birthday_modal",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🗑️ Remove", "emoji": True},
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
                    "text": "🎈 You haven't added your birthday yet! Add it now to receive personalized celebrations.",
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
                        "text": {"type": "plain_text", "text": "➕ Add My Birthday", "emoji": True},
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
            "text": {"type": "mrkdwn", "text": "*🗓️ Upcoming Birthdays*"},
        }
    )

    if upcoming:
        # Build bulleted list of upcoming birthdays
        birthday_lines = []
        for bday in upcoming:
            if bday["days_until"] == 0:
                days_text = "🎂 _Today!_"
            elif bday["days_until"] == 1:
                days_text = "🔜 _Tomorrow_"
            else:
                days_text = f"_in {bday['days_until']} days_"

            birthday_lines.append(f"• <@{bday['user_id']}> ({bday['date']}) — {days_text}")

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
                    "text": "_No upcoming birthdays in the next few days._",
                },
            }
        )

    # Birthday Statistics Section
    if stats:
        blocks.append({"type": "divider"})

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*📊 Birthday Statistics*"},
            }
        )

        # Build stats fields for 2-column layout
        stats_fields = [
            {
                "type": "mrkdwn",
                "text": f"🎂 *Total Registered*\n{stats['total']} birthdays",
            }
        ]

        if stats["this_week"] > 0:
            week_text = (
                "1 celebration" if stats["this_week"] == 1 else f"{stats['this_week']} celebrations"
            )
            stats_fields.append({"type": "mrkdwn", "text": f"📅 *This Week*\n{week_text}"})

        if stats["this_month"] > 0:
            month_text = (
                "1 upcoming" if stats["this_month"] == 1 else f"{stats['this_month']} upcoming"
            )
            stats_fields.append({"type": "mrkdwn", "text": f"🗓️ *Next 30 Days*\n{month_text}"})

        if stats["most_common_month"]:
            count = stats["most_common_count"]
            count_text = "1 birthday" if count == 1 else f"{count} birthdays"
            stats_fields.append(
                {
                    "type": "mrkdwn",
                    "text": f"⭐ *Most Popular*\n{stats['most_common_month']} ({count_text})",
                }
            )

        blocks.append({"type": "section", "fields": stats_fields})

        # Fun fact about empty months as context
        if stats["empty_months"]:
            if len(stats["empty_months"]) == 1:
                fun_fact = f"💡 No one born in {stats['empty_months'][0]} yet — be the first!"
            elif len(stats["empty_months"]) <= 3:
                fun_fact = f"💡 Missing birthdays in: {', '.join(stats['empty_months'])}"
            else:
                fun_fact = None

            if fun_fact:
                blocks.append(
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": fun_fact}],
                    }
                )

    blocks.append({"type": "divider"})

    # Upcoming Special Days
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*✨ Upcoming Special Days*"},
        }
    )

    upcoming_special = get_upcoming_special_days(days_ahead=APP_HOME_UPCOMING_SPECIAL_DAYS)

    if upcoming_special:
        special_lines = []
        today = datetime.now(timezone.utc).date()

        for date_str, days_list in upcoming_special.items():
            # Parse date and calculate days until (with validation)
            try:
                day, month = map(int, date_str.split("/"))
                special_date = today.replace(month=month, day=day)
                # Handle year rollover
                if special_date < today:
                    special_date = special_date.replace(year=today.year + 1)
                days_until = (special_date - today).days
            except (ValueError, TypeError):
                # Skip malformed date entries
                continue

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
                    "text": "_No special days coming up this week._",
                },
            }
        )

    blocks.append({"type": "divider"})

    # Quick Commands
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*⌨️ Quick Commands*"},
        }
    )

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Use these slash commands anywhere:\n"
                + "• `/birthday` — Add or edit your birthday\n"
                + "• `/birthday check` — Check your birthday\n"
                + "• `/birthday list` — See upcoming birthdays\n"
                + "• `/birthday export` — Export to calendar\n"
                + "• `/special-day` — View today's special days",
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
                    "text": "💡 Tip: Send me a DM with your date (e.g., 25/12) to quickly add your birthday!",
                }
            ],
        }
    )

    return {"type": "home", "blocks": blocks}


def _get_upcoming_birthdays(birthdays, app, limit=APP_HOME_UPCOMING_BIRTHDAYS_LIMIT):
    """Get list of upcoming birthdays for validated users only."""
    from config import BIRTHDAY_CHANNEL
    from slack.client import get_channel_members
    from storage.birthdays import is_user_active

    reference_date = datetime.now(timezone.utc)
    upcoming = []

    # Get channel members once for validation
    channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
    channel_member_set = set(channel_members) if channel_members else set()

    for user_id, data in birthdays.items():
        # Skip users not in birthday channel
        if user_id not in channel_member_set:
            continue

        # Skip users with paused celebrations
        if not is_user_active(user_id, data):
            continue

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


def _get_birthday_statistics(birthdays, channel_member_set):
    """
    Calculate fun birthday statistics for the team.

    Args:
        birthdays: Dict of user_id -> birthday_data
        channel_member_set: Set of user IDs in the birthday channel

    Returns:
        Dict with various statistics
    """
    from calendar import month_name
    from collections import Counter

    # Filter to only active channel members
    active_birthdays = {
        uid: data
        for uid, data in birthdays.items()
        if uid in channel_member_set and isinstance(data, dict) and "date" in data
    }

    if not active_birthdays:
        return None

    # Count birthdays by month
    month_counts = Counter()
    for data in active_birthdays.values():
        try:
            day, month = data["date"].split("/")
            month_counts[int(month)] += 1
        except (ValueError, KeyError):
            continue

    if not month_counts:
        return None

    # Find most common month
    most_common_month = month_counts.most_common(1)[0] if month_counts else None

    # Find months with no birthdays
    all_months = set(range(1, 13))
    months_with_birthdays = set(month_counts.keys())
    empty_months = all_months - months_with_birthdays

    # Count birthdays this week (next 7 days)
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    week_end = today + timedelta(days=7)
    month_end = today + timedelta(days=30)

    birthdays_this_week = 0
    birthdays_this_month = 0

    for data in active_birthdays.values():
        try:
            day, month = map(int, data["date"].split("/"))
            # Create date for this year
            bday_this_year = today.replace(month=month, day=day)
            # Handle year rollover
            if bday_this_year < today:
                bday_this_year = bday_this_year.replace(year=today.year + 1)

            if today <= bday_this_year <= week_end:
                birthdays_this_week += 1
            if today <= bday_this_year <= month_end:
                birthdays_this_month += 1
        except (ValueError, TypeError):
            continue

    return {
        "total": len(active_birthdays),
        "most_common_month": month_name[most_common_month[0]] if most_common_month else None,
        "most_common_count": most_common_month[1] if most_common_month else 0,
        "empty_months": [month_name[m] for m in sorted(empty_months)],
        "this_week": birthdays_this_week,
        "this_month": birthdays_this_month,
    }


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
