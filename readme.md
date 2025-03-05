### BrightDayBot

A Slack bot that records and wishes Slack workspace members a happy birthday.

## Setup Instructions

Follow these steps to set up BrightDayBot. These instructions assume you have already created and installed the Slack App in your workspace. Insturctions for how to do that are coming soon.

### 1. Install Dependencies

This bot has been tested with Python 3.12, but might work with earlier versions.

Before running the bot, make sure you have generated SSL certificates within your Python installation. 
On my mac, the path to the file that will install that for you is /Applications/Python\ 3.12/Install\ Certificates.command


Use `pip` to install the required packages into your venv:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```


### 2. Configure Slack API Tokens

In the .env file, add your Slack tokens, as well as the channel id that the bot should send wishes in.
Example:
```plaintext
SLACK_BOT_TOKEN=xoxb-12345
SLACK_SIGNING_SECRET=123abc456def
BIRTHDAY_CHANNEL_ID=C0
```

Replace the placeholders with your actual Slack API tokens.

### 3. Run the Application
Execute the main Python script:

```bash
python app.py
```

Once running, BrightDayBot will start listening for birthdays and sending greetings at the appropriate time.

## Slack App Setup and Installation Instructions

For now, I've already done this. I'll add instructions on how to do it in the future soon.

I will also add more information on how to add more functionality to this bot soon.

Unfortunately I am very sleep right now so that's not going to happen.
