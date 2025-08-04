from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Import configuration
from config import logger, initialize_config

# Import services
from services.scheduler import setup_scheduler, run_now
from services.birthday import timezone_aware_check, simple_daily_check

# Import event handlers
from handlers.event_handler import register_event_handlers

# Initialize configuration from storage files
initialize_config()

# Initialize Slack app with error handling
app = App()
logger.info("INIT: App initialized")

# Register event handlers
register_event_handlers(app)

# Start the app
if __name__ == "__main__":
    handler = SocketModeHandler(app)
    logger.info("INIT: Handler initialized, starting app")
    try:
        # Set up the scheduler with direct birthday check functions
        setup_scheduler(app, timezone_aware_check, simple_daily_check)

        # Check for today's birthdays at startup and catch up on missed celebrations
        run_now()

        # Start the app
        handler.start()
    except Exception as e:
        logger.critical(f"CRITICAL: Error starting app: {e}")
