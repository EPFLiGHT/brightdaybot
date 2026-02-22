"""
BrightDayBot Configuration - Core Settings and Constants

Centralized configuration including environment variables, file paths, feature flags,
and application constants. Functions moved to separate utility modules.

Key modules: storage/settings.py, utils/log_setup.py
"""

import os
from datetime import time

from dotenv import load_dotenv

# Load environment variables first - this should be at the very top
# Project root is one level up from the config/ package directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load .env from the project root
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

# ----- FILE STRUCTURE CONFIGURATION -----

# Directory structure definitions
DATA_DIR = "data"
LOGS_DIR = os.path.join(DATA_DIR, "logs")
STORAGE_DIR = os.path.join(DATA_DIR, "storage")
TRACKING_DIR = os.path.join(DATA_DIR, "tracking")
TRACKED_THREADS_FILE = os.path.join(STORAGE_DIR, "tracked_threads.json")
ANNOUNCEMENTS_FILE = os.path.join(STORAGE_DIR, "announcements.json")
SCHEDULER_STATS_FILE = os.path.join(STORAGE_DIR, "scheduler_stats.json")
CALENDARIFIC_STATS_FILE = os.path.join(STORAGE_DIR, "calendarific_stats.json")
THREAD_TRACKING_TTL_DAYS = int(os.getenv("THREAD_TRACKING_TTL_DAYS", "60"))
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "10"))
CACHE_DIR = os.path.join(DATA_DIR, "cache")
CLEANUP_LOG_FILE = os.path.join(CACHE_DIR, "cleanup_log.json")
MESSAGES_CACHE_DIR = os.path.join(CACHE_DIR, "messages")

# ----- FEATURE FLAGS -----

# Enable or disable web search functionality
WEB_SEARCH_CACHE_ENABLED = os.getenv("WEB_SEARCH_CACHE_ENABLED", "true").lower() == "true"
# Use custom emojis in birthday messages
USE_CUSTOM_EMOJIS = os.getenv("USE_CUSTOM_EMOJIS", "true").lower() == "true"
# Enable AI image generation for birthday messages
AI_IMAGE_GENERATION_ENABLED = os.getenv("AI_IMAGE_GENERATION_ENABLED", "true").lower() == "true"
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
BIRTHDAYS_JSON_FILE = os.path.join(STORAGE_DIR, "birthdays.json")
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
CACHE_REFRESH_TIME = time(3, 0)  # Time to run cache refreshes (early morning)
# NOTE: This uses the server's local timezone, NOT UTC
# If you need UTC scheduling, modify services/scheduler.py

TIMEZONE_CELEBRATION_TIME = time(
    9, 0
)  # Time to celebrate birthdays in timezone-aware mode (USER'S local time)

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
# Structure: {user_id: (username, timestamp)}
username_cache = {}
USERNAME_CACHE_MAX_SIZE = 1000  # Maximum number of cached usernames
USERNAME_CACHE_TTL_HOURS = 24  # Cache entries expire after 24 hours

# ----- OPENAI MODEL CONFIGURATION -----

# Centralized list of supported OpenAI models
SUPPORTED_OPENAI_MODELS = [
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
]

# Default OpenAI models
DEFAULT_OPENAI_MODEL = "gpt-5.2"
DEFAULT_IMAGE_MODEL = "gpt-image-1.5"

# ----- OPENAI API PARAMETERS -----

# Token limits for different chat completion use cases
TOKEN_LIMITS = {
    "single_birthday": 1000,  # Default for regular birthday messages
    "consolidated_birthday": 2000,  # Multiple birthday messages
    "web_search_facts": 1200,  # Historical date summarization (+buffer for reasoning tokens)
    "image_title_generation": 200,  # AI-generated image titles
    "special_day_details": 800,  # Single special day details (+buffer for reasoning tokens, 1950 char Slack limit)
    "special_day_details_consolidated": 1200,  # Multiple special day details (+buffer for reasoning tokens)
    # Interactive features
    "mention_response": 300,  # Responses to @-mentions
    "special_day_thread_response": 400,  # Responses to special day thread replies
    "date_parsing": 100,  # NLP date extraction from natural language
    # Weekly digest
    "digest_descriptions": 400,  # One-line descriptions for weekly digest observances
    # Vision analysis
    "profile_analysis": 100,  # Vision API profile photo element extraction
}

# Temperature settings for creativity control
TEMPERATURE_SETTINGS = {
    "default": 0.7,  # Standard temperature for most messages
    "creative": 1.0,  # Higher creativity for consolidated messages and titles
    "factual": 0.3,  # Lower temperature for factual content (future use)
}

# Reasoning effort for GPT-5+ models (controls thinking tokens)
# Models have different supported levels:
#   GPT-5/5-mini:  minimal, low, medium, high (default: medium, always-on)
#   GPT-5.1:       none, low, medium, high (default: none, opt-in)
#   GPT-5.2:       none, low, medium, high, xhigh (default: none, opt-in)
REASONING_EFFORT = {
    "default": None,  # Don't send param — model uses its own default
    "analytical": "low",  # Light reasoning for factual content (web search, special days)
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

# Retry limits for various operations
RETRY_LIMITS = {
    "message_generation": 2,  # AI message generation retries
    "image_generation": 2,  # AI image generation retries
    "title_generation": 2,  # Image title generation retries
    "file_processing": 10,  # Slack file processing wait attempts
    "date_resolution": 5,  # Years to search for valid date (Feb 29 handling)
}

# Timeout values in seconds
TIMEOUTS = {
    "http_request": 30,  # HTTP request timeout
    "file_lock": 10,  # File lock acquisition timeout
    "confirmation_minutes": 5,  # Admin command confirmation timeout
}

# Scheduler timing constants
SCHEDULER_CHECK_INTERVAL_SECONDS = 60  # How often scheduler checks for birthdays
HEARTBEAT_STALE_THRESHOLD_SECONDS = 120  # When to consider scheduler unhealthy (2 min)

# Lookahead windows for upcoming events
UPCOMING_DAYS_DEFAULT = int(os.getenv("UPCOMING_DAYS_DEFAULT", "7"))
UPCOMING_DAYS_EXTENDED = int(os.getenv("UPCOMING_DAYS_EXTENDED", "30"))

# Cache retention policies (in days)
CACHE_RETENTION_DAYS = {
    "images_default": 30,  # Default image cache cleanup
    "images_generated": 365,  # AI-generated birthday images (keep longer)
    "profile_photos": 7,  # Temporary profile photos (clean more aggressively)
    "calendarific": 30,  # Calendarific holiday cache cleanup
}

# Emoji generation parameters for AI messages
EMOJI_GENERATION_PARAMS = {
    "sample_size": 50,  # Number of random emojis to show AI as examples
    "max_sample_size": 200,  # Maximum sample size (for future expansion)
    "fallback_emojis": ":tada: :sparkles: :star: :calendar: :books: :earth_americas: :hearts: :trophy: :raised_hands: :clap:",  # Fallback if retrieval fails
}

# ----- TEAM AND BOT IDENTITY -----

# Team and bot identity settings
TEAM_NAME = (
    'Laboratory for Intelligent Global Health and Humanitarian Response Technologies ("LiGHT Lab")'
)
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

# Special days announcement mode: "daily" or "weekly"
# - "daily": Individual announcements each day (current behavior)
# - "weekly": Single Monday digest showing all upcoming observances for the week
SPECIAL_DAYS_MODE = os.getenv("SPECIAL_DAYS_MODE", "daily")

# Day of week for weekly digest (0=Monday through 6=Sunday)
SPECIAL_DAYS_WEEKLY_DAY = int(os.getenv("SPECIAL_DAYS_WEEKLY_DAY", "0"))

# Weekday names for display and parsing
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Categories of special days to track
SPECIAL_DAYS_CATEGORIES = [
    "Global Health",
    "Tech",
    "Culture",
    "Company",
]

# Keywords for category classification (minimal set covering ~90% of cases)
HEALTH_CATEGORY_KEYWORDS = (
    "health",
    "disease",
    "cancer",
    "medical",
    "vaccine",
    "mental",
    "aids",
    "hiv",
    "tuberculosis",
    "diabetes",
)
TECH_CATEGORY_KEYWORDS = (
    "internet",
    "digital",
    "cyber",
    "technology",
    "computer",
    "telecom",
    "science",
    "space",
)

# File paths for special days data
SPECIAL_DAYS_JSON_FILE = os.path.join(STORAGE_DIR, "special_days.json")
SPECIAL_DAYS_CONFIG_FILE = os.path.join(STORAGE_DIR, "special_days_config.json")

# Enable AI image generation for special days
SPECIAL_DAYS_IMAGE_ENABLED = os.getenv("SPECIAL_DAYS_IMAGE_ENABLED", "false").lower() == "true"

# Enable @-here mention in special day announcements (default: True for backwards compat)
SPECIAL_DAY_MENTION_ENABLED = os.getenv("SPECIAL_DAY_MENTION_ENABLED", "true").lower() == "true"

# Enable channel topic update with today's special days (default: False)
SPECIAL_DAY_TOPIC_UPDATE_ENABLED = (
    os.getenv("SPECIAL_DAY_TOPIC_UPDATE_ENABLED", "false").lower() == "true"
)

# ----- CALENDARIFIC API CONFIGURATION -----

# Calendarific API for national/local holidays (NOT UN observances)
# Get free API key at: https://calendarific.com
# Free tier: 500 requests/month - we use weekly prefetch strategy (~52 calls/year)
# Note: UN/WHO/UNESCO observances come from integrations/observances/ (scraped from official sites)
CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY")
CALENDARIFIC_ENABLED = os.getenv("CALENDARIFIC_ENABLED", "false").lower() == "true"
CALENDARIFIC_COUNTRY = os.getenv("CALENDARIFIC_COUNTRY", "CH")  # Switzerland
CALENDARIFIC_STATE = os.getenv("CALENDARIFIC_STATE", "VD")  # Vaud canton
CALENDARIFIC_CACHE_DIR = os.path.join(CACHE_DIR, "calendarific")
CALENDARIFIC_CACHE_FILE = os.path.join(CALENDARIFIC_CACHE_DIR, "holidays_cache.json")
CALENDARIFIC_CACHE_TTL_DAYS = int(os.getenv("CALENDARIFIC_CACHE_TTL_DAYS", "7"))
CALENDARIFIC_PREFETCH_DAYS = int(os.getenv("CALENDARIFIC_PREFETCH_DAYS", "7"))
CALENDARIFIC_RATE_LIMIT_MONTHLY = 500  # Free tier: 500 calls/month
CALENDARIFIC_RATE_WARNING_THRESHOLD = 400  # Warn when approaching limit

# ----- UN OBSERVANCES CONFIGURATION -----

# UN International Days scraped from official UN website
# Uses crawl4ai for intelligent scraping (pip install crawl4ai && crawl4ai-setup)
UN_OBSERVANCES_ENABLED = os.getenv("UN_OBSERVANCES_ENABLED", "true").lower() == "true"
UN_OBSERVANCES_URL = "https://www.un.org/en/observances/list-days-weeks"
UN_OBSERVANCES_CACHE_TTL_DAYS = int(os.getenv("UN_OBSERVANCES_CACHE_TTL_DAYS", "7"))
UN_OBSERVANCES_CACHE_DIR = os.path.join(CACHE_DIR, "un_observances")
UN_OBSERVANCES_CACHE_FILE = os.path.join(UN_OBSERVANCES_CACHE_DIR, "un_days.json")

# ----- UNESCO OBSERVANCES CONFIGURATION -----

# UNESCO International Days scraped from official UNESCO website
UNESCO_OBSERVANCES_ENABLED = os.getenv("UNESCO_OBSERVANCES_ENABLED", "true").lower() == "true"
UNESCO_OBSERVANCES_URL = "https://www.unesco.org/en/days/list"
UNESCO_OBSERVANCES_CACHE_TTL_DAYS = int(os.getenv("UNESCO_OBSERVANCES_CACHE_TTL_DAYS", "30"))
UNESCO_OBSERVANCES_CACHE_DIR = os.path.join(CACHE_DIR, "unesco_observances")
UNESCO_OBSERVANCES_CACHE_FILE = os.path.join(UNESCO_OBSERVANCES_CACHE_DIR, "unesco_days.json")

# ----- WHO OBSERVANCES CONFIGURATION -----

# WHO Health Days scraped from official WHO website
WHO_OBSERVANCES_ENABLED = os.getenv("WHO_OBSERVANCES_ENABLED", "true").lower() == "true"
WHO_OBSERVANCES_URL = "https://www.who.int/campaigns"
WHO_OBSERVANCES_CACHE_TTL_DAYS = int(os.getenv("WHO_OBSERVANCES_CACHE_TTL_DAYS", "30"))
WHO_OBSERVANCES_CACHE_DIR = os.path.join(CACHE_DIR, "who_observances")
WHO_OBSERVANCES_CACHE_FILE = os.path.join(WHO_OBSERVANCES_CACHE_DIR, "who_days.json")

# ----- THREAD ENGAGEMENT CONFIGURATION -----

# Enable bot reactions to birthday thread replies
THREAD_ENGAGEMENT_ENABLED = os.getenv("THREAD_ENGAGEMENT_ENABLED", "true").lower() == "true"

# Thread reaction keyword mappings: (keywords, possible_reactions)
THREAD_REACTION_KEYWORDS = (
    (("congrat", "happy birthday", "feliz", "joyeux"), ("tada", "birthday", "partying_face")),
    (("love", "heart", "adore", "<3"), ("heart", "hearts", "sparkling_heart")),
    (("amazing", "awesome", "fantastic", "great", "wonderful"), ("star2", "dizzy", "sparkles")),
    (("thank", "thanks", "thx", "gracias", "merci"), ("pray", "raised_hands", "blush")),
    (("haha", "lol", "funny", "hilarious", ":joy:", ":laughing:"), ("joy", "smile")),
    (("cake", "cupcake", "dessert", "sweet"), ("cake", "cupcake")),
    (("party", "celebrate", "fiesta"), ("confetti_ball", "balloon", "champagne")),
    (("wish", "hope", "dream"), ("star", "rainbow", "sparkles")),
    (("best", "greatest", "legend"), ("trophy", "crown", "medal")),
    (("cheers", "toast", "drink"), ("clinking_glasses", "champagne", "beers")),
    (("gift", "present", "surprise"), ("gift", "ribbon", "gift_heart")),
)

# Default reactions when no keywords match
THREAD_DEFAULT_REACTIONS = ("tada", "sparkles", "heart", "raised_hands", "clap")

# ----- EPIC CELEBRATION CONFIGURATION -----

# Guaranteed reactions for epic celebrations (standard Slack emojis)
EPIC_GUARANTEED_REACTIONS = ("tada", "sparkles", "star2", "fire")

# Fallback reactions if custom emoji fetch fails
EPIC_FALLBACK_REACTIONS = ("rainbow", "trophy", "crown")

# Number of random emojis to fetch from workspace for epic celebrations
EPIC_RANDOM_EMOJI_FETCH_COUNT = 5

# Number of extra random reactions to add (on top of guaranteed)
EPIC_EXTRA_REACTIONS_COUNT = 3

# Epic thread celebration messages (randomly selected)
EPIC_THREAD_MESSAGES = (
    ":tada: :tada: :tada: LET THE CELEBRATIONS BEGIN! :tada: :tada: :tada:\n\nDrop your birthday wishes below! Let's make this thread LEGENDARY!",
    ":rotating_light: EPIC BIRTHDAY THREAD ACTIVATED :rotating_light:\n\n:point_down: Show some love in the replies! :point_down:",
    ":star2: :sparkles: THE CELEBRATION CONTINUES HERE :sparkles: :star2:\n\nWho's got birthday wishes? Don't be shy - PILE ON THE LOVE!",
    ":fire: :fire: :fire: THIS THREAD IS NOW A PARTY ZONE :fire: :fire: :fire:\n\nReact, reply, celebrate! Let's GOOO!",
    ":confetti_ball: :balloon: PARTY IN THE THREAD! :balloon: :confetti_ball:\n\nJoin the celebration - drop your wishes, GIFs, and good vibes below!",
)

# ----- SPECIAL DAY THREAD ENGAGEMENT -----

# Enable intelligent responses to special day thread replies
SPECIAL_DAY_THREAD_ENABLED = os.getenv("SPECIAL_DAY_THREAD_ENABLED", "true").lower() == "true"

# Maximum responses per user per special day thread (prevent spam)
SPECIAL_DAY_THREAD_MAX_RESPONSES_PER_USER = int(
    os.getenv("SPECIAL_DAY_THREAD_MAX_RESPONSES_PER_USER", "3")
)

# ----- @-MENTION Q&A CONFIGURATION -----

# Enable bot responses to @-mentions
MENTION_QA_ENABLED = os.getenv("MENTION_QA_ENABLED", "true").lower() == "true"

# Rate limiting for @-mentions (per user)
MENTION_RATE_LIMIT_WINDOW = int(os.getenv("MENTION_RATE_LIMIT_WINDOW", "60"))  # seconds
MENTION_RATE_LIMIT_MAX = int(os.getenv("MENTION_RATE_LIMIT_MAX", "5"))  # requests

# ----- NLP DATE PARSING CONFIGURATION -----

# Enable LLM-based date parsing for natural language birthday input
# Falls back to regex parsing first, uses LLM only when regex fails
NLP_DATE_PARSING_ENABLED = os.getenv("NLP_DATE_PARSING_ENABLED", "false").lower() == "true"

# ----- PROFILE ANALYSIS CONFIGURATION -----

# Enable Vision API analysis of profile photos to extract visual elements
# (bicycles, pets, logos, themes) for incorporation into birthday images
PROFILE_ANALYSIS_ENABLED = os.getenv("PROFILE_ANALYSIS_ENABLED", "true").lower() == "true"

# ----- DEFAULT VALUES -----

# Default personality for birthday messages (used as fallback throughout the codebase)
DEFAULT_PERSONALITY = "standard"

# Default personality for image generation (Ludo is the face of the bot)
DEFAULT_IMAGE_PERSONALITY = "mystic_dog"

# Default timezone for users without timezone set
DEFAULT_TIMEZONE = "UTC"

# Default announcement time format (string version for display/config)
DEFAULT_ANNOUNCEMENT_TIME = "09:00"

# Minimum valid birth year for birthday validation
MIN_BIRTH_YEAR = 1900

# App Home settings
APP_HOME_UPCOMING_BIRTHDAYS_LIMIT = 5  # Number of upcoming birthdays to show
APP_HOME_UPCOMING_SPECIAL_DAYS = 7  # Days to look ahead for special days

# Slash command settings
SLASH_UPCOMING_BIRTHDAYS_LIMIT = 10  # Number of upcoming birthdays for /birthday list

# Thread engagement settings
THREAD_MIN_TEXT_LENGTH = 15  # Minimum text length for thank you detection
THREAD_TTL_HOURS = 24  # Hours to track birthday/special day threads for engagement

# Slack API limits
SLACK_MAX_BLOCKS = 50  # Maximum blocks per message (Slack API limit)
SLACK_FILE_TITLE_MAX_LENGTH = 100  # Max chars for readable Slack file titles
SLACK_BUTTON_VALUE_CHAR_LIMIT = 1950  # Slack button value max chars (2000 limit with safety buffer)
SLACK_BUTTON_DISPLAY_CHAR_LIMIT = 1850  # Safe display limit for button content

# Announcement tracking
ANNOUNCEMENT_RETENTION_DAYS = 60  # Days to keep announcement history

# Text truncation limits
DESCRIPTION_TEASER_LENGTH = 150  # Characters for description teasers in special days
DIGEST_DESCRIPTION_LENGTH = 80  # Characters for one-line descriptions in weekly digest
LOG_PREVIEW_LENGTH = 200  # Characters for log preview snippets

# AI/LLM settings
MESSAGE_REGENERATION_THRESHOLD = 0.3  # Threshold for regenerating invalid messages
IMAGE_CLEANUP_PROBABILITY = 0.1  # Probability (10%) to run cleanup on each image generation
SLACK_FILE_TITLE_MIN_LENGTH = 3  # Minimum chars for Slack file titles

# Personality selection
MAX_RECENT_PERSONALITIES = 3  # Track this many recent personalities to avoid repetition

# Scheduler settings
SCHEDULER_STATS_SAVE_INTERVAL = 10  # Save stats every N scheduler loop executions

# Deduplication settings (for special days matching)
DEDUP_SIGNIFICANT_WORD_MIN_LENGTH = 4  # Minimum word length to consider significant
DEDUP_CONTAINMENT_THRESHOLD = 0.4  # Minimum ratio for containment matching (40%)
DEDUP_PREFIX_SUFFIX_MIN_LENGTH = 6  # Minimum length for prefix/suffix variation matching

# ----- PERSONALITY CONFIGURATION -----

# Import centralized personality configurations
from config.personality import PERSONALITIES

# For backward compatibility, reference the centralized configurations
BOT_PERSONALITIES = PERSONALITIES

# ----- INITIALIZATION -----

# Initialize logging system
from utils.log_setup import setup_logging

setup_logging(LOGS_DIR)

# Get the main logger
from utils.log_setup import get_logger

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
    CALENDARIFIC_CACHE_DIR,
]:
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f"CONFIG: Created directory {directory}")

# Log any configuration issues
if not BIRTHDAY_CHANNEL:
    logger.error("CONFIG_ERROR: BIRTHDAY_CHANNEL_ID not found in .env file")
