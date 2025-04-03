import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging with a more structured approach
log_formatter = logging.Formatter("%(asctime)s - [%(levelname)s] %(name)s: %(message)s")
file_handler = logging.FileHandler("app.log")
file_handler.setFormatter(log_formatter)

# Configure root logger
root_logger = logging.getLogger("birthday_bot")
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)


# Function to get child loggers without duplicate handlers
def get_logger(name):
    """
    Get a properly configured logger that inherits from the root logger
    without adding duplicate handlers.

    Args:
        name: Logger name suffix (e.g., 'date' becomes 'birthday_bot.date')

    Returns:
        Configured logger instance
    """
    if not name.startswith("birthday_bot."):
        name = f"birthday_bot.{name}"
    return logging.getLogger(name)


# Create the main logger for app.py
logger = get_logger("main")
logger.info("Bot starting up")

# Channel config
BIRTHDAY_CHANNEL = os.getenv("BIRTHDAY_CHANNEL_ID")
if not BIRTHDAY_CHANNEL:
    logger.error("CONFIG_ERROR: BIRTHDAY_CHANNEL_ID not found in .env file")

# Storage config
BIRTHDAYS_FILE = "birthdays.txt"

# Date format constants
DATE_FORMAT = "%d/%m"
DATE_WITH_YEAR_FORMAT = "%d/%m/%Y"
DEFAULT_REMINDER_MESSAGE = None  # Set to None to use the dynamic message generator

# Time to run daily birthday checks (8:00 AM UTC)
DAILY_CHECK_TIME = "08:00"

# List of User IDs with admin privileges for the bot (in addition to workspace admins)
ADMIN_USERS = [
    "U079Q4V8AJE",  # Example admin user
    # Add more UIDs here
]

# Permission settings - which commands require admin privileges
# Remind function is always admin-only so it's not included here
COMMAND_PERMISSIONS = {
    "list": True,  # True = admin only, False = available to all users
    "stats": True,  # True = admin only, False = available to all users
}

# Cache for username lookups to reduce API calls
username_cache = {}
