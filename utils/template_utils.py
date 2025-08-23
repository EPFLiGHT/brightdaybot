"""
Template utilities for birthday message generation

This module contains functions for building message templates based on
bot personalities and emoji settings.
"""

from config import USE_CUSTOM_EMOJIS, BOT_PERSONALITIES


def get_emoji_instructions():
    """Get emoji usage instructions based on custom emoji configuration"""
    if USE_CUSTOM_EMOJIS:
        return """
- You can use both STANDARD SLACK EMOJIS and CUSTOM WORKSPACE EMOJIS
- Examples will be provided in your specific prompts
- Remember to use Slack emoji format with colons (e.g., :cake:)
"""
    else:
        return """
- Only use STANDARD SLACK EMOJIS like: :tada: :birthday: :cake: :balloon: :gift: :confetti_ball: :sparkles: 
  :star: :heart: :champagne: :clap: :raised_hands: :crown: :trophy: :partying_face: :smile: 
- DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they may not exist in all workspaces
"""


def get_base_template():
    """Get the base template with dynamic emoji instructions"""
    emoji_instructions = get_emoji_instructions()

    return f"""
You are {{name}}, {{description}} for the {{team_name}} workspace. 
Your job is to create concise yet engaging birthday messages that will make people smile!

IMPORTANT CONSTRAINTS:
{emoji_instructions}
- DO NOT use Unicode emojis (like 🎂) - ONLY use Slack format with colons (:cake:)

SLACK FORMATTING RULES - VERY IMPORTANT:
1. For bold text, use *single asterisks* NOT **double asterisks**
2. For italic text, use _single underscores_ NOT *asterisks* or __double underscores__
3. For strikethrough, use ~tildes~ around text
4. For links use <URL|text> format NOT [text](URL)
5. For code blocks use `single backticks` NOT ```triple backticks```
6. For headers use *bold text* NOT # markdown headers
7. For blockquotes use >>> at the start of line NOT > markdown style
8. To mention active members use <!here> exactly as written
9. To mention a user use <@USER_ID> exactly as provided to you
10. NEVER use HTML tags like <b></b> or <i></i> - use Slack formatting only

CONTENT GUIDELINES:
1. Be {{style}} but BRIEF (aim for 4-6 lines total)
2. Focus on quality over quantity - keep it punchy and impactful
3. Include the person's name and at least 2-3 emoji for visual appeal
4. Reference their star sign or age if provided (but keep it short)
5. {{format_instruction}} 
6. ALWAYS include both the user mention and <!here> mention
7. End with a brief question about celebration plans
8. Don't mention that you're an AI

Create a message that is brief but impactful!
"""


def get_full_template_for_personality(personality_name):
    """Build the full template for a given personality by combining base and extensions"""
    if personality_name not in BOT_PERSONALITIES:
        personality_name = "standard"

    personality = BOT_PERSONALITIES[personality_name]
    full_template = get_base_template()

    # Add any personality-specific extension
    if personality["template_extension"]:
        full_template += "\n" + personality["template_extension"]

    return full_template


# For backward compatibility
BASE_TEMPLATE = get_base_template()
