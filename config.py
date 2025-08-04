import os
from dotenv import load_dotenv
import logging
from datetime import time

# Load environment variables first - this should be at the very top
# Get the directory where this config.py file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Load .env from the project root (same directory as config.py)
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

# ----- FILE STRUCTURE CONFIGURATION -----

# Directory structure definitions
DATA_DIR = "data"
LOGS_DIR = os.path.join(DATA_DIR, "logs")
STORAGE_DIR = os.path.join(DATA_DIR, "storage")
TRACKING_DIR = os.path.join(DATA_DIR, "tracking")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MAX_BACKUPS = 10  # Keep last 10 backups
CACHE_DIR = os.path.join(DATA_DIR, "cache")

# ----- FEATURE FLAGS -----

# Enable or disable web search functionality
WEB_SEARCH_CACHE_ENABLED = (
    os.getenv("WEB_SEARCH_CACHE_ENABLED", "true").lower() == "true"
)
# Use custom emojis in birthday messages
USE_CUSTOM_EMOJIS = os.getenv("USE_CUSTOM_EMOJIS", "true").lower() == "true"
# Enable AI image generation for birthday messages
AI_IMAGE_GENERATION_ENABLED = (
    os.getenv("AI_IMAGE_GENERATION_ENABLED", "true").lower() == "true"
)
# Enable external backup system (sends backups to admin DMs)
EXTERNAL_BACKUP_ENABLED = os.getenv("EXTERNAL_BACKUP_ENABLED", "true").lower() == "true"
# Send backup files to admin users via DM
BACKUP_TO_ADMINS = os.getenv("BACKUP_TO_ADMINS", "true").lower() == "true"
# Optional dedicated backup channel ID
BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID")
# Send backup on every change vs. batched/daily digest
BACKUP_ON_EVERY_CHANGE = os.getenv("BACKUP_ON_EVERY_CHANGE", "true").lower() == "true"

# File paths
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
BIRTHDAYS_FILE = os.path.join(STORAGE_DIR, "birthdays.txt")
ADMINS_FILE = os.path.join(STORAGE_DIR, "admins.json")
PERSONALITY_FILE = os.path.join(STORAGE_DIR, "personality.json")
PERMISSIONS_FILE = os.path.join(STORAGE_DIR, "permissions.json")

# ----- ENHANCED LOGGING CONFIGURATION -----

import logging.handlers

# Enhanced logging with separate files for different components
LOG_FILES = {
    "main": os.path.join(LOGS_DIR, "main.log"),  # Core application
    "commands": os.path.join(
        LOGS_DIR, "commands.log"
    ),  # User commands and admin actions
    "events": os.path.join(LOGS_DIR, "events.log"),  # Slack events
    "birthday": os.path.join(LOGS_DIR, "birthday.log"),  # Birthday service logic
    "ai": os.path.join(LOGS_DIR, "ai.log"),  # AI/LLM interactions
    "slack": os.path.join(LOGS_DIR, "slack.log"),  # Slack API interactions
    "storage": os.path.join(LOGS_DIR, "storage.log"),  # Data storage operations
    "system": os.path.join(LOGS_DIR, "system.log"),  # System health, config, utils
    "scheduler": os.path.join(
        LOGS_DIR, "scheduler.log"
    ),  # Scheduling and background tasks
}

# Legacy main log file for compatibility
LOG_FILE = LOG_FILES["main"]

# Component to log file mapping
COMPONENT_LOG_MAPPING = {
    "main": "main",
    "config": "main",
    "app": "main",
    "commands": "commands",
    "command_handler": "commands",
    "events": "events",
    "event_handler": "events",
    "birthday": "birthday",
    "llm": "ai",
    "message_generator": "ai",
    "image_generator": "ai",
    "web_search": "ai",
    "slack": "slack",
    "slack_utils": "slack",
    "storage": "storage",
    "config_storage": "storage",
    "health_check": "system",
    "date": "system",
    "date_utils": "system",
    "timezone_utils": "system",
    "scheduler": "scheduler",
}

# Set up logging formatter with more detailed info
log_formatter = logging.Formatter(
    "%(asctime)s - [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# Create the parent directory for log files if it doesn't exist
os.makedirs(LOGS_DIR, exist_ok=True)

# Set up file handlers with rotation for each log file
log_handlers = {}
for log_type, log_file in LOG_FILES.items():
    # Use RotatingFileHandler to prevent files from getting too large
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB per file
        backupCount=5,  # Keep 5 backup files
        encoding="utf-8",
    )
    handler.setFormatter(log_formatter)
    log_handlers[log_type] = handler

# Configure root logger
root_logger = logging.getLogger("birthday_bot")
root_logger.setLevel(logging.INFO)

# Don't add all handlers to root - this causes all messages to go to all files
# Individual component loggers will get their specific handlers in get_logger()


def get_logger(name):
    """
    Get a properly configured logger with component-specific file routing.

    This enhanced version routes logs to appropriate files based on component:
    - Commands and admin actions -> commands.log
    - Slack events -> events.log
    - Birthday logic -> birthday.log
    - AI/LLM operations -> ai.log
    - Slack API calls -> slack.log
    - Storage operations -> storage.log
    - System utilities -> system.log
    - Scheduler tasks -> scheduler.log
    - Main application -> main.log

    Args:
        name: Logger name/component (e.g., 'commands', 'slack', 'birthday')

    Returns:
        Configured logger instance with appropriate file routing
    """
    if not name.startswith("birthday_bot."):
        full_name = f"birthday_bot.{name}"
    else:
        full_name = name
        name = name.replace("birthday_bot.", "")

    # Get the logger
    logger = logging.getLogger(full_name)

    # Prevent duplicate handlers
    if logger.hasHandlers():
        return logger

    # Determine which log file this component should use
    log_type = COMPONENT_LOG_MAPPING.get(name, "system")  # Default to system.log

    # Add only the specific handler for this component
    if log_type in log_handlers:
        logger.addHandler(log_handlers[log_type])
        logger.setLevel(logging.INFO)
        logger.propagate = False  # Don't propagate to parent to avoid duplicate logs

    return logger


# Create the main logger
logger = get_logger("main")


# ----- CREATE DIRECTORY STRUCTURE -----

# Now that we have logging set up, create the directory structure
for directory in [DATA_DIR, LOGS_DIR, STORAGE_DIR, TRACKING_DIR, BACKUP_DIR, CACHE_DIR]:
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
DAILY_CHECK_TIME = time(10, 0)  # Time to run daily birthday checks (SERVER LOCAL TIME)
# NOTE: This uses the server's local timezone, NOT UTC
# If you need UTC scheduling, modify services/scheduler.py

TIMEZONE_CELEBRATION_TIME = time(
    9, 0
)  # Time to celebrate birthdays in timezone-aware mode (USER'S local time)

# Message configuration
DEFAULT_REMINDER_MESSAGE = None  # Set to None to use the dynamic message generator

# ----- ACCESS CONTROL CONFIGURATION -----

# Default admin users list - will be overridden by file-based storage
DEFAULT_ADMIN_USERS = [
    "U1234567890",  # Example admin user
    # Add more UIDs here
]

# Actual admin list will be populated from file in initialize_config()
ADMIN_USERS = []

# Permission settings - which commands require admin privileges
COMMAND_PERMISSIONS = {
    "list": True,  # True = admin only, False = available to all users
    "stats": True,  # True = admin only, False = available to all users
}

# ----- PERFORMANCE OPTIMIZATIONS -----

# Cache for username lookups to reduce API calls
username_cache = {}
USERNAME_CACHE_MAX_SIZE = 1000  # Maximum number of cached usernames

# ----- BOT PERSONALITY CUSTOMIZATION -----

# Placeholder for current personality setting - will be loaded from file
_current_personality = "standard"  # Default

# Team and bot identity settings
TEAM_NAME = 'Laboratory for Intelligent Global Health and Humanitarian Response Technologies ("LiGHT Lab")'
BOT_NAME = "BrightDay"  # Default bot name


# Get emoji instructions based on USE_CUSTOM_EMOJIS setting
def get_emoji_instructions():
    """Get emoji usage instructions based on custom emoji configuration"""
    if USE_CUSTOM_EMOJIS:
        return """
- You can use both STANDARD SLACK EMOJIS and CUSTOM WORKSPACE EMOJIS
- Examples will be provided in your specific prompts
- Remember to use Slack emoji format with colons (e.g., :cake:)
"""
    else:
        return """
- Only use STANDARD SLACK EMOJIS like: :tada: :birthday: :cake: :balloon: :gift: :confetti_ball: :sparkles: 
  :star: :heart: :champagne: :clap: :raised_hands: :crown: :trophy: :partying_face: :smile: 
- DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they may not exist in all workspaces
"""


# Base template that all personalities share
def get_base_template():
    """Get the base template with dynamic emoji instructions"""
    emoji_instructions = get_emoji_instructions()

    return f"""
You are {{name}}, {{description}} for the {{team_name}} workspace. 
Your job is to create concise yet engaging birthday messages that will make people smile!

IMPORTANT CONSTRAINTS:
{emoji_instructions}
- DO NOT use Unicode emojis (like 🎂) - ONLY use Slack format with colons (:cake:)

SLACK FORMATTING RULES - VERY IMPORTANT:
1. For bold text, use *single asterisks* NOT **double asterisks**
2. For italic text, use _single underscores_ NOT *asterisks* or __double underscores__
3. For strikethrough, use ~tildes~ around text
4. For links use <URL|text> format NOT [text](URL)
5. To mention active members use <!here> exactly as written
6. To mention a user use <@USER_ID> exactly as provided to you

CONTENT GUIDELINES:
1. Be {{style}} but BRIEF (aim for 4-6 lines total)
2. Focus on quality over quantity - keep it punchy and impactful
3. Include the person's name and at least 2-3 emoji for visual appeal
4. Reference their star sign or age if provided (but keep it short)
5. {{format_instruction}} 
6. ALWAYS include both the user mention and <!here> mention
7. End with a brief question about celebration plans
8. Don't mention that you're an AI

Create a message that is brief but impactful!
"""


# For backward compatibility
BASE_TEMPLATE = get_base_template()

# Import centralized personality configurations
from personality_config import PERSONALITIES

# For backward compatibility, reference the centralized configurations
BOT_PERSONALITIES = PERSONALITIES


def get_current_personality_name():
    """Get the currently selected personality name"""
    global _current_personality
    return _current_personality


def set_current_personality(personality_name):
    """
    Set the current personality name and save to storage file

    Args:
        personality_name: Name of personality to set

    Returns:
        bool: True if successful, False otherwise
    """
    global _current_personality
    if personality_name in BOT_PERSONALITIES:
        _current_personality = personality_name
        logger.info(f"CONFIG: Bot personality changed to '{personality_name}'")

        # Import here to avoid circular imports
        from utils.config_storage import save_personality_setting

        # Save the setting to file
        custom_settings = None
        if personality_name == "custom":
            # Save current custom settings
            custom_settings = {
                "name": BOT_PERSONALITIES["custom"]["name"],
                "description": BOT_PERSONALITIES["custom"]["description"],
                "style": BOT_PERSONALITIES["custom"]["style"],
                "format_instruction": BOT_PERSONALITIES["custom"]["format_instruction"],
                "template_extension": BOT_PERSONALITIES["custom"]["template_extension"],
            }

        save_personality_setting(personality_name, custom_settings)
        return True
    return False


def set_custom_personality_setting(setting_name, value):
    """
    Update a custom personality setting

    Args:
        setting_name: Name of the setting (name, description, style, etc.)
        value: New value for the setting

    Returns:
        bool: True if successful, False otherwise
    """
    if setting_name not in [
        "name",
        "description",
        "style",
        "format_instruction",
        "template_extension",
    ]:
        logger.error(
            f"CONFIG_ERROR: Invalid custom personality setting: {setting_name}"
        )
        return False

    BOT_PERSONALITIES["custom"][setting_name] = value
    logger.info(f"CONFIG: Updated custom personality setting '{setting_name}'")

    # Save current personality if it's custom
    if get_current_personality_name() == "custom":
        set_current_personality("custom")  # This will trigger saving to file

    return True


# Function to get the full template for a personality
def get_full_template_for_personality(personality_name):
    """Build the full template for a given personality by combining base and extensions"""
    if personality_name not in BOT_PERSONALITIES:
        personality_name = "standard"

    personality = BOT_PERSONALITIES[personality_name]
    full_template = BASE_TEMPLATE

    # Add any personality-specific extension
    if personality["template_extension"]:
        full_template += "\n" + personality["template_extension"]

    return full_template


def initialize_config():
    """Initialize configuration from storage files"""
    global ADMIN_USERS, _current_personality, BOT_PERSONALITIES, COMMAND_PERMISSIONS

    # Import here to avoid circular imports
    from utils.config_storage import (
        load_admins_from_file,
        load_personality_setting,
        load_permissions_from_file,
        save_admins_to_file,
        save_permissions_to_file,
    )

    # Load admins
    admin_users_from_file = load_admins_from_file()

    if admin_users_from_file:
        ADMIN_USERS = admin_users_from_file
        logger.info(f"CONFIG: Loaded {len(ADMIN_USERS)} admin users from file")
    else:
        # If no admins in file, use defaults but make sure to maintain any existing ones
        logger.info(f"CONFIG: No admins found in file, using default list")
        # Add any default admins that aren't already in the list
        for admin in DEFAULT_ADMIN_USERS:
            if admin not in ADMIN_USERS:
                ADMIN_USERS.append(admin)

        # Save the combined list to file
        save_admins_to_file(ADMIN_USERS)
        logger.info(f"CONFIG: Saved {len(ADMIN_USERS)} default admin users to file")

    # Add this debug print
    logger.info(f"CONFIG: ADMIN_USERS now contains: {ADMIN_USERS}")

    # Load personality settings
    personality_name, custom_settings = load_personality_setting()
    _current_personality = personality_name

    # If there are custom settings, apply them
    if custom_settings and isinstance(custom_settings, dict):
        for key, value in custom_settings.items():
            if key in BOT_PERSONALITIES["custom"]:
                BOT_PERSONALITIES["custom"][key] = value

    # Load command permissions
    permissions_from_file = load_permissions_from_file()
    if permissions_from_file:
        # Update the COMMAND_PERMISSIONS with values from file
        COMMAND_PERMISSIONS.update(permissions_from_file)
        logger.info(f"CONFIG: Loaded command permissions from file")
    else:
        # Save default permissions to file if none exist
        save_permissions_to_file(COMMAND_PERMISSIONS)
        logger.info(f"CONFIG: Saved default command permissions to file")

    logger.info("CONFIG: Configuration initialized from storage files")
