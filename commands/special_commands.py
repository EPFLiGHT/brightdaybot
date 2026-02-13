"""
Special days command handling for BrightDayBot.

Handles user special days commands (view, search, stats) and admin commands
(add, remove, config, test). Features quoted string parsing for multi-word
parameters and comprehensive special days management.

Main functions:
- handle_special_command(): User-facing special days commands
- handle_admin_special_command_with_quotes(): Admin commands with quoted parsing
- handle_admin_special_command(): Admin commands (non-add operations)
- parse_quoted_args(): Parse command text with quoted arguments
"""

from datetime import datetime, timedelta

from config import (
    CALENDARIFIC_PREFETCH_DAYS,
    DATE_FORMAT,
    DEFAULT_ANNOUNCEMENT_TIME,
    UPCOMING_DAYS_EXTENDED,
    get_logger,
)
from slack.client import get_username

logger = get_logger("commands")


def handle_special_command(args, user_id, say, app):
    """Handle user special days commands using Block Kit"""
    from slack.blocks import (
        build_special_day_stats_blocks,
        build_special_days_list_blocks,
    )
    from storage.special_days import (
        get_special_day_statistics,
        get_todays_special_days,
        get_upcoming_special_days,
        load_all_special_days,
    )

    # Default to showing today if no args
    if not args:
        args = ["today"]

    subcommand = args[0].lower()

    if subcommand == "today":
        # Show today's special days using Block Kit
        special_days = get_todays_special_days()
        from utils.date import format_date_european_short

        today_str = format_date_european_short(datetime.now())
        blocks, fallback = build_special_days_list_blocks(
            special_days, view_mode="today", date_filter=today_str
        )
        say(blocks=blocks, text=fallback)

    elif subcommand in ["week", "upcoming"]:
        # Show upcoming special days for the week using Block Kit
        upcoming = get_upcoming_special_days(7)

        # Build dict structure for Block Kit (date_str -> [days])
        # Sort by actual date objects for proper chronological order
        today = datetime.now()
        sorted_upcoming = {}
        for i in range(7):
            check_date = today + timedelta(days=i)
            date_str = check_date.strftime("%d/%m")
            if date_str in upcoming:
                sorted_upcoming[date_str] = upcoming[date_str]

        blocks, fallback = build_special_days_list_blocks(sorted_upcoming, view_mode="week")
        say(blocks=blocks, text=fallback)

    elif subcommand == "month":
        # Show special days for the extended lookahead period using Block Kit
        upcoming = get_upcoming_special_days(UPCOMING_DAYS_EXTENDED)

        # Build dict structure for Block Kit (date_str -> [days])
        # Sort by actual date objects for proper chronological order
        today = datetime.now()
        sorted_upcoming = {}
        for i in range(UPCOMING_DAYS_EXTENDED):
            check_date = today + timedelta(days=i)
            date_str = check_date.strftime("%d/%m")
            if date_str in upcoming:
                sorted_upcoming[date_str] = upcoming[date_str]

        blocks, fallback = build_special_days_list_blocks(sorted_upcoming, view_mode="month")
        say(blocks=blocks, text=fallback)

    elif subcommand == "list":
        # List upcoming special days by category using Block Kit (user-friendly view)
        category_filter = args[1] if len(args) > 1 else None
        all_days = load_all_special_days()

        if category_filter:
            all_days = [d for d in all_days if d.category.lower() == category_filter.lower()]

        blocks, fallback = build_special_days_list_blocks(
            all_days, view_mode="list", category_filter=category_filter
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "stats":
        # Show statistics using Block Kit
        stats = get_special_day_statistics()
        blocks, fallback = build_special_day_stats_blocks(stats)
        say(blocks=blocks, text=fallback)

    elif subcommand == "export":
        source_filter = args[1].lower() if len(args) > 1 else None
        _handle_special_day_export(source_filter, user_id, say, app)

    elif subcommand == "help":
        # Show help using Block Kit
        from slack.blocks import build_slash_help_blocks

        blocks, fallback = build_slash_help_blocks("special-day")
        say(blocks=blocks, text=fallback)

    else:
        # Unknown subcommand - show help
        from slack.blocks import build_slash_help_blocks

        blocks, fallback = build_slash_help_blocks("special-day")
        say(blocks=blocks, text=fallback)

    logger.info(f"SPECIAL: {get_username(app, user_id)} used special command: {' '.join(args)}")


def parse_quoted_args(command_text):
    """Parse command text with quoted arguments, handling spaces inside quotes"""
    parts = []
    current = ""
    in_quotes = False
    i = 0

    while i < len(command_text):
        char = command_text[i]

        if char == '"':
            if in_quotes:
                # End quote - add current part
                parts.append(current)
                current = ""
                in_quotes = False
            else:
                # Start quote
                in_quotes = True
        elif char == " " and not in_quotes:
            # Space outside quotes - end current part
            if current:
                parts.append(current)
                current = ""
        else:
            # Regular character
            current += char

        i += 1

    # Add final part if any
    if current:
        parts.append(current)

    return parts


def handle_admin_special_command_with_quotes(command_text, user_id, say, app):
    """Handle admin special days commands with quoted string parsing"""
    from storage.special_days import (
        SpecialDay,
        save_special_day,
    )

    username = get_username(app, user_id)

    # Parse quoted arguments
    args = parse_quoted_args(command_text)

    if not args:
        args = ["help"]

    subcommand = args[0].lower()

    if subcommand == "add":
        # Add a new special day: admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]
        if len(args) < 5:
            say(
                'Usage: `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]`\n'
                "Examples:\n"
                '• `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep"`\n'
                '• `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤"`\n'
                '• `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"`'
            )
            return

        try:
            date_str = args[1]
            name = args[2]
            category = args[3]
            description = args[4]
            emoji = args[5] if len(args) > 5 else ""
            source = args[6] if len(args) > 6 else "Custom"
            url = args[7] if len(args) > 7 else ""

            # Validate date format (DD/MM) using datetime
            date_obj = datetime.strptime(date_str, DATE_FORMAT)
            day, month = date_obj.day, date_obj.month

            # Basic URL validation if provided
            if url and not (url.startswith("http://") or url.startswith("https://")):
                say("❌ URL must start with http:// or https://")
                return

            # Validate category
            from config import SPECIAL_DAYS_CATEGORIES

            if category not in SPECIAL_DAYS_CATEGORIES:
                say(f"Invalid category. Must be one of: {', '.join(SPECIAL_DAYS_CATEGORIES)}")
                return

            special_day = SpecialDay(
                date=f"{day:02d}/{month:02d}",
                name=name,
                category=category,
                description=description,
                emoji=emoji,
                enabled=True,
                source=source,
                url=url,
            )

            if save_special_day(special_day, app, username):
                source_info = f" (Source: {source})" if source != "Custom" else ""
                url_info = f" - {url}" if url else ""
                say(
                    f"✅ Added special day: {emoji} *{name}* on {date_str} ({category}){source_info}{url_info}"
                )
                logger.info(
                    f"ADMIN_SPECIAL: {username} added special day: {name} on {date_str} with source: {source}"
                )
            else:
                say("❌ Failed to add special day. Check logs for details.")

        except (ValueError, IndexError):
            say(
                '❌ Invalid format. Use: `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]`\n'
                'Example: `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"`'
            )

    else:
        # For non-add commands, fall back to the original handler
        # Convert back to simple args for compatibility
        simple_args = command_text.split()
        handle_admin_special_command(simple_args, user_id, say, app)


def handle_admin_special_command(args, user_id, say, app):
    """Handle admin special days commands (non-add commands only)"""
    from services.special_day import generate_special_day_message
    from storage.special_days import (
        get_special_days_for_date,
        load_all_special_days,
        load_special_days_config,
        remove_special_day,
        save_special_days_config,
        update_category_status,
    )

    username = get_username(app, user_id)

    if not args:
        args = ["help"]

    subcommand = args[0].lower()

    if subcommand == "remove":
        # Remove a special day: admin special remove DD/MM [name]
        if len(args) < 2:
            say("Usage: `admin special remove DD/MM [name]`")
            return

        date_str = args[1]
        name = args[2] if len(args) > 2 else None

        if remove_special_day(date_str, name, app, username):
            say(f"✅ Removed special day(s) for {date_str}")
            logger.info(f"ADMIN_SPECIAL: {username} removed special day for {date_str}")
        else:
            say(f"❌ No special day found for {date_str}")

    elif subcommand == "list":
        # List all special days with admin details using Block Kit
        from slack.blocks import build_special_days_list_blocks

        category_filter = args[1] if len(args) > 1 else None
        all_days = load_all_special_days()

        if category_filter:
            all_days = [d for d in all_days if d.category.lower() == category_filter.lower()]

        blocks, fallback = build_special_days_list_blocks(
            all_days, view_mode="list", category_filter=category_filter, admin_view=True
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "categories":
        # Manage category settings
        config = load_special_days_config()
        categories_enabled = config.get("categories_enabled", {})

        if len(args) == 1:
            # Show current status
            message = "📋 *Special Days Categories:*\n\n"
            from config import SPECIAL_DAYS_CATEGORIES

            for category in SPECIAL_DAYS_CATEGORIES:
                status = "✅" if categories_enabled.get(category, True) else "❌"
                message += f"{status} {category}\n"
            say(message)

        elif len(args) >= 3 and args[1] in ["enable", "disable"]:
            # Enable/disable a category
            action = args[1]
            category = " ".join(args[2:])
            enabled = action == "enable"

            if update_category_status(category, enabled):
                say(f"✅ {category} category {'enabled' if enabled else 'disabled'}")
                logger.info(f"ADMIN_SPECIAL: {username} {action}d category: {category}")
            else:
                say(f"❌ Invalid category: {category}")

    elif subcommand == "test":
        # Test announcement for a specific date
        if len(args) < 2:
            # Test today
            test_date = datetime.now()
        else:
            try:
                # Parse date (DD/MM) using datetime
                date_str = args[1]
                date_obj = datetime.strptime(date_str, DATE_FORMAT)
                test_date = datetime.now().replace(day=date_obj.day, month=date_obj.month)
            except (ValueError, IndexError):
                say("Invalid date format. Use DD/MM")
                return

        special_days = get_special_days_for_date(test_date)

        if special_days:
            from utils.date import format_date_european_short

            test_date_str = format_date_european_short(test_date)
            say(f"🧪 Testing special day announcement for {test_date_str}...")

            # Always send separate announcements for each observance
            if len(special_days) >= 1:
                say(f"📋 Sending {len(special_days)} separate test announcement(s)")

                for idx, special_day in enumerate(special_days, 1):
                    try:
                        # say(
                        #     f"\n*{idx}/{len(special_days)}: {special_day.name}* ({special_day.category})"
                        # )

                        # Generate individual message
                        message = generate_special_day_message(
                            [special_day],
                            test_mode=True,
                            app=app,
                            use_teaser=True,
                            test_date=test_date,
                        )

                        # Generate detailed content
                        from services.special_day import (
                            generate_special_day_details,
                        )

                        detailed_content = generate_special_day_details(
                            [special_day], app=app, test_date=test_date
                        )

                        if message:
                            # Build blocks for individual observance (unified function with list)
                            from config import SPECIAL_DAYS_PERSONALITY
                            from slack.blocks import build_special_day_blocks

                            blocks, fallback_text = build_special_day_blocks(
                                [special_day],
                                message,
                                personality=SPECIAL_DAYS_PERSONALITY,
                                detailed_content=detailed_content,
                            )

                            # Send individual announcement to admin DM
                            from slack.client import send_message

                            send_message(app, user_id, fallback_text, blocks)

                        else:
                            say(f"❌ Failed to generate message for {special_day.name}")

                    except Exception as e:
                        say(f"❌ Error testing {special_day.name}: {e}")

                say(f"\n✅ Sent {len(special_days)} separate announcement(s) to your DM")
        else:
            from utils.date import format_date_european_short

            test_date_str = format_date_european_short(test_date)
            say(f"No special days found for {test_date_str}")

    elif subcommand == "config":
        # Show or update configuration
        config = load_special_days_config()

        if len(args) == 1:
            # Show current config
            message = "⚙️ *Special Days Configuration:*\n\n"
            message += (
                f"• Feature: {'✅ Enabled' if config.get('enabled', False) else '❌ Disabled'}\n"
            )
            message += f"• Personality: {config.get('personality', 'chronicler')}\n"
            message += f"• Announcement time: {config.get('announcement_time', DEFAULT_ANNOUNCEMENT_TIME)}\n"
            message += f"• Channel: {config.get('channel_override') or 'Using birthday channel'}\n"
            message += (
                f"• Image generation: {'✅' if config.get('image_generation', False) else '❌'}\n"
            )
            say(message)

        elif len(args) >= 3:
            # Update config
            setting = args[1].lower()
            value = " ".join(args[2:])

            if setting == "personality":
                config["personality"] = value
            elif setting == "time":
                config["announcement_time"] = value
            elif setting == "channel":
                config["channel_override"] = value if value != "none" else None
            elif setting == "images":
                config["image_generation"] = value.lower() in ["true", "on", "yes", "1"]
            elif setting == "enable":
                config["enabled"] = True
            elif setting == "disable":
                config["enabled"] = False
            else:
                say(f"Unknown setting: {setting}")
                return

            if save_special_days_config(config):
                say(f"✅ Updated special days {setting}")
                logger.info(f"ADMIN_SPECIAL: {username} updated config: {setting} = {value}")
            else:
                say("❌ Failed to save configuration")

    elif subcommand == "mode":
        # Switch between daily and weekly announcement modes
        from config import WEEKDAY_NAMES
        from storage.special_days import (
            get_pending_mode_transition,
            get_special_days_mode,
            get_weekly_day,
            set_special_days_mode,
        )

        current_mode = get_special_days_mode()
        current_day = get_weekly_day()
        current_day_name = WEEKDAY_NAMES[current_day].capitalize()
        pending = get_pending_mode_transition()

        if len(args) == 1:
            # Show current mode
            transition_note = ""
            if pending:
                eff = pending["effective_date"].strftime("%A, %b %d")
                transition_note = f"\n• _Switching to *{pending['target_mode']}* on {eff}_"

            if current_mode == "weekly":
                message = f"""📅 *Special Days Announcement Mode*

• Current mode: *Weekly*
• Digest day: *{current_day_name}*{transition_note}

In weekly mode, a single digest of all upcoming observances is posted once per week."""
            else:
                message = f"""📅 *Special Days Announcement Mode*

• Current mode: *Daily*{transition_note}

In daily mode, individual announcements are posted each day with observances."""
            say(message)

        elif args[1].lower() == "daily":
            # Switch to daily mode
            if set_special_days_mode("daily"):
                say(
                    "✅ Switched to *daily* mode. Individual announcements will be posted each day.\n\n"
                    "Change takes effect immediately."
                )
                logger.info(f"ADMIN_SPECIAL: {username} switched to daily mode")
            else:
                say("❌ Failed to switch mode")

        elif args[1].lower() == "weekly":
            # Switch to weekly mode
            # Check if a specific day was provided
            if len(args) >= 3:
                day_input = args[2].lower()
                if day_input in WEEKDAY_NAMES:
                    weekly_day = WEEKDAY_NAMES.index(day_input)
                elif day_input.isdigit() and 0 <= int(day_input) <= 6:
                    weekly_day = int(day_input)
                else:
                    say(
                        f"❌ Invalid day: {day_input}\n"
                        f"Use a day name (monday, tuesday, etc.) or number (0-6 where 0=Monday)"
                    )
                    return
            else:
                weekly_day = current_day  # Keep existing day

            day_name = WEEKDAY_NAMES[weekly_day].capitalize()

            if set_special_days_mode("weekly", weekly_day):
                # Check if transition is deferred
                pending = get_pending_mode_transition()
                if pending:
                    eff = pending["effective_date"].strftime("%A, %b %d")
                    say(
                        f"✅ Switching to *weekly* mode. Digest will be posted every *{day_name}*.\n\n"
                        f"Daily announcements will continue until *{eff}*."
                    )
                else:
                    say(f"✅ Switched to *weekly* mode. Digest will be posted every *{day_name}*.")
                logger.info(f"ADMIN_SPECIAL: {username} switched to weekly mode on {day_name}")
            else:
                say("❌ Failed to switch mode")

        else:
            say(
                "Usage:\n"
                "• `admin special mode` - Show current mode\n"
                "• `admin special mode daily` - Switch to daily mode\n"
                "• `admin special mode weekly` - Switch to weekly (default Monday)\n"
                "• `admin special mode weekly friday` - Switch to weekly on Friday"
            )

    elif subcommand == "verify":
        # Verify special days data
        from storage.special_days import verify_special_days

        results = verify_special_days()

        message = "🔍 *Special Days Verification Report:*\n\n"
        message += "*Statistics:*\n"
        message += f"• Total days: {results['stats']['total']}\n"
        message += f"• Days with source: {results['stats']['with_source']}\n"
        message += f"• Days with URL: {results['stats']['with_url']}\n\n"

        message += "*By Category:*\n"
        for cat, count in results["stats"]["by_category"].items():
            message += f"• {cat}: {count}\n"

        # Report issues
        issues_found = False
        if results["missing_sources"]:
            issues_found = True
            message += f"\n⚠️ *Missing Sources:* {len(results['missing_sources'])} days\n"
            if len(results["missing_sources"]) <= 5:
                for day in results["missing_sources"]:
                    message += f"  - {day}\n"
            else:
                message += "  (showing first 5)\n"
                for day in results["missing_sources"][:5]:
                    message += f"  - {day}\n"

        if results["duplicate_dates"]:
            issues_found = True
            message += "\n⚠️ *Duplicate Dates:*\n"
            for date, names in results["duplicate_dates"].items():
                message += f"  • {date}: {', '.join(names)}\n"

        if results["invalid_dates"]:
            issues_found = True
            message += f"\n❌ *Invalid Dates:* {len(results['invalid_dates'])}\n"

        if not issues_found:
            message += "\n✅ All data validation checks passed!"

        say(message)
        logger.info(f"ADMIN_SPECIAL: {username} ran verification")

    elif subcommand == "import":
        # Import special days from CSV
        say(
            "📥 Import feature not yet implemented. Please add special days individually or edit the CSV file directly."
        )

    elif subcommand == "refresh":
        # Calendarific: Force weekly prefetch
        from config import CALENDARIFIC_API_KEY, CALENDARIFIC_ENABLED

        if not CALENDARIFIC_ENABLED:
            say("❌ Calendarific API is not enabled. Set `CALENDARIFIC_ENABLED=true` in .env")
            return

        if not CALENDARIFIC_API_KEY:
            say("❌ Calendarific API key not configured. Add `CALENDARIFIC_API_KEY=...` to .env")
            return

        try:
            from integrations.calendarific import get_calendarific_client

            client = get_calendarific_client()

            # Check if force refresh
            force = len(args) > 1 and args[1].lower() == "force"
            days = CALENDARIFIC_PREFETCH_DAYS  # Default from config

            if len(args) > 1 and args[1].isdigit():
                days = min(int(args[1]), 14)  # Max 14 days to limit API calls

            say(f"🔄 Refreshing Calendarific cache for next {days} days...")

            stats = client.weekly_prefetch(days_ahead=days, force=force)

            if "error" in stats:
                say(f"❌ Prefetch failed: {stats['error']}")
            else:
                message = f"""✅ *Calendarific Prefetch Complete*

• Days fetched: {stats['fetched']}
• Days skipped (cached): {stats['skipped']}
• Holidays found: {stats['holidays_found']}
• API calls made: {stats['api_calls']}
• Failed: {stats['failed']}"""
                say(message)
                logger.info(f"ADMIN_SPECIAL: {username} ran Calendarific refresh")

        except Exception as e:
            say(f"❌ Prefetch error: {e}")
            logger.error(f"ADMIN_SPECIAL: Calendarific refresh failed: {e}")

    elif subcommand in ["observances-status", "observances", "sources"]:
        # Combined status for all observance sources
        try:
            from integrations.un_observances import get_un_cache_status
            from integrations.unesco_observances import get_unesco_cache_status
            from integrations.who_observances import get_who_cache_status

            un_status = get_un_cache_status()
            unesco_status = get_unesco_cache_status()
            who_status = get_who_cache_status()

            def format_status(status, name):
                fresh = "✅" if status["cache_fresh"] else "⚠️"
                count = status["observance_count"]
                return f"• {name}: {fresh} {count} days"

            message = f"""📊 *Observance Sources Status*

{format_status(un_status, "UN")}
{format_status(unesco_status, "UNESCO")}
{format_status(who_status, "WHO")}

*Total unique days after deduplication:* ~284

_Use `admin special [un|unesco|who]-status` for details._
_Use `admin special [un|unesco|who]-refresh` to force update._"""
            say(message)

        except Exception as e:
            say(f"❌ Failed to get observances status: {e}")
            logger.error(f"ADMIN_SPECIAL: Failed to get observances status: {e}")

    elif subcommand in ["un-status", "un"]:
        # UN Observances: Show cache status
        try:
            from integrations.un_observances import get_un_cache_status

            status = get_un_cache_status()

            last_updated = status.get("last_updated")
            if last_updated:
                last_dt = datetime.fromisoformat(last_updated)
                last_str = last_dt.strftime("%Y-%m-%d %H:%M")
            else:
                last_str = "Never"

            message = f"""📊 *UN Observances Cache Status*

• Cache exists: {'✅ Yes' if status['cache_exists'] else '❌ No'}
• Cache fresh: {'✅ Yes' if status['cache_fresh'] else '⚠️ Stale'}
• Last updated: {last_str}
• Observances cached: {status['observance_count']}

*Source:* {status['source_url']}

_Cache refreshes weekly. Use `admin special un-refresh` to force update._"""
            say(message)

        except Exception as e:
            say(f"❌ Failed to get UN cache status: {e}")
            logger.error(f"ADMIN_SPECIAL: Failed to get UN status: {e}")

    elif subcommand == "un-refresh":
        # UN Observances: Force refresh
        try:
            from integrations.un_observances import refresh_un_cache

            say("🔄 Refreshing UN observances cache...")

            stats = refresh_un_cache(force=True)

            if stats.get("error"):
                say(f"❌ Refresh failed: {stats['error']}")
            else:
                say(f"✅ UN observances cache refreshed: {stats['fetched']} observances")
                logger.info(f"ADMIN_SPECIAL: {username} refreshed UN cache")

        except Exception as e:
            say(f"❌ Refresh error: {e}")
            logger.error(f"ADMIN_SPECIAL: UN refresh failed: {e}")

    elif subcommand in ["unesco-status", "unesco"]:
        # UNESCO Observances: Show cache status
        try:
            from integrations.unesco_observances import get_unesco_cache_status

            status = get_unesco_cache_status()

            last_updated = status.get("last_updated")
            if last_updated:
                last_dt = datetime.fromisoformat(last_updated)
                last_str = last_dt.strftime("%Y-%m-%d %H:%M")
            else:
                last_str = "Never"

            message = f"""📊 *UNESCO Observances Cache Status*

• Cache exists: {'✅ Yes' if status['cache_exists'] else '❌ No'}
• Cache fresh: {'✅ Yes' if status['cache_fresh'] else '⚠️ Stale'}
• Last updated: {last_str}
• Observances cached: {status['observance_count']}

*Source:* {status['source_url']}

_Cache refreshes monthly. Use `admin special unesco-refresh` to force update._"""
            say(message)

        except Exception as e:
            say(f"❌ Failed to get UNESCO cache status: {e}")
            logger.error(f"ADMIN_SPECIAL: Failed to get UNESCO status: {e}")

    elif subcommand == "unesco-refresh":
        # UNESCO Observances: Force refresh
        try:
            from integrations.unesco_observances import refresh_unesco_cache

            say("🔄 Refreshing UNESCO observances cache...")

            stats = refresh_unesco_cache(force=True)

            if stats.get("error"):
                say(f"❌ Refresh failed: {stats['error']}")
            else:
                say(f"✅ UNESCO observances cache refreshed: {stats['fetched']} observances")
                logger.info(f"ADMIN_SPECIAL: {username} refreshed UNESCO cache")

        except Exception as e:
            say(f"❌ Refresh error: {e}")
            logger.error(f"ADMIN_SPECIAL: UNESCO refresh failed: {e}")

    elif subcommand in ["who-status", "who"]:
        # WHO Observances: Show cache status
        try:
            from integrations.who_observances import get_who_cache_status

            status = get_who_cache_status()

            last_updated = status.get("last_updated")
            if last_updated:
                last_dt = datetime.fromisoformat(last_updated)
                last_str = last_dt.strftime("%Y-%m-%d %H:%M")
            else:
                last_str = "Never"

            message = f"""📊 *WHO Observances Cache Status*

• Cache exists: {'✅ Yes' if status['cache_exists'] else '❌ No'}
• Cache fresh: {'✅ Yes' if status['cache_fresh'] else '⚠️ Stale'}
• Last updated: {last_str}
• Observances cached: {status['observance_count']}

*Source:* {status['source_url']}

_Cache refreshes monthly. Use `admin special who-refresh` to force update._"""
            say(message)

        except Exception as e:
            say(f"❌ Failed to get WHO cache status: {e}")
            logger.error(f"ADMIN_SPECIAL: Failed to get WHO status: {e}")

    elif subcommand == "who-refresh":
        # WHO Observances: Force refresh
        try:
            from integrations.who_observances import refresh_who_cache

            say("🔄 Refreshing WHO observances cache...")

            stats = refresh_who_cache(force=True)

            if stats.get("error"):
                say(f"❌ Refresh failed: {stats['error']}")
            else:
                say(f"✅ WHO observances cache refreshed: {stats['fetched']} observances")
                logger.info(f"ADMIN_SPECIAL: {username} refreshed WHO cache")

        except Exception as e:
            say(f"❌ Refresh error: {e}")
            logger.error(f"ADMIN_SPECIAL: WHO refresh failed: {e}")

    elif subcommand in ["api-status", "api", "calendarific"]:
        # Calendarific: Show API status
        from config import CALENDARIFIC_API_KEY, CALENDARIFIC_ENABLED

        if not CALENDARIFIC_ENABLED:
            say("""📊 *Calendarific API Status*

• Status: ❌ Disabled
• To enable: Set `CALENDARIFIC_ENABLED=true` in .env
• Get free API key at: https://calendarific.com""")
            return

        try:
            from integrations.calendarific import get_calendarific_client

            client = get_calendarific_client()
            status = client.get_api_status()

            last_prefetch = status.get("last_prefetch")
            if last_prefetch:
                last_dt = datetime.fromisoformat(last_prefetch)
                last_str = last_dt.strftime("%Y-%m-%d %H:%M")
            else:
                last_str = "Never"

            message = f"""📊 *Calendarific API Status*

• Status: {'✅ Enabled' if status['enabled'] else '❌ Disabled'}
• API Key: {'✅ Configured' if status['api_key_configured'] else '❌ Missing'}
• Country: {status['country']}

*Usage This Month:*
• API calls: {status['month_calls']} / {status['monthly_limit']}
• Remaining: {status['calls_remaining']}

*Cache:*
• Cached dates: {status['cached_dates']}
• Cache TTL: {status['cache_ttl_days']} days
• Last prefetch: {last_str}
• Needs refresh: {'⚠️ Yes' if status['needs_prefetch'] else '✅ No'}

_Run `admin special refresh` to update cache_"""
            say(message)

        except Exception as e:
            say(f"❌ Failed to get API status: {e}")
            logger.error(f"ADMIN_SPECIAL: Failed to get Calendarific status: {e}")

    else:
        # Help message
        help_text = """*Admin Special Days Commands:*

• `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]` - Add a custom day
• `admin special remove DD/MM [name]` - Remove a custom day
• `admin special list [category]` - List all special days (all sources)
• `admin special categories [enable/disable category]` - Manage categories
• `admin special test [DD/MM]` - Test announcement for a date
• `admin special config [setting value]` - View/update configuration
• `admin special verify` - Verify CSV data accuracy

*Announcement Mode:*
• `admin special mode` - Show current mode (daily/weekly)
• `admin special mode daily` - Switch to daily announcements
• `admin special mode weekly [day]` - Switch to weekly digest (e.g., `weekly friday`)

*Observance Sources:*
• `admin special observances` - Combined status for all sources
• `admin special un-status` - UN cache status (~220 days, weekly)
• `admin special un-refresh` - Force refresh UN cache
• `admin special unesco-status` - UNESCO cache status (~75 days, monthly)
• `admin special unesco-refresh` - Force refresh UNESCO cache
• `admin special who-status` - WHO cache status (~26 days, monthly)
• `admin special who-refresh` - Force refresh WHO cache

*Calendarific API (national holidays):*
• `admin special api-status` - Show Calendarific status
• `admin special refresh [days]` - Prefetch upcoming days

*Categories:* Global Health, Tech, Culture, Company"""
        say(help_text)

    logger.info(
        f"ADMIN_SPECIAL: {username} ({user_id}) used admin special command: {' '.join(args)}"
    )


def _handle_special_day_export(source_filter, user_id, say, app):
    """
    Export special days as an ICS calendar file.

    Args:
        source_filter: Optional source to filter by (un/unesco/who/calendarific/custom), or None for all
        user_id: Slack user ID
        say: Slack say/respond function
        app: Slack app instance
    """
    import os
    import tempfile

    from slack.client import send_message_with_file
    from storage.special_days import load_all_special_days

    valid_sources = {"un", "unesco", "who", "calendarific", "custom"}

    # Treat "all" same as no filter
    if source_filter == "all":
        source_filter = None

    if source_filter and source_filter not in valid_sources:
        say(
            text=f"Unknown source `{source_filter}`. "
            f"Valid sources: {', '.join(f'`{s}`' for s in sorted(valid_sources))}\n"
            f"Or omit for all sources (deduplicated)."
        )
        return

    # Load all days (already deduplicated)
    all_days = load_all_special_days()

    # Filter by source if specified
    if source_filter:
        all_days = [d for d in all_days if d.source.lower() == source_filter]

    if not all_days:
        label = f" from `{source_filter}`" if source_filter else ""
        say(text=f"No special days{label} to export.")
        return

    # Generate ICS
    source_label = source_filter.upper() if source_filter else None
    ics_content = _generate_special_days_ics(all_days, source_label)

    logger.info(
        f"EXPORT: Generated special days calendar with {len(all_days)} events for {user_id}"
    )

    # Create temp file and upload
    temp_file_path = None
    try:
        prefix = f"special_days_{source_filter}_" if source_filter else "special_days_"
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ics",
            prefix=prefix,
            delete=False,
            encoding="utf-8",
        ) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(ics_content)

        source_text = f" ({source_label})" if source_label else ""
        message = (
            f"📅 *Special Days Calendar Export{source_text}* — {len(all_days)} observances\n\n"
            f"Import this `.ics` file into your calendar app "
            f"(Google Calendar, Outlook, Apple Calendar)."
        )

        success = send_message_with_file(app, user_id, message, temp_file_path)

        if success:
            say(
                text=f"✅ Calendar exported! Check your DMs for the `.ics` file "
                f"with {len(all_days)} special days{source_text}."
            )
        else:
            say(
                text=f"*Special Days Calendar Export{source_text}* — {len(all_days)} observances\n\n"
                f"Copy the content below and save as `special_days.ics`:\n\n"
                f"```\n{ics_content}\n```"
            )

    except Exception as e:
        logger.error(f"EXPORT_ERROR: Failed to create/upload special days calendar: {e}")
        say(
            text=f"*Special Days Calendar Export* — {len(all_days)} observances\n\n"
            f"Copy the content below and save as `special_days.ics`:\n\n"
            f"```\n{ics_content}\n```"
        )

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


def _generate_special_days_ics(days, source_label=None):
    """
    Generate ICS calendar content for special days.

    Args:
        days: List of SpecialDay objects
        source_label: Optional label for calendar name (e.g. "UN")

    Returns:
        str: ICS format calendar content
    """
    import hashlib
    from datetime import date

    from icalendar import Calendar, Event, vRecur

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
