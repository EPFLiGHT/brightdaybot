"""
BrightDayBot - AI-Powered Slack Birthday Celebration Bot

Main application entry point that initializes Slack Bot framework, event handlers,
and background scheduling for automatic birthday celebrations.

Features: AI messages/images, timezone-aware celebrations, multiple personalities,
admin system, automatic backups, component-specific logging.
Uses Slack Bolt, OpenAI API, and background scheduling.
"""

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Import configuration
from config import logger
from handlers.app_home_handler import register_app_home_handlers

# Import event handlers
from handlers.event_handler import register_event_handlers
from handlers.mention_handler import register_mention_handlers
from handlers.modal_handler import register_modal_handlers
from handlers.slash_handler import register_slash_commands
from services.birthday import simple_daily_check, timezone_aware_check

# Import services
from services.scheduler import run_now, setup_scheduler
from storage.settings import initialize_config
from storage.special_days import initialize_special_days_cache

# Initialize configuration from storage files
initialize_config()

# Initialize Slack app with error handling
app = App()
logger.info("INIT: App initialized")

# Register event handlers
register_event_handlers(app)
register_mention_handlers(app)

# Register slash commands and interactive components
register_slash_commands(app)
register_modal_handlers(app)
register_app_home_handlers(app)


def _check_deploy_notification(app):
    """Detect new deploy on startup and trigger canvas refresh."""
    try:
        import json
        import os

        from config import CANVAS_SETTINGS_FILE, DEPLOY_INFO_FILE
        from slack.canvas import record_change, update_canvas_async

        if not os.path.exists(DEPLOY_INFO_FILE):
            return

        with open(DEPLOY_INFO_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)

        new_commit = info.get("new_short", "")
        if not new_commit:
            return

        # Check if we already processed this deploy
        settings = {}
        if os.path.exists(CANVAS_SETTINGS_FILE):
            with open(CANVAS_SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)

        if settings.get("last_deploy_commit") == new_commit:
            return

        old_short = info.get("old_short", "?")
        status = info.get("status", "success")
        record_change(f"Deploy: `{old_short}` → `{new_commit}` ({status})")

        settings["last_deploy_commit"] = new_commit
        with open(CANVAS_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

        update_canvas_async(app, reason="deploy")
        logger.info(f"INIT: Deploy detected ({old_short} → {new_commit}), canvas refresh triggered")

    except Exception as e:
        logger.warning(f"INIT: Deploy detection failed (non-fatal): {e}")


# Start the app
if __name__ == "__main__":
    handler = SocketModeHandler(app)
    logger.info("INIT: Handler initialized, starting app")
    try:
        # Set up the scheduler with direct birthday check functions
        setup_scheduler(app, timezone_aware_check, simple_daily_check)

        # Initialize special days caches if stale or missing
        initialize_special_days_cache()

        # Detect new deploy and trigger canvas refresh
        _check_deploy_notification(app)

        # Check for today's birthdays at startup and catch up on missed celebrations
        run_now()

        # Start the app
        handler.start()
    except Exception as e:
        logger.critical(f"CRITICAL: Error starting app: {e}")
