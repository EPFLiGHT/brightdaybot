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
from storage.settings import initialize_config

# Import services
from services.scheduler import setup_scheduler, run_now
from services.birthday import timezone_aware_check, simple_daily_check
from storage.special_days import initialize_special_days_cache

# Import event handlers
from handlers.event_handler import register_event_handlers
from handlers.slash_commands import register_slash_commands
from handlers.modal_handlers import register_modal_handlers
from handlers.app_home import register_app_home_handlers
from handlers.mention_handler import register_mention_handlers

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

# Start the app
if __name__ == "__main__":
    handler = SocketModeHandler(app)
    logger.info("INIT: Handler initialized, starting app")
    try:
        # Set up the scheduler with direct birthday check functions
        setup_scheduler(app, timezone_aware_check, simple_daily_check)

        # Initialize special days caches if stale or missing
        initialize_special_days_cache()

        # Check for today's birthdays at startup and catch up on missed celebrations
        run_now()

        # Start the app
        handler.start()
    except Exception as e:
        logger.critical(f"CRITICAL: Error starting app: {e}")
