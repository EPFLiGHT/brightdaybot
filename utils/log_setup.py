"""
Multi-component logging configuration for BrightDayBot.

Sets up component-specific log files with automatic rotation to organize
logs by functionality: commands, events, AI operations, Slack API, etc.

Key functions: setup_logging(), get_logger() with 9 specialized log files.
"""

import os
import logging
import logging.handlers

# Enhanced logging with separate files for different components
# Use relative paths to avoid circular import, construct full paths when needed
LOG_FILE_NAMES = {
    "main": "main.log",  # Core application
    "commands": "commands.log",  # User commands and admin actions
    "events": "events.log",  # Slack events
    "birthday": "birthday.log",  # Birthday service logic
    "ai": "ai.log",  # AI/LLM interactions
    "slack": "slack.log",  # Slack API interactions
    "storage": "storage.log",  # Data storage operations
    "system": "system.log",  # System health, config, utils
    "scheduler": "scheduler.log",  # Scheduling and background tasks
}

# For backwards compatibility and health check usage
LOG_FILES = LOG_FILE_NAMES  # Will be updated with full paths when LOGS_DIR is available

# Component to log file mapping
COMPONENT_LOG_MAPPING = {
    # Core
    "main": "main",
    "config": "main",
    "app": "main",
    # Commands (commands/)
    "commands": "commands",
    "dispatcher": "commands",
    # Events (handlers/)
    "events": "events",
    "event_handler": "events",
    "mention_handler": "events",
    "thread_handler": "events",
    # Birthday (services/)
    "birthday": "birthday",
    "celebration": "birthday",
    # AI (services/, integrations/, image/)
    "ai": "ai",
    "message": "ai",
    "special_day": "ai",
    "image_generator": "ai",
    "web_search": "ai",
    "openai": "ai",
    # Slack (slack/)
    "slack": "slack",
    "slack_client": "slack",
    "blocks": "slack",
    # Storage (storage/)
    "storage": "storage",
    "birthdays": "storage",
    "special_days": "storage",
    "settings": "storage",
    # Integrations (integrations/)
    "calendarific": "special_days",
    "un_observances": "special_days",
    # System (utils/)
    "health": "system",
    "date": "system",
    "date_nlp": "system",
    # Scheduler (services/)
    "scheduler": "scheduler",
}

# Global variables for logging system
log_handlers = {}
_logging_initialized = False


def setup_logging(logs_dir):
    """
    Set up the enhanced logging system with component-specific file routing

    Args:
        logs_dir: Directory where log files should be stored
    """
    global log_handlers, _logging_initialized

    if _logging_initialized:
        return  # Already initialized

    # Create the parent directory for log files if it doesn't exist
    os.makedirs(logs_dir, exist_ok=True)

    # Set up logging formatter with more detailed info
    log_formatter = logging.Formatter(
        "%(asctime)s - [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set up file handlers with rotation for each log file
    for log_type, log_file in LOG_FILES.items():
        full_log_path = os.path.join(logs_dir, log_file)
        # Use RotatingFileHandler to prevent files from getting too large
        handler = logging.handlers.RotatingFileHandler(
            full_log_path,
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

    _logging_initialized = True


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
    if not _logging_initialized:
        raise RuntimeError("Logging system not initialized. Call setup_logging() first.")

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
