from openai import OpenAI
import logging
import os
import random
import argparse
import sys
from datetime import datetime

from config import get_logger
from config import (
    BOT_PERSONALITY,
    BOT_PERSONALITIES,
    TEAM_NAME,
    CUSTOM_BOT_NAME,
    CUSTOM_BOT_DESCRIPTION,
    CUSTOM_BOT_STYLE,
    CUSTOM_FORMAT_INSTRUCTION,
)

from utils.date_utils import get_star_sign
from utils.slack_utils import SAFE_SLACK_EMOJIS

logger = get_logger("llm")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


# Birthday announcement formats
BIRTHDAY_INTROS = [
    ":birthday: ATTENTION WONDERFUL HUMANS! :tada:",
    ":loudspeaker: :sparkles: SPECIAL ANNOUNCEMENT FOR EVERYONE! :sparkles: :loudspeaker:",
    ":rotating_light: BIRTHDAY ALERT! BIRTHDAY ALERT! :rotating_light:",
    ":mega: HEY <!channel>! STOP WHAT YOU'RE DOING! :mega:",
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
    80: "80 years of making the world a better place! That deserves a standing ovation!",
    90: "90 years strong! You should be studied by scientists to discover your secret!",
    100: "A CENTURY! You've officially unlocked legendary status!",
}


def get_current_personality():
    """Get the currently configured bot personality settings"""
    personality = BOT_PERSONALITIES.get(BOT_PERSONALITY, BOT_PERSONALITIES["standard"])

    # If using custom personality, override with custom settings
    if BOT_PERSONALITY == "custom":
        personality["name"] = CUSTOM_BOT_NAME
        personality["description"] = CUSTOM_BOT_DESCRIPTION
        personality["style"] = CUSTOM_BOT_STYLE
        personality["format_instruction"] = CUSTOM_FORMAT_INSTRUCTION

    return personality


def build_template():
    """Build the prompt template based on current personality settings"""
    personality = get_current_personality()

    template = [
        {
            "role": "system",
            "content": f"""
        You are {personality["name"]}, {personality["description"]} for the {TEAM_NAME} workspace. 
        Your job is to create lively, humorous birthday messages that will make people smile!
        
        IMPORTANT CONSTRAINTS:
        - Only use STANDARD SLACK EMOJIS like: :tada: :birthday: :cake: :balloon: :gift: :confetti_ball: :sparkles: 
          :star: :heart: :champagne: :clap: :raised_hands: :crown: :trophy: :partying_face: :smile: 
          DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they may not exist in all workspaces
        - DO NOT use Unicode emojis (like 🎂) - ONLY use Slack format with colons (:cake:)
        
        When writing your message:
        1. Be {personality["style"]}
        2. Use plenty of Slack formatting (bold, italics) and STANDARD Slack emojis only; don't use double asterisks for bold, use *text* instead
        3. Include fun wordplay, puns, or jokes based on their name if possible
        4. Reference their star sign with a humorous "prediction" or trait if provided
        5. If age is provided, include a funny age-related joke or milestone
        6. {personality["format_instruction"]}
        7. Always address the entire channel with <!channel> to notify everyone
        8. Include a question about how they plan to celebrate
        9. Don't mention that you're an AI

        Slack formatting examples:
        - Bold: *text*  
        - Italic: _text_
        - Strikethrough: ~text~
        
        Create a message that takes up space and stands out in a busy Slack channel!
        """,
        }
    ]

    # Add special instructions for mystic dog personality
    if BOT_PERSONALITY == "mystic_dog":
        template[0][
            "content"
        ] += """
        
        Your birthday message should follow this structure:
        1. Start with "Ludo the Mystic Birthday Dog submits his birthday wishes to @[name]"
        2. Request gif assistance from the community
        3. Provide a mystical forecast for the year ahead that incorporates:
           - Their star sign and planetary alignments
           - Numerological significance of their age/birthday
           - A spirit animal or guide for their coming year
           - References to machine learning theory or other scientific concepts reinterpreted mystically
        4. End with an enigmatic but hopeful conclusion
        """

    return template


# Replace the existing TEMPLATE with the dynamic version
def get_template():
    """Get the current template based on personality configuration"""
    return build_template()


def create_birthday_announcement(
    user_id, name, date_str, birth_year=None, star_sign=None
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
    # Parse the date
    try:
        day, month = map(int, date_str.split("/"))
        date_obj = datetime(2025, month, day)  # Using current year just for formatting
        month_name_str = date_obj.strftime("%B")
        day_num = date_obj.day
    except:
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

<@{user_id}>
{emoji1} Birthday Extraordinaire {emoji2}
{month_name_str} {day_num}{age_text}
{star_sign_text}

{f"✨ {age_fact} ✨" if age_fact else ""}

---
{call_to_action}

{ending}

<!channel> Let's celebrate together!
"""
    return message.strip()


# Backup birthday messages for fallback if the API fails
BACKUP_MESSAGES = [
    """
:birthday: HAPPY BIRTHDAY {name}!!! :tada:

<!channel> We've got a birthday to celebrate! 

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
:rotating_light: ATTENTION <!channel> :rotating_light:

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

<!channel> Everyone drop what you're doing because...

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

:loudspeaker: <!channel> Announcement! :loudspeaker:

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

<!channel> HEY EVERYONE! 

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
) -> str:
    """
    Generate an enthusiastic, fun birthday message using OpenAI or fallback messages

    Args:
        name: User's name or Slack ID
        date: User's birthday in natural language format (e.g. "2nd of April")
        user_id: User's Slack ID for mentioning them with @
        birth_date: Original birth date in DD/MM format (for star sign)
        birth_year: Optional birth year for age-related content

    Returns:
        Fun birthday message
    """
    # Get the dynamic template based on current configuration
    template = get_template()

    # Create user mention format if user_id is provided
    user_mention = f"<@{user_id}>" if user_id else name

    # Get star sign if possible
    star_sign = get_star_sign(birth_date) if birth_date else None
    star_sign_text = f" Their star sign is {star_sign}." if star_sign else ""

    # Age information
    age_text = ""
    if birth_year:
        age = datetime.now().year - birth_year
        age_text = f" You're turning {age} today!"

    # Format list of safe emojis for the prompt
    safe_emoji_examples = ", ".join(random.sample(SAFE_SLACK_EMOJIS, 20))

    # Get current personality info for the request
    personality = get_current_personality()

    template.append(
        {
            "role": "user",
            "content": f"""
            {name}'s birthday is on {date}.{star_sign_text}{age_text} Please write them a fun, enthusiastic birthday message for a workplace Slack channel.
            
            IMPORTANT REQUIREMENTS:
            1. Include their Slack mention "{user_mention}" somewhere in the message
            2. Make sure to address the entire channel with <!channel> to notify everyone
            3. Create a message that's lively and engaging with good structure and flow
            4. ONLY USE STANDARD SLACK EMOJIS like: {safe_emoji_examples}
            5. DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they won't work
            6. Remember to use Slack emoji format with colons (e.g., :cake:), not Unicode emojis (e.g., 🎂)
            7. Your name is {personality["name"]} and you are {personality["description"]}
            
            Today is {datetime.now().strftime('%Y-%m-%d')}.
            """,
        }
    )

    try:
        logger.info(
            f"AI: Requesting birthday message for {name} ({date}) using {BOT_PERSONALITY} personality"
        )
        reply = (
            client.chat.completions.create(model=MODEL, messages=template)
            .choices[0]
            .message.content
        )

        logger.info(f"AI: Successfully generated birthday message")
        return reply
    except Exception as e:
        logger.error(f"AI_ERROR: Failed to generate completion: {e}")

        # Use one of our backup messages if the API call fails
        random_message = random.choice(BACKUP_MESSAGES)

        # Replace {name} with user mention if available
        mention_text = user_mention if user_id else name
        formatted_message = random_message.replace("{name}", mention_text)

        logger.info(f"AI: Used fallback birthday message")
        return formatted_message


def test_fallback_messages(name="Test User", user_id="U123456789"):
    """
    Test all fallback messages with a given name and user ID

    Args:
        name: Name to use in the messages
        user_id: User ID to use in mentions
    """
    print(f"\n=== Testing Fallback Messages for {name} (ID: {user_id}) ===\n")

    user_mention = f"<@{user_id}>"

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

    announcement = create_birthday_announcement(user_id, name, birth_date, birth_year)
    print(announcement)
    print("\n" + "-" * 60)


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
        "--personality",
        choices=["standard", "mystic_dog", "custom"],
        help="Bot personality to use for testing",
    )

    args = parser.parse_args()

    # Set personality for testing if specified
    global BOT_PERSONALITY
    if args.personality:
        BOT_PERSONALITY = args.personality
        print(f"Using {BOT_PERSONALITY} personality for testing")

    # Configure console logging for direct testing
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - [%(levelname)s] %(message)s")
    )

    # Create a separate logger just for command-line testing
    test_logger = logging.getLogger("birthday_bot.test")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(console_handler)

    test_logger.info(f"=== Birthday Message Generator Test ===")
    test_logger.info(
        f"Current Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    test_logger.info(f"Model: {MODEL}")
    test_logger.info(
        f"Testing with: Name='{args.name}', User ID='{args.user_id}', Date='{args.date}'"
    )
    test_logger.info(f"Personality: {BOT_PERSONALITY}")
    print("-" * 60)

    if args.fallback:
        test_fallback_messages(args.name, args.user_id)
    elif args.announcement:
        test_announcement(args.name, args.user_id, args.birth_date, args.birth_year)
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
            user_mention = f"<@{args.user_id}>"
            formatted_message = random_message.replace("{name}", user_mention)

            print("-" * 60)
            print(formatted_message)
            print("-" * 60)

    print("\nTest completed!")


if __name__ == "__main__":
    main()
