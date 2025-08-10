"""
AI-powered birthday message generation using OpenAI GPT models.

Creates personalized birthday messages with 8+ bot personalities, user profile
integration (age, star sign, job title), and web search historical facts.
Features fallback templates and proper Slack formatting.

Main functions: create_birthday_announcement(), create_consolidated_birthday_announcement().
Supports dynamic personality selection and configurable AI models.
"""

from openai import OpenAI
import logging
import os
import random
import argparse
import sys
from datetime import datetime

from config import get_logger, USE_CUSTOM_EMOJIS, DATE_FORMAT
from config import (
    BOT_PERSONALITIES,
    TEAM_NAME,
    get_current_personality_name,
)

from utils.date_utils import get_star_sign
from utils.constants import SAFE_SLACK_EMOJIS
from utils.slack_formatting import get_user_mention, fix_slack_formatting
from utils.web_search import get_birthday_facts
from utils.usage_logging import log_chat_completion_usage

logger = get_logger("llm")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Import centralized model configuration function
from utils.app_config import get_configured_openai_model as get_configured_model


# Birthday announcement formats
BIRTHDAY_INTROS = [
    ":birthday: ATTENTION WONDERFUL HUMANS! :tada:",
    ":loudspeaker: :sparkles: SPECIAL ANNOUNCEMENT FOR EVERYONE! :sparkles: :loudspeaker:",
    ":rotating_light: BIRTHDAY ALERT! BIRTHDAY ALERT! :rotating_light:",
    ":mega: HEY <!here>! STOP WHAT YOU'RE DOING! :mega:",
    ":siren: URGENT: CAKE NEEDED IN THE CHAT! :siren:",
]

BIRTHDAY_MIDDLES = [
    "Time to take a break from work and gather 'round because... :drum:",
    "We have a very special occasion that demands your immediate attention! :eyes:",
    "Put those Slack notifications on pause because this is WAY more important! :no_bell:",
    "Forget those deadlines for a moment, we've got something to celebrate! :confetti_ball:",
    "Clear your calendar and prepare the party emojis, folks! :calendar: :tada:",
]

BIRTHDAY_CALL_TO_ACTIONS = [
    ":mega: Let's make some noise and flood the chat with good wishes! Bring your:\n• Best GIFs :movie_camera:\n• Favorite memories :brain:\n• Terrible puns encouraged :nerd_face:",
    ":sparkles: Time to shower them with birthday love! Don't hold back on:\n• Your most ridiculous emojis :stuck_out_tongue_winking_eye:\n• Work-appropriate birthday memes :framed_picture:\n• Tales of their legendary feats :superhero:",
    ":confetti_ball: Operation Birthday Spam is now active! Contribute with:\n• Birthday song lyrics :musical_note:\n• Virtual cake slices :cake:\n• Your worst dad jokes :man:",
    ":rocket: Launch the birthday celebration protocols! Required items:\n• Embarrassing compliments :blush:\n• Pet photos (always welcome) :dog:\n• More exclamation points than necessary!!!!!!",
    ":star2: Commence birthday appreciation sequence! Please submit:\n• Appreciation in GIF form :gift:\n• Your best birthday haiku :scroll:\n• Creative use of emojis :art:",
]

BIRTHDAY_ENDINGS = [
    ":point_down: Drop your birthday messages below! :point_down:",
    ":eyes: We're all watching to see who posts the best birthday wish! :eyes:",
    ":alarm_clock: Don't delay! Birthday wishes must be submitted ASAP! :alarm_clock:",
    ":white_check_mark: Your participation in this birthday celebration is mandatory and appreciated! :white_check_mark:",
    ":handshake: Together we can make this the best birthday they've had at work yet! :handshake:",
]

# Age-based fun facts
AGE_FACTS = {
    20: "You're officially out of your teens! Welcome to the decade of figuring out how taxes work!",
    21: "You can now legally drink in the US! But you'll still get carded until you're 35!",
    25: "Quarter of a century! You're now officially vintage... but not yet an antique!",
    30: "Welcome to your 30s! Your back will start making weird noises when you stand up now!",
    35: "You're now officially 'mid-thirties' - where you inexplicably start enjoying gardening and early nights!",
    40: "40 is like your 30s but with reading glasses! Welcome to the club!",
    45: "At 45, you've earned the right to complain about 'kids these days' without irony!",
    50: "Half a century! You're basically a walking historical monument now!",
    55: "55! Like being 25, but with more wisdom, money, and knee pain!",
    60: "You're now entering the golden years! Where 'going wild' means staying up past 10pm!",
    65: "Traditional retirement age! But knowing you, you're just getting started!",
    70: "70 years young! You're officially old enough to get away with saying whatever you want!",
    75: "You've been around for three quarters of a century! That's a lot of cake!",
    80: "80 years strong! That deserves a standing ovation!",
    90: "90 years strong! You should be studied by scientists to discover your secret!",
    100: "A CENTURY! You've officially unlocked legendary status!",
}


def get_current_personality():
    """Get the currently configured bot personality settings"""
    personality_name = get_current_personality_name()
    personality = BOT_PERSONALITIES.get(personality_name, BOT_PERSONALITIES["standard"])
    return personality


def build_template(override_personality=None):
    """Build the prompt template based on current personality settings or override"""
    global_personality = get_current_personality_name()
    # Determine which personality to use
    if global_personality == "random":
        # use override if provided, else pick randomly
        if override_personality:
            persona = override_personality
        else:
            persona = get_random_personality_name()
            logger.info(f"RANDOM: Using randomly selected personality: {persona}")
    else:
        persona = global_personality
    # Get the complete template including base + extension for the chosen personality
    from config import get_full_template_for_personality

    template_text = get_full_template_for_personality(persona)
    personality = BOT_PERSONALITIES.get(persona, BOT_PERSONALITIES["standard"])

    # Format and return system prompt
    formatted_template = template_text.format(
        name=personality["name"],
        description=personality["description"],
        team_name=TEAM_NAME,
        style=personality["style"],
        format_instruction=personality["format_instruction"],
    )

    return [{"role": "system", "content": formatted_template.strip()}]


# Replace the existing TEMPLATE with the dynamic version
def get_template():
    """Get the current template based on personality configuration"""
    return build_template()


def get_random_personality_name():
    """
    Get a random personality name from the available personalities (excluding 'random' and 'custom')

    Returns:
        str: Name of a randomly selected personality
    """
    # Get a list of all available personalities, excluding 'random' and 'custom'
    available_personalities = [
        name for name in BOT_PERSONALITIES.keys() if name not in ["random", "custom"]
    ]

    # Select a random personality
    if available_personalities:
        random_personality = random.choice(available_personalities)
        logger.info(f"RANDOM: Selected '{random_personality}' personality randomly")
        return random_personality
    else:
        # Fallback to standard if no other personalities are available
        logger.warning("RANDOM: No personalities available, using standard")
        return "standard"


def create_birthday_announcement(
    user_id,
    name,
    date_str,
    birth_year=None,
    star_sign=None,
    test_mode=False,
    quality=None,
    image_size=None,
):
    """
    Create a fun, vertically expansive birthday announcement

    Args:
        user_id: User ID of birthday person
        name: Display name of birthday person
        date_str: Birthday in DD/MM format
        birth_year: Optional birth year
        star_sign: Optional star sign

    Returns:
        Formatted announcement text
    """
    # Parse the date using datetime for proper validation
    try:
        date_obj = datetime.strptime(date_str, DATE_FORMAT)
        # Use current year for formatting but preserve the parsed month/day
        formatted_date_obj = datetime(2025, date_obj.month, date_obj.day)
        month_name_str = formatted_date_obj.strftime("%B")
        day_num = formatted_date_obj.day
    except ValueError as e:
        logger.error(f"Invalid date format in birthday announcement: {date_str} - {e}")
        month_name_str = "Unknown Month"
        day_num = "??"

    # Calculate age if birth year is provided
    age_text = ""
    age_fact = ""
    if birth_year:
        current_year = datetime.now().year
        age = current_year - birth_year
        age_text = f" ({age} years young)"

        # Find the closest age milestone
        age_keys = list(AGE_FACTS.keys())
        if age in AGE_FACTS:
            age_fact = AGE_FACTS[age]
        elif age > 0:
            closest = min(age_keys, key=lambda x: abs(x - age))
            if abs(closest - age) <= 3:  # Only use if within 3 years
                age_fact = AGE_FACTS[closest]

    # Determine star sign if not provided
    if not star_sign:
        star_sign = get_star_sign(date_str)

    star_sign_text = f":crystal_ball: {star_sign}" if star_sign else ""

    # Select random elements
    intro = random.choice(BIRTHDAY_INTROS)
    middle = random.choice(BIRTHDAY_MIDDLES)
    call_to_action = random.choice(BIRTHDAY_CALL_TO_ACTIONS)
    ending = random.choice(BIRTHDAY_ENDINGS)

    # Random emojis (using only standard ones)
    safe_emojis = [
        ":birthday:",
        ":tada:",
        ":cake:",
        ":gift:",
        ":sparkles:",
        ":star:",
        ":crown:",
    ]
    emoji1 = random.choice(safe_emojis)
    emoji2 = random.choice(safe_emojis)

    # Build the announcement
    message = f"""
{intro}

{middle}

{get_user_mention(user_id)}
{emoji1} Birthday Extraordinaire {emoji2}
{month_name_str} {day_num}{age_text}
{star_sign_text}

{f"✨ {age_fact} ✨" if age_fact else ""}

---
{call_to_action}

{ending}

<!here> Let's celebrate together!
"""
    return message.strip()


# Backup birthday messages for fallback if the API fails
BACKUP_MESSAGES = [
    """
:birthday: HAPPY BIRTHDAY {name}!!! :tada:

<!here> We've got a birthday to celebrate! 

:cake: :cake: :cake: :cake: :cake: :cake: :cake:

*Let the festivities begin!* :confetti_ball: 

Wishing you a day filled with:
• Joy :smile:
• Laughter :joy:
• _Way too much_ cake :cake:
• Zero work emails :no_bell:

Any special celebration plans for your big day? :sparkles:

:point_down: Drop your birthday wishes below! :point_down:
    """,
    """
:rotating_light: ATTENTION <!here> :rotating_light:

IT'S {name}'s BIRTHDAY!!! :birthday: 

:star2: :star2: :star2: :star2: :star2:

Time to celebrate *YOU* and all the awesome you bring to our team! :muscle:

• Your jokes :laughing:
• Your hard work :computer:
• Your brilliant ideas :bulb:
• Just being YOU :heart:

Hope your day is as amazing as you are! :star:

So... how are you planning to celebrate? :thinking_face:
    """,
    """
:alarm_clock: *Birthday Alert* :alarm_clock:

<!here> Everyone drop what you're doing because...

{name} is having a BIRTHDAY today! :birthday:

:cake: :gift: :balloon: :confetti_ball: :cake: :gift: :balloon:

Wishing you:
• Mountains of cake :mountain:
• Oceans of presents :ocean:
• Absolutely *zero* work emails! :no_bell:

What's on the birthday agenda today? :calendar:

:point_right: Reply with your best birthday GIF! :point_left:
    """,
    """
Whoop whoop! :tada: 

:loudspeaker: <!here> Announcement! :loudspeaker:

It's {name}'s special day! :birthday:

:sparkles: :sparkles: :sparkles: :sparkles: :sparkles:

May your birthday be filled with:
• Cake that's *just right* :cake:
• Presents that don't need returning :gift:
• Birthday wishes that actually come true! :sparkles:

How are you celebrating this year? :cake:

:clap: :clap: :clap: :clap: :clap:
    """,
    """
:rotating_light: SPECIAL BIRTHDAY ANNOUNCEMENT :rotating_light:

<!here> HEY EVERYONE! 

:arrow_down: :arrow_down: :arrow_down:
It's {name}'s birthday!
:arrow_up: :arrow_up: :arrow_up:

:birthday: :confetti_ball: :birthday: :confetti_ball:

Time to shower them with:
• ~Work assignments~ BIRTHDAY WISHES instead! :grin:
• Your most ridiculous emojis :stuck_out_tongue_closed_eyes:
• Virtual high-fives :raised_hands:

Hope your special day is absolutely *fantastic*! :star2: 

Any exciting birthday plans to share? :eyes:
    """,
]


def completion(
    name: str,
    date: str,
    user_id: str = None,
    birth_date: str = None,
    birth_year: int = None,
    max_retries: int = 2,
    app=None,  # Add app parameter to fetch custom emojis
    user_profile: dict = None,  # Enhanced profile data
    include_image: bool = False,  # Whether to generate AI image
    test_mode: bool = False,  # Use low-cost mode for testing
    quality: str = None,  # Override image quality ("low", "medium", "high", "auto")
    image_size: str = None,  # Override image size ("auto", "1024x1024", "1536x1024", "1024x1536")
) -> str:
    """
    Generate an enthusiastic, fun birthday message using OpenAI or fallback messages
    with validation to ensure proper mentions are included.

    Args:
        name: User's name or Slack ID
        date: User's birthday in natural language format (e.g. "2nd of April")
        user_id: User's Slack ID for mentioning them with @
        birth_date: Original birth date in DD/MM format (for star sign)
        birth_year: Optional birth year for age-related content
        max_retries: Maximum number of retries if validation fails
        app: Slack app instance for fetching custom emojis
        user_profile: Enhanced profile data with job title, timezone, etc.
        include_image: Whether to generate AI birthday image

    Returns:
        If include_image is True: tuple of (message, image_data)
        Otherwise: birthday message string
    """
    # Get current personality info for the request
    current_personality_name = get_current_personality_name()

    # If using random personality, get the actual personality being used
    if current_personality_name == "random":
        selected_personality_name = get_random_personality_name()
        # Use the selected personality's settings, not the "random" personality's settings
        personality = BOT_PERSONALITIES.get(
            selected_personality_name, BOT_PERSONALITIES["standard"]
        )
        logger.info(
            f"RANDOM: Using personality '{selected_personality_name}' with name '{personality['name']}'"
        )
    else:
        selected_personality_name = current_personality_name
        personality = get_current_personality()

    # Create user mention format if user_id is provided
    user_mention = f"{get_user_mention(user_id)}" if user_id else name

    # Get star sign if possible
    star_sign = get_star_sign(birth_date) if birth_date else None
    star_sign_text = f" Their star sign is {star_sign}." if star_sign else ""

    # Age information
    age_text = ""
    if birth_year:
        age = datetime.now().year - birth_year
        age_text = f" They're turning {age} today!"

    # Format list of emojis for the prompt (include custom ones if enabled)
    emoji_list = SAFE_SLACK_EMOJIS
    emoji_instruction = "ONLY USE STANDARD SLACK EMOJIS"
    emoji_warning = "DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they won't work"

    # Get custom emojis if enabled and app is provided
    if USE_CUSTOM_EMOJIS and app:
        try:
            # Get all emojis including custom ones
            from utils.slack_utils import get_all_emojis

            all_emojis = get_all_emojis(app, include_custom=True)
            if len(all_emojis) > len(SAFE_SLACK_EMOJIS):
                emoji_list = all_emojis
                custom_count = len(all_emojis) - len(SAFE_SLACK_EMOJIS)
                emoji_instruction = f"USE STANDARD OR CUSTOM SLACK EMOJIS"
                emoji_warning = (
                    f"The workspace has {custom_count} custom emoji(s) that you can use"
                )
                logger.info(
                    f"AI: Including {custom_count} custom emojis in message generation"
                )
        except Exception as e:
            logger.error(f"AI_ERROR: Failed to get custom emojis: {e}")
            # Fall back to standard emojis if there's an error

    # Get a random sample of emojis to show as examples
    emoji_sample_size = min(20, len(emoji_list))
    safe_emoji_examples = ", ".join(random.sample(emoji_list, emoji_sample_size))

    # Get birthday facts for personalities that use web search
    birthday_facts_text = ""
    personalities_using_web_search = [
        "mystic_dog",
        "time_traveler",
        "superhero",
        "pirate",
        "poet",  # Adding the remaining personalities
        "tech_guru",
        "chef",
        "standard",  # Even the standard personality can benefit from interesting facts!
    ]

    if selected_personality_name in personalities_using_web_search and birth_date:
        try:
            # Get facts formatted for this specific personality
            birthday_facts = get_birthday_facts(birth_date, selected_personality_name)

            if birthday_facts and birthday_facts["facts"]:
                # Get birthday facts text from centralized configuration
                from personality_config import get_personality_config

                personality_config = get_personality_config(selected_personality_name)
                facts_template = personality_config.get(
                    "birthday_facts_text",
                    "Incorporate these interesting facts about their birthday date: {facts}",
                )
                birthday_facts_text = (
                    f"\n\n{facts_template.format(facts=birthday_facts['facts'])}"
                )

                # Add sources if available
                if birthday_facts["sources"]:
                    sources_text = "\n\nYou may reference where this information came from in a way that fits your personality, without mentioning specific URLs."
                    birthday_facts_text += sources_text

                logger.info(
                    f"AI: Added {selected_personality_name}-specific facts for {birth_date}"
                )
        except Exception as e:
            logger.error(
                f"AI_ERROR: Failed to get birthday facts for {selected_personality_name}: {e}"
            )
            # Continue without facts if there's an error

    # Extract profile information for personalization
    profile_context = ""
    if user_profile:
        title = user_profile.get("title", "")
        timezone_label = user_profile.get("timezone_label", "")

        profile_details = []
        if title:
            profile_details.append(f"job title: {title}")
        # if timezone_label:
        #     profile_details.append(f"timezone: {timezone_label}")

        if profile_details:
            profile_context = f"\n\nPersonalize the message using this information about them: {', '.join(profile_details)}."

    # Note: Image will be generated after the message is created
    image_context = ""
    if include_image and user_profile:
        image_context = f"\n\nNote: A personalized birthday image will be generated for them in {selected_personality_name} style. Do NOT mention the image in your message as it will be sent automatically with your text."

    user_content = f"""
        {name}'s birthday is on {date}.{star_sign_text}{age_text} Please write them a fun, enthusiastic birthday message for a workplace Slack channel.
        
        IMPORTANT REQUIREMENTS:
        1. Include their Slack mention "{user_mention}" somewhere in the message
        2. Make sure to address active members with <!here> to notify those currently online
        3. Create a message that's lively and engaging with good structure and flow
        4. {emoji_instruction} like: {safe_emoji_examples}
        5. {emoji_warning}
        6. Remember to use Slack emoji format with colons (e.g., :cake:), not Unicode emojis (e.g., 🎂)
        7. Your name is {personality["name"]} and you are {personality["description"]}
        {birthday_facts_text}{profile_context}{image_context}
        
        Today is {datetime.now().strftime('%Y-%m-%d')}.
    """

    # Build system prompt with the selected personality to keep content and name in sync
    template = build_template(selected_personality_name)
    template.append({"role": "user", "content": user_content})

    retry_count = 0
    while retry_count <= max_retries:
        try:
            logger.info(
                f"AI: Requesting birthday message for {name} ({date}) using {current_personality_name} personality"
                + (f" (retry {retry_count})" if retry_count > 0 else "")
            )

            response = client.chat.completions.create(
                model=get_configured_model(), messages=template
            )

            # Log token usage for monitoring
            log_chat_completion_usage(response, "SINGLE_BIRTHDAY", logger)

            reply = response.choices[0].message.content

            # Fix common Slack formatting issues
            reply = fix_slack_formatting(reply)

            # Validate the message contains required elements
            is_valid = True
            validation_errors = []

            # Check for user mention
            if user_id and f"{get_user_mention(user_id)}" not in reply:
                is_valid = False
                validation_errors.append(
                    f"Missing user mention {get_user_mention(user_id)}"
                )

            # Check for channel mention
            if "<!here>" not in reply:
                is_valid = False
                validation_errors.append("Missing here mention <!here>")

            # If validation passed, generate image if requested and return
            if is_valid:
                logger.info(
                    f"AI: Successfully generated birthday message (passed validation)"
                )

                # Generate AI image if requested (after message is created)
                generated_image = None
                if include_image and user_profile:
                    try:
                        from utils.image_generator import generate_birthday_image

                        logger.info(f"IMAGE: Generating birthday image for {name}")
                        generated_image = generate_birthday_image(
                            user_profile,
                            selected_personality_name,
                            birth_date,
                            birthday_message=reply,  # Pass the generated message
                            test_mode=test_mode,
                            quality=quality,
                            image_size=image_size,
                        )

                        if generated_image:
                            logger.info(
                                f"IMAGE: Successfully generated image for {name}"
                            )
                        else:
                            logger.warning(
                                f"IMAGE: Failed to generate image for {name}"
                            )

                    except Exception as e:
                        logger.error(
                            f"IMAGE_ERROR: Failed to generate birthday image: {e}"
                        )

                if include_image:
                    return reply, generated_image
                return reply

            # If validation failed and we have retries left, try again
            if retry_count < max_retries:
                error_msg = ", ".join(validation_errors)
                logger.warning(
                    f"AI_VALIDATION: Message failed validation: {error_msg}. Retrying..."
                )
                retry_count += 1

                # Add clarification for the next attempt
                template.append({"role": "assistant", "content": reply})
                template.append(
                    {
                        "role": "user",
                        "content": f"The message you provided is missing: {error_msg}. Please regenerate the message including both the user mention {user_mention} and here mention <!here> formats exactly as specified.",
                    }
                )
            else:
                # Log the failure but return the last generated message
                logger.error(
                    f"AI_VALIDATION: Message failed validation after {max_retries} retries. Using last generated message anyway."
                )

                # Generate AI image if requested (after message is created)
                generated_image = None
                if include_image and user_profile:
                    try:
                        from utils.image_generator import generate_birthday_image

                        logger.info(
                            f"IMAGE: Generating birthday image for {name} (fallback case)"
                        )
                        generated_image = generate_birthday_image(
                            user_profile,
                            selected_personality_name,
                            birth_date,
                            birthday_message=reply,  # Pass the generated message
                            test_mode=test_mode,
                            quality=quality,
                            image_size=image_size,
                        )

                        if generated_image:
                            logger.info(
                                f"IMAGE: Successfully generated image for {name}"
                            )
                        else:
                            logger.warning(
                                f"IMAGE: Failed to generate image for {name}"
                            )

                    except Exception as e:
                        logger.error(
                            f"IMAGE_ERROR: Failed to generate birthday image: {e}"
                        )

                if include_image:
                    return reply, generated_image
                return reply

        except Exception as e:
            logger.error(f"AI_ERROR: Failed to generate completion: {e}")

            # Use one of our backup messages if the API call fails
            random_message = random.choice(BACKUP_MESSAGES)

            # Replace {name} with user mention if available
            mention_text = user_mention if user_id else name
            formatted_message = random_message.replace("{name}", mention_text)

            logger.info(f"AI: Used fallback birthday message")

            # Generate AI image if requested (after message is created)
            generated_image = None
            if include_image and user_profile:
                try:
                    from utils.image_generator import generate_birthday_image

                    logger.info(
                        f"IMAGE: Generating birthday image for {name} (error fallback)"
                    )
                    generated_image = generate_birthday_image(
                        user_profile,
                        selected_personality_name,
                        birth_date,
                        birthday_message=formatted_message,  # Pass the fallback message
                        test_mode=test_mode,
                        quality=quality,
                        image_size=image_size,
                    )

                    if generated_image:
                        logger.info(f"IMAGE: Successfully generated image for {name}")
                    else:
                        logger.warning(f"IMAGE: Failed to generate image for {name}")

                except Exception as e:
                    logger.error(f"IMAGE_ERROR: Failed to generate birthday image: {e}")

            if include_image:
                return formatted_message, generated_image
            return formatted_message

        # End of retry loop

    # We should never get here due to the returns in the loop
    logger.error("AI_ERROR: Unexpected flow in completion function")
    return create_birthday_announcement(
        user_id, name, birth_date, birth_year, test_mode=test_mode, quality=quality
    )


def create_consolidated_birthday_announcement(
    birthday_people,
    app=None,
    include_image=False,
    test_mode=False,
    quality=None,
    image_size=None,
):
    """
    Create a single AI-powered consolidated birthday announcement for one or more people

    Args:
        birthday_people: List of dicts with keys: user_id, username, date, year, date_words, profile
        app: Optional Slack app instance for custom emoji fetching
        include_image: Whether to generate AI image for multiple birthdays
        test_mode: If True, uses lower quality/smaller size to reduce costs for testing
        quality: Override image quality ("low", "medium", "high", or "auto"). If None, uses test_mode logic
        image_size: Override image size ("auto", "1024x1024", "1536x1024", "1024x1536"). If None, defaults to "auto"

    Returns:
        If include_image is True and multiple people: tuple of (message, image_data)
        Otherwise: birthday announcement message string
    """
    if not birthday_people:
        return ""

    if len(birthday_people) == 1:
        # Single birthday - use existing single-person completion function
        person = birthday_people[0]
        try:
            result = completion(
                person["username"],
                person["date_words"],
                person["user_id"],
                person["date"],
                person.get("year"),
                app=app,
                user_profile=person.get("profile"),
                include_image=include_image,
                test_mode=test_mode,
                quality=quality,
                image_size=image_size,
            )

            # Convert single person result to consistent list format
            if include_image and isinstance(result, tuple):
                message, single_image = result
                if single_image:
                    # Add person identification to image metadata for consistency
                    single_image["birthday_person"] = {
                        "user_id": person["user_id"],
                        "username": person["username"],
                        "date": person.get("date"),
                        "year": person.get("year"),
                    }
                    return message, [single_image]  # Return as list for consistency
                else:
                    return message, []  # Empty list if no image
            else:
                return result  # Just message for non-image case

        except Exception as e:
            logger.error(
                f"AI_ERROR: Failed to generate consolidated message for {person['username']}: {e}"
            )
            fallback_message = create_birthday_announcement(
                person["user_id"],
                person["username"],
                person["date"],
                person.get("year"),
            )
            if include_image:
                return fallback_message, []  # Return consistent format
            return fallback_message

    # Multiple birthdays - use AI to create creative consolidated message
    try:
        return _generate_ai_consolidated_message(
            birthday_people, app, include_image, test_mode, quality, image_size
        )
    except Exception as e:
        logger.error(f"AI_ERROR: Failed to generate AI consolidated message: {e}")
        # Fallback to static template for multiple birthdays
        if include_image:
            return (
                _generate_fallback_consolidated_message(birthday_people),
                [],
            )  # Return empty list instead of None
        return _generate_fallback_consolidated_message(birthday_people)


def _generate_ai_consolidated_message(
    birthday_people,
    app=None,
    include_image=False,
    test_mode=False,
    quality=None,
    image_size=None,
):
    """
    Generate AI-powered consolidated birthday message for multiple people

    Args:
        birthday_people: List of birthday person dicts
        app: Optional Slack app instance
        include_image: Whether to generate AI image for multiple birthdays
        test_mode: If True, uses lower quality/smaller size to reduce costs for testing
        quality: Override image quality ("low", "medium", "high", or "auto"). If None, uses test_mode logic
        image_size: Override image size ("auto", "1024x1024", "1536x1024", "1024x1536"). If None, defaults to "auto"

    Returns:
        If include_image is True: tuple of (message, image_data)
        Otherwise: AI-generated consolidated birthday message
    """
    # Prepare birthday people information
    people_info = []
    mentions = []

    for person in birthday_people:
        user_mention = f"<@{person['user_id']}>"
        mentions.append(user_mention)

        age_info = ""
        if person.get("year"):
            age = datetime.now().year - person["year"]
            age_info = f" (turning {age})"

        # Add profile information if available
        profile_info = ""
        if person.get("profile"):
            profile = person["profile"]
            profile_details = []
            if profile.get("title"):
                profile_details.append(f"job: {profile['title']}")
            # if profile.get("timezone_label"):
            #     profile_details.append(f"timezone: {profile['timezone_label']}")
            if profile_details:
                profile_info = f" [{', '.join(profile_details)}]"

        people_info.append(
            f"{person['username']} ({user_mention}){age_info}{profile_info}"
        )

    # Format mentions for use in message
    if len(mentions) == 2:
        mention_text = f"{mentions[0]} and {mentions[1]}"
        count_word = "both"
        relationship = "twins"
    elif len(mentions) == 3:
        mention_text = f"{mentions[0]}, {mentions[1]}, and {mentions[2]}"
        count_word = "all three"
        relationship = "triplets"
    else:
        mention_text = ", ".join(mentions[:-1]) + f", and {mentions[-1]}"
        count_word = f"all {len(mentions)}"
        relationship = f"{len(mentions)}-way birthday celebration"

    # Get current personality configuration
    current_personality_name = get_current_personality_name()

    # Handle random personality selection
    if current_personality_name == "random":
        selected_personality_name = get_random_personality_name()
        personality = BOT_PERSONALITIES.get(
            selected_personality_name, BOT_PERSONALITIES["standard"]
        )
        logger.info(
            f"CONSOLIDATED_RANDOM: Using personality '{selected_personality_name}' for multiple birthdays"
        )
    else:
        selected_personality_name = current_personality_name
        personality = BOT_PERSONALITIES.get(
            selected_personality_name, BOT_PERSONALITIES["standard"]
        )

    # Get birthday facts for personalities that use web search (same logic as single birthdays)
    birthday_facts_text = ""
    personalities_using_web_search = [
        "mystic_dog",
        "time_traveler",
        "superhero",
        "pirate",
        "poet",
        "tech_guru",
        "chef",
        "standard",
    ]

    if selected_personality_name in personalities_using_web_search and birthday_people:
        try:
            # Since all people share the same birthday date, use the first person's date
            shared_birthday_date = birthday_people[0]["date"]  # DD/MM format

            # Get facts formatted for this specific personality
            birthday_facts = get_birthday_facts(
                shared_birthday_date, selected_personality_name
            )

            if birthday_facts and birthday_facts["facts"]:
                # Get birthday facts text from centralized configuration
                from personality_config import get_personality_config

                personality_config = get_personality_config(selected_personality_name)
                facts_template = personality_config.get(
                    "birthday_facts_text",
                    "Incorporate these interesting facts about their shared birthday date: {facts}",
                )
                birthday_facts_text = (
                    f"\n\n{facts_template.format(facts=birthday_facts['facts'])}"
                )

                # Add sources if available
                if birthday_facts["sources"]:
                    sources_text = "\n\nYou may reference where this information came from in a way that fits your personality, without mentioning specific URLs."
                    birthday_facts_text += sources_text

                logger.info(
                    f"CONSOLIDATED_AI: Added {selected_personality_name}-specific facts for shared date {shared_birthday_date}"
                )
        except Exception as e:
            logger.error(
                f"CONSOLIDATED_AI_ERROR: Failed to get birthday facts for {selected_personality_name}: {e}"
            )
            # Continue without facts if there's an error

    # Get emoji instructions and list
    emoji_list = SAFE_SLACK_EMOJIS
    emoji_instruction = "ONLY USE STANDARD SLACK EMOJIS"

    if USE_CUSTOM_EMOJIS and app:
        try:
            from utils.slack_utils import get_all_emojis

            all_emojis = get_all_emojis(app)
            if all_emojis:
                emoji_list = all_emojis
                emoji_instruction = (
                    "You can use both STANDARD SLACK EMOJIS and CUSTOM WORKSPACE EMOJIS"
                )
                logger.info(
                    "CONSOLIDATED_AI: Using custom emojis for consolidated message"
                )
        except Exception as e:
            logger.warning(
                f"CONSOLIDATED_AI: Failed to get custom emojis, using standard: {e}"
            )

    # Build the consolidated prompt based on personality
    system_prompt = _build_consolidated_system_prompt(
        personality, selected_personality_name
    )

    # Create the user prompt with all the birthday information
    user_prompt = f"""Create a consolidated birthday celebration message for multiple people sharing the same birthday!

BIRTHDAY PEOPLE:
{chr(10).join(people_info)}

CRITICAL FORMATTING REQUIREMENTS (MUST FOLLOW EXACTLY):
1. **MENTIONS**: You MUST include these exact mentions in your message: {mention_text}
   - Do NOT change, paraphrase, or modify these mentions
   - Do NOT replace with names or other text
   - These EXACT strings must appear in your response: {mention_text}
2. **NOTIFICATION**: Include <!here> exactly as written to notify active members
3. **LENGTH**: Keep the message to 8-12 lines maximum
4. **EMOJIS**: {emoji_instruction}
5. **AVAILABLE EMOJIS**: {', '.join(emoji_list[:20])}{'...' if len(emoji_list) > 20 else ''}

CREATIVE REQUIREMENTS:
- Make this feel special and unique for {count_word} celebrating together
- Reference the fact that they're birthday {relationship}
- Create something more creative and engaging than a simple announcement
- Include interactive elements or questions for the team
- Make it feel like a celebration, not just an announcement

EXAMPLE STRUCTURE:
"<!here> *Birthday [Relationship]!* 🎉

Happy Birthday {mention_text}! [Continue with creative content...]"{birthday_facts_text}

**IMPORTANT**: The mentions {mention_text} must appear EXACTLY as provided. Generate an amazing consolidated birthday message!"""

    # Make the API call
    try:
        response = client.chat.completions.create(
            model=get_configured_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=800,  # Increased for consolidated messages with multiple mentions and personality content
            temperature=1,  # Higher creativity for multiple birthdays
        )

        message = response.choices[0].message.content.strip()

        # Log token usage for monitoring
        log_chat_completion_usage(response, "CONSOLIDATED_AI", logger)

        # Fix any formatting issues
        message = fix_slack_formatting(message)

        # Post-process to ensure all required mentions are present
        message = _ensure_mentions_present(message, mentions, mention_text)

        # Validate the message contains required elements
        if not _validate_consolidated_message(message, mentions):
            logger.error(
                f"CONSOLIDATED_AI: Message validation failed after post-processing. "
                f"Required mentions: {mentions}. Message length: {len(message)}. "
                f"Message preview: {message[:200]}..."
            )
            logger.warning(
                "CONSOLIDATED_AI: Generated message failed validation, regenerating..."
            )
            raise ValueError("Message validation failed")

        logger.info(
            f"CONSOLIDATED_AI: Successfully generated consolidated message for {len(birthday_people)} people"
        )

        # Generate individual images for each birthday person if requested
        generated_images = []
        if include_image:
            try:
                from utils.image_generator import generate_birthday_image

                logger.info(
                    f"IMAGE: Generating individual birthday images for {len(birthday_people)} people using {selected_personality_name} personality"
                )

                # Generate individual images for each person using consistent personality
                for person in birthday_people:
                    try:
                        person_image = generate_birthday_image(
                            person.get("profile", {}),
                            selected_personality_name,  # Use consistent personality across all images
                            person.get("date"),
                            enable_transparency=False,
                            birthday_message=message,  # Pass the consolidated message for context
                            test_mode=test_mode,
                            quality=quality,
                            image_size=image_size,
                        )

                        if person_image:
                            # Add person identification to image metadata
                            person_image["birthday_person"] = {
                                "user_id": person["user_id"],
                                "username": person["username"],
                                "date": person.get("date"),
                                "year": person.get("year"),
                            }
                            generated_images.append(person_image)
                            logger.info(
                                f"IMAGE: Successfully generated individual image for {person['username']}"
                            )
                        else:
                            logger.warning(
                                f"IMAGE: Failed to generate individual image for {person['username']}"
                            )

                    except Exception as e:
                        logger.error(
                            f"IMAGE_ERROR: Failed to generate individual image for {person['username']}: {e}"
                        )

                logger.info(
                    f"IMAGE: Generated {len(generated_images)} individual birthday images out of {len(birthday_people)} people"
                )

            except Exception as e:
                logger.error(
                    f"IMAGE_ERROR: Failed to generate individual birthday images: {e}"
                )

        # Return tuple if images were requested, otherwise just message
        if include_image:
            return (
                message,
                generated_images,
            )  # Return list of individual images instead of single group image
        return message

    except Exception as e:
        logger.error(f"CONSOLIDATED_AI_ERROR: {e}")
        raise


def _build_consolidated_system_prompt(personality, personality_name):
    """Build system prompt for consolidated birthday messages based on personality"""

    base_prompt = f"""You are {personality['name']}, {personality['description']} for the {TEAM_NAME} workspace.

Your special mission today is to create a CONSOLIDATED birthday celebration message for MULTIPLE people who share the same birthday! This is rare and magical!

PERSONALITY STYLE: {personality['style']}
FORMATTING INSTRUCTION: {personality['format_instruction']}

SLACK FORMATTING RULES:
- Use *bold* (single asterisks) NOT **double asterisks**
- Use _italic_ (single underscores) NOT __double underscores__
- Use <!here> exactly as written to notify active members
- Use provided user mentions exactly as given
- Use :emoji_name: format for emojis

CONSOLIDATED MESSAGE GOALS:
- Celebrate the cosmic coincidence of shared birthdays
- Make it feel like a special event, not just a regular announcement
- Include all birthday people equally
- Create excitement and encourage team participation
- Keep it concise but impactful (8-12 lines max)"""

    # Add personality-specific extensions from centralized configuration
    from personality_config import get_personality_config

    personality_config = get_personality_config(personality_name)
    consolidated_prompt = personality_config.get("consolidated_prompt", "")
    if consolidated_prompt:
        base_prompt += consolidated_prompt

    return base_prompt


def create_consolidated_profile(birthday_people):
    """
    Create a consolidated profile for multiple birthday people image generation

    Args:
        birthday_people: List of birthday person dicts with profile data

    Returns:
        Consolidated profile dict for image generation
    """
    names = []
    titles = []

    for person in birthday_people:
        names.append(person.get("username", "Birthday Person"))
        if person.get("profile") and person["profile"].get("title"):
            titles.append(person["profile"]["title"])

    # Create a consolidated name and title
    if len(names) == 2:
        consolidated_name = f"{names[0]} and {names[1]}"
    elif len(names) == 3:
        consolidated_name = f"{names[0]}, {names[1]}, and {names[2]}"
    else:
        consolidated_name = f"{', '.join(names[:-1])}, and {names[-1]}"

    # Use most common job type or generic description
    if titles:
        consolidated_title = f"team members ({', '.join(set(titles))})"
    else:
        consolidated_title = "team members"

    return {
        "preferred_name": consolidated_name,
        "title": consolidated_title,
        "timezone": "multiple timezones",
    }


def _ensure_mentions_present(message, required_mentions, formatted_mentions):
    """
    Post-process message to ensure all required mentions are present.

    This is a safety net in case the AI doesn't include exact mentions.
    """
    missing_mentions = []

    # Check which mentions are missing
    for mention in required_mentions:
        if mention not in message:
            missing_mentions.append(mention)

    if missing_mentions:
        logger.warning(f"POST_PROCESS: AI missed mentions: {missing_mentions}")

        # Try to intelligently inject missing mentions
        # Look for common patterns where mentions should be

        # Pattern 1: After "Happy Birthday" - most common case
        if "Happy Birthday" in message and not any(
            mention in message for mention in required_mentions
        ):
            message = message.replace(
                "Happy Birthday", f"Happy Birthday {formatted_mentions}"
            )
            logger.info(f"POST_PROCESS: Injected mentions after 'Happy Birthday'")

        # Pattern 2: Look for birthday-related keywords and inject nearby
        elif any(
            keyword in message.lower()
            for keyword in ["birthday", "celebrating", "celebrate"]
        ):
            # Find first birthday-related sentence and try to inject there
            lines = message.split("\n")
            for i, line in enumerate(lines):
                if any(
                    keyword in line.lower()
                    for keyword in ["birthday", "celebrating", "celebrate"]
                ):
                    if not any(mention in line for mention in required_mentions):
                        # Try to inject mentions naturally
                        if "birthday" in line.lower():
                            lines[i] = line.replace(
                                "birthday", f"birthday {formatted_mentions}"
                            )
                        elif "celebrating" in line.lower():
                            lines[i] = line.replace(
                                "celebrating", f"celebrating {formatted_mentions}"
                            )
                        elif "celebrate" in line.lower():
                            lines[i] = line.replace(
                                "celebrate", f"celebrate {formatted_mentions}"
                            )

                        message = "\n".join(lines)
                        logger.info(
                            f"POST_PROCESS: Injected mentions in birthday-related line"
                        )
                        break

        # Pattern 3: Last resort - add mentions at the beginning after <!here>
        else:
            if "<!here>" in message:
                message = message.replace(
                    "<!here>", f"<!here>\n\nHappy Birthday {formatted_mentions}!"
                )
                logger.info(f"POST_PROCESS: Added mentions after <!here> as fallback")
            else:
                # Ultimate fallback - prepend mentions
                message = f"Happy Birthday {formatted_mentions}!\n\n{message}"
                logger.info(f"POST_PROCESS: Prepended mentions as ultimate fallback")

    return message


def _validate_consolidated_message(message, required_mentions):
    """Validate that consolidated message contains all required elements"""
    validation_errors = []

    # Check for required mentions
    missing_mentions = []
    for mention in required_mentions:
        if mention not in message:
            missing_mentions.append(mention)

    if missing_mentions:
        validation_errors.append(f"Missing mentions: {missing_mentions}")
        logger.warning(f"VALIDATION: Missing required mentions: {missing_mentions}")

    # Check for channel notification
    if "<!here>" not in message:
        validation_errors.append("Missing <!here> notification")
        logger.warning("VALIDATION: Missing <!here> notification")

    # Check minimum length
    if len(message.strip()) < 50:
        validation_errors.append(
            f"Message too short ({len(message.strip())} chars, need 50+)"
        )
        logger.warning(
            f"VALIDATION: Message too short ({len(message.strip())} characters)"
        )

    # If there are validation errors, log a summary
    if validation_errors:
        logger.error(
            f"VALIDATION_SUMMARY: {len(validation_errors)} error(s): {'; '.join(validation_errors)}"
        )
        return False

    logger.info("VALIDATION: All requirements met - message validated successfully")
    return True


def _generate_fallback_consolidated_message(birthday_people):
    """Generate fallback consolidated message when AI fails"""
    mentions = [f"<@{person['user_id']}>" for person in birthday_people]

    if len(mentions) == 2:
        mention_text = f"{mentions[0]} and {mentions[1]}"
        title = "Birthday Twins"
    elif len(mentions) == 3:
        mention_text = f"{mentions[0]}, {mentions[1]}, and {mentions[2]}"
        title = "Birthday Triplets"
    else:
        mention_text = ", ".join(mentions[:-1]) + f", and {mentions[-1]}"
        title = f"Birthday {len(mentions)}-Celebration"

    # Simple but elegant fallback
    message = f":star2: *{title} Alert!* :star2:\n\n"
    message += f"<!here> What are the odds?! {mention_text} are all celebrating birthdays today!\n\n"
    message += f"This calls for an extra special celebration! :birthday: :tada:\n\n"
    message += f"Let's make their shared special day absolutely amazing! :sparkles:"

    logger.info(
        f"FALLBACK: Generated template consolidated message for {len(birthday_people)} people"
    )
    return message


def generate_birthday_image_title(
    name,
    personality="standard",
    user_profile=None,
    birthday_message=None,
    is_multiple_people=False,
):
    """
    Generate a funny, personalized title for birthday image uploads using OpenAI API

    Args:
        name: Person's name or "Alice and Bob" for multiple people
        personality: Bot personality for styling the title
        user_profile: Optional user profile data for personalization
        birthday_message: Optional birthday message for context
        is_multiple_people: Whether this is for multiple birthday people

    Returns:
        AI-generated title string, or fallback title if AI fails
    """
    try:
        # Get personality-specific title prompt
        from personality_config import get_personality_config

        personality_config = get_personality_config(personality)
        title_prompt_template = personality_config.get("image_title_prompt")

        if not title_prompt_template:
            # Fallback to standard personality if no title prompt found
            standard_config = get_personality_config("standard")
            title_prompt_template = standard_config.get("image_title_prompt", "")

        # Extract context from user profile
        title_context = ""
        if user_profile and user_profile.get("title"):
            title_context = f", who works as a {user_profile['title']}"

        # Format the prompt
        formatted_prompt = title_prompt_template.format(
            name=name,
            title_context=title_context,
            multiple_context=(
                " This is for multiple people celebrating together!"
                if is_multiple_people
                else ""
            ),
        )

        logger.info(f"TITLE_GEN: Generating AI title for {name} in {personality} style")

        # Generate title using OpenAI with name validation and retry logic
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=get_configured_model(),
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a creative title generator for birthday image uploads. Generate funny, witty, and personalized titles that are 2-8 words long. CRITICAL: You MUST include the person's name(s) prominently in every title. Be creative but keep it workplace appropriate. Do not include emojis - they will be added separately.",
                        },
                        {"role": "user", "content": formatted_prompt},
                    ],
                    max_completion_tokens=200,
                    temperature=1,  # Higher creativity for titles
                )

                # Log token usage for monitoring
                log_chat_completion_usage(response, "IMAGE_TITLE_GEN", logger)

                ai_title = response.choices[0].message.content.strip()

                # Clean up the title (remove quotes, extra punctuation)
                ai_title = ai_title.strip("\"'").rstrip(".!?")

                # Validate title length
                if len(ai_title) > 100 or len(ai_title) < 3:
                    if attempt < max_retries:
                        logger.warning(
                            f"TITLE_GEN: Title length invalid ({len(ai_title)} chars), retrying..."
                        )
                        continue
                    raise ValueError(
                        f"Title length invalid: {len(ai_title)} characters"
                    )

                # Validate that the title contains the name(s) - critical for personalization
                name_validation_passed = _validate_title_contains_names(
                    ai_title, name, is_multiple_people
                )

                if not name_validation_passed:
                    if attempt < max_retries:
                        logger.warning(
                            f"TITLE_GEN: Title missing names, retrying... (attempt {attempt + 1})"
                        )
                        continue
                    else:
                        logger.warning(
                            f"TITLE_GEN: Title still missing names after {max_retries} retries, using anyway: '{ai_title}'"
                        )

                logger.info(
                    f"TITLE_GEN: Successfully generated title for {name}: '{ai_title}'"
                )
                return ai_title

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"TITLE_GEN: API error on attempt {attempt + 1}, retrying: {e}"
                    )
                    continue
                else:
                    # If all retries failed, re-raise the exception to trigger fallback
                    raise e

    except Exception as e:
        logger.error(f"TITLE_GEN_ERROR: Failed to generate AI title for {name}: {e}")
        # Fallback to personality-appropriate static title
        return get_fallback_title(name, personality, is_multiple_people)


def _format_multiple_names(name):
    """
    Format multiple names for title display (e.g., "Alice & Bob" or "Alice, Bob & Charlie")

    Args:
        name: Full name string like "Alice Johnson and Bob Smith"

    Returns:
        Formatted names like "Alice & Bob"
    """
    import re

    # Handle common name formats more carefully
    # First, replace ", and " with ", " to normalize
    normalized_name = re.sub(r",\s*and\s+", ", ", name)
    # Then split on commas and "and"
    names_parts = re.split(r"\s*,\s*|\s+and\s+", normalized_name)

    # Extract first names only
    first_names = []
    for part in names_parts:
        part = part.strip()
        if part:  # Skip empty parts
            first_name = part.split()[0]
            # Filter out any remaining connecting words
            if (
                first_name
                and len(first_name) > 1
                and first_name.lower() not in ["and", "or", "the"]
            ):
                first_names.append(first_name)

    # Format based on count
    if len(first_names) == 2:
        return f"{first_names[0]} & {first_names[1]}"
    elif len(first_names) == 3:
        return f"{first_names[0]}, {first_names[1]} & {first_names[2]}"
    elif len(first_names) > 3:
        return f"{first_names[0]}, {first_names[1]} & {len(first_names)-2} others"
    else:
        # Fallback - shouldn't happen but just in case
        return name.split()[0] if name else "Team"


def _validate_title_contains_names(title, name, is_multiple_people):
    """
    Validate that the AI-generated title contains the person's name(s)

    Args:
        title: The AI-generated title to validate
        name: The name(s) to check for (e.g., "Alice" or "Alice and Bob")
        is_multiple_people: Whether this is for multiple people

    Returns:
        bool: True if title contains names, False otherwise
    """
    title_lower = title.lower()

    if is_multiple_people:
        # For multiple people, extract individual names
        # Handle formats like "Alice and Bob", "Alice, Bob, and Charlie"
        import re

        # Handle common name formats more carefully
        # First, replace ", and " with ", " to normalize
        normalized_name = re.sub(r",\s*and\s+", ", ", name)
        # Then split on commas and "and"
        names_parts = re.split(r"\s*,\s*|\s+and\s+", normalized_name)
        individual_names = []

        for part in names_parts:
            part = part.strip()
            if part:  # Skip empty parts
                # Extract first names (assume first word is the first name)
                first_name = part.split()[0]
                # Filter out any remaining connecting words
                if (
                    first_name
                    and len(first_name) > 1
                    and first_name.lower() not in ["and", "or", "the"]
                ):
                    individual_names.append(first_name.lower())

        # Check if at least one name appears in the title
        names_found = sum(
            1 for name_part in individual_names if name_part in title_lower
        )

        # For multiple people, we want at least 50% of names to appear, or at least 1 name
        required_names = max(1, len(individual_names) // 2)
        return names_found >= required_names

    else:
        # For single person, extract first name
        first_name = name.strip().split()[0].lower()
        if len(first_name) > 1:  # Avoid single letters
            return first_name in title_lower

    return True  # If we can't validate properly, assume it's okay


def get_fallback_title(name, personality="standard", is_multiple_people=False):
    """
    Generate fallback titles when AI generation fails

    Args:
        name: Person's name
        personality: Bot personality
        is_multiple_people: Whether this is for multiple people

    Returns:
        Fallback title string
    """
    # Personality-specific fallback titles
    fallback_titles = {
        "mystic_dog": [
            f"{name}'s Cosmic Birthday Vision",
            f"The Stars Aligned for {name}",
            f"Mystical Birthday Prophecy",
            f"{name}'s Celestial Celebration",
        ],
        "superhero": [
            f"Captain {name}'s Birthday Mission",
            f"Super Birthday Powers Activated",
            f"{name} Saves the Day Again",
            f"Birthday Hero in Action",
        ],
        "pirate": [
            f"Cap'n {name}'s Birthday Treasure",
            f"Ahoy! {name}'s Special Day",
            f"Birthday Bounty for {name}",
            f"Sailing into Another Year",
        ],
        "tech_guru": [
            f"{name}.birthday() Successfully Executed",
            f"Deploying Birthday v{random.randint(1,9)}.0",
            f"Birthday Algorithm Optimized",
            f"{name}'s Annual System Update",
        ],
        "chef": [
            f"{name}'s Birthday Recipe",
            f"Master Chef {name}'s Special Day",
            f"Birthday Feast in Progress",
            f"Cooking Up Birthday Magic",
        ],
        "poet": [
            f"Ode to {name}'s Birthday",
            f"Birthday Verses for {name}",
            f"A Poetic Birthday Celebration",
            f"{name}'s Birthday Sonnet",
        ],
        "time_traveler": [
            f"{name}'s Temporal Birthday Anomaly",
            f"Birthday Timeline Established",
            f"Celebrating Across Dimensions",
            f"{name}'s Space-Time Birthday",
        ],
        "standard": [
            f"{name}'s Amazing Birthday",
            f"Birthday Celebration Mode",
            f"Special Day for {name}",
            f"Another Year of Awesome",
        ],
    }

    # Modify for multiple people - include names!
    if is_multiple_people:
        # Create smart name formatting for multiple people
        formatted_names = _format_multiple_names(name)

        if personality == "mystic_dog":
            return f"{formatted_names}'s Cosmic Birthday Convergence"
        elif personality == "superhero":
            return f"{formatted_names}'s Super Birthday Team Assembly"
        elif personality == "pirate":
            return f"{formatted_names}'s Birthday Crew Celebration"
        elif personality == "tech_guru":
            return f"{formatted_names}'s Multi-User Birthday Deployment"
        elif personality == "chef":
            return f"{formatted_names}'s Group Birthday Feast"
        elif personality == "poet":
            return f"{formatted_names}'s Birthday Harmony in Verse"
        elif personality == "time_traveler":
            return f"{formatted_names}'s Synchronized Birthday Timeline"
        else:
            return f"{formatted_names}'s Birthday Celebration Squad"

    # Single person fallback
    personality_titles = fallback_titles.get(personality, fallback_titles["standard"])
    return random.choice(personality_titles)


def test_fallback_messages(name="Test User", user_id="U123456789"):
    """
    Test all fallback messages with a given name and user ID

    Args:
        name: Name to use in the messages
        user_id: User ID to use in mentions
    """
    print(f"\n=== Testing Fallback Messages for {name} (ID: {user_id}) ===\n")

    user_mention = f"{get_user_mention(user_id)}"

    for i, message in enumerate(BACKUP_MESSAGES, 1):
        formatted = message.replace("{name}", user_mention)
        print(f"Message {i}:")
        print(f"{formatted}\n")
        print("-" * 60)


def test_announcement(
    name="Test User", user_id="U123456789", birth_date="14/04", birth_year=1990
):
    """
    Test the birthday announcement format
    """
    print(f"\n=== Testing Birthday Announcement for {name} (ID: {user_id}) ===\n")

    announcement = create_birthday_announcement(
        user_id, name, birth_date, birth_year, test_mode=False, quality=None
    )
    print(announcement)
    print("\n" + "-" * 60)


def test_consolidated_announcement():
    """
    Test the AI-powered consolidated birthday announcement for multiple people
    """
    print(f"\n=== Testing AI-Powered Consolidated Birthday Announcements ===\n")

    # Test with 2 people (twins)
    birthday_twins = [
        {
            "user_id": "U1234567890",
            "username": "Alice Johnson",
            "date": "14/04",
            "year": 1990,
            "date_words": "14th of April, 1990",
        },
        {
            "user_id": "U0987654321",
            "username": "Bob Smith",
            "date": "14/04",
            "year": 1985,
            "date_words": "14th of April, 1985",
        },
    ]

    # Test with 3 people (triplets)
    birthday_triplets = [
        {
            "user_id": "U1111111111",
            "username": "Charlie Brown",
            "date": "25/12",
            "year": None,
            "date_words": "25th of December",
        },
        {
            "user_id": "U2222222222",
            "username": "Diana Prince",
            "date": "25/12",
            "year": 1995,
            "date_words": "25th of December, 1995",
        },
        {
            "user_id": "U3333333333",
            "username": "Ethan Hunt",
            "date": "25/12",
            "year": 1988,
            "date_words": "25th of December, 1988",
        },
    ]

    test_personalities = ["standard", "mystic_dog", "superhero", "pirate", "tech_guru"]

    for personality in test_personalities:
        print(f"\n{'='*20} TESTING {personality.upper()} PERSONALITY {'='*20}")

        # Set personality for testing
        from config import set_current_personality

        set_current_personality(personality)

        print(f"\n--- Birthday Twins with {personality} personality ---")
        try:
            twins_message = create_consolidated_birthday_announcement(
                birthday_twins, test_mode=False, quality=None, image_size=None
            )
            print(twins_message)
        except Exception as e:
            print(f"ERROR: {e}")

        print(f"\n--- Birthday Triplets with {personality} personality ---")
        try:
            triplets_message = create_consolidated_birthday_announcement(
                birthday_triplets, test_mode=False, quality=None, image_size=None
            )
            print(triplets_message)
        except Exception as e:
            print(f"ERROR: {e}")

        print("\n" + "-" * 80)

    print("\nConsolidated announcement testing completed!")


def main():
    """Main function for testing the completion function with placeholder data"""
    parser = argparse.ArgumentParser(description="Test the birthday message generator")
    parser.add_argument("--name", default="John Doe", help="Name of the person")
    parser.add_argument("--user-id", default="U1234567890", help="Slack user ID")
    parser.add_argument(
        "--date", default="25th of December", help="Birthday date in words"
    )
    parser.add_argument(
        "--birth-date", default="25/12", help="Birth date in DD/MM format"
    )
    parser.add_argument(
        "--birth-year", default=1990, type=int, help="Birth year (optional)"
    )
    parser.add_argument(
        "--fallback", action="store_true", help="Test fallback messages instead of API"
    )
    parser.add_argument(
        "--announcement", action="store_true", help="Test birthday announcement format"
    )
    parser.add_argument(
        "--consolidated",
        action="store_true",
        help="Test AI-powered consolidated birthday announcements",
    )
    parser.add_argument(
        "--personality",
        choices=[
            "standard",
            "mystic_dog",
            "poet",
            "tech_guru",
            "chef",
            "superhero",
            "time_traveler",
            "pirate",
            "custom",
            "random",
        ],
        help="Bot personality to use for testing",
    )

    args = parser.parse_args()

    # Set personality for testing if specified
    if args.personality:
        from config import (
            set_current_personality,
        )  # Import here to prevent circular imports

        set_current_personality(args.personality)
        print(f"Using {args.personality} personality for testing")

    # Configure console logging for direct testing
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - [%(levelname)s] %(message)s")
    )

    # Create a separate logger just for command-line testing
    test_logger = logging.getLogger("birthday_bot.test")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(console_handler)

    test_logger.info(f"TEST: === Birthday Message Generator Test ===")
    test_logger.info(
        f"Current Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    current_model = get_configured_model()
    test_logger.info(f"Model: {current_model}")
    test_logger.info(
        f"Testing with: Name='{args.name}', User ID='{args.user_id}', Date='{args.date}'"
    )

    current_personality = get_current_personality_name()
    if current_personality == "random":
        test_logger.info(
            f"Using random personality mode (will select a random personality for each message)"
        )
    else:
        test_logger.info(f"Personality: {current_personality}")

    print("-" * 60)

    if args.fallback:
        test_fallback_messages(args.name, args.user_id)
    elif args.announcement:
        test_announcement(args.name, args.user_id, args.birth_date, args.birth_year)
    elif args.consolidated:
        test_consolidated_announcement()
    else:
        try:
            message = completion(
                args.name, args.date, args.user_id, args.birth_date, args.birth_year
            )
            print("\nGenerated Message:")
            print("-" * 60)
            print(message)
            print("-" * 60)
            print("\nMessage generated successfully!")
        except Exception as e:
            print(f"\nError generating message: {e}")
            print("\nTrying fallback message instead:")

            # Generate a fallback message manually for testing
            random_message = random.choice(BACKUP_MESSAGES)
            user_mention = f"{get_user_mention(args.user_id)}"
            formatted_message = random_message.replace("{name}", user_mention)

            print("-" * 60)
            print(formatted_message)
            print("-" * 60)

    print("\nTest completed!")


if __name__ == "__main__":
    main()
