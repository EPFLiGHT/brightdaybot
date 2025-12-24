"""
AI-powered birthday image generation using OpenAI's image generation API.

Supports face-accurate images with user profile photos and text-only fallback.
Features quality control, automatic cleanup, and personality-themed styles.

Main functions: generate_birthday_image(), download_profile_photo(), cleanup_old_files().
Uses OpenAI API, PIL for processing, with automatic cache management.
"""

import os
import requests
import glob
import random
from datetime import datetime, timedelta
from config import (
    get_logger,
    CACHE_DIR,
    IMAGE_GENERATION_PARAMS,
    DEFAULT_IMAGE_MODEL,
    RETRY_LIMITS,
    TIMEOUTS,
    CACHE_RETENTION_DAYS,
)
from utils.openai_api import log_image_generation_usage, get_openai_client
import base64
from PIL import Image
import io

logger = get_logger("image_generator")

# Lazy-initialized OpenAI client (created on first use, not at import time)
_client = None


def _get_client():
    """Get OpenAI client, initializing lazily on first use."""
    global _client
    if _client is None:
        _client = get_openai_client()
    return _client


def generate_birthday_image(
    user_profile,
    personality="mystic_dog",
    date_str=None,
    enable_transparency=False,
    save_to_file=True,
    birthday_message=None,
    test_mode=False,
    quality=None,
    image_size=None,
    birth_year=None,
):
    """
    Generate a personalized birthday image using OpenAI's image generation API

    Args:
        user_profile: Dictionary with user profile information (from get_user_profile)
        personality: Bot personality for styling the image
        date_str: Date string in DD/MM format (optional, for caching and text overlay)
        enable_transparency: Whether to enable transparent background (requires response_format="b64_json")
        save_to_file: Whether to automatically save the generated image to disk (default: True)
        birthday_message: Optional birthday announcement message to incorporate into the image
        test_mode: If True, uses lower quality/smaller size to reduce costs for testing
        quality: Override quality setting ("low", "medium", "high", or "auto"). If None, uses test_mode logic
        image_size: Override image size ("auto", "1024x1024", "1536x1024", "1024x1536"). If None, defaults to "auto"
        birth_year: Optional birth year for age calculation and display in image

    Returns:
        Dictionary with image URL and metadata, or None if failed
    """
    try:
        # Extract user information for personalization
        name = user_profile.get("preferred_name", "Birthday Person")
        title = user_profile.get("title", "")

        # DEFENSIVE: Ensure name is always a string
        if not isinstance(name, str):
            logger.error(
                f"IMAGE_GEN_BUG: user_profile['preferred_name'] is not a string "
                f"(type={type(name)}): {name}. user_profile={user_profile}"
            )
            # Try to recover
            if isinstance(name, tuple):
                name = name[0] if name else "Birthday Person"
            else:
                name = str(name) if name else "Birthday Person"

        # Try to download and use profile photo as reference
        profile_photo_path = None
        use_reference_mode = False

        # Check if user has a profile photo for reference-based generation
        if user_profile and (
            user_profile.get("photo_512") or user_profile.get("photo_original")
        ):
            profile_photo_path = download_and_prepare_profile_photo(user_profile, name)
            if profile_photo_path:
                use_reference_mode = True
                logger.info(f"IMAGE_GEN: Using reference photo mode for {name}")
            else:
                logger.warning(
                    f"IMAGE_GEN: Failed to prepare reference photo for {name}, falling back to text-only"
                )

        # Create personality-specific prompts (adjusted for reference vs text-only mode)
        prompt = create_image_prompt(
            name,
            title,
            personality,
            user_profile,
            birthday_message,
            use_reference_mode,
            date_str=date_str,
            birth_year=birth_year,
        )

        # Determine quality and fidelity - allow override via quality parameter
        if quality is not None:
            # Use explicit quality override
            image_quality = quality
            cost_mode = f"explicit {quality} quality"
        else:
            # Use centralized quality settings with test_mode logic as fallback
            image_quality = (
                IMAGE_GENERATION_PARAMS["quality"]["test"]
                if test_mode
                else IMAGE_GENERATION_PARAMS["quality"]["default"]
            )
            cost_mode = "low-cost test" if test_mode else "full quality"

        # Use centralized input fidelity setting
        input_fidelity = IMAGE_GENERATION_PARAMS["input_fidelity"]["default"]

        # Determine image size - allow override via image_size parameter
        if image_size is not None:
            final_image_size = image_size
        else:
            final_image_size = IMAGE_GENERATION_PARAMS["size"]["default"]

        logger.info(
            f"IMAGE_GEN: Generating birthday image for {name} in {personality} style ({'reference-based' if use_reference_mode else 'text-only'}, {cost_mode})"
        )

        # Generate image using either reference-based editing or text-only generation
        if use_reference_mode and profile_photo_path:
            # Use OpenAI's image editing API with reference photo
            # Retry once if safety system rejects the request
            max_attempts = RETRY_LIMITS["image_generation"]
            for attempt in range(max_attempts):
                try:
                    with open(profile_photo_path, "rb") as image_file:
                        response = _get_client().images.edit(
                            model=DEFAULT_IMAGE_MODEL,
                            image=image_file,
                            prompt=prompt,
                            size=final_image_size,
                            input_fidelity=input_fidelity,
                            quality=image_quality,
                        )

                    # Log usage for monitoring
                    log_image_generation_usage(
                        response,
                        "IMAGE_EDIT_REFERENCE",
                        logger,
                        image_count=1,
                        quality=image_quality,
                        image_size=final_image_size,
                        model=DEFAULT_IMAGE_MODEL,
                    )

                    logger.info(
                        f"IMAGE_GEN: Successfully used reference photo for {name}"
                    )
                    break  # Success - exit retry loop

                except Exception as e:
                    error_str = str(e)
                    is_safety_rejection = (
                        "safety system" in error_str.lower()
                        or "moderation_blocked" in error_str.lower()
                    )

                    if is_safety_rejection and attempt < max_attempts - 1:
                        # Safety rejection on first attempt - retry with slightly modified prompt
                        logger.warning(
                            f"IMAGE_GEN_RETRY: Safety rejection for {name} (attempt {attempt + 1}/{max_attempts}). "
                            f"Retrying with modified prompt..."
                        )
                        # Simplify prompt slightly to reduce safety concerns
                        prompt = create_image_prompt(
                            name,
                            title,
                            personality,
                            user_profile,
                            birthday_message=None,
                            use_reference_mode=True,
                            date_str=date_str,
                            birth_year=birth_year,
                        )
                        continue  # Retry with modified prompt
                    else:
                        # Non-safety error, or final attempt failed
                        logger.error(
                            f"IMAGE_GEN_ERROR: Reference photo generation failed for {name} "
                            f"(attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        logger.info(
                            f"IMAGE_GEN: Falling back to text-only generation for {name}"
                        )
                        # Fall back to text-only generation
                        use_reference_mode = False
                        prompt = create_image_prompt(
                            name,
                            title,
                            personality,
                            user_profile,
                            birthday_message,
                            False,
                            date_str=date_str,
                            birth_year=birth_year,
                        )
                        break  # Exit retry loop

        if not use_reference_mode:
            # Standard text-only generation
            generation_params = {
                "model": DEFAULT_IMAGE_MODEL,
                "prompt": prompt,
                "size": final_image_size,
                "quality": image_quality,
            }

            # Add transparency support if requested (only for text-only mode)
            if enable_transparency:
                generation_params["response_format"] = "b64_json"
                generation_params["background"] = "transparent"

            response = _get_client().images.generate(**generation_params)

            # Log usage for monitoring
            log_image_generation_usage(
                response,
                "IMAGE_GENERATE_TEXT",
                logger,
                image_count=1,
                quality=image_quality,
                image_size=final_image_size,
                model=DEFAULT_IMAGE_MODEL,
            )

        # Handle both base64 and URL responses
        if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
            # Base64 format response
            image_base64 = response.data[0].b64_json
            image_data = base64.b64decode(image_base64)
            image_url = None
        else:
            # URL format response (fallback)
            image_url = response.data[0].url
            image_data = download_image(image_url)
            image_base64 = None

        result = {
            "success": True,  # Add success flag for command handler validation
            "image_url": image_url,  # None for base64 format
            "image_data": image_data,
            "image_base64": image_base64,  # Include base64 string
            "prompt_used": prompt,
            "personality": personality,
            "generated_for": name,
            "generated_at": datetime.now().isoformat(),
            "model": DEFAULT_IMAGE_MODEL,
            "has_transparency": enable_transparency,
            "format": "png",  # PNG format for transparency support
            "generation_mode": "reference_photo" if use_reference_mode else "text_only",
            "used_profile_photo": profile_photo_path is not None,
            "test_mode": test_mode,
            "image_size": final_image_size,
            "image_quality": image_quality,
            "input_fidelity": input_fidelity if use_reference_mode else None,
            "user_profile": user_profile,  # Include user profile for title generation
        }

        # Automatically save image to file if requested and image data is available
        if save_to_file and image_data:
            try:
                # Occasionally clean up old images and profile photos (10% chance on each generation)
                if random.random() < 0.1:  # 10% chance
                    cleanup_old_images(
                        days_to_keep=CACHE_RETENTION_DAYS["images_generated"]
                    )
                    cleanup_old_profile_photos(
                        days_to_keep=CACHE_RETENTION_DAYS["profile_photos"]
                    )

                # Create a filename based on the user name, personality, and timestamp
                safe_name = "".join(
                    c for c in name if c.isalnum() or c in (" ", "-", "_")
                ).rstrip()
                safe_name = safe_name.replace(" ", "_")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"birthday_{safe_name}_{personality}_{timestamp}.png"

                saved_path = save_image_to_file(image_data, filename)
                if saved_path:
                    result["saved_file_path"] = saved_path
                    logger.info(
                        f"IMAGE_SAVE: Auto-saved birthday image to {saved_path}"
                    )
                else:
                    logger.warning(
                        f"IMAGE_SAVE: Failed to auto-save birthday image for {name}"
                    )
            except Exception as e:
                logger.error(
                    f"IMAGE_SAVE_ERROR: Failed to auto-save birthday image: {e}"
                )

        logger.info(f"IMAGE_GEN: Successfully generated birthday image for {name}")
        return result

    except Exception as e:
        logger.error(f"IMAGE_GEN_ERROR: Failed to generate birthday image: {e}")
        return None


def create_image_prompt(
    name,
    title,
    personality,
    user_profile=None,
    birthday_message=None,
    use_reference_mode=False,
    date_str=None,
    birth_year=None,
):
    """
    Create personality-specific prompts for OpenAI image generation with randomness for creativity

    Args:
        name: User's name
        title: User's job title for personalization
        personality: Bot personality
        user_profile: Full user profile data (includes photo URLs)
        birthday_message: Optional birthday announcement message to incorporate
        use_reference_mode: Whether using reference photo (changes prompt style)
        date_str: Date string in DD/MM format for text overlay
        birth_year: Birth year for age calculation and display

    Returns:
        String prompt for OpenAI image API (either edit or generate mode)
    """
    # Include job title context if available
    title_context = f", who works as a {title}" if title else ""

    # Handle multiple birthday people in prompts
    if " and " in name or " , " in name:
        multiple_context = " This is a special shared birthday celebration with multiple people celebrating together."
    else:
        multiple_context = ""

    # Create date and age display text for image overlays
    date_display = ""
    age_display = ""
    date_age_text = ""

    if date_str:
        try:
            from utils.date_utils import format_date_european_short

            date_obj = datetime.strptime(date_str, "%d/%m")
            date_display = format_date_european_short(date_obj)  # e.g., "25 December"
        except (ValueError, ImportError):
            date_display = date_str

    if birth_year:
        try:
            current_year = datetime.now().year
            age = current_year - int(birth_year)
            age_display = str(age)
        except (ValueError, TypeError):
            age_display = ""

    # Build the combined date/age text instruction
    if date_display and age_display:
        date_age_text = f', with "{date_display}" as the date and "Turning {age_display}" displayed elegantly'
    elif date_display:
        date_age_text = f', with "{date_display}" displayed as the date'
    elif age_display:
        date_age_text = f', showing "Turning {age_display}"'

    # Calculate bot celebration status once (used in multiple places)
    is_bot_celebration = user_profile and user_profile.get("user_id") == "BRIGHTDAYBOT"

    # Adjust face context and no-people instructions based on generation mode
    face_context = ""
    no_people_instruction = ""

    if use_reference_mode:
        # For reference mode: we're editing an existing photo, so focus on transformation
        face_context = f" Transform this photo into a festive birthday celebration scene. If this image contains a human face, maintain and celebrate that person as the central focus. If this image contains no human faces (like a logo, pet, or landscape), create a celebration scene without adding any fake people or human figures."
        logger.info(f"IMAGE_PROMPT: Using reference mode prompt for {name}")
    elif user_profile and (
        user_profile.get("photo_512") or user_profile.get("photo_original")
    ):
        # For text-only mode with profile available: describe face characteristics
        face_context = f" IMPORTANT: Include a representation of {name}'s face in the image, making them the central focus of the celebration."
        logger.info(
            f"IMAGE_PROMPT: Including face context for {name} (has profile photo)"
        )
    else:
        if is_bot_celebration:
            # For bot self-celebration, don't apply no-people restriction since the bot_celebration_image_prompt
            # explicitly describes Ludo and personality dogs
            no_people_instruction = ""
            logger.info(
                f"IMAGE_PROMPT: Bot self-celebration detected for {name}, allowing personality dogs"
            )
        else:
            # For cases with no profile photo: explicitly prevent fake people
            no_people_instruction = " IMPORTANT: Focus only on birthday celebration elements (cake, decorations, balloons, presents, confetti) without including any human faces or people. Create a festive scene celebrating the birthday without any human figures."
            logger.info(
                f"IMAGE_PROMPT: Using no-people instruction for {name} (no profile photo)"
            )

    # Include birthday message context if provided
    message_context = ""
    if birthday_message:
        # Extract key themes from the birthday message
        message_context = f" Incorporate elements that reflect the birthday announcement message's themes and personality."
        logger.info(f"IMAGE_PROMPT: Including message context for {name}")

    # Get image prompt from centralized configuration
    from personality_config import get_personality_config

    personality_config = get_personality_config(personality)

    if use_reference_mode:
        # Use special reference mode prompt if available, otherwise adapt the standard prompt
        prompt_template = personality_config.get("reference_image_prompt")
        if not prompt_template:
            # Create a reference-adapted version of the standard prompt
            base_template = personality_config.get("image_prompt", "")
            if base_template:
                prompt_template = f"Transform this existing photo into {base_template.lower()}{face_context}{message_context}"
            else:
                # Ultimate fallback for reference mode
                prompt_template = f"Transform this photo into a festive birthday celebration for {name}{title_context}.{face_context}{message_context}"
    else:
        # Check if bot celebration should use special prompt
        if is_bot_celebration and personality == "mystic_dog":
            # Use the special bot celebration image prompt instead of regular mystic_dog prompt
            prompt_template = personality_config.get("bot_celebration_image_prompt", "")
            if prompt_template:
                logger.info(
                    f"IMAGE_PROMPT: Using special bot_celebration_image_prompt for {name}"
                )
            else:
                logger.warning(
                    f"IMAGE_PROMPT: bot_celebration_image_prompt not found, falling back to standard"
                )
                prompt_template = personality_config.get("image_prompt", "")
        else:
            # Standard text-only generation mode
            prompt_template = personality_config.get("image_prompt", "")

        if not prompt_template:
            # Fallback to standard if no template found
            standard_config = get_personality_config("standard")
            prompt_template = standard_config["image_prompt"]

    # Format the template with the context variables
    try:
        formatted_prompt = prompt_template.format(
            name=name,
            title_context=title_context,
            multiple_context=multiple_context,
            face_context=face_context,
            message_context=message_context,
            date_display=date_display,
            age_display=age_display,
            date_age_text=date_age_text,
        )
    except KeyError as e:
        logger.warning(f"IMAGE_PROMPT: Template formatting issue for {name}: {e}")
        # Simple fallback prompt for reference mode
        if use_reference_mode:
            formatted_prompt = f"Transform this photo into a festive birthday celebration for {name}{title_context}. {face_context}{message_context}"
        else:
            formatted_prompt = f"Create a joyful birthday celebration for {name}{title_context}. {face_context}{message_context}"

    # Append no-people instruction directly to the final prompt if needed
    if no_people_instruction:
        formatted_prompt += no_people_instruction

    return formatted_prompt


def download_image(image_url):
    """
    Download image from URL and return as bytes

    Args:
        image_url: URL of the image to download

    Returns:
        Image data as bytes, or None if failed
    """
    try:
        response = requests.get(image_url, timeout=TIMEOUTS["http_request"])
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"IMAGE_DOWNLOAD_ERROR: Failed to download image: {e}")
        return None


def download_and_prepare_profile_photo(user_profile, name):
    """
    Download user's profile photo and prepare it for OpenAI image API reference

    Args:
        user_profile: User profile dictionary with photo URLs
        name: User's name for file naming

    Returns:
        File path to prepared profile photo, or None if failed
    """
    try:
        # Get the highest resolution photo available
        photo_url = None
        if user_profile.get("photo_original"):
            photo_url = user_profile["photo_original"]
        elif user_profile.get("photo_512"):
            photo_url = user_profile["photo_512"]
        elif user_profile.get("photo_192"):
            photo_url = user_profile["photo_192"]

        if not photo_url:
            logger.info(f"PROFILE_PHOTO: No profile photo available for {name}")
            return None

        logger.info(
            f"PROFILE_PHOTO: Downloading profile photo for {name} from {photo_url}"
        )

        # Download the image
        image_data = download_image(photo_url)
        if not image_data:
            return None

        # Open and process the image
        image = Image.open(io.BytesIO(image_data))

        # Convert to RGB if necessary (remove alpha channel)
        if image.mode in ("RGBA", "LA"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "RGBA":
                background.paste(
                    image, mask=image.split()[-1]
                )  # Use alpha channel as mask
            else:
                background.paste(image)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize to standard size for OpenAI image API (1024x1024 max)
        max_size = 1024
        if image.width > max_size or image.height > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            logger.info(f"PROFILE_PHOTO: Resized profile photo to {image.size}")

        # Save the processed image
        safe_name = "".join(
            c for c in name if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        safe_name = safe_name.replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"profile_{safe_name}_{timestamp}.png"

        # Ensure profile photos directory exists
        profiles_dir = os.path.join(CACHE_DIR, "profiles")
        os.makedirs(profiles_dir, exist_ok=True)

        file_path = os.path.join(profiles_dir, filename)

        # Save as PNG for best quality
        image.save(file_path, "PNG", quality=95)

        logger.info(f"PROFILE_PHOTO: Saved processed profile photo to {file_path}")
        return file_path

    except Exception as e:
        logger.error(
            f"PROFILE_PHOTO_ERROR: Failed to download/prepare profile photo for {name}: {e}"
        )
        return None


def save_image_to_file(image_data, filename):
    """
    Save image data to a file

    Args:
        image_data: Image data as bytes
        filename: Filename to save as

    Returns:
        Full file path if successful, None if failed
    """
    try:
        # Ensure images directory exists
        images_dir = os.path.join(CACHE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)

        file_path = os.path.join(images_dir, filename)

        with open(file_path, "wb") as f:
            f.write(image_data)

        logger.info(f"IMAGE_SAVE: Saved image to {file_path}")
        return file_path

    except Exception as e:
        logger.error(f"IMAGE_SAVE_ERROR: Failed to save image: {e}")
        return None


def test_image_generation():
    """
    Test function for image generation with new reference photo capabilities
    """
    # Mock user profile for testing with profile photo
    test_profile_with_photo = {
        "preferred_name": "Alex",
        "title": "Software Engineer",
        "photo_512": "https://example.com/photo.jpg",  # Simulating profile photo
        "photo_original": "https://example.com/photo_original.jpg",
    }

    # Mock birthday message
    test_message = "🎉 Hey <@U123456>, happy birthday! The stars have aligned perfectly for your special day! 🌟"

    personalities = ["mystic_dog", "superhero", "pirate", "tech_guru"]

    print("=== Testing NEW Reference Photo Image Generation ===")
    print("🚀 This tests OpenAI's reference photo image generation capabilities!")

    for personality in personalities:
        print(f"\n--- Testing {personality} personality with REFERENCE PHOTO ---")
        result = generate_birthday_image(
            test_profile_with_photo, personality, birthday_message=test_message
        )

        if result:
            print(f"✅ Generated image for {personality}")
            if result.get("image_url"):
                print(f"URL: {result['image_url']}")
            else:
                print("Base64 image generated")
            print(f"Prompt excerpt: {result['prompt_used'][:200]}...")

            # Check for reference mode indicators
            if "transform" in result["prompt_used"].lower():
                print("✓ Reference mode prompt detected!")

            # Check if face context was included
            if (
                "face" in result["prompt_used"].lower()
                or "photo" in result["prompt_used"].lower()
            ):
                print("✓ Face/photo context included in prompt")

            # Check if image was automatically saved
            if result.get("saved_file_path"):
                print(f"💾 Saved to: {result['saved_file_path']}")
            elif result.get("image_data"):
                print("✓ Image data available but not saved to file")
        else:
            print(f"❌ Failed to generate image for {personality}")

    # Test without profile photo (fallback mode)
    print("\n\n--- Testing TEXT-ONLY mode (no profile photo) ---")
    test_profile_no_photo = {"preferred_name": "Bob", "title": "Designer"}
    result = generate_birthday_image(
        test_profile_no_photo, "standard", birthday_message=test_message
    )

    if result:
        if "transform" not in result["prompt_used"].lower():
            print("✓ Correctly using text-only generation mode")
        else:
            print("❌ Incorrectly using reference mode without photo")

        if "face" not in result["prompt_used"].lower():
            print("✓ Face context correctly NOT included when no profile photo")
        else:
            print("❌ Face context incorrectly included without profile photo")

    print("\n🎯 Test complete! The new system should now generate:")
    print("   📸 Reference-based images with HIGH input fidelity for face preservation")
    print("   ✍️  Text-only images as fallback")
    print("   💰 Cost optimization via quality settings (low=test, high=production)")
    print("   🧹 Automatic cleanup of temporary profile photos")


def cleanup_old_images(days_to_keep=None):
    """
    Clean up old generated birthday images to save disk space

    Args:
        days_to_keep: Number of days to keep images (default: from config)

    Returns:
        Number of files deleted
    """
    if days_to_keep is None:
        days_to_keep = CACHE_RETENTION_DAYS["images_default"]

    try:
        images_dir = os.path.join(CACHE_DIR, "images")
        if not os.path.exists(images_dir):
            return 0

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        # Find all PNG files in the images directory
        pattern = os.path.join(images_dir, "*.png")
        image_files = glob.glob(pattern)

        deleted_count = 0
        for file_path in image_files:
            try:
                # Get file modification time
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

                # Delete if older than cutoff
                if file_mtime < cutoff_date:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(
                        f"IMAGE_CLEANUP: Deleted old image {os.path.basename(file_path)}"
                    )

            except Exception as e:
                logger.error(f"IMAGE_CLEANUP_ERROR: Failed to delete {file_path}: {e}")

        if deleted_count > 0:
            logger.info(
                f"IMAGE_CLEANUP: Deleted {deleted_count} old birthday images (older than {days_to_keep} days)"
            )
        else:
            logger.debug(f"IMAGE_CLEANUP: No old images found to delete")

        return deleted_count

    except Exception as e:
        logger.error(f"IMAGE_CLEANUP_ERROR: Failed to cleanup old images: {e}")
        return 0


def cleanup_old_profile_photos(days_to_keep=None):
    """
    Clean up old downloaded profile photos to save disk space

    Args:
        days_to_keep: Number of days to keep profile photos (default: from config)

    Returns:
        Number of files deleted
    """
    if days_to_keep is None:
        days_to_keep = CACHE_RETENTION_DAYS["profile_photos"]

    try:
        profiles_dir = os.path.join(CACHE_DIR, "profiles")
        if not os.path.exists(profiles_dir):
            return 0

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        # Find all profile photo files
        pattern = os.path.join(profiles_dir, "profile_*.png")
        profile_files = glob.glob(pattern)

        deleted_count = 0
        for file_path in profile_files:
            try:
                # Get file modification time
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

                # Delete if older than cutoff
                if file_mtime < cutoff_date:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(
                        f"PROFILE_CLEANUP: Deleted old profile photo {os.path.basename(file_path)}"
                    )

            except Exception as e:
                logger.error(
                    f"PROFILE_CLEANUP_ERROR: Failed to delete {file_path}: {e}"
                )

        if deleted_count > 0:
            logger.info(
                f"PROFILE_CLEANUP: Deleted {deleted_count} old profile photos (older than {days_to_keep} days)"
            )
        else:
            logger.debug(f"PROFILE_CLEANUP: No old profile photos found to delete")

        return deleted_count

    except Exception as e:
        logger.error(
            f"PROFILE_CLEANUP_ERROR: Failed to cleanup old profile photos: {e}"
        )
        return 0


def create_profile_photo_birthday_image(
    user_profile, personality="standard", date_str=None, test_mode=False
):
    """
    Create a birthday image using the user's profile photo as fallback.

    This function is used when AI image generation is disabled or fails,
    providing a visual birthday image by using the user's Slack profile photo
    with a birthday-themed caption.

    Args:
        user_profile: Dictionary with user profile information
        personality: Bot personality (for context, not used in image)
        date_str: Date string in DD/MM format (optional, for logging)
        test_mode: Whether this is a test generation

    Returns:
        Dictionary with image data in same format as generate_birthday_image(),
        or None if profile photo unavailable
    """
    try:
        name = user_profile.get("preferred_name") or user_profile.get("name", "User")

        # Check if user has a profile photo
        photo_url = (
            user_profile.get("photo_original")
            or user_profile.get("photo_512")
            or user_profile.get("photo_192")
        )

        if not photo_url:
            logger.info(
                f"PROFILE_FALLBACK: No profile photo available for {name}, cannot create fallback image"
            )
            return None

        logger.info(
            f"PROFILE_FALLBACK: Creating birthday image from profile photo for {name}"
        )

        # Download and prepare the profile photo
        profile_photo_path = download_and_prepare_profile_photo(user_profile, name)

        if not profile_photo_path:
            logger.error(
                f"PROFILE_FALLBACK_ERROR: Failed to download profile photo for {name}"
            )
            return None

        # Read the image file
        with open(profile_photo_path, "rb") as f:
            image_data = f.read()

        # Convert to base64
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        # Create result in same format as AI-generated images
        result = {
            "success": True,
            "image_url": None,  # No URL for local file
            "image_data": image_data,
            "image_base64": image_base64,
            "prompt_used": "Profile photo fallback (no AI generation)",
            "personality": personality,
            "generated_for": name,
            "generated_at": datetime.now().isoformat(),
            "model": "profile_photo_fallback",
            "has_transparency": False,
            "format": "png",
            "generation_mode": "profile_photo_fallback",
            "used_profile_photo": True,
            "test_mode": test_mode,
            "image_size": "original",
            "image_quality": "original",
            "input_fidelity": None,
            "user_profile": user_profile,
        }

        # Save to birthday images cache for consistency
        try:
            safe_name = "".join(
                c for c in name if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            safe_name = safe_name.replace(" ", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"birthday_{safe_name}_profile_fallback_{timestamp}.png"

            saved_path = save_image_to_file(image_data, filename)
            result["file_path"] = saved_path
            logger.info(
                f"PROFILE_FALLBACK: Saved profile photo fallback to {saved_path}"
            )
        except Exception as save_error:
            logger.warning(
                f"PROFILE_FALLBACK: Could not save fallback image: {save_error}"
            )
            result["file_path"] = None

        logger.info(
            f"PROFILE_FALLBACK: Successfully created birthday image from profile photo for {name}"
        )
        return result

    except Exception as e:
        logger.error(
            f"PROFILE_FALLBACK_ERROR: Failed to create profile photo birthday image for {user_profile.get('name', 'User')}: {e}"
        )
        return None


if __name__ == "__main__":
    test_image_generation()
