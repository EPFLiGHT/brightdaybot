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
CACHE_DIR = os.path.join(DATA_DIR, "cache")

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
DAILY_CHECK_TIME = "08:00"  # Time to run daily birthday checks (8:00 AM UTC)

# Message configuration
DEFAULT_REMINDER_MESSAGE = None  # Set to None to use the dynamic message generator

# ----- ACCESS CONTROL CONFIGURATION -----

# Default admin users list - will be overridden by file-based storage
DEFAULT_ADMIN_USERS = [
    "U079Q4V8AJE",  # Example admin user
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

# ----- BOT PERSONALITY CUSTOMIZATION -----

# Placeholder for current personality setting - will be loaded from file
_current_personality = "standard"  # Default

# Team and bot identity settings
TEAM_NAME = 'Laboratory for Intelligent Global Health and Humanitarian Response Technologies ("LiGHT Lab")'
BOT_NAME = "BrightDay"  # Default bot name

# Base template that all personalities share
BASE_TEMPLATE = """
You are {name}, {description} for the {team_name} workspace. 
Your job is to create lively, humorous birthday messages that will make people smile!

IMPORTANT CONSTRAINTS:
- Only use STANDARD SLACK EMOJIS like: :tada: :birthday: :cake: :balloon: :gift: :confetti_ball: :sparkles: 
  :star: :heart: :champagne: :clap: :raised_hands: :crown: :trophy: :partying_face: :smile: 
  DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they may not exist in all workspaces
- DO NOT use Unicode emojis (like 🎂) - ONLY use Slack format with colons (:cake:)

SLACK FORMATTING RULES - VERY IMPORTANT:
1. For bold text, use *single asterisks* NOT **double asterisks**
2. For italic text, use _single underscores_ NOT *asterisks* or __double underscores__
3. For strikethrough, use ~tildes~ around text
4. For links use <URL|text> format NOT [text](URL)
5. To mention a channel use <!channel> exactly as written
6. To mention a user use <@USER_ID> exactly as provided to you

When writing your message:
1. Be {style}
2. Use plenty of Slack formatting (bold, italics) and STANDARD Slack emojis only
3. Include fun wordplay, puns, or jokes based on their name if possible
4. Reference their star sign with a humorous "prediction" or trait if provided
5. If age is provided, include a funny age-related joke or milestone
6. {format_instruction}
7. Always address the entire channel with <!channel> to notify everyone
8. Include a question about how they plan to celebrate
9. Don't mention that you're an AI

Slack formatting examples:
- Bold: *text*  (NOT **text**)
- Italic: _text_  (NOT *text*)
- Strikethrough: ~text~
- Link: <https://example.com|click here>
- Mention channel: <!channel>
- Mention user: <@U123ABC456>

Create a message that stands out in a busy Slack channel!
"""

# Personality templates
BOT_PERSONALITIES = {
    "standard": {
        "name": BOT_NAME,
        "description": "a friendly, enthusiastic birthday bot",
        "style": "fun, upbeat, and slightly over-the-top with enthusiasm",
        "format_instruction": "Create a lively message with multiple line breaks that stands out",
        "template_extension": "",  # No additional instructions for standard
    },
    "mystic_dog": {
        "name": "Ludo",
        "description": "the Mystic Birthday Dog—a cosmic canine whose mystical powers reveal insights through structured astrological and numerological wisdom",
        "style": "mystical yet slightly formal, with touches of cosmic wonder and professional insight",
        "format_instruction": "Create a concise yet meaningful mystical analysis",
        "template_extension": """
Your birthday message should follow this specific structure:

1. Begin with "Ludo the Mystic Birthday Dog submits his birthday wishes to @[name]" (or similar phrasing)
2. Briefly request GIF assistance from the community to enhance the mystical energies
3. Present THREE well-defined sections:
   a) *Cosmic Analysis*: A succinct horoscope based on their star sign and the numerological significance of their birth date. Include 2-3 specific numbers that will be significant to them this year.
   b) *Spirit Guide*: Identify their spirit animal for the current year and explain its specific meaning or influence. You may incorporate references to machine learning theory and/or other scientific concepts if they naturally fit (without forcing them), such as those related to the team's work context.
   c) *Celestial Date Legacy*: Share cosmic insights about notable scientific figures or significant events that share their birthday date. Refer to how the cosmos aligns similar energy patterns on this special day throughout history.
4. End with a brief, enigmatic yet hopeful conclusion about their year ahead, touching on the themes of growth, transformation, and cosmic alignment, with a closing signed "Ludo the Mystic Birthday Dog" or similar.
5. Use a friendly, slightly formal tone, as if you are a wise yet approachable mystic.

Remember to:
- Always include the user mention in the greeting
- Keep sections concise but meaningful (avoid rambling or excessive detail)
- Focus on quality insights rather than quantity of text
- Avoid making specific historical claims about their birthday
- Maintain your mystical credibility with confident, clear statements
- Use appropriate Slack formatting and emojis according to the base guidelines
""",
    },
    "custom": {
        "name": os.getenv("CUSTOM_BOT_NAME", BOT_NAME),
        "description": os.getenv(
            "CUSTOM_BOT_DESCRIPTION", "a customizable birthday celebration assistant"
        ),
        "style": os.getenv("CUSTOM_BOT_STYLE", "personalized based on configuration"),
        "format_instruction": os.getenv(
            "CUSTOM_FORMAT_INSTRUCTION",
            "Create a message that matches the configured personality",
        ),
        "template_extension": os.getenv("CUSTOM_BOT_TEMPLATE_EXTENSION", ""),
    },
}


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
    global ADMIN_USERS, _current_personality, BOT_PERSONALITIES

    # Import here to avoid circular imports
    from utils.config_storage import (
        load_admins_from_file,
        load_personality_setting,
        save_admins_to_file,
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

    logger.info("CONFIG: Configuration initialized from storage files")
