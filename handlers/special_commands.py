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
from collections import defaultdict
from calendar import month_name
import csv

from config import (
    get_logger,
    SPECIAL_DAYS_CATEGORIES,
    SPECIAL_DAYS_PERSONALITY,
    DEFAULT_ANNOUNCEMENT_TIME,
)
from utils.slack_utils import get_username, send_message

logger = get_logger("commands")


def handle_special_command(args, user_id, say, app):
    """Handle user special days commands using Block Kit"""
    from utils.special_days_storage import (
        get_todays_special_days,
        get_upcoming_special_days,
        get_special_day_statistics,
        load_special_days,
    )
    from utils.block_builder import (
        build_special_days_list_blocks,
        build_special_day_stats_blocks,
    )
    from datetime import datetime, timedelta

    # Default to showing today if no args
    if not args:
        args = ["today"]

    subcommand = args[0].lower()

    if subcommand == "today":
        # Show today's special days using Block Kit
        special_days = get_todays_special_days()
        from utils.date_utils import format_date_european_short

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

        blocks, fallback = build_special_days_list_blocks(
            sorted_upcoming, view_mode="week"
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "month":
        # Show special days for the next 30 days using Block Kit
        upcoming = get_upcoming_special_days(30)

        # Build dict structure for Block Kit (date_str -> [days])
        # Sort by actual date objects for proper chronological order
        today = datetime.now()
        sorted_upcoming = {}
        for i in range(30):
            check_date = today + timedelta(days=i)
            date_str = check_date.strftime("%d/%m")
            if date_str in upcoming:
                sorted_upcoming[date_str] = upcoming[date_str]

        blocks, fallback = build_special_days_list_blocks(
            sorted_upcoming, view_mode="month"
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "search":
        # Search for specific special days using Block Kit
        if len(args) < 2:
            say("Please provide a search term. Example: `special search mental health`")
            return

        search_term = " ".join(args[1:]).lower()
        all_days = load_special_days()

        # Search in name and description
        matches = [
            day
            for day in all_days
            if search_term in day.name.lower() or search_term in day.description.lower()
        ]

        blocks, fallback = build_special_days_list_blocks(matches, view_mode="search")
        say(blocks=blocks, text=fallback)

    elif subcommand == "list":
        # List all special days by category using Block Kit
        category_filter = args[1] if len(args) > 1 else None
        all_days = load_special_days()

        if category_filter:
            all_days = [
                d for d in all_days if d.category.lower() == category_filter.lower()
            ]

        blocks, fallback = build_special_days_list_blocks(
            all_days, view_mode="list", category_filter=category_filter
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "stats":
        # Show statistics using Block Kit
        stats = get_special_day_statistics()
        blocks, fallback = build_special_day_stats_blocks(stats)
        say(blocks=blocks, text=fallback)

    else:
        # Help message (keeping as plain text for now)
        help_text = """*Special Days Commands:*

• `special` or `special today` - Show today's special days
• `special week` - Show special days for the next 7 days
• `special month` - Show special days for the next 30 days
• `special list [category]` - List all special days (optionally by category)
• `special search [term]` - Search for specific special days
• `special stats` - Show special days statistics

_Special days include global health observances, technology celebrations, and cultural events._"""
        say(help_text)

    logger.info(
        f"SPECIAL: {get_username(app, user_id)} used special command: {' '.join(args)}"
    )


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
    from utils.special_days_storage import (
        SpecialDay,
        save_special_day,
        remove_special_day,
        load_special_days,
        update_category_status,
        load_special_days_config,
        save_special_days_config,
        format_special_days_list,
        get_special_days_for_date,
        mark_special_day_announced,
    )
    from utils.special_day_generator import generate_special_day_message
    from datetime import datetime
    import csv

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

            # Validate date format (DD/MM)
            day, month = map(int, date_str.split("/"))
            if not (1 <= day <= 31 and 1 <= month <= 12):
                raise ValueError("Invalid date")

            # Basic URL validation if provided
            if url and not (url.startswith("http://") or url.startswith("https://")):
                say("❌ URL must start with http:// or https://")
                return

            # Validate category
            from config import SPECIAL_DAYS_CATEGORIES

            if category not in SPECIAL_DAYS_CATEGORIES:
                say(
                    f"Invalid category. Must be one of: {', '.join(SPECIAL_DAYS_CATEGORIES)}"
                )
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

        except (ValueError, IndexError) as e:
            say(
                f'❌ Invalid format. Use: `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]`\n'
                'Example: `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"`'
            )

    else:
        # For non-add commands, fall back to the original handler
        # Convert back to simple args for compatibility
        simple_args = command_text.split()
        handle_admin_special_command(simple_args, user_id, say, app)


def handle_admin_special_command(args, user_id, say, app):
    """Handle admin special days commands (non-add commands only)"""
    from utils.special_days_storage import (
        remove_special_day,
        load_special_days,
        update_category_status,
        load_special_days_config,
        save_special_days_config,
        format_special_days_list,
        get_special_days_for_date,
        mark_special_day_announced,
    )
    from utils.special_day_generator import generate_special_day_message
    from datetime import datetime
    import csv

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
        # List all special days or by category
        category_filter = args[1] if len(args) > 1 else None
        all_days = load_special_days()

        if category_filter:
            all_days = [
                d for d in all_days if d.category.lower() == category_filter.lower()
            ]

        if all_days:
            message = f"📅 *All Special Days{f' ({category_filter})' if category_filter else ''}:*\n\n"

            # Group by month
            from collections import defaultdict

            by_month = defaultdict(list)
            for day in all_days:
                month = int(
                    day.date.split("/")[1]
                )  # DD/MM format - month is second part
                by_month[month].append(day)

            for month in sorted(by_month.keys()):
                from calendar import month_name

                message += f"*{month_name[month]}:*\n"
                for day in sorted(
                    by_month[month],
                    key=lambda d: int(
                        d.date.split("/")[0]
                    ),  # DD/MM format - sort by day within month
                ):
                    emoji = f"{day.emoji} " if day.emoji else ""
                    status = "✅" if day.enabled else "❌"
                    message += (
                        f"  {status} {day.date}: {emoji}{day.name} ({day.category})\n"
                    )
                message += "\n"
        else:
            message = f"No special days found{f' for category {category_filter}' if category_filter else ''}."

        say(message)

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
                # Parse date (DD/MM)
                date_str = args[1]
                day, month = map(int, date_str.split("/"))
                test_date = datetime.now().replace(day=day, month=month)
            except:
                say("Invalid date format. Use DD/MM")
                return

        special_days = get_special_days_for_date(test_date)

        if special_days:
            from utils.date_utils import format_date_european_short

            test_date_str = format_date_european_short(test_date)
            say(f"🧪 Testing special day announcement for {test_date_str}...")

            # NEW: Check if observances should be split
            from utils.special_days_storage import should_split_observances

            should_split = should_split_observances(special_days)

            if should_split and len(special_days) > 1:
                # SPLIT APPROACH: Send individual test announcements
                say(
                    f"📋 Splitting {len(special_days)} observances into separate announcements (different categories)"
                )

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
                        from utils.special_day_generator import (
                            generate_special_day_details,
                        )

                        detailed_content = generate_special_day_details(
                            [special_day], app=app, test_date=test_date
                        )

                        if message:
                            # Build blocks for individual observance
                            from utils.block_builder import build_special_day_blocks
                            from config import SPECIAL_DAYS_PERSONALITY

                            blocks, fallback_text = build_special_day_blocks(
                                observance_name=special_day.name,
                                message=message,
                                observance_date=special_day.date,
                                source=special_day.source,
                                personality=SPECIAL_DAYS_PERSONALITY,
                                detailed_content=detailed_content,
                                category=special_day.category,
                                url=special_day.url,
                            )

                            # Send individual announcement to admin DM
                            from utils.slack_utils import send_message

                            send_message(app, user_id, fallback_text, blocks)

                        else:
                            say(f"❌ Failed to generate message for {special_day.name}")

                    except Exception as e:
                        say(f"❌ Error testing {special_day.name}: {e}")

                say(f"\n✅ Sent {len(special_days)} separate announcements to your DM")

            else:
                # COMBINED APPROACH: Original behavior for same category or single observance
                if len(special_days) > 1:
                    say(
                        f"📋 Combining {len(special_days)} observances into single announcement (same category)"
                    )

                # Generate SHORT teaser message (NEW: use_teaser=True by default)
                # Pass test_date so web search uses the correct date
                message = generate_special_day_message(
                    special_days,
                    test_mode=True,
                    app=app,
                    use_teaser=True,
                    test_date=test_date,
                )

                # Generate DETAILED content for "View Details" button (NEW)
                # Pass test_date so web search uses the correct date
                from utils.special_day_generator import generate_special_day_details

                detailed_content = generate_special_day_details(
                    special_days, app=app, test_date=test_date
                )

                if message:
                    # Build Block Kit blocks exactly like formal announcements
                    try:
                        from utils.block_builder import (
                            build_special_day_blocks,
                            build_consolidated_special_days_blocks,
                        )
                        from config import SPECIAL_DAYS_PERSONALITY

                        # Handle single or multiple special days (same logic as formal code)
                        if len(special_days) == 1:
                            special_day = special_days[0]
                            blocks, fallback_text = build_special_day_blocks(
                                observance_name=special_day.name,
                                message=message,
                                observance_date=special_day.date,
                                source=special_day.source,
                                personality=SPECIAL_DAYS_PERSONALITY,
                                detailed_content=detailed_content,  # NEW: Use detailed content instead of description
                                category=special_day.category,
                                url=special_day.url,
                            )
                        else:
                            # For multiple special days, use consolidated block structure
                            blocks, fallback_text = (
                                build_consolidated_special_days_blocks(
                                    special_days=special_days,
                                    message=message,
                                    personality=SPECIAL_DAYS_PERSONALITY,
                                    detailed_content=detailed_content,
                                )
                            )

                        logger.info(
                            f"ADMIN_SPECIAL_TEST: Built Block Kit structure with {len(blocks)} blocks"
                        )

                        # Send with Block Kit blocks to admin DM
                        from utils.slack_utils import send_message

                        send_message(app, user_id, fallback_text, blocks)

                    except Exception as block_error:
                        logger.warning(
                            f"ADMIN_SPECIAL_TEST: Failed to build blocks: {block_error}. Using plain text."
                        )
                        say(f"*Generated Message:*\n\n{message}")
                else:
                    say("❌ Failed to generate message")
        else:
            from utils.date_utils import format_date_european_short

            test_date_str = format_date_european_short(test_date)
            say(f"No special days found for {test_date_str}")

    elif subcommand == "config":
        # Show or update configuration
        config = load_special_days_config()

        if len(args) == 1:
            # Show current config
            message = "⚙️ *Special Days Configuration:*\n\n"
            message += f"• Feature: {'✅ Enabled' if config.get('enabled', False) else '❌ Disabled'}\n"
            message += f"• Personality: {config.get('personality', 'chronicler')}\n"
            message += f"• Announcement time: {config.get('announcement_time', DEFAULT_ANNOUNCEMENT_TIME)}\n"
            message += f"• Channel: {config.get('channel_override') or 'Using birthday channel'}\n"
            message += f"• Image generation: {'✅' if config.get('image_generation', False) else '❌'}\n"
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
                logger.info(
                    f"ADMIN_SPECIAL: {username} updated config: {setting} = {value}"
                )
            else:
                say("❌ Failed to save configuration")

    elif subcommand == "verify":
        # Verify special days data
        from utils.special_days_storage import verify_special_days

        results = verify_special_days()

        message = "🔍 *Special Days Verification Report:*\n\n"
        message += f"*Statistics:*\n"
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
            message += (
                f"\n⚠️ *Missing Sources:* {len(results['missing_sources'])} days\n"
            )
            if len(results["missing_sources"]) <= 5:
                for day in results["missing_sources"]:
                    message += f"  - {day}\n"
            else:
                message += f"  (showing first 5)\n"
                for day in results["missing_sources"][:5]:
                    message += f"  - {day}\n"

        if results["duplicate_dates"]:
            issues_found = True
            message += f"\n⚠️ *Duplicate Dates:*\n"
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

    else:
        # Help message
        help_text = """*Admin Special Days Commands:*

• `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]` - Add a special day (quoted strings support spaces)
• `admin special remove DD/MM [name]` - Remove a special day
• `admin special list [category]` - List all special days
• `admin special categories [enable/disable category]` - Manage categories
• `admin special test [DD/MM]` - Test announcement for a date
• `admin special config [setting value]` - View/update configuration
• `admin special verify` - Verify data accuracy and completeness
• `admin special import` - Import from CSV (coming soon)

*Categories:* Global Health, Tech, Culture, Company

*Add Command Examples:*
```
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep"
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤"
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society"
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"
```

*Note:* Use quotes around parameters with spaces. Source and URL are automatically integrated into AI-generated messages."""
        say(help_text)

    logger.info(
        f"ADMIN_SPECIAL: {username} ({user_id}) used admin special command: {' '.join(args)}"
    )
