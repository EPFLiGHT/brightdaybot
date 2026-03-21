"""
App Home handlers for BrightDayBot.

Displays user's birthday status, quick actions, and upcoming birthdays
when users open the app's Home tab.
"""

from datetime import datetime, timezone

from slack_sdk.errors import SlackApiError

from config import (
    APP_HOME_UPCOMING_BIRTHDAY_DATES,
    APP_HOME_UPCOMING_SPECIAL_DAYS,
    SLACK_SECTION_TEXT_MAX_LENGTH,
    get_logger,
)
from slack.client import get_username
from storage.birthdays import get_user_preferences, load_birthdays
from storage.special_days import get_upcoming_special_days
from utils.date_utils import calculate_days_until_birthday

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
    from utils.date_utils import calculate_age, date_to_words, get_star_sign

    # Get user's birthday status
    birthdays = load_birthdays()
    user_birthday = birthdays.get(user_id)

    # Get channel members for filtering (used by multiple sections)
    from config import BIRTHDAY_CHANNEL
    from slack.client import get_channel_members

    channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
    channel_member_set = set(channel_members) if channel_members else set()

    # Get upcoming birthdays (date-grouped)
    upcoming = _get_upcoming_birthdays(birthdays, app, channel_member_set=channel_member_set)

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

        # Personal birthday countdown
        days_until_own = calculate_days_until_birthday(
            user_birthday["date"], datetime.now(timezone.utc)
        )
        if days_until_own == 0:
            countdown = "🎉 *Today is your birthday!*"
        elif days_until_own == 1:
            countdown = "🔜 *Your birthday is tomorrow!*"
        elif days_until_own is not None:
            countdown = f"⏳ *{days_until_own} days* until your birthday"
        else:
            countdown = None
        if countdown:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": countdown}]})

        # Get and display preferences (use centralized defaults)
        from storage.birthdays import DEFAULT_PREFERENCES

        prefs = get_user_preferences(user_id) or {}
        is_active = prefs.get("active", DEFAULT_PREFERENCES["active"])
        image_enabled = prefs.get("image_enabled", DEFAULT_PREFERENCES["image_enabled"])
        show_age = prefs.get("show_age", DEFAULT_PREFERENCES["show_age"])
        celebration_style = prefs.get("celebration_style", DEFAULT_PREFERENCES["celebration_style"])

        # Only show non-obvious preferences (deviations from defaults)
        pref_items = []
        if not is_active:
            pref_items.append("⏸️ Paused")
        if not image_enabled:
            pref_items.append("📝 Text Only")
        if not show_age:
            pref_items.append("🤫 Age Hidden")

        if pref_items:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": " | ".join(pref_items)}],
                }
            )

        # Celebration style selector
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Celebration Style*"},
            }
        )

        # Style buttons - highlight current selection
        style_buttons = []
        for style_id, style_label in [
            ("quiet", "🤫 Quiet"),
            ("standard", "🎊 Standard"),
            ("epic", "🚀 Epic"),
        ]:
            button = {
                "type": "button",
                "text": {"type": "plain_text", "text": style_label, "emoji": True},
                "action_id": f"set_celebration_style_{style_id}",
                "value": style_id,
            }
            # Highlight current style with primary style
            if celebration_style == style_id:
                button["style"] = "primary"
            style_buttons.append(button)

        blocks.append({"type": "actions", "elements": style_buttons})

        # Style descriptions
        style_descriptions = {
            "quiet": "_No @-here, no image, simple message_",
            "standard": "_Message + AI image + @-here notification_",
            "epic": "_Extra reactions, celebratory flair_",
        }
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": style_descriptions.get(celebration_style, ""),
                    }
                ],
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

    # Upcoming Birthdays (date-grouped, consistent with special days)
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*🗓️ Upcoming Birthdays*"},
        }
    )

    if upcoming:
        birthday_lines = []
        for group in upcoming:
            days = group["days_until"]
            if days == 0:
                days_text = "_Today!_ 🎉"
            elif days == 1:
                days_text = "_Tomorrow_"
            else:
                days_text = f"_in {days} days_"

            names = ", ".join(f"<@{p['user_id']}>" for p in group["people"])
            birthday_lines.append(f"• 🎂 {names} ({group['date_words']}) - {days_text}")

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(birthday_lines)},
            }
        )

        # View All button
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 View All Birthdays",
                            "emoji": True,
                        },
                        "action_id": "view_all_birthdays",
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
                    "text": "_No upcoming birthdays this week._",
                },
            }
        )

    blocks.append({"type": "divider"})

    # Upcoming Special Days (no truncation — show all names per date)
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
            try:
                day, month = map(int, date_str.split("/"))
                special_date = today.replace(month=month, day=day)
                if special_date < today:
                    special_date = special_date.replace(year=today.year + 1)
                days_until = (special_date - today).days
            except (ValueError, TypeError):
                continue

            if days_until == 0:
                days_text = "_Today!_ 🎉"
            elif days_until == 1:
                days_text = "_Tomorrow_"
            else:
                days_text = f"_in {days_until} days_"

            # Blank line before each group (except first)
            if special_lines:
                special_lines.append("")
            special_lines.append(f"*{date_str}* — {days_text}")
            for d in days_list:
                prefix = f"{d.emoji} " if d.emoji else "• "
                special_lines.append(f"› {prefix}{d.name}")

        # Truncate on line boundary if exceeding Slack section text limit
        kept_lines = []
        total_len = 0
        for line in special_lines:
            if total_len + len(line) + 1 > SLACK_SECTION_TEXT_MAX_LENGTH:
                break
            kept_lines.append(line)
            total_len += len(line) + 1

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(kept_lines)}}
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No special days coming up this week._"},
            }
        )

    # Birthday Statistics (enhanced)
    if stats:
        blocks.append({"type": "divider"})

        # Compact stats: coverage + upcoming as header, month + sign as fields
        total = stats["total"]
        channel = stats.get("channel_size", 0)
        pct = f" ({round(total / channel * 100)}%)" if channel > 0 else ""
        week = stats["this_week"]
        month = stats["this_month"]

        summary_parts = [f"👥 *{total}* registered{pct}"]
        if week > 0:
            summary_parts.append(f"🎉 *{week}* this week")
        if month > 0:
            summary_parts.append(f"📅 *{month}* next 30 days")
        summary = " · ".join(summary_parts)

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "*📊 Birthday Statistics*"}}
        )
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": summary}],
            }
        )

        stats_fields = []
        if stats["most_common_month"]:
            stats_fields.append(
                {
                    "type": "mrkdwn",
                    "text": f"🏆 *Top Month*\n{stats['most_common_month']} ({stats['most_common_count']})",
                }
            )
        if stats.get("most_common_sign"):
            stats_fields.append(
                {
                    "type": "mrkdwn",
                    "text": f"⭐ *Top Star Sign*\n{stats['most_common_sign']} ({stats['most_common_sign_count']})",
                }
            )

        if stats_fields:
            blocks.append({"type": "section", "fields": stats_fields})

        # Fun facts as context
        fun_facts = []
        if stats.get("empty_months"):
            if len(stats["empty_months"]) == 1:
                fun_facts.append(f"No one born in {stats['empty_months'][0]} yet — be the first!")
            elif len(stats["empty_months"]) <= 3:
                fun_facts.append(f"Missing: {', '.join(stats['empty_months'])}")
        if fun_facts:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"💡 {' · '.join(fun_facts)}"}],
                }
            )

    blocks.append({"type": "divider"})

    # Export & Tools (action buttons replacing Quick Commands)
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📅 Export Birthdays (ICS)",
                        "emoji": True,
                    },
                    "action_id": "export_birthdays_ics",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🌍 Export Special Days (ICS)",
                        "emoji": True,
                    },
                    "action_id": "export_special_days_ics",
                },
            ],
        }
    )

    # Context footer
    if user_birthday:
        tip_text = "💡 Use `/birthday check @name` to check a teammate's birthday."
    else:
        tip_text = "💡 Click *Add My Birthday* above to get started!"
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": tip_text}],
        }
    )

    return {"type": "home", "blocks": blocks}


def _safe_date_words(date_str):
    """Convert DD/MM to words, falling back to raw string on error."""
    from utils.date_utils import date_to_words

    try:
        return date_to_words(date_str)
    except (ValueError, TypeError):
        return date_str


def _get_upcoming_birthdays(
    birthdays, app, limit=APP_HOME_UPCOMING_BIRTHDAY_DATES, channel_member_set=None
):
    """Get upcoming birthdays grouped by date for validated users only.

    Returns list of date groups: [{"date": "DD/MM", "date_words": "...", "days_until": N, "people": [...]}]
    Limited to `limit` unique dates (all people per date shown).
    """
    from storage.birthdays import is_user_active

    reference_date = datetime.now(timezone.utc)
    flat = []

    if channel_member_set is None:
        from config import BIRTHDAY_CHANNEL
        from slack.client import get_channel_members

        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        channel_member_set = set(channel_members) if channel_members else set()

    for user_id, data in birthdays.items():
        if user_id not in channel_member_set:
            continue
        if not is_user_active(user_id, data):
            continue

        days = calculate_days_until_birthday(data["date"], reference_date)
        if days is not None:
            flat.append({"user_id": user_id, "date": data["date"], "days_until": days})

    flat.sort(key=lambda x: x["days_until"])

    # Group by date, preserving sort order
    by_date = {}
    for entry in flat:
        by_date.setdefault(entry["date"], []).append(entry)

    # Take first N dates, resolve usernames only for displayed people
    result = []
    for date_str, people in list(by_date.items())[:limit]:
        for p in people:
            p["username"] = get_username(app, p["user_id"])
        result.append(
            {
                "date": date_str,
                "date_words": _safe_date_words(date_str),
                "days_until": people[0]["days_until"],
                "people": people,
            }
        )

    return result


def _get_birthday_statistics(birthdays, channel_member_set):
    """Calculate birthday statistics including coverage and star sign distribution."""
    from calendar import month_name
    from collections import Counter

    from utils.date_utils import get_star_sign

    active_birthdays = {
        uid: data
        for uid, data in birthdays.items()
        if uid in channel_member_set and isinstance(data, dict) and "date" in data
    }

    if not active_birthdays:
        return None

    from datetime import timedelta

    today = datetime.now(timezone.utc).date()
    week_end = today + timedelta(days=7)
    month_end = today + timedelta(days=30)

    month_counts = Counter()
    star_sign_counts = Counter()
    birthdays_this_week = 0
    birthdays_this_month = 0

    for data in active_birthdays.values():
        try:
            day, month = map(int, data["date"].split("/"))
            month_counts[month] += 1

            sign = get_star_sign(data["date"])
            if sign:
                star_sign_counts[sign] += 1

            bday_this_year = today.replace(month=month, day=day)
            if bday_this_year < today:
                bday_this_year = bday_this_year.replace(year=today.year + 1)
            if today <= bday_this_year <= week_end:
                birthdays_this_week += 1
            if today <= bday_this_year <= month_end:
                birthdays_this_month += 1
        except (ValueError, TypeError):
            continue

    if not month_counts:
        return None

    most_common_month = month_counts.most_common(1)[0] if month_counts else None
    most_common_sign = star_sign_counts.most_common(1)[0] if star_sign_counts else None
    empty_months = set(range(1, 13)) - set(month_counts.keys())

    return {
        "total": len(active_birthdays),
        "channel_size": len(channel_member_set),
        "most_common_month": month_name[most_common_month[0]] if most_common_month else None,
        "most_common_count": most_common_month[1] if most_common_month else 0,
        "most_common_sign": most_common_sign[0] if most_common_sign else None,
        "most_common_sign_count": most_common_sign[1] if most_common_sign else 0,
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
