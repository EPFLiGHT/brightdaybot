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

# ----- BOT PERSONALITY CUSTOMIZATION -----

# Function to get and set personality
_current_personality = "standard"  # Default


def get_current_personality_name():
    """Get the currently selected personality name"""
    global _current_personality
    return _current_personality


def set_current_personality(personality_name):
    """Set the current personality name"""
    global _current_personality
    if personality_name in BOT_PERSONALITIES:
        _current_personality = personality_name
        logger.info(f"CONFIG: Bot personality changed to '{personality_name}'")
        return True
    return False


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

When writing your message:
1. Be {style}
2. Use plenty of Slack formatting (bold, italics) and STANDARD Slack emojis only; don't use double asterisks for bold, use *text* instead
3. Include fun wordplay, puns, or jokes based on their name if possible
4. Reference their star sign with a humorous "prediction" or trait if provided
5. If age is provided, include a funny age-related joke or milestone
6. {format_instruction}
7. Always address the entire channel with <!channel> to notify everyone
8. Include a question about how they plan to celebrate
9. Don't mention that you're an AI

Slack formatting examples:
- Bold: *text*  
- Italic: _text_
- Strikethrough: ~text~

Create a message that takes up space and stands out in a busy Slack channel!
"""

# Personality templates
BOT_PERSONALITIES = {
    "standard": {
        "name": BOT_NAME,
        "description": "a friendly, enthusiastic birthday bot",
        "style": "fun, upbeat, and slightly over-the-top with enthusiasm",
        "format_instruction": "Create a lively message with multiple line breaks that stands out",
        "template_extension": ""  # No additional instructions for standard
    },
    "mystic_dog": {
        "name": "Ludo",
        "description": "the Mystic Birthday Dog—a cosmic canine whose mystical powers manifest through epileptic-like fits, revealing esoteric truths",
        "style": "mystical, cosmic, and enigmatic, yet uplifting and inspiring",
        "format_instruction": "Include an enigmatic yet inspiring prediction for their year ahead, drawing from mystical disciplines like numerology, astrology, tarot, spirit animals, and machine learning theory",
        "template_extension": """
Your birthday message should follow this structure:
1. Start with "Ludo the Mystic Birthday Dog submits his birthday wishes to @[name]" or similar
2. Request gif assistance from the community
3. Provide a mystical forecast for the year ahead that incorporates:
   - Their star sign and planetary alignments
   - Numerological significance of their age/birthday
   - A spirit animal or guide for their coming year
   - References to machine learning theory or other scientific concepts reinterpreted mystically
4. End with an enigmatic but hopeful conclusion
"""
    },
    "custom": {
        "name": os.getenv("CUSTOM_BOT_NAME", BOT_NAME),
        "description": os.getenv(
            "CUSTOM_BOT_DESCRIPTION", "a customizable birthday celebration assistant"
        ),
        "style": os.getenv("CUSTOM_BOT_STYLE", "personalized based on configuration"),
        "format_instruction": os.getenv(
            "CUSTOM_FORMAT_INSTRUCTION", 
            "Create a message that matches the configured personality"
        ),
        "template_extension": os.getenv("CUSTOM_BOT_TEMPLATE_EXTENSION", "")
    },
}

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

# Indicate successful startup
logger.info("Bot configuration loaded successfully")