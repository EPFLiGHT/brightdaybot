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
):
    """
    Generate a personalized birthday image using GPT-Image-1

    Args:
        user_profile: Dictionary with user profile information (from get_user_profile)
        personality: Bot personality for styling the image
        date_str: Date string in DD/MM format (optional, for caching)
        enable_transparency: Whether to enable transparent background (requires response_format="b64_json")
        save_to_file: Whether to automatically save the generated image to disk (default: True)

    Returns:
        Dictionary with image URL and metadata, or None if failed
    """
    try:
        # Extract user information for personalization
        name = user_profile.get("preferred_name", "Birthday Person")
        title = user_profile.get("title", "")

        # Create personality-specific prompts
        prompt = create_image_prompt(name, title, personality)

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


def create_image_prompt(name, title, personality):
    """
    Create personality-specific prompts for GPT-Image-1 generation with randomness for creativity

    Args:
        name: User's name
        title: User's job title for personalization
        personality: Bot personality

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

    base_prompts = {
        "mystic_dog": f"A mystical birthday celebration for {name}{title_context}{multiple_context}. Cosmic scene with a wise golden retriever wearing a wizard hat, surrounded by swirling galaxies, birthday cake with candles that look like stars, magical sparkles, and celestial birthday decorations. Add 2-3 creative, unexpected magical elements that would make this celebration truly special and unique. Ethereal lighting with deep purples, blues, and gold. Fantasy art style.",
        "time_traveler": f"A futuristic birthday party for {name}{title_context}{multiple_context}. Sci-fi celebration with holographic birthday cake, floating presents, time portals in the background, robotic party decorations, neon lighting, and futuristic cityscape. Add 2-3 creative, unexpected futuristic elements that would make this celebration truly special and unique. Cyberpunk aesthetic with bright blues, purples, and electric colors.",
        "superhero": f"A superhero-themed birthday celebration for {name}{title_context}{multiple_context}. Comic book style party with a caped birthday hero, dynamic action poses, 'HAPPY BIRTHDAY' in bold comic lettering, colorful balloons shaped like superhero symbols, explosive background with 'POW!' and 'BOOM!' effects. Add 2-3 creative, unexpected superhero elements that would make this celebration truly special and unique. Bright primary colors and comic book art style.",
        "pirate": f"A pirate birthday adventure for {name}{title_context}{multiple_context}. Treasure island celebration with a birthday treasure chest overflowing with gold and birthday presents, pirate ship in the background, palm trees with birthday decorations, compass pointing to 'BIRTHDAY', and tropical sunset. Add 2-3 creative, unexpected nautical elements that would make this celebration truly special and unique. Rich browns, golds, and ocean blues.",
        "poet": f"An elegant literary birthday celebration for {name}{title_context}{multiple_context}. Romantic scene with birthday cake surrounded by floating books, quill pens writing 'Happy Birthday' in calligraphy, vintage library setting, rose petals, candles, and soft lighting. Add 2-3 creative, unexpected literary elements that would make this celebration truly special and unique. Warm sepia tones with golden highlights.",
        "tech_guru": f"A high-tech birthday celebration for {name}{title_context}{multiple_context}. Digital party with holographic birthday cake made of code, binary numbers floating in air spelling 'HAPPY BIRTHDAY', computer screens showing birthday animations, circuit board decorations, and glowing tech elements. Add 2-3 creative, unexpected tech elements that would make this celebration truly special and unique. Electric blues, greens, and silver.",
        "chef": f"A culinary birthday feast for {name}{title_context}{multiple_context}. Gourmet kitchen scene with an elaborate multi-tier birthday cake, chef's hat decorations, colorful ingredients artistically arranged, cooking utensils as party decorations, and steam rising appetizingly. Add 2-3 creative, unexpected culinary elements that would make this celebration truly special and unique. Warm kitchen lighting with rich food colors.",
        "standard": f"A joyful birthday celebration for {name}{title_context}{multiple_context}. Cheerful party scene with a beautiful birthday cake with lit candles, colorful balloons, confetti falling, wrapped presents, and festive decorations. Add 2-3 creative, unexpected party elements that would make this celebration truly special and unique. Bright, happy colors with warm lighting and celebratory atmosphere.",
    }

    # Default to standard if personality not found
    return base_prompts.get(personality, base_prompts["standard"])


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
    # Mock user profile for testing
    test_profile = {"preferred_name": "Alex", "title": "Software Engineer"}

    personalities = ["mystic_dog", "superhero", "pirate", "tech_guru"]

    for personality in personalities:
        print(f"\n=== Testing {personality} personality ===")
        result = generate_birthday_image(test_profile, personality)

        if result:
            print(f"✅ Generated image for {personality}")
            print(f"URL: {result['image_url']}")
            print(f"Prompt: {result['prompt_used']}")

            # Check if image was automatically saved
            if result.get("saved_file_path"):
                print(f"Saved to: {result['saved_file_path']}")
            elif result.get("image_data"):
                print("Image data available but not saved to file")
        else:
            print(f"❌ Failed to generate image for {personality}")


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
