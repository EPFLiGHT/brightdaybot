import os
from dotenv import load_dotenv
import logging

# Load environment variables first - this should be at the very top
load_dotenv()

# ----- FILE STRUCTURE CONFIGURATION -----

# Directory structure definitions
DATA_DIR = "data"
LOGS_DIR = os.path.join(DATA_DIR, "logs")
STORAGE_DIR = os.path.join(DATA_DIR, "storage")
TRACKING_DIR = os.path.join(DATA_DIR, "tracking")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MAX_BACKUPS = 10  # Keep last 10 backups

# File paths
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
BIRTHDAYS_FILE = os.path.join(STORAGE_DIR, "birthdays.txt")

# ----- LOGGING CONFIGURATION -----

# Set up logging formatter
log_formatter = logging.Formatter("%(asctime)s - [%(levelname)s] %(name)s: %(message)s")

# Create the parent directory for log file if it doesn't exist
os.makedirs(LOGS_DIR, exist_ok=True)

# Set up file handler
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(log_formatter)

# Configure root logger
root_logger = logging.getLogger("birthday_bot")
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)


# Function to get child loggers
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


# Create the main logger
logger = get_logger("main")


# ----- CREATE DIRECTORY STRUCTURE -----

# Now that we have logging set up, create the directory structure
for directory in [DATA_DIR, LOGS_DIR, STORAGE_DIR, TRACKING_DIR, BACKUP_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"CONFIG: Created directory {directory}")


# ----- APPLICATION CONFIGURATION -----

# Channel configuration
BIRTHDAY_CHANNEL = os.getenv("BIRTHDAY_CHANNEL_ID")
if not BIRTHDAY_CHANNEL:
    logger.error("CONFIG_ERROR: BIRTHDAY_CHANNEL_ID not found in .env file")

# Date format constants
DATE_FORMAT = "%d/%m"
DATE_WITH_YEAR_FORMAT = "%d/%m/%Y"

# Scheduling configuration
DAILY_CHECK_TIME = "08:00"  # Time to run daily birthday checks (8:00 AM UTC)

# Message configuration
DEFAULT_REMINDER_MESSAGE = None  # Set to None to use the dynamic message generator

# ----- ACCESS CONTROL CONFIGURATION -----

# Admin users list
ADMIN_USERS = [
    "U079Q4V8AJE",  # Example admin user
    # Add more UIDs here
]

# Permission settings - which commands require admin privileges
COMMAND_PERMISSIONS = {
    "list": True,  # True = admin only, False = available to all users
    "stats": True,  # True = admin only, False = available to all users
}

# ----- PERFORMANCE OPTIMIZATIONS -----

# Cache for username lookups to reduce API calls
username_cache = {}

# Indicate successful startup
logger.info("Bot configuration loaded successfully")
