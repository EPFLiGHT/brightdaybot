"""
BrightDayBot Configuration Package

Re-exports all settings for backward compatibility.
Usage: from config import BIRTHDAY_CHANNEL, get_logger, ...

Modules:
    config.settings        - Core settings, constants, feature flags
    config.personality     - Personality helpers and definitions
    config.personality_data - Personality data constants
"""

from config.settings import *  # noqa: F401, F403
