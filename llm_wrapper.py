from openai import OpenAI
from dotenv import load_dotenv
import logging
import os
load_dotenv()
client = OpenAI()
logging.basicConfig(filename="app.log", level=logging.INFO)
logger = logging.getLogger(__name__)
MODEL: str = "gpt-4o-mini"

TEMPLATE= [
    {
        "role": "developer",
        "content": """
        You are a helpful assistant. 
        Your job is to create short and fun ways to wish people happy birthday.
        You will be given an input of the person's name and the day and month of their birthday.
        Given this input, your task is to generate a short, nice, and fun message wishing them happy birthday.
        If you would like, you may use the date of their birth to make a reference to their star sign, or
        their name for wordplay or a pun, and to include emojis in the message. It is also alright not to do these things.
        Please also ask how they plan to celebrate their birthday!
        Note: There is a small chance the name is a Slack User ID, which would look something like: <@U07H5SUR8VA> or <@W16CA3W98F9>. In this case, pretend that their name is their user id. So you might wish "Happy birthday <@U07H5SUR8VA>! [rest of message]", for example.
        Be sure to limit your response to a short paragraph, and do not include references saying that you are a chatbot.
        Limit your response to the message only.
        """
    }
]

def completion(name: str, date: str) -> str:
    '''
    :param name: str, user's name in plaintext or possible their SlackID if there was an API error
    :param date: str, user's birthday in natural language
    :return: str, GPT generated birthday wish
    '''
    template = TEMPLATE
    template.append(
        {
            "role": "user",
            "content": f"""{name}'s birthday is on {date}. Please write them a message wishing them a happy birthday. 
            As a reminder, this is their information: \n name: {name} \n birthday: {date}."""
        }
    )
    try:
        logger.log(logging.INFO, f"Requesting completion for {name}'s birthday on {date}")
        reply = client.chat.completions.create(
            model=MODEL,
            messages=TEMPLATE
        ).choices[0].message.content
    except:
        logger.log(logging.ERROR, f"Failed request for completion for {name}'s birthday on {date}")
        reply = f"Happy Birthday {name}!!! Wishing you a fantastic day filled with joy, laughter, and, of course, lots of cake! May this year bring you lots of happiness and everythign you wish for. How are you planning on celebrating it this year?"
        pass

    return reply
