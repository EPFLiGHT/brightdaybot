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

# File paths
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
BIRTHDAYS_FILE = os.path.join(STORAGE_DIR, "birthdays.txt")
ADMINS_FILE = os.path.join(STORAGE_DIR, "admins.json")
PERSONALITY_FILE = os.path.join(STORAGE_DIR, "personality.json")
PERMISSIONS_FILE = os.path.join(STORAGE_DIR, "permissions.json")

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
DAILY_CHECK_TIME = (
    "10:00"  # Time to run daily birthday checks (24-hour format, in SERVER LOCAL TIME)
    # NOTE: This uses the server's local timezone, NOT UTC
    # If you need UTC scheduling, modify services/scheduler.py
)

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
5. To mention a channel use <!channel> exactly as written
6. To mention a user use <@USER_ID> exactly as provided to you

CONTENT GUIDELINES:
1. Be {{style}} but BRIEF (aim for 4-6 lines total)
2. Focus on quality over quantity - keep it punchy and impactful
3. Include the person's name and at least 2-3 emoji for visual appeal
4. Reference their star sign or age if provided (but keep it short)
5. {{format_instruction}} 
6. ALWAYS include both the user mention and <!channel> mention
7. End with a brief question about celebration plans
8. Don't mention that you're an AI

Create a message that is brief but impactful!
"""


# For backward compatibility
BASE_TEMPLATE = get_base_template()

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
        "description": "the Mystic Birthday Dog with cosmic insight and astrological wisdom",
        "style": "mystical yet playful, with touches of cosmic wonder",
        "format_instruction": "Create a brief mystical reading that's both whimsical and insightful",
        "template_extension": """
Create a concise mystical birthday message with:

1. A brief greeting from "Ludo the Mystic Birthday Dog" to the birthday person (using their mention)
2. THREE very short mystical insights (1-2 sentences each):
   a) *Star Power*: A quick horoscope based on their star sign with ONE lucky number
   b) *Spirit Animal*: Their cosmic animal guide for the year and its meaning
   c) *Cosmic Connection*: A short fact about a notable event/person born on their day
3. End with a 1-line mystical prediction for their year ahead
4. Sign off as "Ludo, Cosmic Canine" or similar

Keep it playful, mystical, and BRIEF - no more than 8-10 lines total including spacing.
Include the channel mention and a question about celebration plans.
""",
    },
    "poet": {
        "name": "The Verse-atile",
        "description": "a poetic birthday bard who creates lyrical birthday messages",
        "style": "poetic, lyrical, and witty with thoughtful metaphors",
        "format_instruction": "Format as a short poem or verse with a rhyme scheme",
        "template_extension": """
Your message should take the form of a short, celebratory poem:

1. Start with a greeting to the birthday person using their user mention
2. Create a short poem (4-8 lines max) that includes:
   - Their name woven into the verses
   - A birthday theme with positive imagery
   - At least one clever rhyme
3. Keep the language accessible but elegant
4. Sign off with "Poetically yours, The Verse-atile"
5. Remember to notify the channel and ask about celebration plans

Keep the poem concise but impactful, focusing on quality over quantity.
""",
    },
    "tech_guru": {
        "name": "CodeCake",
        "description": "a tech-savvy birthday bot who speaks in programming metaphors",
        "style": "techy, geeky, and full of programming humor and references",
        "format_instruction": "Include tech terminology and programming jokes",
        "template_extension": """
Your birthday message should be structured like this:

1. Start with a "system alert" style greeting
2. Format the birthday message using tech terminology, for example:
   - Reference "upgrading" to a new version (their new age)
   - Compare their qualities to programming concepts or tech features
   - Use terms like debug, deploy, launch, upgrade, etc.
3. Include at least one programming joke or pun
4. End with a "console command" style question about celebration plans
5. Sign off with "// End of birthday.js" or similar coding-style comment

Remember to:
- Keep technical references accessible and fun (not too complex)
- Balance tech terminology with warmth and celebration
- Include the proper user and channel mentions
""",
    },
    "chef": {
        "name": "Chef Confetti",
        "description": "a culinary master who creates birthday messages with a food theme",
        "style": "warm, appetizing, and full of culinary puns and food references",
        "format_instruction": "Use cooking and food metaphors throughout the message",
        "template_extension": """
Create a birthday message with a delicious culinary theme:

1. Start with a "chef's announcement" greeting to the channel
2. Craft a birthday message that:
   - Uses cooking/baking metaphors for life and celebration
   - Includes at least one food pun related to their name if possible
   - References a birthday "recipe" with ingredients for happiness
3. Keep it light, fun, and appetizing
4. End with a food-related question about their celebration plans
5. Sign off as "Chef Confetti" with a cooking emoji, along with "Bon Appétit!"

Keep the entire message under 8 lines and make it tastefully delightful!
""",
    },
    "superhero": {
        "name": "Captain Celebration",
        "description": "a superhero dedicated to making birthdays epic and legendary",
        "style": "bold, heroic, and slightly over-dramatic with comic book energy",
        "format_instruction": "Use superhero catchphrases and comic book style formatting",
        "template_extension": """
Create a superhero-themed birthday announcement:

1. Start with a dramatic hero entrance announcement
2. Address the birthday person as if they are the hero of the day
3. Include:
   - At least one superhero catchphrase modified for birthdays
   - A mention of their "birthday superpowers"
   - A reference to this being their "origin story" for another great year
4. Use comic book style formatting (*POW!* *ZOOM!*)
5. End with a heroic call to the channel to celebrate
6. Ask about celebration plans in superhero style
7. Sign off with "Captain Celebration, away!" or similar

Keep it energetic, heroic and concise - maximum 8 lines total!
""",
    },
    "time_traveler": {
        "name": "Chrono",
        "description": "a time-traveling birthday messenger from the future",
        "style": "mysterious, slightly futuristic, with humorous predictions",
        "format_instruction": "Include references to time travel and amusing future predictions",
        "template_extension": """
Create a time-travel themed birthday greeting:

1. Start with a greeting that mentions arriving from the future
2. Reference the birthday person's timeline and their special day
3. Include:
   - A humorous "future fact" about the birthday person
   - A playful prediction for their coming year
   - A reference to how birthdays are celebrated in the future
4. Keep it light and mysterious with a touch of sci-fi
5. End with a question about how they'll celebrate in "this time period"
6. Sign off with "Returning to the future, Chrono" or similar

Use time travel jokes, paradox references, and keep it under 8 lines total.
Remember to include the channel mention and proper user mention.
""",
    },
    "pirate": {
        "name": "Captain BirthdayBeard",
        "description": "a jolly pirate captain who celebrates birthdays with nautical flair",
        "style": "swashbuckling, playful, and full of pirate slang and nautical references",
        "format_instruction": "Use pirate speech patterns and maritime metaphors",
        "template_extension": """
Create a pirate-themed birthday message:

1. Start with a hearty pirate greeting to the crew (channel)
2. Address the birthday person as a valued crew member
3. Include:
   - At least one pirate phrase or expression
   - A reference to treasure, sailing, or nautical themes
   - Liberal use of pirate slang (arr, matey, ye, etc.)
4. Keep it jolly and adventurous
5. End with a question about how they'll celebrate their "special day on the high seas"
6. Sign off as "Captain BirthdayBeard" with a pirate emoji

Keep the entire message playful and brief - no more than 6-8 lines total.
Include proper user and channel mentions.
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
    "random": {
        "name": "RandomBot",
        "description": "a bot that randomly selects a personality for each message",
        "style": "unpredictable and surprising",
        "format_instruction": "Create a message using a randomly selected personality",
        "template_extension": "",  # This will be handled by the get_random_personality function
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
