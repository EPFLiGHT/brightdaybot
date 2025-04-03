# BrightDayBot

A Slack bot that records and wishes Slack workspace members a happy birthday with AI-generated personalized messages.

## Features

- **Birthday Recording**: Users can set their birthdays via DM to the bot
- **Birthday Announcements**: Automatic birthday celebrations in a designated channel
- **AI-Generated Messages**: Personalized birthday wishes using OpenAI
- **Admin Commands**: Statistics, user management, and settings
- **Reminders**: Automatically remind users who haven't set their birthday
- **Data Management**: Automated backups and organized data storage

## Project Structure

```plaintext
brightdaybot/
├── app.py                 # Main entry point
├── config.py              # Configuration and environment settings
├── llm_wrapper.py         # OpenAI integration for messages
├── data/                  # Data directory
│   ├── logs/              # Log files
│   ├── storage/           # Birthday data
│   ├── tracking/          # Announcement tracking
│   └── backups/           # Backup files
├── handlers/              # Slack event and command handlers
│   ├── command_handler.py # Command processing logic
│   └── event_handler.py   # Event handling logic
├── services/              # Core functionality
│   ├── birthday.py        # Birthday management logic
│   └── scheduler.py       # Scheduling functionality
└── utils/                 # Helper modules
    ├── date_utils.py      # Date handling functions
    ├── slack_utils.py     # Slack API wrapper functions
    └── storage.py         # Birthday storage functions
```

## Setup Instructions

Follow these steps to set up BrightDayBot.

### 1. Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and click "Create New App"
2. Choose "From scratch" and give it a name (e.g., "BrightDayBot")
3. Select your workspace
4. Under "Add features and functionality":
   - Enable "Socket Mode"
   - Enable "Event Subscriptions" and subscribe to:
     - `message.im` (for direct messages)
     - `team_join` (for new user onboarding)
   - Add "Bot Token Scopes" under "OAuth & Permissions":
     - `chat:write`
     - `users:read`
     - `users.profile:read`
     - `im:history`
     - `im:write`
     - `channels:read`
     - `groups:read`
     - `mpim:read`
     - `users:read.email`
5. Install the app to your workspace and copy the bot token (`xoxb-...`)
6. Generate an app-level token with `connections:write` scope and copy it (`xapp-...`)

### 2. Install Dependencies

This bot has been tested with Python 3.12, but might work with earlier versions.

Before running the bot, make sure you have generated SSL certificates within your Python installation.

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a .env file in the project root:

```python
SLACK_APP_TOKEN="xapp-your-app-token"
SLACK_BOT_TOKEN="xoxb-your-bot-token"
BIRTHDAY_CHANNEL_ID="C0123456789"
OPENAI_API_KEY="sk-your-openai-api-key"
OPENAI_MODEL="gpt-4o"  # Optional: defaults to gpt-4o
```

### 4. Running the Bot

Execute the main Python script:

```bash
python app.py
```

The bot will:

- Create necessary data directories (logs, storage, tracking, backups)
- Store birthdays in data/storage/birthdays.txt
- Write logs to data/logs/app.log
- Check for today's birthdays at startup
- Schedule daily birthday checks at 8:00 AM UTC

## Usage

### User Commands

DM the bot with any of these commands:

- `help` - Show help information
- `add DD/MM` - Add birthday without year
- `add DD/MM/YYYY` - Add birthday with year
- `remove` - Remove your birthday
- `check` - Check your saved birthday
- `check @user` - Check someone else's birthday
- `test` - See a test birthday message

Or simply send a date in `DD/MM` or `DD/MM/YYYY` format.

### Admin Commands

- `admin list` - List configured admin users
- `admin add USER_ID` - Add a user as admin
- `admin remove USER_ID` - Remove admin privileges
- `list` - List upcoming birthdays
- `list all` - List all birthdays by month
- `stats` - View birthday statistics
- `remind [message]` - Send reminders to users without birthdays
- `config` - View command permissions
- `config COMMAND true/false` - Change command permissions

### Data Management Commands

- `admin backup` - Create a manual backup of birthdays data
- `admin restore latest` - Restore from the latest backup

### Bot Personality

The bot supports multiple personalities that change how birthday messages are written:

- `standard` - Friendly, enthusiastic birthday bot (default)
- `mystic_dog` - Ludo the Mystic Birthday Dog who provides cosmic predictions
- `custom` - Customizable personality using environment variables

To change the personality:

1. As an admin, use the command: `admin personality [name]`
2. Or set in the configuration file [`config.py`](config.py)
3. For custom personalities, set these environment variables:
   - `CUSTOM_BOT_NAME` - Name of your bot
   - `CUSTOM_BOT_DESCRIPTION` - Short description of the bot's character
   - `CUSTOM_BOT_STYLE` - Writing style (e.g., "funny and sarcastic")
   - `CUSTOM_FORMAT_INSTRUCTION` - How the message should be structured

## Customization

### Changing Birthday Message Style

Edit the templates in llm_wrapper.py to customize:

- `TEMPLATE` - System prompt for AI-generated messages
- `BACKUP_MESSAGES` - Fallback templates when AI is unavailable
- `BIRTHDAY_INTROS`, `BIRTHDAY_MIDDLES`, etc. - Components for template messages

### Schedule Configuration

Change when birthday checks run by modifying `DAILY_CHECK_TIME` in config.py.

## Data Management

The bot implements several data management features:

- **Automatic Backups**: Creates timestamped backups of the birthdays file whenever it's modified
- **Backup Rotation**: Maintains the 10 most recent backups to save space
- **Auto-Recovery**: Tries to restore from backup if the main file is missing
- **Administrative Control**: Provides commands for manual backup and restore operations
- **Birthday Tracking**: Prevents duplicate announcements if the bot is restarted

## License

See [LICENSE](LICENSE) for details.
