from openai import OpenAI
import os
import requests
import glob
import random
from datetime import datetime, timedelta
from config import get_logger, CACHE_DIR
import json
import base64

logger = get_logger("image_generator")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_birthday_image(
    user_profile,
    personality="mystic_dog",
    date_str=None,
    enable_transparency=False,
    save_to_file=True,
    birthday_message=None,
):
    """
    Generate a personalized birthday image using GPT-Image-1

    Args:
        user_profile: Dictionary with user profile information (from get_user_profile)
        personality: Bot personality for styling the image
        date_str: Date string in DD/MM format (optional, for caching)
        enable_transparency: Whether to enable transparent background (requires response_format="b64_json")
        save_to_file: Whether to automatically save the generated image to disk (default: True)
        birthday_message: Optional birthday announcement message to incorporate into the image

    Returns:
        Dictionary with image URL and metadata, or None if failed
    """
    try:
        # Extract user information for personalization
        name = user_profile.get("preferred_name", "Birthday Person")
        title = user_profile.get("title", "")

        # Create personality-specific prompts
        prompt = create_image_prompt(
            name, title, personality, user_profile, birthday_message
        )

        logger.info(
            f"IMAGE_GEN: Generating birthday image for {name} in {personality} style"
        )

        # Generate image using GPT-Image-1 (newest model)
        generation_params = {
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1024",
            "quality": "high",  # High quality for better generation
        }

        # Add transparency support if requested
        if enable_transparency:
            generation_params["response_format"] = "b64_json"
            generation_params["background"] = "transparent"

        response = client.images.generate(**generation_params)

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
            "image_url": image_url,  # None for base64 format
            "image_data": image_data,
            "image_base64": image_base64,  # Include base64 string
            "prompt_used": prompt,
            "personality": personality,
            "generated_for": name,
            "generated_at": datetime.now().isoformat(),
            "model": "gpt-image-1",
            "has_transparency": enable_transparency,
            "format": "png",  # PNG format for transparency support
        }

        # Automatically save image to file if requested and image data is available
        if save_to_file and image_data:
            try:
                # Occasionally clean up old images (10% chance on each generation)
                if random.random() < 0.1:  # 10% chance
                    cleanup_old_images(days_to_keep=30)

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
    name, title, personality, user_profile=None, birthday_message=None
):
    """
    Create personality-specific prompts for GPT-Image-1 generation with randomness for creativity

    Args:
        name: User's name
        title: User's job title for personalization
        personality: Bot personality
        user_profile: Full user profile data (includes photo URLs)
        birthday_message: Optional birthday announcement message to incorporate

    Returns:
        String prompt for DALL-E
    """
    # Include job title context if available
    title_context = f", who works as a {title}" if title else ""

    # Handle multiple birthday people in prompts
    if " and " in name or " , " in name:
        multiple_context = " This is a special shared birthday celebration with multiple people celebrating together."
    else:
        multiple_context = ""

    # Check if user has a profile picture with a face
    face_context = ""
    if user_profile:
        # Check if user has a high-res profile photo
        if user_profile.get("photo_512") or user_profile.get("photo_original"):
            face_context = f" IMPORTANT: Include a representation of {name}'s face in the image, making them the central focus of the celebration."
            logger.info(
                f"IMAGE_PROMPT: Including face context for {name} (has profile photo)"
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
    prompt_template = personality_config.get("image_prompt", "")

    if not prompt_template:
        # Fallback to standard if no template found
        standard_config = get_personality_config("standard")
        prompt_template = standard_config["image_prompt"]

    # Format the template with the context variables
    formatted_prompt = prompt_template.format(
        name=name,
        title_context=title_context,
        multiple_context=multiple_context,
        face_context=face_context,
        message_context=message_context,
    )

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
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"IMAGE_DOWNLOAD_ERROR: Failed to download image: {e}")
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
    Test function for image generation
    """
    # Mock user profile for testing with profile photo
    test_profile = {
        "preferred_name": "Alex",
        "title": "Software Engineer",
        "photo_512": "https://example.com/photo.jpg",  # Simulating profile photo
        "photo_original": "https://example.com/photo_original.jpg",
    }

    # Mock birthday message
    test_message = "🎉 Hey <@U123456>, happy birthday! The stars have aligned perfectly for your special day! 🌟"

    personalities = ["mystic_dog", "superhero", "pirate", "tech_guru"]

    print("=== Testing image generation with profile photos and birthday messages ===")

    for personality in personalities:
        print(f"\n--- Testing {personality} personality ---")
        result = generate_birthday_image(
            test_profile, personality, birthday_message=test_message
        )

        if result:
            print(f"✅ Generated image for {personality}")
            print(f"URL: {result['image_url']}")
            print(f"Prompt excerpt: {result['prompt_used'][:200]}...")

            # Check if face context was included
            if "face" in result["prompt_used"].lower():
                print("✓ Face context included in prompt")

            # Check if message context was included
            if "message" in result["prompt_used"].lower():
                print("✓ Message context included in prompt")

            # Check if image was automatically saved
            if result.get("saved_file_path"):
                print(f"Saved to: {result['saved_file_path']}")
            elif result.get("image_data"):
                print("Image data available but not saved to file")
        else:
            print(f"❌ Failed to generate image for {personality}")

    # Test without profile photo
    print("\n\n--- Testing without profile photo ---")
    test_profile_no_photo = {"preferred_name": "Bob", "title": "Designer"}
    result = generate_birthday_image(
        test_profile_no_photo, "standard", birthday_message=test_message
    )

    if result:
        if "face" not in result["prompt_used"].lower():
            print("✓ Face context correctly NOT included when no profile photo")
        else:
            print("❌ Face context incorrectly included without profile photo")


def cleanup_old_images(days_to_keep=30):
    """
    Clean up old generated birthday images to save disk space

    Args:
        days_to_keep: Number of days to keep images (default: 30)

    Returns:
        Number of files deleted
    """
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


if __name__ == "__main__":
    test_image_generation()
