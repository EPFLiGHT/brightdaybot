# BrightDayBot

A Slack bot that records and wishes Slack workspace members a happy birthday with AI-generated personalized messages.

## Features

- **Birthday Recording**: Users can set their birthdays via DM to the bot
- **Multi-Timezone Celebrations**: Celebrates birthdays at 9 AM in each user's local timezone
- **AI-Generated Messages**: Personalized birthday wishes using OpenAI GPT-4.1
- **AI Image Generation**: Creates personalized birthday images using OpenAI GPT-Image-1
- **Enhanced Profile Integration**: Uses Slack profile data (job title, timezone, photos) for personalization
- **Historical Date Facts**: Includes interesting scientific and historical facts about the birthday date
- **Multiple Personalities**: 8 different bot personalities with unique message styles
- **Smart Consolidation**: Single message for multiple birthdays on the same day to avoid spam
- **Admin Commands**: Statistics, user management, and settings
- **System Health Monitoring**: Built-in diagnostics for troubleshooting
- **Data Management**: Automated backups and recovery options
- **Reminders**: Automatically remind users who haven't set their birthday
- **Web Search Caching**: Store historical date facts to reduce API calls
- **Custom Templates**: Fully customizable message templates for each personality
- **Startup Recovery**: Automatically catches missed birthday celebrations after server downtime

## Project Structure

```plaintext
brightdaybot/
├── app.py                    # Main entry point
├── config.py                 # Configuration and environment settings
├── data/                     # Data directory
│   ├── logs/                 # Log files
│   ├── storage/              # Birthday data and configuration
│   ├── tracking/             # Announcement tracking
│   ├── cache/                # Cache for web search results
│   └── backups/              # Backup files
├── handlers/                 # Slack event and command handlers
│   ├── command_handler.py    # Command processing logic
│   └── event_handler.py      # Event handling logic
├── services/                 # Core functionality
│   ├── birthday.py           # Birthday management logic
│   └── scheduler.py          # Scheduling functionality
└── utils/                    # Helper modules
    ├── config_storage.py     # Configuration storage
    ├── date_utils.py         # Date handling functions
    ├── health_check.py       # System diagnostics
    ├── message_generator.py  # Message generation using OpenAI
    ├── image_generator.py    # AI image generation using OpenAI GPT-Image-1
    ├── timezone_utils.py     # Timezone handling utilities
    ├── web_search.py         # Web search for birthday facts
    ├── slack_utils.py        # Slack API wrapper functions
    └── storage.py            # Birthday storage functions
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
     - `files:write`
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
OPENAI_MODEL="gpt-4.1"  # Optional: defaults to gpt-4.1

# Optional: AI image generation settings
AI_IMAGE_GENERATION_ENABLED="true"  # Set to "false" to disable image generation

# Optional: Custom bot personality settings
CUSTOM_BOT_NAME="Birthday Wizard"
CUSTOM_BOT_DESCRIPTION="a magical birthday celebration wizard"
CUSTOM_BOT_STYLE="magical, whimsical, and full of enchantment"
CUSTOM_FORMAT_INSTRUCTION="Create a magical spell-like birthday message"
CUSTOM_BOT_TEMPLATE_EXTENSION="Your custom template extension here"

# Optional: Web search caching (defaults to enabled)
WEB_SEARCH_CACHE_ENABLED="true"  # Set to "false" to disable caching
```

### 4. Running the Bot

Execute the main Python script:

```bash
python app.py
```

The bot will:

- Create necessary data directories (logs, storage, tracking, backups, cache)
- Initialize configuration from storage or create default settings
- Store birthdays in data/storage/birthdays.txt
- Store configuration in data/storage/\*.json files
- Write logs to data/logs/app.log
- Check for today's birthdays at startup with catch-up for missed celebrations
- Schedule hourly timezone-aware birthday checks at :00 past each hour
- Schedule daily safety net check at 10:00 AM in server local timezone (configurable in config.py)

## Deployment

### Running as a System Service

To run BrightDayBot as a persistent service that starts automatically after reboots:

1. **Create a systemd service file**:

   ```bash
   sudo nano /etc/systemd/system/brightdaybot.service
   ```

   With content:

   ```ini
   [Unit]
   Description=BrightDayBot Service
   After=network.target

   [Service]
   Type=simple
   ExecStart=/path/to/venv/bin/python /path/to/brightdaybot/app.py
   WorkingDirectory=/path/to/brightdaybot
   User=your_username
   Group=your_group
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

2. **Enable and start the service**:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable brightdaybot.service
   sudo systemctl start brightdaybot.service
   ```

3. **Manage the bot service**:

   ```bash
   # Check status
   sudo systemctl status brightdaybot.service
   # Restart the bot
   sudo systemctl restart brightdaybot.service
   # View logs
   sudo journalctl -u brightdaybot.service -f
   ```

### Updating the Bot

When you update the code or configuration:

```bash
# Pull latest changes
cd /path/to/brightdaybot
git pull

# Restart the service
sudo systemctl restart brightdaybot.service
```

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
- `admin status` - Check system health and component status
- `admin status detailed` - Get detailed system information
- `admin timezone` - View birthday celebration schedule across timezones
- `remind [message]` - Send reminders to users without birthdays
- `config` - View command permissions
- `config COMMAND true/false` - Change command permissions

### Data Management Commands

- `admin backup` - Create a manual backup of birthdays data
- `admin restore latest` - Restore from the latest backup
- `admin cache clear` - Clear all web search cache
- `admin cache clear DD/MM` - Clear web search cache for a specific date
- `admin test-upload` - Test the image upload functionality

### Bot Personality

The bot supports multiple personalities that change how birthday messages are written:

- `standard` - Friendly, enthusiastic birthday bot (default)
- `mystic_dog` - Ludo the Mystic Birthday Dog who provides cosmic predictions and historical date facts
- `poet` - The Verse-atile, a poetic birthday bard who creates lyrical birthday messages
- `tech_guru` - CodeCake, a tech-savvy bot who speaks in programming metaphors
- `chef` - Chef Confetti, a culinary master who creates food-themed messages
- `superhero` - Captain Celebration, a superhero dedicated to making birthdays epic
- `time_traveler` - Chrono, a time-traveling messenger from the future
- `pirate` - Captain BirthdayBeard, a jolly pirate with nautical-themed messages
- `custom` - Customizable personality using environment variables or commands

To change the personality:

1. As an admin, use the command: `admin personality [name]`
2. The selection persists across bot restarts

#### Ludo the Mystic Birthday Dog

Ludo's messages follow a specific structured format:

1. A mystical greeting and request for celebratory GIFs
2. Three insightful sections:
   - **Star Power**: Horoscope and numerological insights
   - **Spirit Animal**: The person's spirit animal for the year
   - **Cosmic Connection**: Scientific and historical facts about the birthday date, drawing from web searches
3. A concluding message about the year ahead

The Cosmic Connection section incorporates web-searched information about notable scientific figures born on that date and significant historical events.

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

Additional message components can be customized in utils/message_generator.py:

- `BACKUP_MESSAGES` - Fallback templates when AI is unavailable
- `BIRTHDAY_INTROS`, `BIRTHDAY_MIDDLES`, etc. - Components for template messages

### Schedule Configuration

The bot now uses a sophisticated multi-timezone celebration system:

- **Hourly Checks**: Runs at :00 past each hour to check for 9 AM celebrations in different timezones
- **Daily Safety Net**: Runs at 10:00 AM in server local timezone as a backup (configurable via `DAILY_CHECK_TIME` in config.py)
- **Startup Recovery**: Automatically catches missed celebrations when the bot restarts after downtime
- **Smart Consolidation**: When multiple people have birthdays on the same day, the first person hitting 9 AM triggers a single consolidated message for everyone

### AI Image Generation

The bot can generate personalized birthday images using OpenAI's GPT-Image-1 model:

- **Personality-Themed Images**: Each bot personality generates images in its unique style
- **Creative Randomness**: AI adds unexpected creative elements to make each image unique
- **Profile Integration**: Uses user's job title for personalization
- **Automatic Caching**: Images are saved to `data/cache/images/` directory
- **Fallback Support**: Text-only messages if image generation fails

Enable/disable with `AI_IMAGE_GENERATION_ENABLED` environment variable.

## Data Management

The bot implements several data management features:

- **Automatic Backups**: Creates timestamped backups of the birthdays file whenever it's modified
- **Backup Rotation**: Maintains the 10 most recent backups to save space
- **Auto-Recovery**: Tries to restore from backup if the main file is missing
- **Web Search Caching**: Stores retrieved historical date facts to reduce API calls
  - Cached data is stored in `data/cache/` directory
  - Control caching with `WEB_SEARCH_CACHE_ENABLED` environment variable
  - Clear cache with `admin cache clear` or manually delete cache files
- **Image Caching**: Auto-saves generated birthday images to `data/cache/images/`
  - Automatic cleanup removes images older than 30 days
  - Manual cleanup can be performed by deleting files from the cache directory
- **Administrative Control**: Provides commands for manual backup and restore operations
- **Multi-Timezone Birthday Tracking**: Prevents duplicate announcements across different celebration methods
  - Legacy tracking: `data/tracking/announced_YYYY-MM-DD.txt`
  - Timezone tracking: `data/tracking/timezone_announced_YYYY-MM-DD.txt`

## System Health Monitoring

BrightDayBot includes a health check system to monitor the status of critical components:

- **Storage Status**: Checks if birthday data is accessible and reports the number of birthdays
- **Admin Configuration**: Verifies admin user configuration is properly loaded
- **Web Search Cache**: Monitors cache status, size, and most recent updates
- **API Configuration**: Validates that required API keys are configured

To check system health:

1. As an admin, use the command: `admin status`
2. For detailed information including file paths and cache details: `admin status detailed`

The health check helps diagnose issues quickly by showing the status of each component with visual indicators:

- ✅ Component is working correctly
- ℹ️ Component has a non-critical status
- ❌ Component has a critical issue that needs attention

## Troubleshooting

If you encounter issues with BrightDayBot, follow these steps:

1. Run the health check with `admin status` command in Slack
2. Check for any ❌ indicators in the status report
3. For more detailed diagnostics, use `admin status detailed`
4. Verify all required environment variables are set correctly
5. Ensure the bot has proper permissions in Slack
6. Check that all required directories and files exist with proper permissions
7. Review the log files in `data/logs/` for any error messages

Common issues:

- Missing API keys: Ensure `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `OPENAI_API_KEY` are set
- Permission problems: Verify the bot has read/write permissions to the data directories
- Invalid configuration: Check that the `BIRTHDAY_CHANNEL` is set to a valid Slack channel ID
- Image generation issues: Verify OpenAI API key has access to GPT-Image-1 model
- Timezone issues: Ensure users have set their timezone in their Slack profile settings
- Missing dependencies: Run `pip install -r requirements.txt` to install all required packages including `pytz` and `Pillow`

## License

See [LICENSE](LICENSE) for details.
