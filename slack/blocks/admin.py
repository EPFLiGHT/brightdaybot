"""Block Kit builders for admin operations, health status, and permission messages."""

from typing import Any, Dict, List, Optional


def build_announce_result_blocks(success: bool) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for announcement confirmation results

    Args:
        success: Whether the announcement was sent successfully

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    if success:
        emoji = "✅"
        title = "Announcement Sent"
        message = "The announcement was sent successfully to the birthday channel!"
    else:
        emoji = "❌"
        title = "Announcement Failed"
        message = "Failed to send the announcement. Check the logs for details."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    fallback = f"{emoji} {title}: {message}"
    return blocks, fallback


def build_remind_result_blocks(
    successful: int,
    failed: int = 0,
    skipped_bots: int = 0,
    skipped_inactive: int = 0,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for reminder confirmation results

    Args:
        successful: Number of reminders sent successfully
        failed: Number of failed reminders
        skipped_bots: Number of bots skipped
        skipped_inactive: Number of inactive users skipped

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Build stats list
    stats_lines = [f"• Successfully sent: {successful}"]
    if failed > 0:
        stats_lines.append(f"• Failed: {failed}")
    if skipped_bots > 0:
        stats_lines.append(f"• Skipped (bots): {skipped_bots}")
    if skipped_inactive > 0:
        stats_lines.append(f"• Skipped (inactive): {skipped_inactive}")

    stats_text = "\n".join(stats_lines)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "✅ Reminders Sent"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": stats_text}},
    ]

    # Add context if there were issues
    if failed > 0 or skipped_bots > 0 or skipped_inactive > 0:
        context_parts = []
        if failed > 0:
            context_parts.append("Some reminders failed to send")
        if skipped_bots > 0 or skipped_inactive > 0:
            context_parts.append("Some users were skipped")

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"💡 {' and '.join(context_parts)}. Check logs for details.",
                    }
                ],
            }
        )

    fallback = f"✅ Reminders sent: {successful} successful"
    if failed > 0:
        fallback += f", {failed} failed"
    if skipped_bots > 0:
        fallback += f", {skipped_bots} bots skipped"
    if skipped_inactive > 0:
        fallback += f", {skipped_inactive} inactive skipped"

    return blocks, fallback


def build_confirmation_blocks(
    title: str,
    message: str,
    action_type: str = "success",
    details: Optional[Dict[str, str]] = None,
    actions: Optional[List[Dict[str, str]]] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for confirmation messages (birthday saved, updated, removed, etc.)

    Args:
        title: Main confirmation title (e.g., "Birthday Updated!")
        message: Main confirmation message
        action_type: Type of action - "success", "error", "warning", "info"
        details: Optional key-value pairs to display (e.g., {"Birthday": "25 December", "Age": "30"})
        actions: Optional list of action buttons (e.g., [{"text": "Edit", "action_id": "edit_birthday"}])

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Map action types to emojis
    emoji_map = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
    }
    emoji = emoji_map.get(action_type, "ℹ️")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add details as fields if provided
    if details:
        fields = []
        for key, value in details.items():
            fields.append({"type": "mrkdwn", "text": f"*{key}:*\n{value}"})

        if fields:
            blocks.append({"type": "section", "fields": fields})

    # Add action buttons if provided
    if actions:
        button_elements = []
        for action in actions:
            button_elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": action["text"]},
                    "action_id": action.get("action_id", f"action_{action['text'].lower()}"),
                    "value": action.get("value", ""),
                }
            )
        blocks.append({"type": "actions", "elements": button_elements})

    # Fallback text
    fallback_text = f"{emoji} {title}: {message}"

    return blocks, fallback_text


def build_health_status_blocks(
    status_data: Dict[str, Any], detailed: bool = False
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for system health status

    Args:
        status_data: Full status dictionary from get_system_status()
        detailed: If True, include additional diagnostic information

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    from utils.health import STATUS_OK

    blocks = []
    components = status_data.get("components", {})
    timestamp = status_data.get("timestamp", "Unknown")

    # Header
    blocks.append(
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤖 System Health Check"},
        }
    )
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Last checked: {timestamp}"}],
        }
    )
    blocks.append({"type": "divider"})

    # Core System Section
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*📁 Core System*"}})

    core_fields = []
    # Storage comes from directories.storage
    directories = components.get("directories", {})
    storage = directories.get("storage", {})
    storage_emoji = "✅" if storage.get("status") == STATUS_OK else "❌"
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{storage_emoji} *Storage*\n{'Available' if storage.get('status') == STATUS_OK else 'Unavailable'}",
        }
    )

    # Birthdays file
    birthdays = components.get("birthdays", {})
    birthday_emoji = "✅" if birthdays.get("status") == STATUS_OK else "❌"
    birthday_count = birthdays.get("birthday_count", "Unknown")
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{birthday_emoji} *Birthdays*\n{birthday_count} records",
        }
    )

    # Admins config
    admins = components.get("admins", {})
    admin_emoji = "✅" if admins.get("status") == STATUS_OK else "❌"
    admin_count = admins.get("admin_count", "Unknown")
    core_fields.append(
        {"type": "mrkdwn", "text": f"{admin_emoji} *Admins*\n{admin_count} configured"}
    )

    # Personality config
    personality = components.get("personality", {})
    personality_emoji = "✅" if personality.get("status") == STATUS_OK else "ℹ️"
    personality_name = personality.get("current_personality", "standard")
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{personality_emoji} *Personality*\n{personality_name}",
        }
    )

    blocks.append({"type": "section", "fields": core_fields})
    blocks.append({"type": "divider"})

    # API & Services Section
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🔌 APIs & Services*"}})

    api_fields = []
    # Environment variables for API keys
    env = components.get("environment", {})
    env_vars = env.get("variables", {})

    openai_var = env_vars.get("OPENAI_API_KEY", {})
    openai_emoji = "✅" if openai_var.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{openai_emoji} *OpenAI API*\n{'Configured' if openai_var.get('set') else 'Not configured'}",
        }
    )

    # Get model info from storage if available
    from storage.settings import get_openai_model_info

    model_info = get_openai_model_info()
    model_emoji = "✅" if model_info.get("valid") else "⚠️"
    model_name = model_info.get("model", "unknown")
    model_source = model_info.get("source", "default")
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{model_emoji} *AI Model*\n{model_name} ({model_source})",
        }
    )

    slack_bot_var = env_vars.get("SLACK_BOT_TOKEN", {})
    slack_bot_emoji = "✅" if slack_bot_var.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{slack_bot_emoji} *Slack Bot*\n{'Configured' if slack_bot_var.get('set') else 'Not configured'}",
        }
    )

    slack_app_var = env_vars.get("SLACK_APP_TOKEN", {})
    slack_app_emoji = "✅" if slack_app_var.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{slack_app_emoji} *Socket Mode*\n{'Configured' if slack_app_var.get('set') else 'Not configured'}",
        }
    )

    blocks.append({"type": "section", "fields": api_fields})
    blocks.append({"type": "divider"})

    # Features Section
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*⚙️ Features & Settings*"},
        }
    )

    feature_fields = []
    # Timezone settings from storage
    from storage.settings import load_timezone_settings

    tz_enabled, _ = load_timezone_settings()
    timezone_emoji = "✅" if tz_enabled else "ℹ️"
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{timezone_emoji} *Timezone Mode*\n{'Enabled' if tz_enabled else 'Disabled'}",
        }
    )

    # Cache directory
    cache_dir = directories.get("cache", {})
    cache_emoji = "✅" if cache_dir.get("status") == STATUS_OK else "ℹ️"
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{cache_emoji} *Cache*\n{'Available' if cache_dir.get('status') == STATUS_OK else 'Unavailable'}",
        }
    )

    # Log files
    logs = components.get("logs", {})
    logs_emoji = "✅" if logs.get("status") == STATUS_OK else "ℹ️"
    logs_size = logs.get("total_size_mb", 0)
    log_file_count = len(logs.get("files", {}))
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{logs_emoji} *Log Files*\n{log_file_count} files ({logs_size} MB)",
        }
    )

    # Birthday channel
    channel = components.get("birthday_channel", {})
    channel_emoji = "✅" if channel.get("status") == STATUS_OK else "❌"
    channel_name = channel.get("channel", "Not configured")
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{channel_emoji} *Birthday Channel*\n{channel_name}",
        }
    )

    blocks.append({"type": "section", "fields": feature_fields})
    blocks.append({"type": "divider"})

    # Scheduler & Backup summary (always shown)
    from services.scheduler import get_scheduler_health

    sched = get_scheduler_health()
    sched_emoji = "✅" if sched.get("status") == "ok" else "❌"
    sched_rate = sched.get("success_rate_percent")
    sched_rate_str = f"{sched_rate:.1f}%" if isinstance(sched_rate, (int, float)) else "N/A"
    sched_jobs = sched.get("scheduled_jobs", "?")

    # Calculate uptime
    from datetime import datetime

    sched_uptime = ""
    started_raw = sched.get("started_at")
    if isinstance(started_raw, str):
        try:
            started_dt = datetime.fromisoformat(started_raw)
            delta = datetime.now(started_dt.tzinfo) - started_dt
            days = delta.days
            hours = delta.seconds // 3600
            sched_uptime = f" · Up {days}d {hours}h" if days > 0 else f" · Up {hours}h"
        except (ValueError, TypeError):
            pass

    quick_fields = []
    quick_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{sched_emoji} *Scheduler*\n{sched_jobs} jobs · {sched_rate_str} success{sched_uptime}",
        }
    )

    # Backup summary
    import os

    from config import BACKUP_DIR

    backup_text = "No backups"
    if os.path.exists(BACKUP_DIR):
        backup_files = [
            f for f in os.listdir(BACKUP_DIR) if f.startswith("birthdays_") and f.endswith(".json")
        ]
        if backup_files:
            backup_count = len(backup_files)
            latest_path = max(
                (os.path.join(BACKUP_DIR, f) for f in backup_files),
                key=os.path.getmtime,
            )
            latest_time = (
                datetime.fromtimestamp(os.path.getmtime(latest_path))
                .astimezone()
                .strftime("%Y-%m-%d %H:%M")
            )
            backup_text = f"{backup_count} files · Last: `{latest_time}`"

    quick_fields.append({"type": "mrkdwn", "text": f"💾 *Backups*\n{backup_text}"})

    blocks.append({"type": "section", "fields": quick_fields})

    if detailed:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Detailed mode - showing additional diagnostics",
                    }
                ],
            }
        )

        # System Paths
        from config import BIRTHDAYS_JSON_FILE, CACHE_DIR, DATA_DIR, STORAGE_DIR

        paths_text = f"*System Paths:*\n• Data Directory: `{DATA_DIR}`\n• Storage Directory: `{STORAGE_DIR}`\n• Birthdays File: `{BIRTHDAYS_JSON_FILE}`\n• Cache Directory: `{CACHE_DIR}`"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": paths_text}})

        # Scheduler Health
        from services.scheduler import get_scheduler_summary

        scheduler_summary = get_scheduler_summary()
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Scheduler:*\n• {scheduler_summary}",
                },
            }
        )

        # Timing & Configuration
        from config import (
            DAILY_CHECK_TIME,
            IMAGE_GENERATION_PARAMS,
            MENTION_RATE_LIMIT_MAX,
            MENTION_RATE_LIMIT_WINDOW,
            PROFILE_ANALYSIS_ENABLED,
            SPECIAL_DAY_MENTION_ENABLED,
            SPECIAL_DAY_THREAD_ENABLED,
            SPECIAL_DAY_TOPIC_UPDATE_ENABLED,
            SPECIAL_DAYS_CHECK_TIME,
            SPECIAL_DAYS_IMAGE_ENABLED,
            SPECIAL_DAYS_MODE,
            SPECIAL_DAYS_WEEKLY_DAY,
            TIMEZONE_CELEBRATION_TIME,
        )
        from storage.settings import get_configured_openai_image_model

        active_image_model = get_configured_openai_image_model()

        tz_enabled, _ = load_timezone_settings()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        sd_mode = SPECIAL_DAYS_MODE.title()
        if SPECIAL_DAYS_MODE == "weekly":
            sd_mode += f" ({day_names[SPECIAL_DAYS_WEEKLY_DAY]})"

        timing_text = "*Timing & Configuration:*"
        if tz_enabled:
            timing_text += f"\n• Birthday check: `{TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')}` (per-user timezone)"
        else:
            timing_text += (
                f"\n• Birthday check: `{DAILY_CHECK_TIME.strftime('%H:%M')}` (server time)"
            )
        timing_text += f"\n• Special days check: `{SPECIAL_DAYS_CHECK_TIME.strftime('%H:%M')}` · Mode: {sd_mode}"
        timing_text += f"\n• Special days: @-here {'✅' if SPECIAL_DAY_MENTION_ENABLED else '❌'} · Topic update {'✅' if SPECIAL_DAY_TOPIC_UPDATE_ENABLED else '❌'} · Thread replies {'✅' if SPECIAL_DAY_THREAD_ENABLED else '❌'} · Images {'✅' if SPECIAL_DAYS_IMAGE_ENABLED else '❌'}"

        img_quality = IMAGE_GENERATION_PARAMS["quality"]["default"]
        img_size = IMAGE_GENERATION_PARAMS["size"]["default"]
        timing_text += f"\n• Image model: {active_image_model} · Quality: {img_quality} · Size: {img_size} · Profile analysis {'✅' if PROFILE_ANALYSIS_ENABLED else '❌'}"
        timing_text += f"\n• @-Mention rate limit: {MENTION_RATE_LIMIT_MAX} requests / {MENTION_RATE_LIMIT_WINDOW}s"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": timing_text}})

        # Special Days Sources
        special_days = components.get("special_days", {})
        if special_days.get("enabled"):
            sd_text = f"*Special Days:*\n• Custom: {special_days.get('observance_count', 0)}"

            # Check UN observances cache
            import json
            import os

            from config import UN_OBSERVANCES_CACHE_FILE, UN_OBSERVANCES_ENABLED

            if UN_OBSERVANCES_ENABLED and os.path.exists(UN_OBSERVANCES_CACHE_FILE):
                try:
                    with open(UN_OBSERVANCES_CACHE_FILE, "r") as f:
                        un_data = json.load(f)
                    un_count = len(un_data.get("observances", []))
                    un_refreshed_raw = un_data.get("last_updated", "unknown")
                    un_refreshed = un_refreshed_raw[:10] if un_refreshed_raw else "unknown"
                    sd_text += f"\n• UN observances: {un_count} (updated: {un_refreshed})"
                except (json.JSONDecodeError, OSError, KeyError, TypeError):
                    sd_text += "\n• UN observances: cache error"

            # Check UNESCO observances cache
            from config import UNESCO_OBSERVANCES_CACHE_FILE, UNESCO_OBSERVANCES_ENABLED

            if UNESCO_OBSERVANCES_ENABLED and os.path.exists(UNESCO_OBSERVANCES_CACHE_FILE):
                try:
                    with open(UNESCO_OBSERVANCES_CACHE_FILE, "r") as f:
                        unesco_data = json.load(f)
                    unesco_count = len(unesco_data.get("observances", []))
                    unesco_refreshed_raw = unesco_data.get("last_updated", "unknown")
                    unesco_refreshed = (
                        unesco_refreshed_raw[:10] if unesco_refreshed_raw else "unknown"
                    )
                    sd_text += (
                        f"\n• UNESCO observances: {unesco_count} (updated: {unesco_refreshed})"
                    )
                except (json.JSONDecodeError, OSError, KeyError, TypeError):
                    sd_text += "\n• UNESCO observances: cache error"

            # Check WHO observances cache
            from config import WHO_OBSERVANCES_CACHE_FILE, WHO_OBSERVANCES_ENABLED

            if WHO_OBSERVANCES_ENABLED and os.path.exists(WHO_OBSERVANCES_CACHE_FILE):
                try:
                    with open(WHO_OBSERVANCES_CACHE_FILE, "r") as f:
                        who_data = json.load(f)
                    who_count = len(who_data.get("observances", []))
                    who_refreshed_raw = who_data.get("last_updated", "unknown")
                    who_refreshed = who_refreshed_raw[:10] if who_refreshed_raw else "unknown"
                    sd_text += f"\n• WHO observances: {who_count} (updated: {who_refreshed})"
                except (json.JSONDecodeError, OSError, KeyError, TypeError):
                    sd_text += "\n• WHO observances: cache error"

            # Check Calendarific sources
            from config import CALENDARIFIC_ENABLED

            if CALENDARIFIC_ENABLED:
                try:
                    from integrations.calendarific import get_calendarific_client

                    cal_status = get_calendarific_client().get_api_status()
                    month_calls = cal_status.get("month_calls", 0)
                    monthly_limit = cal_status.get("monthly_limit", 500)

                    for sid, info in cal_status.get("sources", {}).items():
                        if info.get("enabled"):
                            count = info.get("holiday_count", 0)
                            sd_text += f"\n• {info['label']}: {count} holidays"
                    sd_text += (
                        f"\n• _Calendarific API: {month_calls}/{monthly_limit} calls this month_"
                    )
                except (ImportError, AttributeError, KeyError, TypeError):
                    sd_text += "\n• Calendarific: error"

            # Total deduplicated count
            try:
                from storage.special_days import load_all_special_days

                total_sd = len(load_all_special_days())
                sd_text += f"\n• *Total (deduplicated): {total_sd}*"
            except Exception:
                pass

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": sd_text}})

        # Thread Tracker Stats
        from storage.thread_tracking import get_thread_tracker

        tracker = get_thread_tracker()
        tracker_stats = tracker.get_all_stats()
        tracker_text = f"*Thread Tracking:*\n• Active threads: {tracker_stats.get('active_threads', 0)}\n• Total reactions: {tracker_stats.get('total_reactions', 0)}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": tracker_text}})

        # Interactive Features Status
        from config import (
            AI_IMAGE_GENERATION_ENABLED,
            MENTION_QA_ENABLED,
            NLP_DATE_PARSING_ENABLED,
            THREAD_ENGAGEMENT_ENABLED,
        )

        features_text = "*Interactive Features:*"
        features_text += (
            f"\n• Thread engagement: {'✅ enabled' if THREAD_ENGAGEMENT_ENABLED else '❌ disabled'}"
        )
        features_text += (
            f"\n• @-Mention Q&A: {'✅ enabled' if MENTION_QA_ENABLED else '❌ disabled'}"
        )
        features_text += (
            f"\n• NLP date parsing: {'✅ enabled' if NLP_DATE_PARSING_ENABLED else '❌ disabled'}"
        )
        features_text += f"\n• AI image generation: {'✅ enabled' if AI_IMAGE_GENERATION_ENABLED else '❌ disabled'}"

        from storage.settings import load_bot_celebration_setting

        bot_celebration = load_bot_celebration_setting()
        features_text += (
            f"\n• Bot self-celebration: {'✅ enabled' if bot_celebration else '❌ disabled'}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": features_text}})

        # Backup details
        backup_text = "*Backups:*"
        if os.path.exists(BACKUP_DIR):
            backup_files = sorted(
                [
                    f
                    for f in os.listdir(BACKUP_DIR)
                    if f.startswith("birthdays_") and f.endswith(".json")
                ],
                key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)),
                reverse=True,
            )
            if backup_files:
                total_size = sum(os.path.getsize(os.path.join(BACKUP_DIR, f)) for f in backup_files)
                total_size_kb = round(total_size / 1024, 1)
                latest_name = backup_files[0]
                latest_size_kb = round(
                    os.path.getsize(os.path.join(BACKUP_DIR, latest_name)) / 1024, 1
                )
                backup_text += f"\n• Files: {len(backup_files)} ({total_size_kb} KB total)"
                backup_text += f"\n• Latest: `{latest_name}` ({latest_size_kb} KB)"
            else:
                backup_text += "\n• No backup files yet"
        else:
            backup_text += "\n• Backup directory not found"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": backup_text}})

        # Log file details
        logs_detail = components.get("logs", {})
        if logs_detail.get("files"):
            log_text = "*Log Files:*"
            for log_name, log_info in logs_detail.get("files", {}).items():
                if log_info.get("exists"):
                    size_kb = log_info.get("size_kb", 0)
                    log_text += f"\n• {log_name}: {size_kb} KB"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": log_text}})

    fallback_text = f"🤖 System Health Check ({timestamp})\nBirthdays: {birthday_count} | Admins: {admin_count} | Model: {model_name}"

    return blocks, fallback_text


def build_permission_error_blocks(
    command: str, required_level: str = "admin"
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for permission error messages

    Args:
        command: The command that was attempted
        required_level: Required permission level (e.g., "admin")

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔒 Permission Denied"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"You don't have permission to use this command.\n\n*Command:* `{command}`\n*Required Level:* {required_level.title()}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 Contact a workspace admin if you believe this is an error",
                }
            ],
        },
    ]

    fallback_text = f"🔒 Permission denied: {command} requires {required_level} access"

    return blocks, fallback_text
