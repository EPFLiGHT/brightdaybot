"""
BrightDayBot Configuration - Core Settings and Constants

Centralized configuration including environment variables, file paths, feature flags,
and application constants. Functions moved to separate utility modules.

Key modules: utils/app_config.py, utils/logging_config.py, utils/template_utils.py
Provides backward compatibility imports for refactored functions.
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

# ----- TEAM AND BOT IDENTITY -----

# Team and bot identity settings
TEAM_NAME = 'Laboratory for Intelligent Global Health and Humanitarian Response Technologies ("LiGHT Lab")'
BOT_NAME = "BrightDay"  # Default bot name

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
for directory in [DATA_DIR, LOGS_DIR, STORAGE_DIR, TRACKING_DIR, BACKUP_DIR, CACHE_DIR]:
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

from utils.template_utils import (
    get_emoji_instructions,
    get_base_template,
    get_full_template_for_personality,
    BASE_TEMPLATE,
)
