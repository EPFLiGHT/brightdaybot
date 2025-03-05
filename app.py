from dotenv import load_dotenv
import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
from datetime import datetime, timezone, timedelta
from calendar import month_name
import logging
from slack_sdk.errors import SlackApiError

#loads API keys into os.environ from the .env file.
# Make sure that the .env file contains the correct Slack API keys
load_dotenv()
birthday_channel = os.getenv("BIRTHDAY_CHANNEL_ID")
logging.basicConfig(filename="app.log", level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Logging started")

#initializes Slack app
app = App()
logger.log(msg="app initialized", level=logging.INFO)
tom_time = datetime.now(tz=timezone.utc)
#this would be where you mess with what time the message gets sent at the earliest (but the time would coincide with the first message in a public channel)
tom_time = datetime(year=tom_time.year, month=tom_time.month, day=tom_time.day, hour=8, minute=0, second=0, microsecond=0) - timedelta(days=1)

#CONFIGURE your birthday message here
def daily(moment) -> None:
    '''
    all once-daily tasks

    Checks birthdays.txt list for any dates matching today, and if so, sends a happy birthday message.

    :param moment: datetime object, the current moment
    '''
    logger.log(msg=f"daily task, {moment}", level=logging.INFO)
    date = moment.strftime("%d/%m")
    lines = []
    try:
        with open("birthdays.txt", "r") as birthdays:
            lines = birthdays.readlines()
    except FileNotFoundError:
        logger.log(msg=f"birthdays.txt file not found", level=logging.ERROR)
        pass
    for line in lines:
        if line.split(",")[1].strip() == date:
            user = line.split(",")[0]
            send_im(
                message=f"Happy Birthday <@{user}>!!! \n \n <!channel>",
                channel=birthday_channel,
            )
    return

@app.event("message")
def handle_message(body, say = None):
    '''
    Handles ALL message events. Ignores anything that isn't an IM for now.
    We can add more functionality here for IMs.
    For channel messages, use the app mentioned event instead if you want to add functionality.
    '''
    checkTime() #leave this in, it allows daily tasks to work properly.
    #If the message is not from a user in a direct message channel (im)
    if body['event']['channel_type'] != 'im':
        return

    text = body['event']['text'].lower()
    user = body['event']['user']

    #remove command,allows the user to remove their birthday from the bot's record
    if "remove" in text:
        removed = remove_birthday(user)
        if removed:
            say("Birthday removed from records successfully")
        else:
            say("Birthday not found in record, please ask the administrator of the bot to manually delete the record if you believe it exists")
        return

    #if it's not a remove command, assume it is an attempt to add their own birthday
    date = extract_date(text)

    if date == "no_date":
        say("No date found in your message. Please include your birthday in the format DD/MM")
        return

    if date == "invalid_date":
        say("Invalid date. Please include your birthday in the format DD/MM")
        return

    date_words = date_to_words(date)
    updated = save_birthday(date, user)

    if updated:
        say(f"Birthday updated to {date_words}, if this is incorrect, please try again with the corrected date in the format DD/MM")
        return
    say(f"{date_words} added to record as your birthday, if this is incorrect, please try again with the corrected date in the format DD/MM. If you'd like to remove your birthday from our record, please send us a message with the word 'remove' in it.")
    return

@app.event("team_join")
def handle_team_join(body, say):
    '''
    Triggered when any new member joins our slack workspace
    Sends them a message asking them to tell us their birthday
    Also sends them an invite to the birthday channel

    TODO: This has NOT been tested and might be buggy and might cause a crash, I don't know how to test it unfortunately.
    '''
    logger.log(msg=f"team_join event: {body['event']}", level=logging.INFO)
    checkTime() #leave this in, allows daily tasks to work properly.
    user = body['event']['user']
    send_im(
        message=f"Hello <@{user}>! Welcome to the team. I'm brightdaybot, I'm in charge of remembering everyone's birthdays!.",
        channel=user
    )
    send_im(
        message=f"I'm going to be sending you an invite to join the birthday channel, where we celebrate everyone's birthdays!.",
        channel=user
    )

    try:
        app.client.conversations_invite(channel=birthday_channel, users=[user])
    except SlackApiError as e:
        logger.error(f"Slack API error: {e}")

    send_im(
        message="""Also, in this conversation, please send me your birthday in the format DD/MM so I can remember it for you! \n
                If you'd ever like to remove it in the future, just send me a message with the word "remove" in it.
        """,
        channel=user
    )

#Helper functions:

#Helper functions for adding and removing birthdays:

def extract_date(message: str) -> str:
    """
    extracts the first found date from a user's message

    :param message: str, entire message sent by user
    :return: date: str, date in format DD/MM, ready to be stored if message contains valid date, else:
    "no date found" if there is not matched pattern, "invalid date" if the DD/MM is not a possible date in a year
    """

    match = re.search(r'\b(\d{2}/\d{2})(?:/\d{4})?\b', message)
    if match:
        date = match.group(1)
        try:
            datetime.strptime(date, "%d/%m")
            return date
        except:
            logger.error(f"Could not parse date from message: {message}, led to invalid_date")
            return "invalid_date"
    logger.error(f"Could not parse date from message: {message}, led to no_date")
    return "no_date"

def date_to_words(date: str) -> str:
    """
    converts date in DD/MM to date in words, for display to user

    :param date: str, date in format DD/MM
    :return: str, date in words (e.g. "Fifth of July")
    """

    # Parse the date string
    date = datetime.strptime(date, "%d/%m")

    # Convert day to ordinal words
    day = date.day
    if 11 <= day <= 13:
        day_str = f"{day}th"
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        day_str = f"{day}{suffix}"

    # Get the month name
    month = month_name[date.month]

    # Combine day and month
    return f"{day_str} of {month}"

def remove_birthday(user: str) -> bool:
    """
    removes user's birthday from the record, if it is there

    :param user: str, user's ID
    :return: bool, True if user's birthday was removed, False if user's birthday was not found in records
    """
    lines = []
    newLines = []
    removed = False

    try:
        with open("birthdays.txt", "r") as birthdays:
            lines = birthdays.readlines()
    except FileNotFoundError:
        #file doesn't exist yet
        return False

    for line in lines:
        if line.split(",")[0] != user:
            newLines.append(line)
        else:
            #user found, and this line won't be copied to newLines
            removed = True

    with open("birthdays.txt", "w") as birthdays:
        birthdays.writelines(newLines)

    return removed


def save_birthday(date: str, user: str) -> bool:
    """
    Saves user's birthday into the record.
    If the user already had a birthday in the record, then it replaces it, and returns True.
    If not, then the user's birthday is saved, and it returns False.

    :param date: str, date in format DD/MM
    :param user: str, user's ID'
    :return: bool, False if user's birthday was new to the record, True if user's birthday was already in records and updated
    """
    lines = []

    try:
        with open("birthdays.txt", "r") as birthdays:
            lines = birthdays.readlines()
    except FileNotFoundError:
        #file doesn't exist yet
        pass

    user_found = False
    #search through lines for user
    for i, line in enumerate(lines):
        #if user is found in lines
        if line and line.split(",")[0] == user:
            user_found = True
            lines[i] = f"{user},{date}\n"
            break

    if not user_found:
        lines.append(f"{user},{date}\n")

    #write to file
    with open("birthdays.txt", "w") as birthdays:
        birthdays.writelines(lines)

    #true if user was found and updated, false if user was added
    return user_found

#Helper function for team join:
def send_im(message: str, channel: str) -> None:
    '''
    wrapper for slack messages with exception handling

    :param message: str, content of message
    :param channel: str, Channel ID'
    :return: None
    '''
    try:
        app.client.chat_postMessage(
            channel=channel,
            text=message,
        )
    except SlackApiError as e:
        logger.error(f"Slack API error: {e}")

#Helper function for daily tasks:

def checkTime() -> None:
    global tom_time
    cur_time = datetime.now() #TODO: use +/- timedelta() for adding an offset if you need
    if cur_time > tom_time:
        tom_time += timedelta(days=1)
        daily(cur_time)


#Initializes Websocket handler and runs app.
handler = SocketModeHandler(app)
logger.info("Handler initialized, starting...")
handler.start()

