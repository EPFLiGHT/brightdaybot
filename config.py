"""
BrightDayBot Configuration - Core Settings and Constants

Centralized configuration including environment variables, file paths, feature flags,
and application constants. Functions moved to separate utility modules.

Key modules: utils/app_config.py, utils/logging_config.py
"""

import os
from dotenv import load_dotenv
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
MESSAGES_CACHE_DIR = os.path.join(CACHE_DIR, "messages")

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

# ----- EMOJI CONSTANTS -----

# Common Slack emojis that work across all workspaces
SAFE_SLACK_EMOJIS = [
    ":tada:",
    ":birthday:",
    ":cake:",
    ":balloon:",
    ":gift:",
    ":confetti_ball:",
    ":sparkles:",
    ":star:",
    ":star2:",
    ":dizzy:",
    ":heart:",
    ":hearts:",
    ":champagne:",
    ":clap:",
    ":raised_hands:",
    ":thumbsup:",
    ":muscle:",
    ":crown:",
    ":trophy:",
    ":medal:",
    ":first_place_medal:",
    ":mega:",
    ":loudspeaker:",
    ":partying_face:",
    ":smile:",
    ":grinning:",
    ":joy:",
    ":sunglasses:",
    ":rainbow:",
    ":fire:",
    ":boom:",
    ":zap:",
    ":bulb:",
    ":art:",
    ":musical_note:",
    ":notes:",
    ":rocket:",
    ":100:",
    ":pizza:",
    ":hamburger:",
    ":sushi:",
    ":ice_cream:",
    ":beers:",
    ":cocktail:",
    ":wine_glass:",
    ":tumbler_glass:",
    ":drum_with_drumsticks:",
    ":guitar:",
    ":microphone:",
    ":headphones:",
    ":game_die:",
    ":dart:",
    ":bowling:",
    ":soccer:",
    ":basketball:",
    ":football:",
    ":baseball:",
    ":tennis:",
    ":8ball:",
    ":table_tennis_paddle_and_ball:",
    ":eyes:",
    ":wave:",
    ":point_up:",
    ":point_down:",
    ":point_left:",
    ":point_right:",
    ":ok_hand:",
    ":v:",
    ":handshake:",
    ":writing_hand:",
    ":pray:",
    ":clinking_glasses:",
]

# Dictionary to store fetched custom workspace emojis
CUSTOM_SLACK_EMOJIS = {}

# ----- FILE PATHS -----

# Core data files
BIRTHDAYS_FILE = os.path.join(STORAGE_DIR, "birthdays.txt")
ADMINS_FILE = os.path.join(STORAGE_DIR, "admins.json")
PERSONALITY_FILE = os.path.join(STORAGE_DIR, "personality.json")
PERMISSIONS_FILE = os.path.join(STORAGE_DIR, "permissions.json")

# Legacy log file for compatibility
LOG_FILE = os.path.join(LOGS_DIR, "app.log")

# ----- APPLICATION CONFIGURATION -----

# Channel configuration
BIRTHDAY_CHANNEL = os.getenv("BIRTHDAY_CHANNEL_ID")

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

# ----- OPENAI MODEL CONFIGURATION -----

# Centralized list of supported OpenAI models
SUPPORTED_OPENAI_MODELS = [
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-4-turbo",
]

# Default OpenAI model
DEFAULT_OPENAI_MODEL = "gpt-4.1"

# ----- OPENAI API PARAMETERS -----

# Token limits for different chat completion use cases
TOKEN_LIMITS = {
    "single_birthday": 1000,  # Default for regular birthday messages
    "consolidated_birthday": 2000,  # Multiple birthday messages
    "web_search_facts": 1000,  # Historical date summarization
    "image_title_generation": 200,  # AI-generated image titles
    "special_day_details": 600,  # Single special day details (10-14 lines, View Details button - 1950 char Slack limit)
    "special_day_details_consolidated": 1000,  # Multiple special day details (12-18 lines covering multiple observances)
}

# Temperature settings for creativity control
TEMPERATURE_SETTINGS = {
    "default": 0.7,  # Standard temperature for most messages
    "creative": 1.0,  # Higher creativity for consolidated messages and titles
    "factual": 0.3,  # Lower temperature for factual content (future use)
}

# Image generation parameters
IMAGE_GENERATION_PARAMS = {
    "quality": {
        "default": "high",  # Production default
        "test": "low",  # Test mode default
        "options": ["low", "medium", "high", "auto"],
    },
    "size": {
        "default": "1536x1024",  # Production default
        "options": ["auto", "1024x1024", "1536x1024", "1024x1536"],
    },
    "input_fidelity": {
        "default": "high",  # Always high for face preservation
        "options": ["low", "high"],
    },
}

# Emoji generation parameters for AI messages
EMOJI_GENERATION_PARAMS = {
    "sample_size": 50,  # Number of random emojis to show AI as examples
    "max_sample_size": 200,  # Maximum sample size (for future expansion)
    "fallback_emojis": ":tada: :sparkles: :star: :calendar: :books: :earth_americas: :hearts: :trophy: :raised_hands: :clap:",  # Fallback if retrieval fails
}

# ----- TEAM AND BOT IDENTITY -----

# Team and bot identity settings
TEAM_NAME = 'Laboratory for Intelligent Global Health and Humanitarian Response Technologies ("LiGHT Lab")'
BOT_NAME = "BrightDay"  # Default bot name

# ----- BOT BIRTHDAY CONFIGURATION -----

# BrightDayBot's own birthday configuration
BOT_BIRTHDAY = "05/03"  # DD/MM format
BOT_BIRTH_YEAR = 2025  # Year the bot was created
BOT_USER_ID = "BRIGHTDAYBOT"  # Special identifier for the bot itself

# ----- SPECIAL DAYS CONFIGURATION -----

# Enable or disable special days/holidays announcements
SPECIAL_DAYS_ENABLED = os.getenv("SPECIAL_DAYS_ENABLED", "true").lower() == "true"

# Default personality for special day announcements
SPECIAL_DAYS_PERSONALITY = os.getenv("SPECIAL_DAYS_PERSONALITY", "chronicler")

# Channel for special day announcements (defaults to birthday channel)
SPECIAL_DAYS_CHANNEL = os.getenv("SPECIAL_DAYS_CHANNEL_ID", BIRTHDAY_CHANNEL)

# Time to check for special days (default: 9:00 AM server time)
SPECIAL_DAYS_CHECK_TIME = time(9, 0)

# Categories of special days to track
SPECIAL_DAYS_CATEGORIES = [
    "Global Health",
    "Tech",
    "Culture",
    "Company",
]

# File paths for special days data
SPECIAL_DAYS_FILE = os.path.join(STORAGE_DIR, "special_days.csv")
SPECIAL_DAYS_CONFIG_FILE = os.path.join(STORAGE_DIR, "special_days_config.json")

# Enable AI image generation for special days
SPECIAL_DAYS_IMAGE_ENABLED = (
    os.getenv("SPECIAL_DAYS_IMAGE_ENABLED", "false").lower() == "true"
)

# ----- DEFAULT VALUES -----

# Default personality for birthday messages (used as fallback throughout the codebase)
DEFAULT_PERSONALITY = "standard"

# Default timezone for users without timezone set
DEFAULT_TIMEZONE = "UTC"

# Default announcement time format (string version for display/config)
DEFAULT_ANNOUNCEMENT_TIME = "09:00"

# ----- PERSONALITY CONFIGURATION -----

# Import centralized personality configurations
from personality_config import PERSONALITIES

# For backward compatibility, reference the centralized configurations
BOT_PERSONALITIES = PERSONALITIES

# ----- INITIALIZATION -----

# Initialize logging system
from utils.logging_config import setup_logging

setup_logging(LOGS_DIR)

# Get the main logger
from utils.logging_config import get_logger

logger = get_logger("main")

# Create directory structure
for directory in [
    DATA_DIR,
    LOGS_DIR,
    STORAGE_DIR,
    TRACKING_DIR,
    BACKUP_DIR,
    CACHE_DIR,
    MESSAGES_CACHE_DIR,
]:
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"CONFIG: Created directory {directory}")

# Log any configuration issues
if not BIRTHDAY_CHANNEL:
    logger.error("CONFIG_ERROR: BIRTHDAY_CHANNEL_ID not found in .env file")

# ----- BACKWARD COMPATIBILITY IMPORTS -----

# Re-export functions from new modules for backward compatibility
from utils.app_config import (
    get_current_personality_name,
    set_current_personality,
    get_current_openai_model,
    set_current_openai_model,
    is_valid_openai_model,
    get_supported_openai_models,
    set_custom_personality_setting,
    initialize_config,
)

from utils.app_config import (
    get_emoji_instructions,
    get_base_template,
    get_full_template_for_personality,
    BASE_TEMPLATE,
)
