"""
Test command handlers for BrightDayBot.

This module contains all test-related command handlers.
These commands are used for testing various bot features including:
- Birthday celebrations and messages
- Block Kit rendering
- Image uploads and multiple attachments
- File uploads and external backups
- Bot self-celebration
- Channel join events
- Block Kit image embedding

All test commands require admin permissions and are designed for development,
testing, and verification purposes.
"""

from datetime import datetime

from config import (
    AI_IMAGE_GENERATION_ENABLED,
    BACKUP_DIR,
    BACKUP_ON_EVERY_CHANGE,
    BIRTHDAY_CHANNEL,
    BOT_BIRTH_YEAR,
    BOT_BIRTHDAY,
    EXTERNAL_BACKUP_ENABLED,
    IMAGE_GENERATION_PARAMS,
    OPS_CHANNEL_ID,
    get_logger,
)
from slack.client import (
    get_user_mention,
    get_user_profile,
    get_username,
)
from slack.messaging import send_message, send_message_with_image

logger = get_logger("commands")


def parse_test_command_args(args):
    """
    Parse test command arguments to extract quality, image_size, and text_only flag

    Args:
        args: List of command arguments

    Returns:
        tuple: (quality, image_size, text_only, error_message)
        If error_message is not None, parsing failed
    """
    quality = None
    image_size = None
    text_only = False

    # Filter out --text-only flag first
    filtered_args = []
    for arg in args:
        if arg.lower() == "--text-only":
            text_only = True
        else:
            filtered_args.append(arg)

    # Process remaining arguments for quality and size
    if len(filtered_args) > 0:
        quality_arg = filtered_args[0].lower()
        if quality_arg in ["low", "medium", "high", "auto"]:
            quality = quality_arg
        else:
            return (
                None,
                None,
                False,
                f"Invalid quality '{filtered_args[0]}'. Valid options: low, medium, high, auto",
            )

    if len(filtered_args) > 1:
        size_arg = filtered_args[1].lower()
        if size_arg in ["auto", "1024x1024", "1536x1024", "1024x1536"]:
            image_size = size_arg
        else:
            return (
                None,
                None,
                False,
                f"Invalid size '{filtered_args[1]}'. Valid options: auto, 1024x1024, 1536x1024, 1024x1536",
            )

    if len(filtered_args) > 2:
        return (
            None,
            None,
            False,
            "Too many arguments. Expected: [quality] [size] [--text-only]",
        )

    return quality, image_size, text_only, None


def handle_test_command(
    user_id,
    say,
    app,
    quality=None,
    image_size=None,
    target_user_id=None,
    text_only=None,
):
    """
    Generate test birthday message using production pipeline.

    Supports:
    - test: User tests their own birthday
    - admin test @user: Admin tests single user
    - admin test @user1 @user2: Admin tests multiple users (consolidated format)

    Args:
        user_id: The admin user who requested the test
        say: Slack say function
        app: Slack app instance
        quality: Optional quality setting for image generation
        image_size: Optional image size setting
        target_user_id: Single user ID or list of user IDs to test
        text_only: Skip image generation if True
    """
    from services.celebration import BirthdayCelebrationPipeline
    from storage.birthdays import load_birthdays
    from utils.date_utils import date_to_words

    # Handle single or multiple target users
    if target_user_id is None:
        # Regular user testing their own birthday
        target_user_ids = [user_id]
        is_admin_test = False
    elif isinstance(target_user_id, list):
        # Admin testing multiple users
        target_user_ids = target_user_id
        is_admin_test = True
    else:
        # Admin testing single user
        target_user_ids = [target_user_id]
        is_admin_test = True

    # Build birthday_people list for all target users
    birthdays = load_birthdays()
    birthday_people = []

    for tid in target_user_ids:
        username = get_username(app, tid)
        user_profile = get_user_profile(app, tid)

        # Get birthday date
        if tid in birthdays:
            user_date = birthdays[tid]["date"]
            birth_year = birthdays[tid]["year"]
            date_words = date_to_words(user_date, birth_year)
        else:
            # If no birthday saved, use today's date
            user_date = datetime.now().strftime("%d/%m")
            birth_year = None
            date_words = "today"

        birthday_people.append(
            {
                "user_id": tid,
                "username": username,
                "date": user_date,
                "year": birth_year,
                "date_words": date_words,
                "profile": user_profile,
            }
        )

    # Send explanation message
    if len(birthday_people) == 1:
        username = birthday_people[0]["username"]
        if is_admin_test:
            say(f"Here's what {username}'s birthday message would look like:")
        else:
            say("Here's what your birthday message would look like:")
    else:
        usernames = [p["username"] for p in birthday_people]
        names_str = (
            ", ".join(usernames[:-1]) + f" and {usernames[-1]}"
            if len(usernames) > 1
            else usernames[0]
        )
        say(f"Here's what a consolidated message for {names_str} would look like:")

    # Use production pipeline with DM as destination
    pipeline = BirthdayCelebrationPipeline(
        app=app,
        birthday_channel=user_id,  # Send to requestor's DM, not birthday channel
        mode="test",
    )

    # Determine image inclusion
    include_image = AI_IMAGE_GENERATION_ENABLED and not text_only

    # Log parameters
    if quality:
        logger.info(f"TEST: Using quality: {quality}")
    if image_size:
        logger.info(f"TEST: Using image size: {image_size}")
    if text_only:
        logger.info("TEST: Using text-only mode (skipping image generation)")

    # Call production pipeline - handles single OR multiple automatically!
    result = pipeline.celebrate(
        birthday_people=birthday_people,  # 1 user = single, N users = consolidated
        include_image=include_image,
        test_mode=True,
        quality=quality,
        image_size=image_size,
    )

    # Log result
    if result["success"]:
        logger.info(
            f"TEST: Sent birthday test - "
            f"people: {len(birthday_people)}, "
            f"images: {result['images_sent']}, "
            f"personality: {result.get('personality', 'unknown')}"
        )
    else:
        logger.error(f"TEST: Failed - {result.get('error', 'unknown')}")
        say("❌ Test failed. Check logs for details.")


def handle_test_block_command(user_id, args, say, app):
    """
    Test Block Kit rendering without AI content generation.

    Supports testing birthday, multi-birthday, special day, and bot celebration
    block layouts with sample data.

    Args:
        user_id: Slack user ID requesting the test
        args: Block type and optional user mentions [birthday|multi|special|bot, @users...]
        say: Slack say function for sending messages
        app: Slack app instance for API calls
    """
    from slack.blocks import (
        build_birthday_blocks,
        build_bot_celebration_blocks,
        build_special_day_blocks,
    )
    from storage.settings import get_current_personality_name

    username = get_username(app, user_id)

    if not args:
        say(
            "📦 *Block Kit Testing Commands*\n\n"
            "Usage:\n"
            "• `admin test-block birthday [@user]` - Test single birthday block\n"
            "• `admin test-block multi @user1 @user2 [...]` - Test multiple birthdays block\n"
            "• `admin test-block special` - Test special day block with buttons\n"
            "• `admin test-block bot` - Test bot celebration block\n\n"
            "These commands test Block Kit rendering without generating AI content."
        )
        return

    block_type = args[0].lower()

    try:
        personality = get_current_personality_name()

        if block_type == "birthday":
            # Test single birthday block
            target_user_id = None
            if len(args) > 1 and args[1].startswith("<@"):
                # Extract user ID from mention - uppercase to normalize
                target_user_id = args[1].strip("<@>").split("|")[0].upper()
            else:
                target_user_id = user_id

            target_username = get_username(app, target_user_id)

            # Build test birthday block (unified function with list format)
            test_message = f"🎉 Happy birthday {target_username}! This is a test Block Kit message to demonstrate the visual layout without AI generation. The actual message would be personalized and creative!"

            blocks, fallback_text = build_birthday_blocks(
                [
                    {
                        "username": target_username,
                        "user_id": target_user_id,
                        "age": 28,  # Dummy age
                        "star_sign": "♒ Aquarius",
                    }
                ],
                test_message,
                historical_fact="On this day in 1955, Steve Jobs was born, co-founder of Apple Inc.",
                personality=personality,
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Birthday Block Test Sent!*\n"
                f"• User: {target_username}\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Personality: {personality}\n"
                f"Check the message above to see the Block Kit layout!"
            )
            logger.info(f"TEST_BLOCK: {username} tested birthday block for {target_username}")

        elif block_type == "multi":
            # Test multiple birthdays block
            user_mentions = [arg for arg in args[1:] if arg.startswith("<@")]

            if len(user_mentions) < 2:
                say(
                    "❌ Please mention at least 2 users for multiple birthday testing.\nExample: `admin test-block multi @alice @bob`"
                )
                return

            # Extract user IDs and build birthday people data
            birthday_people = []
            for mention in user_mentions[:5]:  # Limit to 5 for testing
                test_user_id = mention.strip("<@>").split("|")[0].upper()
                test_username = get_username(app, test_user_id)
                birthday_people.append(
                    {
                        "username": test_username,
                        "user_id": test_user_id,
                        "age": 25 + len(birthday_people),  # Dummy ages
                        "star_sign": "♒ Aquarius",
                    }
                )

            # Build test consolidated block (unified function handles multiple)
            mentions = ", ".join([f"<@{p['user_id']}>" for p in birthday_people])
            test_message = f"🎉 Let's celebrate {mentions}! This is a test Block Kit message showing how multiple birthdays appear with proper structure and dividers."

            blocks, fallback_text = build_birthday_blocks(
                birthday_people,
                test_message,
                historical_fact="On this day in history, multiple amazing people were born, proving that great minds think alike!",
                personality=personality,
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Multiple Birthday Block Test Sent!*\n"
                f"• Users: {len(birthday_people)}\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Personality: {personality}\n"
                f"Check the message above to see the consolidated layout!"
            )
            logger.info(
                f"TEST_BLOCK: {username} tested multi-birthday block with {len(birthday_people)} users"
            )

        elif block_type == "special":
            # Test special day block with interactive buttons (unified function with list format)
            test_message = "🌍 Today we celebrate World Block Kit Day! This special observance demonstrates the power of structured, interactive messaging in modern workplace communication."

            blocks, fallback_text = build_special_day_blocks(
                [
                    {
                        "name": "World Block Kit Day",
                        "date": "21/01",
                        "source": "Slack Technologies",
                        "category": "Technology",
                        "url": "https://api.slack.com/block-kit",
                        "emoji": "🌍",
                    }
                ],
                test_message,
                personality="chronicler",
                detailed_content="World Block Kit Day celebrates the revolutionary UI framework that enables developers to create rich, interactive messages in Slack. Introduced in 2019, Block Kit transformed how apps communicate, making messages more visual, structured, and engaging. This test demonstrates interactive buttons, structured layouts, and proper information hierarchy.",
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Special Day Block Test Sent!*\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Interactive buttons: ✅ (Click '📖 View Details' to test ephemeral message!)\n"
                f"• Official URL button: ✅\n"
                f"Check the message above and test the interactive elements!"
            )
            logger.info(f"TEST_BLOCK: {username} tested special day block with buttons")

        elif block_type == "bot":
            # Test bot celebration block
            current_year = datetime.now().year
            bot_age = current_year - BOT_BIRTH_YEAR

            from config.personality import get_celebration_personality_count

            personality_count = get_celebration_personality_count()
            test_message = f"🌟 COSMIC BIRTHDAY ALIGNMENT DETECTED! 🌟\n\nGreetings, mortals! Today marks the digital manifestation of Ludo | LiGHT BrightDay Coordinator. This is a test of the mystical celebration blocks that Ludo uses to announce the bot's birthday. All {personality_count} Sacred Forms unite in cosmic harmony!"

            blocks, fallback_text = build_bot_celebration_blocks(
                message=test_message, bot_age=bot_age, personality="mystic_dog"
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Bot Celebration Block Test Sent!*\n"
                f"• Bot Age: {bot_age} years\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Personality: Ludo the Mystic Dog\n"
                f"Check the message above to see the mystical layout!"
            )
            logger.info(f"TEST_BLOCK: {username} tested bot celebration block")

        else:
            say(
                f"❌ Unknown block type: `{block_type}`\n\n"
                f"Valid options: `birthday`, `multi`, `special`, `bot`\n"
                f"Type `admin test-block` for usage examples."
            )

    except Exception as e:
        logger.error(f"TEST_BLOCK: Failed to execute test-block command: {e}")
        say(f"❌ An error occurred during block testing: {e}\n\nCheck logs for details.")


def handle_test_upload_command(user_id, say, app):
    """
    Test single image upload to Slack.

    Creates a simple test image and uploads it to the requesting user's DM
    to verify image upload functionality.

    Args:
        user_id: Slack user ID to receive test image
        say: Slack say function for sending messages
        app: Slack app instance for file upload
    """
    say("Attempting to upload a test image to you via DM...")
    try:
        import io

        from PIL import Image, ImageDraw

        # Create a dummy image
        img = Image.new("RGB", (200, 50), color="blue")
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Test Upload", fill="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        image_data = {"image_data": image_bytes, "personality": "test", "format": "png"}

        if send_message_with_image(
            app,
            user_id,
            "This is a test upload from the `admin test-upload` command.",
            image_data=image_data,
            context={"message_type": "test", "command_name": "admin test-upload"},
        ):
            say("Test image uploaded successfully to your DMs!")
        else:
            say("Test image upload failed. Check logs for details.")
    except ImportError:
        logger.error("TEST_UPLOAD: Pillow library is not installed. Cannot create a test image.")
        say(
            "I can't create a test image because the `Pillow` library is not installed. Please install it (`pip install Pillow`) and try again."
        )
    except Exception as e:
        logger.error(f"TEST_UPLOAD: Failed to execute test upload command: {e}")
        say(f"An error occurred during the test upload: {e}")


def handle_test_upload_multi_command(user_id, say, app):
    """
    Test multiple image attachment upload system.

    Creates multiple dummy images simulating consolidated birthday celebrations
    and tests the batch upload functionality.

    Args:
        user_id: Slack user ID to receive test images
        say: Slack say function for sending messages
        app: Slack app instance for file uploads
    """
    from slack.messaging import send_message_with_multiple_attachments

    username = get_username(app, user_id)
    say(
        "🔄 *Testing Multiple Attachment Upload System*\nCreating dummy images and testing batch upload..."
    )

    try:
        import io

        from PIL import Image, ImageDraw, ImageFont

        # Create multiple dummy images with different themes
        test_images = []
        image_configs = [
            {"color": "blue", "text": "Alice's Birthday", "personality": "mystic_dog"},
            {"color": "green", "text": "Bob's Birthday", "personality": "superhero"},
            {"color": "red", "text": "Charlie's Birthday", "personality": "pirate"},
        ]

        for i, config in enumerate(image_configs):
            # Create dummy image
            img = Image.new("RGB", (300, 150), color=config["color"])
            d = ImageDraw.Draw(img)

            # Add text to image
            try:
                # Try to use default font, fallback to basic if not available
                font = ImageFont.load_default()
            except OSError:
                font = None

            d.text((10, 20), config["text"], fill="white", font=font)
            d.text((10, 50), f"Style: {config['personality']}", fill="white", font=font)
            d.text((10, 80), f"Test Image #{i+1}", fill="white", font=font)
            d.text((10, 110), "Multi-Attachment Test", fill="white", font=font)

            # Convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()

            # Create image data with birthday person metadata (simulate real birthday images)
            image_data = {
                "image_data": image_bytes,
                "personality": config["personality"],
                "format": "png",
                "birthday_person": {
                    "user_id": f"U{1111111111 + i}",  # Fake user IDs
                    "username": config["text"].split("'s")[0],  # Extract name
                    "date": f"{15+i}/04",  # Fake birthday dates
                    "year": 1990 + i,
                },
                "user_profile": {
                    "preferred_name": config["text"].split("'s")[0],
                    "title": f"Test {config['personality'].replace('_', ' ').title()}",
                },
            }

            test_images.append(image_data)

        # Test the multiple attachment function
        logger.info(f"TEST_UPLOAD_MULTI: Created {len(test_images)} test images for {username}")

        test_message = (
            f"🎂 *Multi-Attachment Test Results* 🎂\n\n"
            f"Testing the new consolidated birthday attachment system with {len(test_images)} images.\n\n"
            f"This simulates a multiple birthday celebration with individual face-accurate images "
            f"sent as attachments to a single consolidated message.\n\n"
            f"_Expected behavior_: One message with all {len(test_images)} images attached, "
            f"each with personalized AI-generated titles."
        )

        # Send using the new multiple attachment system
        results = send_message_with_multiple_attachments(app, user_id, test_message, test_images)

        # Report results
        if results["success"]:
            success_message = (
                f"✅ *Multi-Attachment Test Successful!*\n\n"
                f"_Results:_\n"
                f"• Message sent: {'✅' if results['message_sent'] else '❌'}\n"
                f"• Attachments sent: {results['attachments_sent']}/{results['total_attachments']}\n"
                f"• Failed attachments: {results['attachments_failed']}\n"
                f"• Fallback used: {'Yes' if results.get('fallback_used') else 'No'}\n\n"
                f"The multiple attachment system is working correctly! "
                f"{'(Used fallback method due to API limitations)' if results.get('fallback_used') else '(Used native batch upload)'}"
            )
            say(success_message)
            logger.info(
                f"TEST_UPLOAD_MULTI: Success for {username} - {results['attachments_sent']}/{results['total_attachments']} attachments sent"
            )
        else:
            error_message = (
                f"❌ *Multi-Attachment Test Failed*\n\n"
                f"_Results:_\n"
                f"• Message sent: {'✅' if results['message_sent'] else '❌'}\n"
                f"• Attachments sent: {results['attachments_sent']}/{results['total_attachments']}\n"
                f"• Failed attachments: {results['attachments_failed']}\n"
                f"• Fallback used: {'Yes' if results.get('fallback_used') else 'No'}\n\n"
                f"Please check the logs for detailed error information."
            )
            say(error_message)
            logger.error(
                f"TEST_UPLOAD_MULTI: Failed for {username} - only {results['attachments_sent']}/{results['total_attachments']} attachments sent"
            )

    except ImportError:
        logger.error("TEST_UPLOAD_MULTI: Pillow library is not installed.")
        say(
            "❌ Cannot create test images because the `Pillow` library is not installed.\n"
            "Please install it with: `pip install Pillow`"
        )
    except Exception as e:
        logger.error(f"TEST_UPLOAD_MULTI: Failed to execute multi-upload test: {e}")
        say(f"❌ Multi-attachment test failed with error: {e}\nPlease check the logs for details.")


def handle_test_file_upload_command(user_id, say, app):
    """
    Test text file upload functionality.

    Creates a temporary test file with sample birthday data format and uploads
    it to verify the external backup file delivery system.

    Args:
        user_id: Slack user ID to receive test file
        say: Slack say function for sending messages
        app: Slack app instance for file upload
    """
    import os
    import tempfile

    from slack.messaging import send_message_with_file

    username = get_username(app, user_id)
    say("📄 Creating and uploading a test text file to you via DM...")

    temp_file_path = None
    try:
        # Create a temporary test file with sample birthday data
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        test_content = f"""# Ludo | LiGHT BrightDay Coordinator Test File Upload
# Generated: {timestamp}
# Command: admin test-file-upload
# Requested by: {username} ({user_id})

## Sample Birthday Data Format:
U1234567890,15/05,1990
U0987654321,25/12
U1122334455,01/01,1995
U5566778899,31/10

## Test Information:
- Total sample entries: 4
- Entries with birth year: 2
- Entries without birth year: 2
- File format: CSV (user_id,DD/MM[,YYYY])

## Notes:
This is a test file to verify the text file upload functionality.
If you received this file, the external backup system should work correctly.

---
End of test file
"""

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix="_test_upload.txt",
            prefix="brightday_",
            delete=False,
            encoding="utf-8",
        ) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(test_content)
            logger.info(f"TEST_FILE_UPLOAD: Created temporary test file: {temp_file_path}")

        # Prepare upload message
        file_size = os.path.getsize(temp_file_path)
        file_size_kb = round(file_size / 1024, 2)
        filename = os.path.basename(temp_file_path)

        upload_message = f"""📄 *Test File Upload* - {timestamp}

🧪 *Test Details:*
• File: {filename} ({file_size_kb} KB)
• Content: Sample birthday data format
• Purpose: Verify text file upload functionality

This test file contains sample birthday data in the same format used by the external backup system. If you received this file successfully, the backup delivery system should work correctly."""

        # Attempt to upload the file
        if send_message_with_file(app, user_id, upload_message, temp_file_path):
            say(
                "✅ *Test file uploaded successfully!*\nCheck your DMs for the test file. If you received it, the external backup system is working correctly."
            )
            logger.info(f"TEST_FILE_UPLOAD: Successfully sent test file to {username} ({user_id})")
        else:
            say(
                "❌ *Test file upload failed.*\nCheck the logs for details. This may indicate issues with the external backup system."
            )
            logger.error(f"TEST_FILE_UPLOAD: Failed to send test file to {username} ({user_id})")

    except Exception as e:
        logger.error(f"TEST_FILE_UPLOAD: Error creating or uploading test file: {e}")
        say(
            f"❌ *Test file upload failed with error:* {e}\n\nThis may indicate issues with file creation or the upload system."
        )

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"TEST_FILE_UPLOAD: Cleaned up temporary file: {temp_file_path}")
            except OSError as cleanup_error:
                logger.warning(
                    f"TEST_FILE_UPLOAD: Failed to clean up temporary file {temp_file_path}: {cleanup_error}"
                )


def handle_test_external_backup_command(user_id, say, app):
    """
    Test the canvas dashboard backup notification system.

    Displays current configuration, finds the latest backup file,
    and triggers a canvas dashboard update.

    Args:
        user_id: Slack user ID requesting the test
        say: Slack say function for sending messages
        app: Slack app instance
    """
    import glob
    import os

    from storage.birthdays import send_external_backup

    username = get_username(app, user_id)
    say("🔄 *Testing Canvas Backup System*\nChecking configuration and triggering canvas update...")

    config_status = f"""📋 *Configuration:*
• `EXTERNAL_BACKUP_ENABLED`: {EXTERNAL_BACKUP_ENABLED}
• `BACKUP_ON_EVERY_CHANGE`: {BACKUP_ON_EVERY_CHANGE}
• `OPS_CHANNEL_ID`: {OPS_CHANNEL_ID or 'Not set'}"""

    say(config_status)
    logger.info(f"TEST_EXTERNAL_BACKUP: Configuration check by {username} ({user_id})")

    # Find the latest backup file
    backup_files = glob.glob(os.path.join(BACKUP_DIR, "birthdays_*.json"))

    if not backup_files:
        say("❌ *No backup files found!* Try creating a backup first with `admin backup`.")
        return

    # Sort by modification time (newest first)
    backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_backup = backup_files[0]

    backup_info = f"""📁 *Latest Backup File:*
• File: {os.path.basename(latest_backup)}
• Size: {round(os.path.getsize(latest_backup) / 1024, 1)} KB
• Modified: {datetime.fromtimestamp(os.path.getmtime(latest_backup)).strftime('%Y-%m-%d %H:%M:%S')}"""

    say(backup_info)

    try:
        say("🚀 *Triggering canvas dashboard update...*")
        logger.info(f"TEST_EXTERNAL_BACKUP: Triggering manual test by {username} ({user_id})")

        send_external_backup(latest_backup, "manual", username, app)

        say(
            "✅ *Test completed!* Canvas dashboard has been updated. Check the ops channel canvas for results."
        )
        logger.info(f"TEST_EXTERNAL_BACKUP: Test completed by {username} ({user_id})")

    except Exception as e:
        say(f"❌ *Test failed:* {e}")
        logger.error(f"TEST_EXTERNAL_BACKUP: Test failed for {username} ({user_id}): {e}")


def handle_test_blockkit_command(user_id, args, say, app):
    """
    Handles the admin test-blockkit [mode] command to test Block Kit image embedding.

    Test modes:
    - with-channel: Upload with channel parameter (current failing approach)
    - private: Upload without channel parameter
    - url-only: Use image_url instead of slack_file
    - simple: Simplest possible block structure
    - all: Run all modes sequentially
    """
    import io

    from PIL import Image, ImageDraw

    username = get_username(app, user_id)

    # Parse mode argument
    mode = "all"  # Default to testing all modes
    if args and len(args) > 0:
        mode = args[0].lower()

    valid_modes = ["with-channel", "private", "url-only", "simple", "all"]
    if mode not in valid_modes:
        say(f"❌ Invalid test mode: `{mode}`\n\nValid modes: {', '.join(valid_modes)}")
        return

    say(
        f"🧪 *Testing Block Kit Image Embedding*\nMode: `{mode}`\n\nCreating test image and uploading..."
    )
    logger.info(
        f"TEST_BLOCKKIT: {username} ({user_id}) testing Block Kit embedding with mode: {mode}"
    )

    # Create a simple test image using PIL
    try:
        img = Image.new("RGB", (400, 200), color="blue")
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Block Kit Test Image", fill="white")
        d.text((10, 50), f"Mode: {mode}", fill="white")
        d.text((10, 90), f"User: {username}", fill="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    except Exception as e:
        logger.error(f"TEST_BLOCKKIT: Failed to create test image: {e}")
        say(f"❌ Failed to create test image: {e}")
        return

    # Mode configs: (label, upload_with_channel, use_image_url, simple_blocks)
    _BLOCKKIT_MODES = {
        "with-channel": ("With Channel", True, False, False),
        "private": ("Private Upload", False, False, False),
        "url-only": ("image_url", True, True, False),
        "simple": ("Simple", False, False, True),
    }

    modes_to_test = [mode] if mode != "all" else list(_BLOCKKIT_MODES.keys())

    for test_mode in modes_to_test:
        say(f"\n📋 *Testing Mode: `{test_mode}`*")
        logger.info(f"TEST_BLOCKKIT: Testing mode: {test_mode}")

        try:
            _test_blockkit_mode(
                app,
                user_id,
                username,
                image_bytes,
                say,
                test_mode,
                *_BLOCKKIT_MODES[test_mode],
            )
        except Exception as e:
            logger.error(
                f"TEST_BLOCKKIT: Mode {test_mode} failed with exception: {e}",
                exc_info=True,
            )
            say(f"❌ Mode `{test_mode}` failed with exception: {e}")

    say("\n✅ *Block Kit testing complete!* Check logs for detailed results.")


def _test_blockkit_mode(
    app,
    user_id,
    username,
    image_bytes,
    say,
    mode_key,
    label,
    upload_with_channel,
    use_image_url,
    simple_blocks,
):
    """Test a single Block Kit image embedding mode."""
    import time

    log_prefix = f"TEST_BLOCKKIT_{mode_key.upper().replace('-', '_')}"

    say(f"Uploading image for `{mode_key}` mode...")
    logger.info(f"{log_prefix}: Uploading image")

    file_uploads = [
        {
            "file": image_bytes,
            "filename": f"blockkit_test_{mode_key.replace('-', '_')}_{int(time.time())}.png",
            "title": f"Block Kit Test ({label})",
        }
    ]

    upload_kwargs = {"file_uploads": file_uploads}
    if upload_with_channel:
        upload_kwargs["channel"] = user_id

    upload_response = app.client.files_upload_v2(**upload_kwargs)

    if not upload_response["ok"]:
        say(f"❌ Upload failed: {upload_response.get('error', 'Unknown error')}")
        logger.error(f"{log_prefix}: Upload failed: {upload_response}")
        return

    uploaded_file = upload_response.get("files", [{}])[0]
    file_id = uploaded_file.get("id")
    file_url = uploaded_file.get("url_private")

    logger.info(f"{log_prefix}: Upload successful - ID: {file_id}, URL: {file_url}")
    say(f"✅ Upload successful\nFile ID: `{file_id}`\nURL: `{file_url}`")

    # Build blocks
    if simple_blocks:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🧪 *Simple Test*\n\nMinimal block structure with `slack_file`.",
                },
            },
            {"type": "image", "slack_file": {"url": file_url}, "alt_text": "Test image"},
        ]
    else:
        image_block = {
            "type": "image",
            "alt_text": f"Block Kit test image for {username}",
            "title": {"type": "plain_text", "text": f"🧪 Test Image ({label} Mode)"},
        }
        if use_image_url:
            image_block["image_url"] = file_url
        else:
            image_block["slack_file"] = {"url": file_url}

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🧪 Block Kit Test: {label}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Testing image embedding for `{mode_key}` mode.\n\nUser: <@{user_id}>",
                },
            },
            image_block,
        ]

    logger.info(f"{log_prefix}: Sending message with blocks")
    say("Sending Block Kit message with embedded image...")

    try:
        result = app.client.chat_postMessage(
            channel=user_id, text=f"Block Kit Test: {label}", blocks=blocks
        )

        if result["ok"]:
            say("✅ Block Kit message sent successfully!")
            logger.info(f"{log_prefix}: Success!")
        else:
            say(f"❌ Block Kit message failed: {result.get('error', 'Unknown')}")
            logger.error(f"{log_prefix}: Failed: {result}")
    except Exception as e:
        say(f"❌ Block Kit message exception: {str(e)}")
        logger.error(f"{log_prefix}: Exception: {e}", exc_info=True)


def handle_test_join_command(args, user_id, say, app):
    """
    Simulate a member joining the birthday channel.

    Triggers the welcome message flow for the specified user or the requesting
    admin, useful for testing the onboarding experience.

    Args:
        args: Optional user mention to simulate join for
        user_id: Slack user ID requesting the test (default target)
        say: Slack say function for sending messages
        app: Slack app instance for API calls
    """

    username = get_username(app, user_id)

    # Determine target user - default to requesting admin if no user specified
    test_user_id = user_id
    if args and args[0].startswith("<@") and args[0].endswith(">"):
        # Extract user ID from mention
        test_user_id = args[0][2:-1].split("|")[0].upper()
        logger.info(f"TEST_JOIN: Extracted user ID: {test_user_id}")

    test_username = get_username(app, test_user_id)

    # Show what we're testing
    if test_user_id == user_id:
        say(
            "🧪 *Testing Birthday Channel Welcome for Yourself*\nSimulating member_joined_channel event..."
        )
    else:
        say(
            f"🧪 *Testing Birthday Channel Welcome for {test_username}*\nSimulating member_joined_channel event..."
        )

    logger.info(
        f"TEST_JOIN: {username} ({user_id}) testing birthday channel welcome for {test_username} ({test_user_id})"
    )

    try:
        # Create a mock event body for member_joined_channel
        member_joined_body = {
            "event": {
                "type": "member_joined_channel",
                "user": test_user_id,
                "channel": BIRTHDAY_CHANNEL,
                "channel_type": "C",
                "team": "TEST_TEAM",
                "inviter": user_id,
            },
            "team_id": "TEST_TEAM",
            "event_id": f"test_member_joined_{test_user_id}",
            "event_time": int(datetime.now().timestamp()),
        }

        # Test member_joined_channel event
        say("📝 *Testing birthday channel welcome...*")

        # Simulate member_joined_channel handler behavior directly
        event = member_joined_body.get("event", {})
        event_user = event.get("user")
        channel = event.get("channel")

        logger.debug(f"TEST_CHANNEL_JOIN: User {event_user} joined channel {channel}")

        # Send welcome message if they joined the birthday channel
        if channel == BIRTHDAY_CHANNEL:
            try:
                event_username = get_username(app, event_user)

                welcome_msg = f"""🎉 Welcome to the birthday channel, {get_user_mention(event_user)}!

Here I celebrate everyone's birthdays with personalized messages and AI-generated images!

📅 *To add your birthday:* Use `/birthday` anywhere in Slack, or visit my *App Home* tab

💡 *Commands:* Type `help` in a DM to see all available options

Hope to celebrate your special day soon! 🎂

*Not interested in birthday celebrations?*
No worries! Use `/birthday pause` or visit my *App Home* to disable celebrations."""

                send_message(app, event_user, welcome_msg)
                logger.info(
                    f"TEST_BIRTHDAY_CHANNEL: Welcomed {event_username} ({event_user}) to birthday channel"
                )

            except Exception as e:
                logger.error(
                    f"TEST_BIRTHDAY_CHANNEL: Failed to send welcome message to {event_user}: {e}"
                )

        say("✅ *Birthday channel welcome simulated* - Check your DMs for the welcome message")

        say(
            f"🎉 *Birthday Channel Welcome Test Complete!*\n\n{test_username} should have received the birthday channel welcome message with instructions.\n\nCheck the logs for detailed event processing information."
        )

        logger.info(
            f"TEST_JOIN: Successfully completed birthday channel welcome test for {test_username} ({test_user_id})"
        )

    except Exception as e:
        say(f"❌ *Birthday channel welcome test failed:* {e}")
        logger.error(
            f"TEST_JOIN: Failed to simulate birthday channel welcome for {test_user_id}: {e}"
        )
        import traceback

        logger.error(traceback.format_exc())


def handle_test_birthday_command(args, user_id, say, app):
    """
    Generate test birthday celebration for specified users.

    Supports single or multiple user testing with optional quality, size,
    and text-only parameters. Uses the production celebration pipeline.

    Args:
        args: User mentions and optional parameters [@users, quality, size, --text-only]
        user_id: Slack user ID requesting the test
        say: Slack say function for sending messages
        app: Slack app instance for API calls
    """
    if not args:
        say(
            "Please specify user(s): `admin test @user1 [@user2 @user3...] [quality] [size] [--text-only]`\n"
            "Quality options: low, medium, high, auto\n"
            "Size options: auto, 1024x1024, 1536x1024, 1024x1536\n"
            "Flags: --text-only (skip image generation)\n\n"
            "Examples:\n"
            "• `admin test @alice` - Single user test\n"
            "• `admin test @alice @bob @charlie` - Multiple user test\n"
            "• `admin test @alice @bob high auto` - Multiple users with quality/size\n"
            "• `admin test @alice --text-only` - Single user text-only test\n"
            "• `admin test @alice @bob --text-only` - Multiple users text-only test"
        )
        return

    # Extract user IDs from mentions (support multiple users)
    test_user_ids = []
    non_user_args = []

    for arg in args:
        if arg.startswith("<@") and arg.endswith(">"):
            # This is a user mention
            user_id_part = arg[2:-1].split("|")[0].upper()
            test_user_ids.append(user_id_part)
            logger.info(f"TEST_COMMAND: Extracted user ID: {user_id_part}")
        else:
            # This is a quality/size parameter
            non_user_args.append(arg)

    if not test_user_ids:
        say("Please mention at least one user with @username")
        return

    if len(test_user_ids) > 5:
        say("Maximum 5 users allowed for testing to avoid spam")
        return

    # Extract quality, image_size, and --text-only parameters from non-user arguments
    quality, image_size, text_only, error_message = parse_test_command_args(non_user_args)

    if error_message:
        say(error_message)
        return

    # Use unified test command for both single and multiple users
    handle_test_command(
        user_id,
        say,
        app,
        quality,
        image_size,
        target_user_id=test_user_ids if len(test_user_ids) > 1 else test_user_ids[0],
        text_only=text_only,
    )


def handle_test_bot_celebration_command(
    user_id, say, app, quality=None, image_size=None, text_only=None
):
    """
    Test the bot's self-celebration feature using the production celebration pipeline.

    Sends the celebration to the admin's DM instead of the birthday channel.

    Args:
        user_id: Slack user ID to receive test celebration
        say: Slack say function for sending messages
        app: Slack app instance for API calls
        quality: Optional image quality (low/medium/high/auto)
        image_size: Optional image size (auto/1024x1024/etc.)
        text_only: Skip image generation if True
    """
    from services.birthday import run_bot_celebration
    from utils.date_utils import date_to_words

    username = get_username(app, user_id)
    say(
        "🤖 *Testing Ludo | LiGHT BrightDay Coordinator's Self-Celebration* 🤖\n_Test message will stay in this DM._"
    )

    try:
        # Show configuration preview
        display_quality = (
            quality if quality is not None else IMAGE_GENERATION_PARAMS["quality"]["test"]
        )
        display_image_size = (
            image_size if image_size is not None else IMAGE_GENERATION_PARAMS["size"]["default"]
        )

        say(
            f"_Configuration:_\n"
            f"• Quality: {display_quality} {'(custom)' if quality is not None else '(default)'}\n"
            f"• Size: {display_image_size} {'(custom)' if image_size is not None else '(default)'}\n"
            f"• Images: {'enabled' if (AI_IMAGE_GENERATION_ENABLED and not text_only) else 'disabled'}"
        )

        say("Generating Ludo's mystical celebration message... this might take a moment.")

        logger.info(f"TEST_BOT_CELEBRATION: Starting test for {username} ({user_id})")

        # Run the same celebration pipeline as production, but to DM
        include_image = AI_IMAGE_GENERATION_ENABLED and not text_only
        result = run_bot_celebration(
            app,
            channel=user_id,
            test_mode=True,
            quality=quality,
            image_size=image_size,
            include_image=include_image,
        )

        # Show result summary with statistics from the pipeline
        if result["success"]:
            image_status = (
                "✅ Generated and sent" if result["image_success"] else "⚠️ Skipped or failed"
            )
            say(
                f"✅ *Bot Celebration Test Completed!* ✅\n\n"
                f"_Results:_\n"
                f"• Bot age: {result['bot_age']} years ({date_to_words(BOT_BIRTHDAY)}, {BOT_BIRTH_YEAR})\n"
                f"• Birthdays tracked: {result['total_birthdays']}\n"
                f"• Special days tracked: {result['special_days_count']}\n"
                f"• Channel members: {result['channel_members_count']}\n"
                f"• Estimated savings: ${result['yearly_savings']}/year\n"
                f"• Ludo's mystical message: ✅ Generated successfully\n"
                f"• AI image: {image_status}\n"
                f"• Processing: Complete - ready for {date_to_words(BOT_BIRTHDAY)} automatic celebration\n\n"
                f"🎉 _Test successful!_ This demonstrates the complete bot self-celebration flow."
            )
            logger.info(f"TEST_BOT_CELEBRATION: Successfully completed for {username}")
        else:
            say(
                f"❌ *Bot Celebration Test Failed* ❌\n\n"
                f"• Error: {result.get('error', 'Unknown')}\n\n"
                f"🔧 _Admin tip:_ Check logs for detailed error information."
            )
            logger.error(f"TEST_BOT_CELEBRATION: Failed for {username}: {result.get('error')}")

    except Exception as e:
        say(
            f"❌ *Bot Celebration Test Failed* ❌\n\n"
            f"• Error: {str(e)}\n\n"
            f"🔧 _Admin tip:_ Check logs for detailed error information."
        )
        logger.error(f"TEST_BOT_CELEBRATION: Test failed by {username} ({user_id}): {e}")
