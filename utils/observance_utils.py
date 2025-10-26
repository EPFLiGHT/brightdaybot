"""
Observance Relationship Analysis Utilities

Determines whether multiple observances should be combined into a single announcement
or separated into individual announcements based on thematic relationships.
"""

import logging
from typing import List

from utils.logging_config import get_logger

# Get dedicated logger
logger = get_logger("special_days")


def should_split_observances(special_days: List) -> bool:
    """
    Determine if multiple observances should be split into separate announcements
    based on their thematic relationship.

    Strategy:
    - Always split if observances are from DIFFERENT categories (Culture vs Tech vs Global Health)
    - Combine only if observances share the SAME category (e.g., Culture + Culture)

    This ensures each observance gets proper attention and avoids forced connections
    between fundamentally different topics (e.g., LGBTQ+ rights + telecommunications).

    Args:
        special_days: List of SpecialDay objects for today

    Returns:
        bool: True if observances should be split, False if they should be combined
    """
    if not special_days or len(special_days) <= 1:
        return False  # Nothing to split

    # Extract categories
    categories = [day.category for day in special_days if hasattr(day, "category")]

    if not categories:
        logger.warning("No categories found for observances, defaulting to split")
        return True

    # Check if all categories are the same
    unique_categories = set(categories)

    if len(unique_categories) == 1:
        # All observances share the same category - can be combined
        logger.info(
            f"OBSERVANCE_ANALYSIS: {len(special_days)} observances share category '{categories[0]}' - will combine"
        )
        return False
    else:
        # Multiple different categories - should split
        logger.info(
            f"OBSERVANCE_ANALYSIS: {len(special_days)} observances have different categories {unique_categories} - will split"
        )
        return True


def group_observances_by_category(special_days: List) -> dict:
    """
    Group observances by their category for potential combined announcements.

    This is used when we want to send multiple combined announcements, one per category.
    For example: Culture observances together, Tech observances together.

    Args:
        special_days: List of SpecialDay objects

    Returns:
        dict: Dictionary mapping category names to lists of SpecialDay objects
              e.g., {"Culture": [day1, day2], "Tech": [day3]}
    """
    grouped = {}

    for day in special_days:
        category = getattr(day, "category", "Unknown")
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(day)

    logger.info(
        f"OBSERVANCE_GROUPING: Grouped {len(special_days)} observances into {len(grouped)} categories"
    )

    return grouped
