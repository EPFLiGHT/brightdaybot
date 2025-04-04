# BrightDayBot

A Slack bot that records and wishes Slack workspace members a happy birthday with AI-generated personalized messages.

## Features

- **Birthday Recording**: Users can set their birthdays via DM to the bot
- **Birthday Announcements**: Automatic birthday celebrations in a designated channel
- **AI-Generated Messages**: Personalized birthday wishes using OpenAI
- **Admin Commands**: Statistics, user management, and settings
- **Reminders**: Automatically remind users who haven't set their birthday
- **Data Management**: Automated backups and organized data storage
- **Multiple Personalities**: Switch between different bot personalities with persistent settings
- **Custom Templates**: Fully customizable message templates for each personality

## Project Structure

```plaintext
brightdaybot/
├── app.py                 # Main entry point
├── config.py              # Configuration and environment settings
├── llm_wrapper.py         # OpenAI integration for messages
├── data/                  # Data directory
│   ├── logs/              # Log files
│   ├── storage/           # Birthday data and configuration
│   ├── tracking/          # Announcement tracking
│   └── backups/           # Backup files
├── handlers/              # Slack event and command handlers
│   ├── command_handler.py # Command processing logic
│   └── event_handler.py   # Event handling logic
├── services/              # Core functionality
│   ├── birthday.py        # Birthday management logic
│   └── scheduler.py       # Scheduling functionality
└── utils/                 # Helper modules
    ├── config_storage.py  # Configuration storage
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

# Optional: Custom bot personality settings
CUSTOM_BOT_NAME="Birthday Wizard"
CUSTOM_BOT_DESCRIPTION="a magical birthday celebration wizard"
CUSTOM_BOT_STYLE="magical, whimsical, and full of enchantment"
CUSTOM_FORMAT_INSTRUCTION="Create a magical spell-like birthday message"
CUSTOM_BOT_TEMPLATE_EXTENSION="Your custom template extension here"
```

### 4. Running the Bot

Execute the main Python script:

```bash
python app.py
```

The bot will:

- Create necessary data directories (logs, storage, tracking, backups)
- Initialize configuration from storage or create default settings
- Store birthdays in data/storage/birthdays.txt
- Store configuration in data/storage/\*.json files
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
- `custom` - Customizable personality using environment variables or commands

To change the personality:

1. As an admin, use the command: `admin personality [name]`
2. The selection persists across bot restarts

### Persistent Configuration

The bot maintains persistent configuration across restarts:

1. **Admin Users**: Admins are saved to `data/storage/admins.json`

   - Changes made with `admin add` and `admin remove` commands are persisted
   - Workspace admins always have admin privileges regardless of this list

2. **Bot Personality**: Settings are saved to `data/storage/personality.json`

   - Active personality selection is remembered between restarts
   - Custom personality settings are saved automatically

3. **Custom Personality Configuration**:
   - `admin custom name [value]` - Set the bot's name
   - `admin custom description [value]` - Set the bot's character description
   - `admin custom style [value]` - Set the writing style
   - `admin custom format [value]` - Set formatting instructions
   - `admin custom template [value]` - Set additional template instructions

## Customization

### Changing Birthday Message Style

Edit the templates in config.py to customize:

- `BASE_TEMPLATE` - The core template all personalities share
- `BOT_PERSONALITIES` - Individual personality definitions
- `template_extension` - Personality-specific additions to the base template

Additional message components can be customized in llm_wrapper.py:

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

## Troubleshooting

- **Admin List Issues**: If admin commands aren't working properly, restart the bot and check the logs to verify admins are loading correctly.
- **Personality Not Applying**: Use `admin personality` to check the current personality setting.
- **Message Generation Fails**: The bot will automatically fall back to template messages if the AI service is unavailable.

## License

See [LICENSE](LICENSE) for details.
