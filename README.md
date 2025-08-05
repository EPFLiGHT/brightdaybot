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
- **Streamlined User Experience**: Single welcome message per user (birthday channel only, no team-wide notifications)
- **Admin Commands**: Statistics, user management, and settings
- **System Health Monitoring**: Built-in diagnostics for troubleshooting
- **Data Management**: Automated backups and recovery options
- **Reminders**: Automatically remind users who haven't set their birthday
- **Announcement System**: Broadcast feature updates and important messages to all users
- **Web Search Caching**: Store historical date facts to reduce API calls
- **Custom Templates**: Fully customizable message templates for each personality
- **Startup Recovery**: Automatically catches missed birthday celebrations after server downtime

## Project Structure

```plaintext
brightdaybot/
├── app.py                    # Main entry point
├── config.py                 # Configuration and environment settings
├── personality_config.py     # 🆕 NEW: Centralized personality configurations
├── data/                     # Data directory
│   ├── logs/                 # Log files
│   ├── storage/              # Birthday data and configuration
│   ├── tracking/             # Announcement tracking
│   ├── cache/                # Cache for web search results and images
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

# Optional: External backup system (defaults to enabled)
EXTERNAL_BACKUP_ENABLED="true"  # Set to "false" to disable external backups
BACKUP_TO_ADMINS="true"  # Send backup files to admin users via DM
BACKUP_CHANNEL_ID=""  # Optional: dedicated backup channel ID
BACKUP_ON_EVERY_CHANGE="true"  # Send backup on every change vs. batched
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
- Write comprehensive logs to data/logs/ with component-specific files
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
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   ExecStart=/path/to/venv/bin/python /path/to/brightdaybot/app.py
   WorkingDirectory=/path/to/brightdaybot
   User=your_username
   Group=your_group
   Restart=always
   RestartSec=30

   [Install]
   WantedBy=multi-user.target
   ```

   **Important**: This configuration ensures the service waits for internet connectivity:
   - `After=network-online.target` - Waits for actual internet connectivity, not just network interface
   - `Wants=network-online.target` - Explicitly requests network connectivity
   - `RestartSec=30` - Waits 30 seconds between restart attempts to avoid rapid failures

2. **Enable and start the service**:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable brightdaybot.service
   sudo systemctl start brightdaybot.service
   ```

3. **Enable network connectivity waiting** (required for reliable startup):

   ```bash
   sudo systemctl enable NetworkManager-wait-online.service
   ```

   This ensures the system waits for internet connectivity before starting network-dependent services.

4. **Manage the bot service**:

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

### Welcome Experience

When new users join your workspace:

1. **Automatic Birthday Channel Access**: New members are automatically added to the birthday channel
2. **Single Welcome Message**: Users receive one comprehensive welcome message when they join the birthday channel (no duplicate team-wide notifications)
3. **Clear Instructions**: The welcome message includes instructions for setting birthdays and using commands
4. **Proper Slack Formatting**: All messages use correct Slack formatting (`*bold*` instead of `**bold**`)

**Note**: The bot no longer sends general team welcome messages - users only receive the birthday channel welcome, eliminating notification spam.

### User Commands

DM the bot with any of these commands:

- `help` - Show help information
- `add DD/MM` - Add birthday without year
- `add DD/MM/YYYY` - Add birthday with year
- `remove` - Remove your birthday
- `check` - Check your saved birthday
- `check @user` - Check someone else's birthday
- `test [quality] [size]` - See a test birthday message with optional quality and image size (quality: low/medium/high/auto, size: auto/1024x1024/1536x1024/1024x1536)
- `confirm` - Confirm pending announcement or reminder commands

Or simply send a date in `DD/MM` or `DD/MM/YYYY` format.

### Admin Commands

- `admin help` - View complete admin command reference with all available personalities
- `admin list` - List configured admin users
- `admin add USER_ID` - Add a user as admin
- `admin remove USER_ID` - Remove admin privileges
- `list` - List upcoming birthdays
- `list all` - List all birthdays by month
- `stats` - View birthday statistics
- `admin status` - Check system health and component status
- `admin status detailed` - Get detailed system information
- `admin timezone` - View birthday celebration schedule across timezones
- `admin test @user [quality] [size]` - **NEW**: Generate test birthday message & image with quality and size control (stays in DM)
- `admin test-join [@user]` - **NEW**: Test birthday channel welcome message flow
- `remind` or `remind new` - Send reminders to users without birthdays (requires confirmation)
- `remind update` - Send profile update reminders to users with birthdays (requires confirmation)
- `remind new [message]` - Send custom reminder to new users (requires confirmation)
- `remind update [message]` - Send custom profile update reminder (requires confirmation)
- `config` - View command permissions
- `config COMMAND true/false` - Change command permissions

### Data Management Commands

- `admin backup` - Create a manual backup of birthdays data
- `admin restore latest` - Restore from the latest backup
- `admin cache clear` - Clear all web search cache
- `admin cache clear DD/MM` - Clear web search cache for a specific date
- `admin test-upload` - Test the image upload functionality
- `admin test-file-upload` - Test text file upload functionality (like backup files)
- `admin test-external-backup` - Test the external backup system with detailed diagnostics

### Announcement Commands

- `admin announce image` - Announce AI image generation feature to birthday channel (requires confirmation)
- `admin announce [message]` - Send custom announcement to birthday channel (requires confirmation)

**Note**: Announcements use `@here` mentions for better timezone consideration and require confirmation to prevent accidental mass notifications.

### Bot Personality

#### Enhanced Personality System 🎭

The bot supports multiple personalities that change birthday messages, images, and web search formatting. All personalities are now defined in `personality_config.py`:

- `standard` - Friendly, enthusiastic birthday bot (default)
- `mystic_dog` - Ludo the Mystic Birthday Dog who provides cosmic predictions and historical date facts
- `poet` - The Verse-atile, a poetic birthday bard who creates lyrical birthday messages
- `tech_guru` - CodeCake, a tech-savvy bot who speaks in programming metaphors
- `chef` - Chef Confetti, a culinary master who creates food-themed messages
- `superhero` - Captain Celebration, a superhero dedicated to making birthdays epic
- `time_traveler` - Chrono, a time-traveling messenger from the future
- `pirate` - Captain BirthdayBeard, a jolly pirate with nautical-themed messages
- `random` - Randomly selects a different personality for each birthday
- `custom` - Fully customizable personality

#### Managing Personalities

1. View current: `admin personality`
2. Change personality: `admin personality [name]`
3. Test personality: `admin test @user`
4. View all options: `admin help`

#### Adding Custom Personalities

Edit `personality_config.py` and add a new entry with all required fields. The new personality will automatically be available.

### Confirmation System

To prevent accidental mass notifications, certain commands require a two-step confirmation process:

#### Commands Requiring Confirmation

**Mass Notification Commands:**
- `admin announce image` - Announces features to all birthday channel members
- `admin announce [message]` - Sends custom announcements to all birthday channel members
- `remind` or `remind new` - Sends DM reminders to users without birthdays
- `remind update` - Sends DM reminders to users with birthdays
- `remind new [message]` - Sends custom DM reminders to new users
- `remind update [message]` - Sends custom profile update reminders

#### How It Works

1. **Initial Command**: Run any mass notification command (e.g., `admin announce Hello everyone!`)
2. **Preview & Confirmation Request**: The bot shows:
   - Preview of the message that will be sent
   - Number of users who will be notified
   - Request to type `confirm` within 5 minutes
3. **Confirmation**: Type `confirm` to proceed with sending
4. **Execution**: The bot sends the notifications and provides a summary
5. **Timeout**: Confirmations automatically expire after 5 minutes

#### Example Flow

```
You: admin announce Welcome to our new birthday system!

Bot: 📢 CONFIRMATION REQUIRED 📢

Preview of announcement to birthday channel:
"Welcome to our new birthday system!"

This will notify approximately 25 users in #birthdays.

Type `confirm` within 5 minutes to send, or any other message to cancel.

You: confirm

Bot: ✅ Announcement sent successfully to the birthday channel!
```

This system ensures that mass notifications are intentional and helps prevent accidental spam to team members.

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

#### NEW: Centralized Personality Configuration 🎨

All personality configurations are now centralized in `personality_config.py` for easy management:

- **`personality_config.py`** - Complete personality definitions including:
  - Basic info (name, description, style)
  - Message generation templates and prompts
  - Image generation prompts
  - Web search formatting
  - Consolidated message prompts

#### Adding a New Personality

1. Add a new entry to the `PERSONALITIES` dictionary in `personality_config.py`
2. Define all required fields (see existing personalities as examples)
3. The new personality will automatically be available in all bot functions

#### Legacy Configuration

- `BASE_TEMPLATE` - The core template all personalities share (in config.py)
- `BACKUP_MESSAGES` - Fallback templates when AI is unavailable (in utils/message_generator.py)

### Schedule Configuration

The bot now uses a sophisticated multi-timezone celebration system:

- **Hourly Checks**: Runs at :00 past each hour to check for 9 AM celebrations in different timezones
- **Daily Safety Net**: Runs at 10:00 AM in server local timezone as a backup (configurable via `DAILY_CHECK_TIME` in config.py)
- **Startup Recovery**: Automatically catches missed celebrations when the bot restarts after downtime
- **Smart Consolidation**: When multiple people have birthdays on the same day, the first person hitting 9 AM triggers a single consolidated message for everyone

### AI Image Generation

#### 🚀 REVOLUTIONARY: Reference Photo Generation 🖼️

The bot now generates face-accurate birthday images using OpenAI's GPT-Image-1 model with breakthrough reference photo technology:

#### NEW: Face-Accurate Images

- **Reference Photo Mode**: Automatically uses user's Slack profile photo as reference
- **High Input Fidelity**: GPT-Image-1 preserves facial features and expressions accurately
- **Smart Dual-Mode**: Reference-based when photos available, text-only fallback
- **Quality Control**: Configurable quality settings for cost optimization

#### Advanced Features

- **Profile Photo Pipeline**: Downloads, processes, and prepares user photos automatically
- **Personality-Themed Styles**: Each personality generates images in its unique style
- **Message Context Integration**: Incorporates themes from the generated birthday message
- **Cost Optimization**: Test commands use lower quality for reduced costs
- **Automatic Cleanup**: Profile photos cleaned after 7 days, images after 30 days

#### Quality & Size Settings

- `test [quality] [size]` - User test with optional quality and image size control
- `admin test @user [quality] [size]` - Admin test with quality and size control
- Production birthdays automatically use high quality and auto sizing
- **NEW**: Default image size is now "auto" for optimal sizing

#### Technical Details

- Uses GPT-Image-1's `images.edit` API for reference-based generation
- `input_fidelity="high"` for optimal face preservation
- Supports auto, 1024x1024, 1536x1024, 1024x1536 image sizes
- Automatic fallback when profile photos unavailable

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
  - Profile photos cleaned after 7 days to save space
  - Manual cleanup can be performed by deleting files from the cache directory
- **Administrative Control**: Provides commands for manual backup and restore operations
- **Multi-Timezone Birthday Tracking**: Prevents duplicate announcements across different celebration methods
  - Legacy tracking: `data/tracking/announced_YYYY-MM-DD.txt`
  - Timezone tracking: `data/tracking/timezone_announced_YYYY-MM-DD.txt`

## Enhanced Logging System

### NEW: Component-Specific Logging 📝

BrightDayBot now features an advanced multi-file logging system that organizes logs by component for easier debugging and monitoring:

#### Log Files Structure

- **`main.log`** - Core application startup, configuration, and general operations
- **`commands.log`** - User commands, admin actions, and command processing
- **`events.log`** - Slack events like direct messages and team joins
- **`birthday.log`** - Birthday service logic, celebrations, and scheduling
- **`ai.log`** - AI/LLM interactions (OpenAI API calls, message/image generation)
- **`slack.log`** - Slack API interactions and user profile operations
- **`storage.log`** - Data storage operations, file access, and backups
- **`system.log`** - System utilities, health checks, and date operations
- **`scheduler.log`** - Background scheduling and periodic tasks

#### Features for Enhanced Logging

- **Automatic Rotation**: Log files rotate when they reach 10MB (keeping 5 backup files)
- **Component Routing**: Each module logs to its appropriate file automatically
- **Health Monitoring**: The `admin status` command monitors all log files
- **Size Management**: Prevents logs from consuming excessive disk space
- **Structured Format**: Consistent timestamped format across all components

## System Health Monitoring

BrightDayBot includes a comprehensive health check system to monitor the status of critical components:

- **Storage Status**: Checks if birthday data is accessible and reports the number of birthdays
- **Admin Configuration**: Verifies admin user configuration is properly loaded
- **Web Search Cache**: Monitors cache status, size, and most recent updates
- **Log Files**: Monitors all component log files for size, activity, and potential issues
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
7. Review the component-specific log files in `data/logs/` for error messages:
   - `main.log` - Core application logs
   - `commands.log` - User commands and admin actions
   - `events.log` - Slack events
   - `birthday.log` - Birthday service logic
   - `ai.log` - AI/LLM interactions
   - `slack.log` - Slack API interactions
   - `storage.log` - Data storage operations
   - `system.log` - System utilities and health checks
   - `scheduler.log` - Scheduling and background tasks

Common issues:

- **Network connectivity at startup**: If the service fails at boot with "exit-code status=217/USER":
  - Update systemd service to use `network-online.target` instead of `network.target`
  - Add `RestartSec=30` to prevent rapid restart failures
  - Enable NetworkManager-wait-online service: `sudo systemctl enable NetworkManager-wait-online.service`
  - Test connectivity manually before starting: `curl -I https://api.slack.com`
- Missing API keys: Ensure `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `OPENAI_API_KEY` are set
- Permission problems: Verify the bot has read/write permissions to the data directories
- Invalid configuration: Check that the `BIRTHDAY_CHANNEL` is set to a valid Slack channel ID
- Image generation issues: Verify OpenAI API key has access to GPT-Image-1 model
- Timezone issues: Ensure users have set their timezone in their Slack profile settings
- Missing dependencies: Run `pip install -r requirements.txt` to install all required packages including `pytz` and `Pillow`

## Slack Message Formatting

BrightDayBot follows proper Slack formatting guidelines for optimal display:

### Text Formatting

- **Bold text**: Use `*bold*` (single asterisks) ✅
- **Avoid**: `**bold**` (double asterisks) ❌ - This doesn't work properly in Slack
- **Italics**: Use `_italic_` (underscores)
- **Code**: Use `code` (backticks)

### Message Structure

- Uses proper Slack mentions: `<@USER_ID>`
- Includes appropriate emojis and formatting for readability
- Follows consistent structure across all personalities
- Properly formatted line breaks and spacing

**Note**: All messages have been updated to use correct Slack formatting as of the latest version.

## License

See [LICENSE](LICENSE) for details.
