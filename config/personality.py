"""
Personality helper functions for BrightDayBot.

Provides accessor and display functions for personality data.
Personality definitions are in personality_data.py.
"""

from config.personality_data import (  # noqa: F401
    LUDO_DESCRIPTION,
    LUDO_NEGATIVE_PROMPT,
    PERSONALITIES,
)

# =============================================================================
# Helper Functions for Personality Display (read from PERSONALITIES below)
# =============================================================================
# These functions dynamically generate display information from PERSONALITIES.
# Each personality in PERSONALITIES contains:
#   - name: Short name (e.g., "Ludo")
#   - vivid_name: Full display name if different from name (e.g., "Ludo, Mystic Birthday Dog")
#   - emoji: Emoji(s) for display (e.g., "✨🐕")
#   - celebration_desc: Short description for bot self-celebration (None for meta-personalities)
#   - image_desc: Visual description for image generation (None for meta-personalities)


def get_vivid_name(personality: str) -> str:
    """Get vivid display name with emoji (e.g., 'Ludo, Mystic Birthday Dog ✨🐕')."""
    config = PERSONALITIES.get(personality, {})
    name = config.get("vivid_name") or config.get("name", personality)
    emoji = config.get("emoji", "")
    return f"{name} {emoji}".strip()


def get_celebration_personality_count() -> int:
    """Get the count of personalities included in bot celebrations."""
    return sum(1 for p in PERSONALITIES.values() if p.get("celebration_desc"))


def get_celebration_personality_list() -> str:
    """
    Generate the formatted personality list for bot_self_celebration prompt.

    Returns:
        str: Formatted list like "- Ludo, Mystic Birthday Dog ✨🐕 (that's me! *tail wags*)"
    """
    lines = []
    for config in PERSONALITIES.values():
        celebration_desc = config.get("celebration_desc")
        if celebration_desc:  # Skip meta-personalities
            name = config.get("vivid_name") or config.get("name", "")
            emoji = config.get("emoji", "")
            vivid = f"{name} {emoji}".strip()
            lines.append(f"   - {vivid} ({celebration_desc})")
    return "\n".join(lines)


def get_celebration_image_descriptions() -> str:
    """
    Generate the formatted personality descriptions for bot_celebration_image_prompt.

    Returns:
        str: Comma-separated list of visual descriptions for image generation
    """
    descriptions = []
    for key, config in PERSONALITIES.items():
        image_desc = config.get("image_desc")
        # Skip mystic_dog (center) and meta-personalities
        if key != "mystic_dog" and image_desc:
            name = config.get("vivid_name") or config.get("name", key)
            descriptions.append(f"{image_desc} ({name})")

    # Join with proper grammar
    if len(descriptions) > 1:
        return ", ".join(descriptions[:-1]) + ", and " + descriptions[-1]
    return descriptions[0] if descriptions else ""


def get_personality_config(personality_name):
    """
    Get complete personality configuration by name.

    Args:
        personality_name: Name of the personality

    Returns:
        Dictionary with complete personality configuration
    """
    return PERSONALITIES.get(personality_name, PERSONALITIES["standard"])


def get_personality_descriptions():
    """Get dict of personality names to descriptions."""
    return {name: config["description"] for name, config in PERSONALITIES.items()}


def get_personality_display_name(personality: str, include_title: bool = True) -> str:
    """
    Get the display name for a personality.

    Args:
        personality: Personality key (e.g., "mystic_dog", "standard")
        include_title: If True, return full vivid name with emoji. If False, return short name only.

    Returns:
        Display name for the personality (e.g., "Ludo, Mystic Birthday Dog ✨🐕" or just "Ludo")
    """
    config = PERSONALITIES.get(personality, PERSONALITIES["standard"])

    if include_title:
        # Return vivid name (or name) with emoji
        name = config.get("vivid_name") or config.get("name", "BrightDay")
        emoji = config.get("emoji", "")
        return f"{name} {emoji}".strip()
    else:
        # Return short name only (e.g., "Ludo" not "Ludo, Mystic Birthday Dog")
        return config.get("name", "BrightDay")
