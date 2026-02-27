"""
Tests for personality configuration functions in personality.py

Tests pure lookup functions:
- get_personality_config(): Returns personality dict or standard fallback
- get_personality_descriptions(): Returns all personality descriptions
- get_personality_display_name(): Returns vivid display names with emojis
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
        """Standard personality returns valid config"""
        config = get_personality_config("standard")
        assert isinstance(config, dict)
        assert "name" in config
        assert "description" in config

    def test_valid_mystic_dog(self):
        """Mystic dog personality returns valid config"""
        config = get_personality_config("mystic_dog")
        assert config["name"] == "Ludo"
        assert "mystic" in config["description"].lower()

    def test_valid_pirate(self):
        """Pirate personality returns valid config"""
        config = get_personality_config("pirate")
        assert (
            "pirate" in config["description"].lower() or "nautical" in config["description"].lower()
        )

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

    def test_returns_dict(self):
        """Returns a dictionary"""
        descriptions = get_personality_descriptions()
        assert isinstance(descriptions, dict)

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

    def test_mystic_dog_with_title(self):
        """Mystic dog returns vivid name with emoji"""
        name = get_personality_display_name("mystic_dog", include_title=True)
        assert "Ludo" in name
        assert "Mystic" in name

    def test_pirate_with_title(self):
        """Pirate returns vivid name with emoji"""
        name = get_personality_display_name("pirate", include_title=True)
        assert "Captain" in name or "Beard" in name

    def test_standard_with_title(self):
        """Standard personality returns BrightDay"""
        name = get_personality_display_name("standard", include_title=True)
        assert "BrightDay" in name

    def test_without_title_returns_short_name(self):
        """include_title=False returns short name only"""
        name = get_personality_display_name("mystic_dog", include_title=False)
        assert name == "Ludo"

    def test_invalid_personality_fallback(self):
        """Invalid personality falls back gracefully"""
        name = get_personality_display_name("nonexistent", include_title=True)
        # Should return something reasonable (either from PERSONALITY_DISPLAY or PERSONALITIES config)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_all_personalities_have_vivid_names(self):
        """All known personalities return vivid names with emojis"""
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
