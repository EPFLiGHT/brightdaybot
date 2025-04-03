import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Import configuration
from config import logger

# Import services
from services.scheduler import setup_scheduler, run_now
from services.birthday import daily

# Import event handlers
from handlers.event_handler import register_event_handlers

# Initialize Slack app with error handling
app = App()
logger.info("INIT: App initialized")

# Register event handlers
register_event_handlers(app)


# Daily function for scheduler
def run_daily(moment):
    """Wrapper to run daily tasks with the app instance"""
    return daily(app, moment)


# Start the app
if __name__ == "__main__":
    handler = SocketModeHandler(app)
    logger.info("INIT: Handler initialized, starting app")
    try:
        # Set up the scheduler before starting the app
        setup_scheduler(run_daily)

        # Check for today's birthdays at startup
        run_now()

        # Start the app
        handler.start()
    except Exception as e:
        logger.critical(f"CRITICAL: Error starting app: {e}")
