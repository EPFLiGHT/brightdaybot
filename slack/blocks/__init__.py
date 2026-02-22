"""
Slack Block Kit builder utilities for BrightDayBot.

Re-exports all block builders from domain-specific submodules for backward
compatibility. External code can continue to use `from slack.blocks import ...`.
"""

from slack.blocks.admin import (
    build_announce_result_blocks,
    build_confirmation_blocks,
    build_health_status_blocks,
    build_permission_error_blocks,
    build_remind_result_blocks,
)
from slack.blocks.birthday import (
    build_birthday_blocks,
    build_birthday_check_blocks,
    build_birthday_error_blocks,
    build_birthday_list_blocks,
    build_birthday_modal,
    build_birthday_not_found_blocks,
    build_bot_celebration_blocks,
    build_upcoming_birthdays_blocks,
)
from slack.blocks.help import (
    build_hello_blocks,
    build_help_blocks,
    build_slash_help_blocks,
    build_unrecognized_input_blocks,
    build_welcome_blocks,
)
from slack.blocks.special_day import (
    build_special_day_blocks,
    build_special_day_stats_blocks,
    build_special_days_list_blocks,
    build_weekly_special_days_blocks,
)

__all__ = [
    # Birthday
    "build_birthday_blocks",
    "build_bot_celebration_blocks",
    "build_birthday_list_blocks",
    "build_birthday_error_blocks",
    "build_birthday_check_blocks",
    "build_birthday_not_found_blocks",
    "build_birthday_modal",
    "build_upcoming_birthdays_blocks",
    # Special day
    "build_special_day_blocks",
    "build_weekly_special_days_blocks",
    "build_special_days_list_blocks",
    "build_special_day_stats_blocks",
    # Admin
    "build_health_status_blocks",
    "build_announce_result_blocks",
    "build_remind_result_blocks",
    "build_confirmation_blocks",
    "build_permission_error_blocks",
    # Help
    "build_help_blocks",
    "build_welcome_blocks",
    "build_hello_blocks",
    "build_unrecognized_input_blocks",
    "build_slash_help_blocks",
]
