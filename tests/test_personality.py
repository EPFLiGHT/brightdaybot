"""
Tests for personality configuration functions in personality.py

Tests behavioral logic:
- get_personality_config(): Fallback behavior for invalid/None inputs
- get_personality_descriptions(): Completeness and non-empty invariants
- get_personality_display_name(): Fallback for invalid names, vivid name invariant
"""

from config.personality import (
    PERSONALITIES,
    get_personality_config,
    get_personality_descriptions,
    get_personality_display_name,
)


class TestGetPersonalityConfig:
    """Tests for get_personality_config() lookup function"""

    def test_valid_standard(self):
        """Standard personality returns valid config with required keys"""
        config = get_personality_config("standard")
        assert isinstance(config, dict)
        assert "name" in config
        assert "description" in config

    def test_invalid_falls_back_to_standard(self):
        """Invalid personality name falls back to standard"""
        config = get_personality_config("nonexistent_personality")
        standard = get_personality_config("standard")
        assert config == standard

    def test_none_falls_back_to_standard(self):
        """None as input falls back to standard"""
        config = get_personality_config(None)
        standard = get_personality_config("standard")
        assert config == standard


class TestGetPersonalityDescriptions:
    """Tests for get_personality_descriptions() function"""

    def test_contains_all_personalities(self):
        """Contains all defined personalities"""
        descriptions = get_personality_descriptions()
        for name in PERSONALITIES.keys():
            assert name in descriptions

    def test_descriptions_non_empty(self):
        """All descriptions are non-empty strings"""
        descriptions = get_personality_descriptions()
        for name, desc in descriptions.items():
            assert isinstance(desc, str)
            assert len(desc) > 0, f"Description for {name} is empty"


class TestGetPersonalityDisplayName:
    """Tests for get_personality_display_name() vivid names"""

    def test_invalid_personality_fallback(self):
        """Invalid personality falls back gracefully"""
        name = get_personality_display_name("nonexistent", include_title=True)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_all_personalities_have_vivid_names(self):
        """All known personalities return non-empty vivid names"""
        known_personalities = [
            "standard",
            "mystic_dog",
            "poet",
            "tech_guru",
            "chef",
            "superhero",
            "time_traveler",
            "pirate",
            "gardener",
            "philosopher",
            "random",
            "chronicler",
            "custom",
        ]
        for personality in known_personalities:
            name = get_personality_display_name(personality, include_title=True)
            assert len(name) > 0, f"No vivid name for {personality}"
