"""
Tests for capability-aware parameter gating in services.image_generator.

Focus: gpt-image-2 must NOT receive input_fidelity or background=transparent;
older gpt-image-1.x must continue to receive them as before.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_response():
    """Minimal images.generate / images.edit response shape used by the code."""
    resp = MagicMock()
    item = MagicMock()
    item.b64_json = None
    item.url = "https://example.invalid/image.png"
    resp.data = [item]
    resp.created = 0
    return resp


@pytest.fixture
def fake_user_profile():
    return {
        "user_id": "U_TEST",
        "preferred_name": "Tester",
        "name": "Tester",
        "title": "QA",
        # No photo URLs → forces text-only path (so we exercise images.generate).
    }


def _patch_common(monkeypatch, fake_response, image_model):
    """Wire shared mocks for both images.edit and images.generate."""
    fake_client = MagicMock()
    fake_client.images.generate.return_value = fake_response
    fake_client.images.edit.return_value = fake_response

    monkeypatch.setattr("services.image_generator._get_client", lambda: fake_client)
    monkeypatch.setattr(
        "services.image_generator.get_configured_openai_image_model",
        lambda: image_model,
    )
    monkeypatch.setattr(
        "services.image_generator.download_image",
        lambda url: b"\x89PNG\r\n\x1a\n",
    )
    return fake_client


def test_gpt_image_2_text_only_omits_input_fidelity_and_transparency(
    monkeypatch, fake_response, fake_user_profile
):
    from services import image_generator

    fake_client = _patch_common(monkeypatch, fake_response, "gpt-image-2")

    result = image_generator.generate_birthday_image(
        user_profile=fake_user_profile,
        personality="standard",
        save_to_file=False,
        enable_transparency=True,  # caller asks for transparent — must be ignored
    )

    assert result is not None
    fake_client.images.generate.assert_called_once()
    kwargs = fake_client.images.generate.call_args.kwargs

    assert kwargs["model"] == "gpt-image-2"
    assert "input_fidelity" not in kwargs, "gpt-image-2 must not receive input_fidelity"
    assert "background" not in kwargs, "gpt-image-2 must not receive background=transparent"
    assert "response_format" not in kwargs


def test_gpt_image_1_5_text_only_keeps_transparency_when_requested(
    monkeypatch, fake_response, fake_user_profile
):
    from services import image_generator

    fake_client = _patch_common(monkeypatch, fake_response, "gpt-image-1.5")

    image_generator.generate_birthday_image(
        user_profile=fake_user_profile,
        personality="standard",
        save_to_file=False,
        enable_transparency=True,
    )

    fake_client.images.generate.assert_called_once()
    kwargs = fake_client.images.generate.call_args.kwargs
    assert kwargs["model"] == "gpt-image-1.5"
    assert kwargs["background"] == "transparent"
    assert kwargs["response_format"] == "b64_json"


def test_gpt_image_2_edit_omits_input_fidelity(monkeypatch, fake_response, tmp_path):
    """When a profile photo is downloaded, the edit path is used. gpt-image-2
    must not receive input_fidelity even though IMAGE_GENERATION_PARAMS keeps
    a default."""
    from services import image_generator

    # Create a profile photo on disk so reference mode is selected.
    photo = tmp_path / "profile.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\n")

    fake_client = _patch_common(monkeypatch, fake_response, "gpt-image-2")
    monkeypatch.setattr(
        "services.image_generator.download_and_prepare_profile_photo",
        lambda profile, name: str(photo),
    )

    profile = {
        "user_id": "U_TEST",
        "preferred_name": "Tester",
        "name": "Tester",
        "title": "QA",
        "photo_512": "https://example.invalid/p.png",
        "is_custom_image": True,
    }

    image_generator.generate_birthday_image(
        user_profile=profile,
        personality="standard",
        save_to_file=False,
    )

    fake_client.images.edit.assert_called_once()
    kwargs = fake_client.images.edit.call_args.kwargs
    assert kwargs["model"] == "gpt-image-2"
    assert "input_fidelity" not in kwargs


def test_gpt_image_1_5_edit_keeps_input_fidelity(monkeypatch, fake_response, tmp_path):
    from services import image_generator

    photo = tmp_path / "profile.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\n")

    fake_client = _patch_common(monkeypatch, fake_response, "gpt-image-1.5")
    monkeypatch.setattr(
        "services.image_generator.download_and_prepare_profile_photo",
        lambda profile, name: str(photo),
    )

    profile = {
        "user_id": "U_TEST",
        "preferred_name": "Tester",
        "name": "Tester",
        "title": "QA",
        "photo_512": "https://example.invalid/p.png",
        "is_custom_image": True,
    }

    image_generator.generate_birthday_image(
        user_profile=profile,
        personality="standard",
        save_to_file=False,
    )

    fake_client.images.edit.assert_called_once()
    kwargs = fake_client.images.edit.call_args.kwargs
    assert kwargs["model"] == "gpt-image-1.5"
    assert kwargs["input_fidelity"] == "high"


def test_capabilities_lookup_unknown_model_safe_defaults():
    from config import get_image_model_capabilities

    caps = get_image_model_capabilities("gpt-image-99-future")
    assert caps["input_fidelity"] is False
    assert caps["transparent_bg"] is False


def test_admin_image_model_set_unknown_warns_but_persists(monkeypatch):
    """`admin image-model set <unknown>` warns the user yet still saves the value
    (intentional: lets us deploy ahead of our SUPPORTED_IMAGE_MODELS list)."""
    from commands.admin_commands import handle_image_model_command

    sent = []

    def fake_say(msg):
        sent.append(msg)

    set_calls = []

    def fake_set(model):
        set_calls.append(model)
        return True

    monkeypatch.setattr(
        "commands.admin_commands.get_current_openai_image_model",
        lambda: "gpt-image-2",
    )
    monkeypatch.setattr("commands.admin_commands.set_current_openai_image_model", fake_set)

    handle_image_model_command(
        ["set", "gpt-image-99-future"],
        user_id="U_ADMIN",
        say=fake_say,
        _app=None,
        username="admin",
    )

    # Both messages: warning + success
    joined = "\n".join(sent)
    assert "Unknown image model" in joined
    assert "✅" in joined and "gpt-image-99-future" in joined
    assert set_calls == ["gpt-image-99-future"]
